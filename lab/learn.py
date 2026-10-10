"""Protocol profile learner, drift checker, and probe executor.

Learns the original service's contract (messages, statuses, keys, commands, suggestions)
from the declarative probe catalog and stateful sequence fuzzing without hardcoded strings.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from fastapi.testclient import TestClient

from lab.client import LabClient, TransportError
from lab.explore import boundaries, inputs, precedence, replay, shapes, stateful
from lab.explore.observation import Observation, Target
from lab.explore.targets import LiveTarget, ReplicaTarget, ScopedTarget
from lab.runner import json_equal
from lab.synthesize import synthesize_profile
from lab.versioning import DEFAULT_PROFILES_DIR, publish_version
from src import profile
from src.main import app
from src.protocol import compute_control

DEFAULT_PROBES_PATH = Path(__file__).resolve().parent / "probes.json"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "src" / "profile.json"
DEFAULT_CANDIDATE_PATH = Path("reports/profile.candidate.json")
DEFAULT_DIFF_PATH = Path("reports/profile.diff.md")

COMMAND_PROBE_SECTIONS = {
    "cmd_ping": ("PING", "response"),
    "cmd_alta": ("ALTA", "response"),
    "cmd_consulta": ("CONSULTA", "response"),
    "cmd_deposito": ("DEPOSITO", "response"),
    "cmd_transfer": ("TRANSFER", "response"),
    "cmd_anula": ("ANULA", "response"),
    "cmd_anula_already": ("ANULA", "already_annulled"),
}


def load_probes(path: Path | str = DEFAULT_PROBES_PATH) -> List[Dict[str, Any]]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def format_request_payload(template: str) -> str:
    """Format payload with valid {ctrl} or invalid {bad_ctrl} checksum."""
    if "{ctrl}" in template:
        payload = template.rsplit(";{ctrl}", 1)[0]
        ctrl = compute_control(payload)
        return f"{payload};{ctrl}"
    if "{bad_ctrl}" in template:
        payload = template.rsplit(";{bad_ctrl}", 1)[0]
        ctrl = compute_control(payload)
        bad_ctrl = 1 if ctrl != 1 else 2
        return f"{payload};{bad_ctrl}"
    # If no delimiter or explicit control present
    return template


def _normalize_request(
    req: Any,
) -> Tuple[str, str, Optional[Dict[str, str]], Optional[Dict[str, Any]], Optional[bytes]]:
    """Return (method, path, headers, json_body, raw_bytes) for probe requests."""
    if isinstance(req, str):
        m_str = format_request_payload(req)
        return "POST", "/msg", None, {"m": m_str}, None
    if isinstance(req, dict):
        method = req.get("method", "POST")
        path = req.get("path", "/msg")
        headers = req.get("headers")
        raw = req.get("raw")
        raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
        body = req.get("body")
        return method, path, headers, body, raw_bytes
    raise ValueError(f"Invalid request format: {req!r}")


def execute_probe_on_client(
    client: LabClient,
    probe: Dict[str, Any],
    seq_id: str = "learn_probes",
    reset_first: bool = True,
) -> Tuple[Optional[int], Any, int]:
    """Execute reset, setup, and request for a probe through LabClient.

    Returns (status, body, requests_sent).
    """
    requests_sent = 0

    if reset_first:
        client.reset(seq=seq_id, hipotesis=f"Reset before probe {probe['id']}")
        requests_sent += 1

    setup_items = probe.get("setup", [])
    for step in setup_items:
        m_str = format_request_payload(step)
        client.msg(message=m_str, seq=seq_id, hipotesis=f"Setup for {probe['id']}: {m_str}")
        requests_sent += 1

    method, path, headers, body, raw_bytes = _normalize_request(probe["request"])
    res = client.send(
        method=method,
        path=path,
        seq=seq_id,
        hipotesis=f"Probe {probe['id']} {method} {path}",
        payload=body,
        headers=headers,
        raw_content=raw_bytes,
    )
    requests_sent += 1
    return res.get("status"), res.get("response"), requests_sent


def execute_probe_on_replica(
    replica_client: TestClient,
    probe: Dict[str, Any],
    auth_headers: Optional[Dict[str, str]] = None,
    reset_first: bool = True,
) -> Tuple[int, Any]:
    """Execute reset, setup, and request for a probe against local replica TestClient."""
    headers = dict(auth_headers or {})

    if reset_first:
        replica_client.post("/__reset", headers=headers)

    setup_items = probe.get("setup", [])
    for step in setup_items:
        m_str = format_request_payload(step)
        replica_client.post("/msg", headers=headers, json={"m": m_str})

    method, path, req_headers, body, raw_bytes = _normalize_request(probe["request"])
    merged_headers = dict(headers)
    if req_headers:
        merged_headers.update(req_headers)

    if raw_bytes is not None:
        resp = replica_client.request(method, path, headers=merged_headers, content=raw_bytes)
    else:
        resp = replica_client.request(method, path, headers=merged_headers, json=body)

    try:
        parsed_body = resp.json()
    except Exception:
        parsed_body = resp.text

    return resp.status_code, parsed_body


def calculate_plan_budget(probes: List[Dict[str, Any]]) -> int:
    """Calculate the exact request budget needed to run all declarative probes."""
    return sum(1 + len(p.get("setup", [])) + 1 for p in probes)


def run_plan_mode(probes: List[Dict[str, Any]]) -> int:
    """Default mode: print probes and budget without touching network."""
    budget = calculate_plan_budget(probes)
    print("==================================================")
    print(f"Plan Mode: {len(probes)} declarative probes cataloged.")
    print(f"Request budget required: {budget} requests.")
    print("==================================================")
    for idx, p in enumerate(probes, 1):
        print(f"[{idx:02d}] {p['id']:22s} -> {p['description']}")
    print("--------------------------------------------------")
    print(f"Total budget for probes execution: {budget} requests.")
    print("Run with --live --budget <N> to contact service and learn.")
    return 0


def run_check_mode(
    probes: List[Dict[str, Any]],
    client: LabClient,
) -> int:
    """Check mode: verify parities, report drift only, write nothing else."""
    divergences = []
    from src import config

    token = config.TEAM_TOKEN or client.token
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    with TestClient(app) as replica_client:
        # Initial reset
        try:
            client.reset(seq="canary_check", hipotesis="Initial reset for drift check")
        except TransportError as te:
            print(f"TransportError during check reset: {te}", file=sys.stderr)
            return 1

        for p in probes:
            try:
                live_status, live_body, _ = execute_probe_on_client(client, p, seq_id="canary_check")
            except TransportError as te:
                print(f"TransportError during probe {p['id']}: {te}", file=sys.stderr)
                return 1

            repl_status, repl_body = execute_probe_on_replica(
                replica_client, p, auth_headers=auth_headers
            )

            status_ok = live_status == repl_status
            body_ok = json_equal(live_body, repl_body)

            if not (status_ok and body_ok):
                divergences.append({
                    "probe": p["id"],
                    "description": p["description"],
                    "expected_status": repl_status,
                    "actual_status": live_status,
                    "expected_body": repl_body,
                    "actual_body": live_body,
                })

    if divergences:
        print(f"⚠️ CONTRACT DRIFT DETECTED: {len(divergences)} divergences found!")
        for d in divergences:
            print(f"  - [{d['probe']}] Status: {d['actual_status']} (expected {d['expected_status']})")
            print(f"       Expected: {json.dumps(d['expected_body'], ensure_ascii=False)}")
            print(f"       Actual:   {json.dumps(d['actual_body'], ensure_ascii=False)}")
        return 1

    print(f"✅ OK: 100% parity across all {len(probes)} probes.")
    return 0


def generate_diff_markdown(
    base: Dict[str, Any],
    candidate: Dict[str, Any],
    needs_review: List[str],
) -> str:
    """Generate human-readable diff markdown between active and candidate profiles."""
    lines = [
        "# Protocol Profile Diff",
        "",
        f"Base Version: {base.get('version', 1)} | Candidate Version: {candidate.get('version', 1)}",
        "",
        "## Changes",
    ]

    changes: List[str] = []

    # Check error message changes
    base_errors = base.get("errors", {})
    cand_errors = candidate.get("errors", {})
    for code, spec in cand_errors.items():
        base_spec = base_errors.get(code, {})
        if base_spec.get("mensaje") != spec.get("mensaje"):
            changes.append(
                f"- `errors.{code}.mensaje`: '{base_spec.get('mensaje')}' -> '{spec.get('mensaje')}'"
            )
        if base_spec.get("status") != spec.get("status"):
            changes.append(
                f"- `errors.{code}.status`: {base_spec.get('status')} -> {spec.get('status')}"
            )

    # Check command response changes
    base_cmds = base.get("commands", {})
    cand_cmds = candidate.get("commands", {})
    for cmd_name, cmd_spec in cand_cmds.items():
        base_cmd = base_cmds.get(cmd_name, {})
        if base_cmd.get("response", {}).get("status") != cmd_spec.get("response", {}).get("status"):
            changes.append(
                f"- `commands.{cmd_name}.response.status`: "
                f"{base_cmd.get('response', {}).get('status')} -> {cmd_spec.get('response', {}).get('status')}"
            )

    if not changes:
        lines.append("- No parameter or message drift detected.")
    else:
        lines.extend(changes)

    lines.extend([
        "",
        "## Needs Review",
    ])
    if not needs_review:
        lines.append("- None.")
    else:
        for cmd in sorted(needs_review):
            lines.append(f"- `{cmd}`: suggested command fits no existing handler kind; requires human review.")

    lines.append("")
    return "\n".join(lines)


def run_live_learning(
    probes: List[Dict[str, Any]],
    client: LabClient,
    budget: int,
    base_profile_path: Path = DEFAULT_PROFILE_PATH,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    diff_path: Path = DEFAULT_DIFF_PATH,
) -> int:
    """Execute probes and seqfuzz through LabClient within budget and generate candidate profile."""
    base_data = profile.load_profile(base_profile_path)
    candidate_data = copy.deepcopy(base_data)

    used_requests = 0
    stop_reason = "completed"
    discovered_commands: Set[str] = set()

    # 1. Execute Probes
    for p in probes:
        setup_count = len(p.get("setup", []))
        needed = 1 + setup_count + 1  # reset + setup + probe
        if used_requests + needed > budget:
            stop_reason = "budget"
            break

        try:
            status, body, sent = execute_probe_on_client(client, p, seq_id="learn_live")
            used_requests += sent
        except TransportError:
            stop_reason = "transport_error"
            break

        if status == 429:
            stop_reason = "infra_rate_limit"
            break

        # Harvest error message and status
        if isinstance(body, dict):
            err_key = candidate_data["error_keys"]["code"]
            msg_key = candidate_data["error_keys"]["message"]

            code = body.get(err_key)
            if code and code in candidate_data["errors"]:
                candidate_data["errors"][code]["status"] = status
                if msg_key in body:
                    candidate_data["errors"][code]["mensaje"] = body[msg_key]

            # Harvest sugerencia
            sug = body.get("sugerencia")
            if sug and isinstance(sug, str):
                sug_cmd = sug.strip().upper()
                if sug_cmd not in candidate_data["commands"]:
                    discovered_commands.add(sug_cmd)

        # Harvest command status
        p_id = p["id"]
        if status and p_id in COMMAND_PROBE_SECTIONS:
            cmd_name, section = COMMAND_PROBE_SECTIONS[p_id]
            candidate_data["commands"][cmd_name][section]["status"] = status

    # 3. Optional seqfuzz campaign with remaining budget
    if stop_reason == "completed" and used_requests < budget:
        from lab.seqfuzz import generate_campaign

        remaining_budget = budget - used_requests
        campaign = generate_campaign(seed=42, n_single=10, n_short=5, n_long=2)
        for seq in campaign:
            if used_requests + 1 + len(seq["steps"]) > budget:
                stop_reason = "budget"
                break
            try:
                client.reset(seq=seq["id"], hipotesis=f"Reset for {seq['id']}")
                used_requests += 1
                for n, step in enumerate(seq["steps"], 1):
                    used_requests += 1
                    if "__raw__" in step:
                        entry = client.send(
                            "POST",
                            "/msg",
                            seq=seq["id"],
                            raw_content=step["__raw__"].encode(),
                            hipotesis=f"Step {n}",
                        )
                    else:
                        entry = client.send(
                            "POST",
                            "/msg",
                            seq=seq["id"],
                            payload=step,
                            hipotesis=f"Step {n}",
                        )
                    resp_body = entry.get("response")
                    if isinstance(resp_body, dict):
                        sug = resp_body.get("sugerencia")
                        if sug and isinstance(sug, str):
                            sug_cmd = sug.strip().upper()
                            if sug_cmd not in candidate_data["commands"]:
                                discovered_commands.add(sug_cmd)
                    if entry.get("status") == 429:
                        stop_reason = "infra_rate_limit"
                        break
                if stop_reason != "completed":
                    break
            except TransportError:
                stop_reason = "transport_error"
                break

    # 4. Classify discovered commands
    # A command whose behavior fits no handler kind is listed under "needs review", never guessed.
    needs_review: List[str] = []
    for cmd in sorted(discovered_commands):
        # We check if it matches existing commands
        if cmd not in candidate_data["commands"]:
            needs_review.append(cmd)

    if needs_review:
        candidate_data["needs_review"] = needs_review

    # 5. Write outputs
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(json.dumps(candidate_data, indent=2, ensure_ascii=False), encoding="utf-8")

    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_content = generate_diff_markdown(base_data, candidate_data, needs_review)
    diff_path.write_text(diff_content, encoding="utf-8")

    print(
        f"Learning finished ({stop_reason}): {used_requests} requests used. "
        f"Candidate saved to {candidate_path}, diff to {diff_path}."
    )
    return 0


def run_autonomous_pipeline(
    target: Target,
    budget: int,
    base_profile_path: Path = DEFAULT_PROFILE_PATH,
    profiles_dir: Optional[Path | str] = None,
    log_path: Optional[Path | str] = "experimentos.jsonl",
) -> int:
    """Run full autonomous exploration, synthesis, and gate promotion pipeline."""
    base_data = profile.load_profile(base_profile_path)

    print(f"🚀 Starting Autonomous Pipeline with budget: {budget} requests...")

    # Allocate sub-budgets to ensure each engine gets adequate execution
    has_log = bool(log_path and Path(log_path).exists())
    b_replay = max(10, int(budget * 0.10)) if has_log else 0
    b_xfer = max(15, int(budget * 0.15))
    b_body = max(10, int(budget * 0.10))
    b_prec = max(5, int(budget * 0.05))
    rem = max(10, budget - (b_replay + b_xfer + b_body + b_prec))
    b_inputs = rem // 2
    b_state = rem - b_inputs

    all_obs: List[Observation] = []

    # Engine 0: Historical Replay (if recorded log exists)
    if has_log:
        clean_segs = replay.extract_clean_segments(log_path, max_segments=5)
        if clean_segs:
            t_replay = ScopedTarget(target, b_replay)
            try:
                obs_replay, replay_summary = replay.replay_segments(t_replay, clean_segs, budget=b_replay)
                all_obs.extend(obs_replay)
                print(
                    f"  [Replay] Replayed {replay_summary['total_segments']} segments, "
                    f"{replay_summary['divergent_segments']} divergent clusters found"
                )
            except Exception as e:
                print(f"  [Replay] Historical replay skipped: {e}")

    # Engine 1: Boundaries (transfer limit)
    t_xfer = ScopedTarget(target, b_xfer)
    try:
        xfer_limit, obs_xfer = boundaries.search_transfer_limit(t_xfer)
        all_obs.extend(obs_xfer)
        print(f"  [Boundaries] Transfer limit inferred: {xfer_limit} ({len(obs_xfer)} observations)")
    except Exception as e:
        print(f"  [Boundaries] Transfer limit search skipped: {e}")
        xfer_limit = 0

    # Engine 2: Boundaries (body size)
    t_body = ScopedTarget(target, b_body)
    try:
        body_size, obs_body = boundaries.search_body_size(t_body)
        all_obs.extend(obs_body)
        print(f"  [Boundaries] Body size limit inferred: {body_size} ({len(obs_body)} observations)")
    except Exception as e:
        print(f"  [Boundaries] Body size search skipped: {e}")
        body_size = 0

    # Engine 3: Precedence
    t_prec = ScopedTarget(target, b_prec)
    try:
        prec_order, obs_prec = precedence.determine_transfer_checks_order(t_prec, transfer_limit=xfer_limit)
        all_obs.extend(obs_prec)
        print(f"  [Precedence] Transfer checks order: {prec_order} ({len(obs_prec)} observations)")
    except Exception as e:
        print(f"  [Precedence] Precedence search skipped: {e}")
        prec_order = []

    # Engine 4: Grammar Inputs
    t_inputs = ScopedTarget(target, b_inputs)
    try:
        obs_inputs = inputs.explore(t_inputs, budget=b_inputs, n=max(5, b_inputs // 3))
        all_obs.extend(obs_inputs)
        print(f"  [Inputs] Generated {len(obs_inputs)} grammar mutation observations")
    except Exception as e:
        print(f"  [Inputs] Input exploration skipped: {e}")

    # Engine 5: Stateful Chains
    t_state = ScopedTarget(target, b_state)
    try:
        obs_state = stateful.explore(t_state, budget=b_state, n=max(3, b_state // 8))
        all_obs.extend(obs_state)
        print(f"  [Stateful] Generated {len(obs_state)} stateful chain observations")
    except Exception as e:
        print(f"  [Stateful] Stateful exploration skipped: {e}")

    # Shapes inference
    bal_fmt = shapes.infer_balance_format(all_obs)
    print(f"  [Shapes] Inferred balance format: {bal_fmt}")

    # Prepare synthesis inputs
    inferred_bounds = {}
    if xfer_limit > 0:
        inferred_bounds["transfer_limit"] = xfer_limit
    if 0 < body_size < 65536:
        inferred_bounds["max_body_bytes"] = body_size

    inferred_shapes = {}
    if bal_fmt:
        inferred_shapes["balance_format"] = bal_fmt

    inferred_prec = {}
    if prec_order:
        inferred_prec["TRANSFER"] = prec_order

    # Synthesize candidate profile
    candidate, manifest = synthesize_profile(
        base_profile=base_data,
        observations=all_obs,
        inferred_boundaries=inferred_bounds,
        inferred_shapes=inferred_shapes,
        inferred_precedence=inferred_prec,
    )

    diff_text = generate_diff_markdown(
        base=base_data,
        candidate=candidate,
        needs_review=candidate.get("needs_review", []),
    )

    # Automated Gates
    print("  [Gates] Verifying candidate profile validity...")
    try:
        profile._validate(candidate)
    except Exception as e:
        print(f"  ❌ Gate validation failed: {e}", file=sys.stderr)
        return 1

    # Publish version
    version_dir = publish_version(
        profile_data=candidate,
        manifest_data=manifest,
        profiles_dir=profiles_dir,
        diff_text=diff_text,
    )
    print(f"  ✅ Gate promotion passed! Version published to {version_dir}")
    print(f"  ACTIVE pointer updated to: {version_dir.name}")
    return 0


def main(
    argv: Optional[List[str]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> int:
    parser = argparse.ArgumentParser(description="BlackBox protocol learning and drift checking engine.")
    parser.add_argument("--plan", action="store_true", help="Print probes and budget without network (default)")
    parser.add_argument("--live", action="store_true", help="Execute live learning via LabClient")
    parser.add_argument("--check", action="store_true", help="Check parity and report drift only (replaces canary)")
    parser.add_argument("--autonomous", action="store_true", help="Run full autonomous exploration and promotion")
    parser.add_argument("--profiles-dir", type=Path, default=None, help="Directory for versioned profiles")
    parser.add_argument("--budget", type=int, default=100, help="Maximum request budget for live learning")
    parser.add_argument("--probes", type=Path, default=DEFAULT_PROBES_PATH, help="Path to probes.json")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH, help="Path to active profile.json")
    parser.add_argument("--candidate-out", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Output path for candidate")
    parser.add_argument("--diff-out", type=Path, default=DEFAULT_DIFF_PATH, help="Output path for diff markdown")

    args = parser.parse_args(argv)

    if args.autonomous:
        if transport is not None:
            with LabClient(transport=transport, rate_limit_delay=0.0) as client:
                target = LiveTarget(client, budget=args.budget)
                return run_autonomous_pipeline(
                    target=target,
                    budget=args.budget,
                    base_profile_path=args.profile,
                    profiles_dir=args.profiles_dir,
                )
        elif args.live:
            with LabClient(rate_limit_delay=0.15) as client:
                target = LiveTarget(client, budget=args.budget)
                return run_autonomous_pipeline(
                    target=target,
                    budget=args.budget,
                    base_profile_path=args.profile,
                    profiles_dir=args.profiles_dir,
                )
        else:
            target = ReplicaTarget(args.profile)
            return run_autonomous_pipeline(
                target=target,
                budget=args.budget,
                base_profile_path=args.profile,
                profiles_dir=args.profiles_dir,
            )

    probes = load_probes(args.probes)

    if args.check:
        with LabClient(transport=transport, rate_limit_delay=0.0 if transport else 0.15) as client:
            return run_check_mode(probes, client)

    if args.live:
        with LabClient(transport=transport, rate_limit_delay=0.0 if transport else 0.15) as client:
            return run_live_learning(
                probes=probes,
                client=client,
                budget=args.budget,
                base_profile_path=args.profile,
                candidate_path=args.candidate_out,
                diff_path=args.diff_out,
            )

    # Default: plan mode
    return run_plan_mode(probes)


if __name__ == "__main__":
    sys.exit(main())
