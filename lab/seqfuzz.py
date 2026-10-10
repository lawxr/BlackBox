"""Seeded, state-aware sequence differential fuzzer (original vs in-process replica).

Own code only: stdlib `random` drives generation. Network is used only by
`diff_campaign` through `LabClient`, and the CLI only enables it with `--live`.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from lab.client import LabClient, TransportError
from lab.runner import json_equal
from src.protocol import compute_control

Trace = List[Tuple[Optional[int], Any]]
VALID_CTRL_P = 0.6

WEIRD_AMOUNTS = ["0", "-1", "1", "100000", "100001", "1e3", "01000", "+5", "1.0",
                 "99999999999999999999", " 100", "100 ", "abc"]
NEAR_ACCOUNTS = ["AC-0000", "AC-1", "ac-0001", "AC-00001", "AC-9999", "AC-0001 ", "AC0001"]
NEAR_OPS = ["OP-0000", "OP-1", "op-0001", "OP-00001", "OP-9999"]
NAMES = ["Lucia", "Peña", "José María", "Ana😀", "x", "Ñandú", "A" * 300, "  Bob  ", "名前"]
TYPOS = ["CONSULTAR", "DEPOSITAR", "TRANSFERIR", "ALT", "PIN", "ANULAR", "SALDO", "HELP"]
MALFORMED = [{}, {"m": 5}, {"m": None}, {"m": ["PING;1"]}, {"x": "PING;1"},
             {"__raw__": "{"}, {"__raw__": "PING;1"}, {"__raw__": ""}, {"__raw__": '["m"]'}]


# --- payload mutation operators: (rng, parts) -> parts -------------------------
def mut_lower_cmd(rng: random.Random, parts: List[str]) -> List[str]:
    return [parts[0].lower()] + parts[1:]


def mut_mixed_cmd(rng: random.Random, parts: List[str]) -> List[str]:
    return [parts[0][:1] + parts[0][1:].lower()] + parts[1:]


def mut_space_field(rng: random.Random, parts: List[str]) -> List[str]:
    i = rng.randrange(len(parts))
    prefix = rng.choice([" ", "  "])
    suffix = rng.choice(["", " "])
    return parts[:i] + [prefix + parts[i] + suffix] + parts[i + 1:]


def mut_extra_arg(rng: random.Random, parts: List[str]) -> List[str]:
    return parts + [rng.choice(["extra", "1", "AC-0001"])]


def mut_drop_arg(rng: random.Random, parts: List[str]) -> List[str]:
    return parts[:-1] if len(parts) > 1 else parts


def mut_typo_cmd(rng: random.Random, parts: List[str]) -> List[str]:
    return [rng.choice(TYPOS)] + parts[1:]


def mut_empty_seg(rng: random.Random, parts: List[str]) -> List[str]:
    return parts + [""] if rng.random() < 0.5 else [""] + parts


PAYLOAD_MUTATIONS: List[Tuple[str, Callable]] = [
    ("lower_cmd", mut_lower_cmd),
    ("mixed_cmd", mut_mixed_cmd),
    ("space_field", mut_space_field),
    ("extra_arg", mut_extra_arg),
    ("drop_arg", mut_drop_arg),
    ("typo_cmd", mut_typo_cmd),
    ("empty_seg", mut_empty_seg),
]

# --- control mutation operators: (rng, payload, ctrl) -> message ---------------
CTRL_MUTATIONS: List[Tuple[str, Callable]] = [
    ("ctrl_off_by_one", lambda r, p, c: f"{p};{c % 97 + 1}"),
    ("ctrl_leading_zero", lambda r, p, c: f"{p};0{c}"),
    ("ctrl_fixed_bad", lambda r, p, c: f"{p};{r.choice(['0', '98', '99', '100'])}"),
    ("ctrl_missing", lambda r, p, c: p),
    ("ctrl_signed", lambda r, p, c: f"{p};+{c}"),
    ("ctrl_spaced", lambda r, p, c: f"{p}; {c}"),
]


def _parse_entity_index(raw_id: str) -> int:
    """Extract zero-based index from 'AC-XXXX' or 'OP-XXXX' string, or -1 if invalid."""
    if len(raw_id) == 7 and raw_id[3:].isdigit() and raw_id[:3] in ("AC-", "OP-"):
        return int(raw_id[3:]) - 1
    return -1


def _parse_amount(raw_amount: str) -> int:
    """Parse positive integer amount without leading zero, or 0 if invalid."""
    if raw_amount.isdigit() and not raw_amount.startswith("0"):
        return int(raw_amount)
    return 0


class _Model:
    """Approximate ledger tracking plausible successes of the generated steps."""

    def __init__(self) -> None:
        self.balances: List[int] = []
        self.ops: List[Dict[str, Any]] = []  # {"kind","src","dst","amount","annulled"}

    def account(self, rng: random.Random) -> str:
        if self.balances and rng.random() < 0.8:
            return f"AC-{rng.randrange(len(self.balances)) + 1:04d}"
        return rng.choice(NEAR_ACCOUNTS + [f"AC-{len(self.balances) + 1:04d}"])

    def op(self, rng: random.Random) -> str:
        if self.ops and rng.random() < 0.8:
            return f"OP-{rng.randrange(len(self.ops)) + 1:04d}"
        return rng.choice(NEAR_OPS + [f"OP-{len(self.ops) + 1:04d}"])

    def apply(self, parts: List[str]) -> None:
        cmd, args = parts[0], parts[1:]
        if cmd == "ALTA":
            self.balances.append(0)
        elif cmd == "DEPOSITO":
            idx = _parse_entity_index(args[0])
            amt = _parse_amount(args[1])
            if 0 <= idx < len(self.balances) and amt > 0:
                self.balances[idx] += amt
                self.ops.append({"src": None, "dst": idx, "amount": amt, "annulled": False})
        elif cmd == "TRANSFER":
            src = _parse_entity_index(args[0])
            dst = _parse_entity_index(args[1])
            amt = _parse_amount(args[2])
            is_valid = 0 <= src < len(self.balances) and 0 <= dst < len(self.balances) and src != dst
            if is_valid and 0 < amt <= min(self.balances[src], 100000):
                self.balances[src] -= amt
                self.balances[dst] += amt
                self.ops.append({"src": src, "dst": dst, "amount": amt, "annulled": False})
        elif cmd == "ANULA":
            idx = _parse_entity_index(args[0])
            if 0 <= idx < len(self.ops):
                op = self.ops[idx]
                if not op["annulled"]:
                    op["annulled"] = True
                    self.balances[op["dst"]] -= op["amount"]
                    if op["src"] is not None:
                        self.balances[op["src"]] += op["amount"]


def _amount(rng, model: _Model, src: Optional[str] = None) -> str:
    if rng.random() < 0.3:
        return rng.choice(WEIRD_AMOUNTS)
    if src and model.balances and rng.random() < 0.3:  # transfer over balance
        i = _parse_entity_index(src)
        if 0 <= i < len(model.balances):
            return str(model.balances[i] + rng.randint(1, 1000))
    return str(rng.randint(1, 60000))


def _base_parts(rng, model: _Model) -> List[str]:
    if not model.balances and rng.random() < 0.6:
        kind = "ALTA"
    else:
        kind = rng.choices(["PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"],
                           weights=[8, 18, 16, 22, 20, 16])[0]
    if kind == "PING":
        return ["PING"]
    if kind == "ALTA":
        return ["ALTA", rng.choice(NAMES) if rng.random() < 0.4 else f"User{rng.randint(1, 99)}"]
    if kind == "CONSULTA":
        return ["CONSULTA", model.account(rng)]
    if kind == "DEPOSITO":
        return ["DEPOSITO", model.account(rng), _amount(rng, model)]
    if kind == "TRANSFER":
        src = model.account(rng)
        return ["TRANSFER", src, model.account(rng), _amount(rng, model, src)]
    return ["ANULA", model.op(rng)]


def _generate(rng: random.Random, length: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    model, steps, tags = _Model(), [], []
    for _ in range(length):
        if rng.random() < 0.05:
            body = rng.choice(MALFORMED)
            steps.append(dict(body))
            tags.append("malformed_body")
            continue
        parts = _base_parts(rng, model)
        mutated = False
        if rng.random() < 0.25:
            name, op = rng.choice(PAYLOAD_MUTATIONS)
            parts, mutated = op(rng, parts), True
            tags.append(name)
        payload = ";".join(parts)
        ctrl = compute_control(payload)
        if rng.random() < VALID_CTRL_P:
            message = f"{payload};{ctrl}"
            if not mutated:
                model.apply(parts)
        else:
            name, op = rng.choice(CTRL_MUTATIONS)
            message = op(rng, payload, ctrl)
            tags.append(name)
        steps.append({"m": message})
    return steps, tags


def generate_sequence(rng: random.Random, length: int) -> List[Dict[str, Any]]:
    return _generate(rng, length)[0]


def generate_campaign(seed: int, n_single: int, n_short: int, n_long: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    lengths = [1] * n_single + [rng.randint(2, 5) for _ in range(n_short)] + \
              [rng.randint(6, 12) for _ in range(n_long)]
    campaign = []
    for i, n in enumerate(lengths):
        steps, tags = _generate(rng, n)
        cmds = ",".join(_command(s) for s in steps)
        muts = ",".join(sorted(set(tags))) or "none"
        campaign.append({"id": f"sf_{seed}_{i}", "steps": steps,
                         "hipotesis": f"seqfuzz len={n} cmds={cmds} mutations={muts}"})
    return campaign


# --- execution ---------------------------------------------------------------
def _command(step: Dict[str, Any]) -> str:
    if "__raw__" in step:
        return "<raw>"
    m = step.get("m")
    if not isinstance(m, str):
        return "<body>"
    return m.split(";")[0].strip().upper() or "<empty>"


def _parse(response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def run_replica(steps: List[Dict[str, Any]]) -> Trace:
    from fastapi.testclient import TestClient
    from src import main

    headers = {"Authorization": f"Bearer {main.TEAM_TOKEN}"} if main.TEAM_TOKEN else {}
    with TestClient(main.app) as tc:
        tc.post("/__reset", headers=headers)
        trace: Trace = []
        for step in steps:
            if "__raw__" in step:
                r = tc.post("/msg", headers=headers, content=step["__raw__"].encode())
            else:
                r = tc.post("/msg", headers=headers, json=step)
            trace.append((r.status_code, _parse(r)))
    return trace


def _infra_flag(client: LabClient) -> bool:
    """X-Frontier-Infra lives only in the audit log; read its last line."""
    try:
        with open(client.audit_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            last = f.read().decode("utf-8", "ignore").strip().splitlines()[-1]
        return bool(json.loads(last).get("x_infra"))
    except Exception:
        return False


def run_original(client: LabClient, steps: List[Dict[str, Any]], seq_id: str,
                 hipotesis: str = "seqfuzz") -> Tuple[Trace, str, int]:
    """Returns (trace, stop_reason, requests_sent). Reset first; stop on infra signals."""
    sent, trace = 0, []
    calls = [("reset", None)] + [("step", s) for s in steps]
    for n, (kind, step) in enumerate(calls):
        sent += 1
        try:
            if kind == "reset":
                entry = client.reset(seq=seq_id, hipotesis=f"Reset {seq_id}: {hipotesis}")
            elif "__raw__" in step:
                entry = client.send("POST", "/msg", seq=seq_id, raw_content=step["__raw__"].encode(),
                                    hipotesis=f"Step {n} raw={step['__raw__']!r}: {hipotesis}")
            else:
                entry = client.send("POST", "/msg", seq=seq_id, payload=step,
                                    hipotesis=f"Step {n}: {hipotesis}")
        except TransportError:
            return trace, "transport_error", sent
        if entry.get("status") == 429 or _infra_flag(client):
            return trace, "infra_rate_limit", sent
        if kind == "step":
            trace.append((entry.get("status"), entry.get("response")))
    return trace, "completed", sent


def _code(body: Any) -> Optional[str]:
    return body.get("error") if isinstance(body, dict) else None


def diff_campaign(client: LabClient, campaign: List[Dict[str, Any]], budget: int) -> Dict[str, Any]:
    used, run, divergences, stop = 0, 0, [], "completed"
    for seq in campaign:
        if used + 1 + len(seq["steps"]) > budget:
            stop = "budget"
            break
        orig, reason, sent = run_original(client, seq["steps"], seq["id"], seq["hipotesis"])
        used += sent
        if reason != "completed":
            stop = reason
            break
        run += 1
        repl = run_replica(seq["steps"])
        for i, ((os_, ob), (rs, rb)) in enumerate(zip(orig, repl), 1):
            if os_ != rs or not json_equal(ob, rb):
                divergences.append({
                    "seq_id": seq["id"], "hipotesis": seq["hipotesis"], "step": i,
                    "steps": seq["steps"], "original": orig, "replica": repl,
                    "signature": [_command(seq["steps"][i - 1]), os_, _code(ob), rs, _code(rb)],
                })
                break
    return {"requests_used": used, "sequences_run": run, "stop_reason": stop,
            "divergences": divergences}


def cluster(divergences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for d in divergences:
        groups.setdefault(json.dumps(d["signature"]), []).append(d)
    clusters = [{"signature": items[0]["signature"], "count": len(items),
                 "example": min(items, key=lambda d: (len(d["steps"]), d["step"]))}
                for items in groups.values()]
    return sorted(clusters, key=lambda c: -c["count"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="State-aware sequence differential fuzzer")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--budget", type=int, default=100, help="Max original requests, resets included")
    ap.add_argument("--single", type=int, default=40)
    ap.add_argument("--short", type=int, default=45)
    ap.add_argument("--long", type=int, default=15)
    ap.add_argument("--report", default="seqfuzz_report.json")
    ap.add_argument("--dry-run", action="store_true", help="No network: print sequences and replica outputs")
    ap.add_argument("--live", action="store_true", help="Required to contact the original service")
    args = ap.parse_args(argv)
    campaign = generate_campaign(args.seed, args.single, args.short, args.long)
    if args.dry_run:
        for seq in campaign:
            print(f"== {seq['id']} | {seq['hipotesis']}")
            for step, (status, body) in zip(seq["steps"], run_replica(seq["steps"])):
                print(f"  {json.dumps(step, ensure_ascii=False)} -> {status} {json.dumps(body, ensure_ascii=False)}")
        return 0
    if not args.live:
        print("Refusing network access: pass --live (or use --dry-run).", file=sys.stderr)
        return 2
    report = diff_campaign(LabClient(), campaign, args.budget)
    report.update(seed=args.seed, clusters=cluster(report["divergences"]))
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['stop_reason']}: {report['sequences_run']} sequences, {report['requests_used']} "
          f"requests, {len(report['divergences'])} divergences, {len(report['clusters'])} clusters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
