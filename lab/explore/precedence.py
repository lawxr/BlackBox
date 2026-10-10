"""Generic precedence exploration engine determining validation order from errors."""
from __future__ import annotations

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


def determine_transfer_checks_order(
    target: Target,
    transfer_limit: Optional[int] = None,
) -> Tuple[List[str], List[Observation]]:
    """Determine precedence between max_amount (E506) and sufficient_balance (E507)."""
    prof = profile.get()
    commands = prof.get("commands", {})
    routes = prof.get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "/msg")
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    id_formats = prof.get("id_formats", {})
    acct_fmt = id_formats.get("account", "AC-{n:04d}")
    lim = transfer_limit or prof.get("transfer_limit", 50000)

    create_cmd = next((name for name, c in commands.items() if c.get("kind") == "create_account"), "ALTA")
    credit_cmd = next((name for name, c in commands.items() if c.get("kind") == "credit"), "DEPOSITO")
    transfer_cmd = next((name for name, c in commands.items() if c.get("kind") == "transfer"), "TRANSFER")

    a1 = acct_fmt.format(n=1)
    a2 = acct_fmt.format(n=2)

    # Deposit a small balance (100) into a1, then transfer amount > lim (e.g. lim + 10000).
    # This violates BOTH max_amount (amt > lim) AND sufficient_balance (amt > balance).
    small_balance = 100
    violating_amt = lim + 10000

    steps: List[Step] = [
        {msg_field: _make_msg(create_cmd, ["Alice"], commands.get(create_cmd, {}).get("control", True), sep), "__path__": path},
        {msg_field: _make_msg(create_cmd, ["Bob"], commands.get(create_cmd, {}).get("control", True), sep), "__path__": path},
        {msg_field: _make_msg(credit_cmd, [a1, str(small_balance)], commands.get(credit_cmd, {}).get("control", True), sep), "__path__": path},
        {msg_field: _make_msg(transfer_cmd, [a1, a2, str(violating_amt)], commands.get(transfer_cmd, {}).get("control", True), sep), "__path__": path},
    ]

    seq = "precedence_xfer_001"
    note = "determine check precedence between max_amount and sufficient_balance"

    try:
        trace = target.run(steps, seq=seq, note=note)
    except (BudgetExceeded, TargetStopped):
        return ["max_amount", "sufficient_balance"], []

    obs = [
        Observation(
            engine="precedence",
            seq=seq,
            steps=steps,
            trace=trace,
            note=note,
            exp_ids=target.last_exp_ids(),
        )
    ]

    last_status, last_body = trace[-1]
    error_code = last_body.get("error") if isinstance(last_body, dict) else ""

    if error_code == "E506":
        order = ["max_amount", "sufficient_balance"]
    elif error_code == "E507":
        order = ["sufficient_balance", "max_amount"]
    else:
        # Default or fallback
        order = ["max_amount", "sufficient_balance"]

    return order, obs
