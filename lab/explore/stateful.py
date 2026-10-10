"""Profile-derived stateful exploration engine favoring 6-12 step chains."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from lab.explore.observation import BudgetExceeded, Observation, Step, Target, TargetStopped
from src import profile
from src.protocol import compute_control


def _find_cmd_by_kind(commands: Dict[str, Any], kind: str) -> Optional[str]:
    for name, spec in commands.items():
        if spec.get("kind") == kind:
            return name
    return None


class StateModel:
    """State model tracking observed accounts, balances, and operations."""

    def __init__(self) -> None:
        self.accounts: List[str] = []
        self.balances: Dict[str, int] = {}
        self.ops: List[Dict[str, Any]] = []

    def update(
        self,
        step: Step,
        status: int,
        body: Any,
        prof: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update model only if target response indicates success."""
        if status not in (200, 201):
            return

        active_prof = prof or profile.get()
        sep = active_prof.get("message", {}).get("separator", ";")
        msg_field = active_prof.get("http", {}).get("message_field", "m")
        commands = active_prof.get("commands", {})
        id_formats = active_prof.get("id_formats", {})
        account_fmt = id_formats.get("account", "AC-{n:04d}")
        op_fmt = id_formats.get("operation", "OP-{n:04d}")

        raw_msg = step.get(msg_field, "")
        if not isinstance(raw_msg, str) or not raw_msg:
            return

        parts = raw_msg.split(sep)
        cmd_name = parts[0].strip().upper()
        spec = commands.get(cmd_name, {})
        kind = spec.get("kind", "")

        if kind == "create_account":
            account_id = None
            if isinstance(body, dict):
                account_id = (
                    body.get("cuentaId")
                    or body.get("cuenta_id")
                    or body.get("account_id")
                )
            if not account_id:
                account_id = account_fmt.format(n=len(self.accounts) + 1)
            if account_id and account_id not in self.accounts:
                self.accounts.append(account_id)
                self.balances[account_id] = 0

        elif kind == "credit":
            acct_idx = spec.get("account_arg", 1)
            amt_idx = spec.get("amount_arg", 2)
            if len(parts) > max(acct_idx, amt_idx):
                acct = parts[acct_idx]
                amt_str = parts[amt_idx]
                if amt_str.isdigit():
                    amt = int(amt_str)
                    self.balances[acct] = self.balances.get(acct, 0) + amt
                    op_id = (
                        body.get("op_id")
                        if isinstance(body, dict)
                        else None
                    ) or op_fmt.format(n=len(self.ops) + 1)
                    self.ops.append(
                        {
                            "id": op_id,
                            "src": None,
                            "dst": acct,
                            "amount": amt,
                            "annulled": False,
                        }
                    )

        elif kind == "transfer":
            src_idx = spec.get("source_arg", 1)
            dst_idx = spec.get("destination_arg", 2)
            amt_idx = spec.get("amount_arg", 3)
            if len(parts) > max(src_idx, dst_idx, amt_idx):
                src = parts[src_idx]
                dst = parts[dst_idx]
                amt_str = parts[amt_idx]
                if amt_str.isdigit():
                    amt = int(amt_str)
                    self.balances[src] = self.balances.get(src, 0) - amt
                    self.balances[dst] = self.balances.get(dst, 0) + amt
                    op_id = (
                        body.get("op_id")
                        if isinstance(body, dict)
                        else None
                    ) or op_fmt.format(n=len(self.ops) + 1)
                    self.ops.append(
                        {
                            "id": op_id,
                            "src": src,
                            "dst": dst,
                            "amount": amt,
                            "annulled": False,
                        }
                    )

        elif kind == "annul":
            op_idx = spec.get("operation_arg", 1)
            if len(parts) > op_idx:
                op_id = parts[op_idx]
                for op in self.ops:
                    if op["id"] == op_id and not op["annulled"]:
                        op["annulled"] = True
                        amt = op["amount"]
                        self.balances[op["dst"]] = self.balances.get(op["dst"], 0) - amt
                        if op["src"]:
                            self.balances[op["src"]] = self.balances.get(op["src"], 0) + amt
                        break


# Compatibility alias
Model = StateModel


def _build_step(
    cmd: str,
    args: List[str],
    spec: Dict[str, Any],
    sep: str,
    msg_field: str,
    path: str,
) -> Step:
    uses_ctrl = spec.get("control", True)
    parts = [cmd] + args
    payload = sep.join(parts)
    if uses_ctrl:
        ctrl = compute_control(payload)
        msg_str = f"{payload}{sep}{ctrl}"
    else:
        msg_str = payload

    step: Step = {msg_field: msg_str}
    if path:
        step["__path__"] = path
    return step


# --- Chain Generators ---

def _chain_transfer_then_annul(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    op_fmt = id_formats.get("operation", "OP-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    annul_cmd = _find_cmd_by_kind(commands, "annul")
    query_cmd = _find_cmd_by_kind(commands, "query_account")

    if not all([create_cmd, credit_cmd, transfer_cmd, annul_cmd, query_cmd]):
        return [], "skip"

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)
    op1 = op_fmt.format(n=2)  # operation 2 is the transfer (credit was op 1)
    u1 = f"U{rng.randint(10, 99)}"
    u2 = f"U{rng.randint(10, 99)}"
    amt = str(rng.randint(max(1, lim // 4), lim))

    steps = [
        _build_step(create_cmd, [u1], commands[create_cmd], sep, msg_field, path),
        _build_step(create_cmd, [u2], commands[create_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(lim)], commands[credit_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, amt], commands[transfer_cmd], sep, msg_field, path),
        _build_step(annul_cmd, [op1], commands[annul_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a2], commands[query_cmd], sep, msg_field, path),
    ]
    return steps, "chain:transfer_then_annul"


def _chain_annul_twice(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    op_fmt = id_formats.get("operation", "OP-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    annul_cmd = _find_cmd_by_kind(commands, "annul")

    if not all([create_cmd, credit_cmd, transfer_cmd, annul_cmd]):
        return [], "skip"

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)
    op1 = op_fmt.format(n=2)
    u1 = f"U{rng.randint(10, 99)}"
    u2 = f"U{rng.randint(10, 99)}"
    amt = str(rng.randint(max(1, lim // 4), lim))

    steps = [
        _build_step(create_cmd, [u1], commands[create_cmd], sep, msg_field, path),
        _build_step(create_cmd, [u2], commands[create_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(lim)], commands[credit_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, amt], commands[transfer_cmd], sep, msg_field, path),
        _build_step(annul_cmd, [op1], commands[annul_cmd], sep, msg_field, path),
        _build_step(annul_cmd, [op1], commands[annul_cmd], sep, msg_field, path),
    ]
    return steps, "chain:annul_twice"


def _chain_consult_after_annul(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    op_fmt = id_formats.get("operation", "OP-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    annul_cmd = _find_cmd_by_kind(commands, "annul")
    query_cmd = _find_cmd_by_kind(commands, "query_account")

    if not all([create_cmd, credit_cmd, transfer_cmd, annul_cmd, query_cmd]):
        return [], "skip"

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)
    op1 = op_fmt.format(n=2)

    steps = [
        _build_step(create_cmd, ["Alice"], commands[create_cmd], sep, msg_field, path),
        _build_step(create_cmd, ["Bob"], commands[create_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(lim)], commands[credit_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, str(max(1, lim // 2))], commands[transfer_cmd], sep, msg_field, path),
        _build_step(annul_cmd, [op1], commands[annul_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a2], commands[query_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(max(1, lim // 4))], commands[credit_cmd], sep, msg_field, path),
    ]
    return steps, "chain:consult_after_annul"


def _chain_ops_after_failed_ops(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    query_cmd = _find_cmd_by_kind(commands, "query_account")

    if not all([create_cmd, credit_cmd, transfer_cmd, query_cmd]):
        return [], "skip"

    a1 = acct_fmt.format(n=1)
    a_fake = acct_fmt.format(n=9999)

    steps = [
        _build_step(create_cmd, ["Alice"], commands[create_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, "-10"], commands[credit_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(lim)], commands[credit_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a1, str(max(1, lim // 2))], commands[transfer_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a_fake, str(max(1, lim // 2))], commands[transfer_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a_fake], commands[query_cmd], sep, msg_field, path),
    ]
    return steps, "chain:ops_after_failed_ops"


def _chain_many_alta_then_old_ids(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    query_cmd = _find_cmd_by_kind(commands, "query_account")

    if not all([create_cmd, credit_cmd, transfer_cmd, query_cmd]):
        return [], "skip"

    steps = [
        _build_step(create_cmd, [f"User{i}"], commands[create_cmd], sep, msg_field, path)
        for i in range(1, 6)
    ]
    a1 = acct_fmt.format(n=1)
    a5 = acct_fmt.format(n=5)
    steps.extend(
        [
            _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
            _build_step(credit_cmd, [a1, str(lim)], commands[credit_cmd], sep, msg_field, path),
            _build_step(transfer_cmd, [a1, a5, str(max(1, lim - 1))], commands[transfer_cmd], sep, msg_field, path),
            _build_step(query_cmd, [a5], commands[query_cmd], sep, msg_field, path),
            _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
        ]
    )
    return steps, "chain:many_alta_then_old_ids"


def _chain_boundary_values(prof: Dict[str, Any], rng: random.Random) -> Tuple[List[Step], str]:
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    lim = prof.get("transfer_limit", 1000)

    create_cmd = _find_cmd_by_kind(commands, "create_account")
    credit_cmd = _find_cmd_by_kind(commands, "credit")
    transfer_cmd = _find_cmd_by_kind(commands, "transfer")
    query_cmd = _find_cmd_by_kind(commands, "query_account")

    if not all([create_cmd, credit_cmd, transfer_cmd, query_cmd]):
        return [], "skip"

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)

    steps = [
        _build_step(create_cmd, ["Alice"], commands[create_cmd], sep, msg_field, path),
        _build_step(create_cmd, ["Bob"], commands[create_cmd], sep, msg_field, path),
        _build_step(credit_cmd, [a1, str(lim * 3)], commands[credit_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, str(lim - 1)], commands[transfer_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, str(lim)], commands[transfer_cmd], sep, msg_field, path),
        _build_step(transfer_cmd, [a1, a2, str(lim + 1)], commands[transfer_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a1], commands[query_cmd], sep, msg_field, path),
        _build_step(query_cmd, [a2], commands[query_cmd], sep, msg_field, path),
    ]
    return steps, "chain:boundary_values"


CHAIN_FACTORIES: List[Callable[[Dict[str, Any], random.Random], Tuple[List[Step], str]]] = [
    _chain_transfer_then_annul,
    _chain_annul_twice,
    _chain_consult_after_annul,
    _chain_ops_after_failed_ops,
    _chain_many_alta_then_old_ids,
    _chain_boundary_values,
]


def explore(
    target: Target,
    seed: int = 42,
    n: int = 20,
    budget: int = 1000,
) -> List[Observation]:
    """Execute profile-derived stateful chain sequences weighted to 6-12 steps."""
    rng = random.Random(seed)
    prof = profile.get()
    observations: List[Observation] = []
    used_requests = 0

    for i in range(n):
        factory = CHAIN_FACTORIES[i % len(CHAIN_FACTORIES)]
        steps, note = factory(prof, rng)
        if not steps:
            continue

        needed = 1 + len(steps)
        if used_requests + needed > budget:
            break

        seq = f"stateful_{i:04d}"
        try:
            trace = target.run(steps, seq=seq, note=note)
        except (BudgetExceeded, TargetStopped):
            break

        used_requests += needed
        observations.append(
            Observation(
                engine="stateful",
                seq=seq,
                steps=steps,
                trace=trace,
                note=note,
                exp_ids=target.last_exp_ids(),
            )
        )

    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile-derived stateful exploration engine.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--n", type=int, default=20, help="Number of sequences")
    parser.add_argument("--budget", type=int, default=1000, help="Request budget")
    parser.add_argument("--report", type=str, default=None, help="Path to write report")
    parser.add_argument("--live", action="store_true", help="Run against live service via LabClient")
    args = parser.parse_args()

    if args.live:
        from lab.client import LabClient
        from lab.explore.targets import LiveTarget

        client = LabClient()
        target = LiveTarget(client, budget=args.budget)
    else:
        from lab.explore.targets import ReplicaTarget

        target = ReplicaTarget()

    obs = explore(target, seed=args.seed, n=args.n, budget=args.budget)
    print(f"Generated {len(obs)} observations.")

    if args.report:
        report_data = {
            "engine": "stateful",
            "seed": args.seed,
            "observations_count": len(obs),
            "sequences": [
                {
                    "seq": o.seq,
                    "note": o.note,
                    "steps_count": len(o.steps),
                    "first_status": o.trace[0][0] if o.trace else None,
                }
                for o in obs
            ],
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
