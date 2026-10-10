"""Generic binary-search exploration engine for numeric boundaries in protocol."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from lab.explore.observation import BudgetExceeded, Observation, Step, Target, TargetStopped
from src import profile
from src.protocol import compute_control


def _make_msg(cmd: str, args: List[str], uses_ctrl: bool, sep: str) -> str:
    parts = [cmd] + args
    payload = sep.join(parts)
    if uses_ctrl:
        ctrl = compute_control(payload)
        return f"{payload}{sep}{ctrl}"
    return payload


def search_transfer_limit(
    target: Target,
    low: int = 1000,
    high: int = 200000,
) -> Tuple[int, List[Observation]]:
    """Binary-search the exact transfer limit where E506 triggers."""
    prof = profile.get()
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "/msg")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")

    create_cmd = next((name for name, c in commands.items() if c.get("kind") == "create_account"), None)
    credit_cmd = next((name for name, c in commands.items() if c.get("kind") == "credit"), None)
    transfer_cmd = next((name for name, c in commands.items() if c.get("kind") == "transfer"), None)

    if not transfer_cmd:
        return 0, []

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)
    observations: List[Observation] = []
    best_limit = low

    step_num = 0
    while low <= high:
        mid = (low + high) // 2
        step_num += 1

        steps: List[Step] = []
        if create_cmd and credit_cmd:
            # Setup accounts and sufficient balance
            steps.append({msg_field: _make_msg(create_cmd, ["Alice"], commands[create_cmd].get("control", True), sep), "__path__": path})
            steps.append({msg_field: _make_msg(create_cmd, ["Bob"], commands[create_cmd].get("control", True), sep), "__path__": path})
            steps.append({msg_field: _make_msg(credit_cmd, [a1, str(high * 2)], commands[credit_cmd].get("control", True), sep), "__path__": path})

        transfer_step = {
            msg_field: _make_msg(transfer_cmd, [a1, a2, str(mid)], commands[transfer_cmd].get("control", True), sep),
            "__path__": path,
        }
        steps.append(transfer_step)

        seq = f"boundary_xfer_{step_num:03d}"
        note = f"binary_search_xfer_limit: test amount {mid}"
        try:
            trace = target.run(steps, seq=seq, note=note)
        except (BudgetExceeded, TargetStopped):
            break

        observations.append(
            Observation(
                engine="boundaries",
                seq=seq,
                steps=steps,
                trace=trace,
                note=note,
                exp_ids=target.last_exp_ids(),
            )
        )

        last_status, last_body = trace[-1]
        is_limit_exceeded = False
        if last_status == 422:
            if isinstance(last_body, dict) and last_body.get("error") == "E506":
                is_limit_exceeded = True
            elif isinstance(last_body, dict) and "límite" in str(last_body.get("mensaje", "")).lower():
                is_limit_exceeded = True

        if is_limit_exceeded:
            high = mid - 1
        else:
            best_limit = mid
            low = mid + 1

    return best_limit, observations


def search_body_size(
    target: Target,
    low: int = 1024,
    high: int = 65536,
) -> Tuple[int, List[Observation]]:
    """Binary-search the exact max request body size before 413 triggers."""
    routes = profile.get().get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "/msg")

    observations: List[Observation] = []
    best_size = low
    step_num = 0

    while low <= high:
        mid = (low + high) // 2
        step_num += 1

        # Build valid raw JSON of exact length mid
        prefix = '{"m": "PING;val1", "pad": "'
        suffix = '"}'
        pad_len = mid - len(prefix) - len(suffix)
        if pad_len >= 0:
            raw_body = prefix + ("A" * pad_len) + suffix
        else:
            base_json = '{"m": "PING;val1"}'
            raw_body = base_json + (" " * max(0, mid - len(base_json)))

        steps: List[Step] = [{"__raw__": raw_body, "__path__": path}]
        seq = f"boundary_body_{step_num:03d}"
        note = f"binary_search_body_size: test size {len(raw_body)}"

        try:
            trace = target.run(steps, seq=seq, note=note)
        except (BudgetExceeded, TargetStopped):
            break

        observations.append(
            Observation(
                engine="boundaries",
                seq=seq,
                steps=steps,
                trace=trace,
                note=note,
                exp_ids=target.last_exp_ids(),
            )
        )

        last_status, _ = trace[-1]
        if last_status == 413:
            high = mid - 1
        else:
            best_size = mid
            low = mid + 1

    return best_size, observations
