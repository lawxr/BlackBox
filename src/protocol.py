"""Generic message engine driven by src/profile.json.

The code knows *how* to validate and execute (stages, checks, handler kinds);
the profile says *what* the protocol looks like (codes, messages, statuses,
keys, commands, limits, precedence).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from src import profile
from src.state import ledger

Result = Tuple[int, Dict[str, Any]]


class ProtocolError(Exception):
    """Short-circuits the pipeline with one profile error code."""

    def __init__(self, code: str, extra: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra or {}


def error_response(code: str, extra: Optional[Dict[str, Any]] = None) -> Result:
    prof = profile.get()
    spec = prof["errors"][code]
    keys = prof["error_keys"]
    body: Dict[str, Any] = {keys["code"]: code, keys["message"]: spec["mensaje"]}
    body.update(extra or {})
    return spec["status"], body


def parse_amount(raw: str) -> Optional[int]:
    """Return the amount if the profile's amount rule accepts it, else None."""
    if not re.fullmatch(profile.get()["amount_pattern"], raw):
        return None
    return int(raw)


def compute_control(payload: str) -> int:
    """Calculate the exact ISO 7064 MOD 97-10 check value for the protocol payload."""
    digits: list[str] = []
    for ch in payload.upper():
        if "0" <= ch <= "9":  # ASCII only: fullwidth digits are not digits (exp 1196)
            digits.append(ch)
        elif "A" <= ch <= "Z":
            digits.append(str(ord(ch) - ord("A") + 1))
    if not digits:
        return 1
    num_str = "".join(digits)
    rem = (int(num_str) * 100) % 97
    ctrl = 98 - rem
    if ctrl == 98:
        return 1
    return ctrl


def compute_levenshtein(s1: str, s2: str) -> int:
    """Calculate the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return compute_levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


# --- validation stages ---------------------------------------------------------
class _Msg:
    def __init__(self, raw: str, prof: Dict[str, Any]) -> None:
        self.raw = raw
        self.sep = prof["message"]["separator"]
        self.parts = raw.split(self.sep)
        name = self.parts[0]
        self.name = name.upper() if prof["message"]["case_insensitive_commands"] else name
        self.command = prof["commands"].get(self.name)
        # Commands declared control-free skip the control stages entirely.
        self.uses_control = self.command is None or self.command.get("control", True)
        self.args = self.parts[:-1] if self.uses_control else self.parts


def _stage_missing_control(msg: _Msg, stage: Dict[str, Any]) -> None:
    if msg.sep not in msg.raw:
        raise ProtocolError(stage["error"])


def _stage_empty_segment(msg: _Msg, stage: Dict[str, Any]) -> None:
    if any(len(p) == 0 for p in msg.parts):
        raise ProtocolError(stage["error"])


def _stage_control_format(msg: _Msg, stage: Dict[str, Any]) -> None:
    if not msg.uses_control:
        return
    ctrl = msg.parts[-1]
    if not ctrl.isdigit() or not 1 <= len(ctrl) <= stage["max_digits"]:
        raise ProtocolError(stage["error"])


def _stage_control_value(msg: _Msg, stage: Dict[str, Any]) -> None:
    if not msg.uses_control:
        return
    payload = msg.raw.rsplit(msg.sep, 1)[0]
    # Strict string equality: a leading zero is a wrong control.
    if msg.parts[-1] != str(compute_control(payload)):
        raise ProtocolError(stage["error"])


def _stage_command(msg: _Msg, stage: Dict[str, Any]) -> None:
    if msg.command is not None:
        return
    rule = profile.get()["message"]["suggestion"]
    best, best_dist = None, rule["max_distance"] + 1
    for candidate in profile.get()["commands"]:
        dist = compute_levenshtein(msg.name, candidate)
        if dist < best_dist:
            best, best_dist = candidate, dist
    raise ProtocolError(stage["error"], {rule["key"]: best} if best is not None else None)


def _stage_arity(msg: _Msg, stage: Dict[str, Any]) -> None:
    if len(msg.parts) != msg.command["segments"]:
        raise ProtocolError(stage["error"])


STAGES: Dict[str, Callable[[_Msg, Dict[str, Any]], None]] = {
    "missing_control": _stage_missing_control,
    "empty_segment": _stage_empty_segment,
    "control_format": _stage_control_format,
    "control_value": _stage_control_value,
    "command": _stage_command,
    "arity": _stage_arity,
}


# --- business checks -------------------------------------------------------------
def _check(check: Dict[str, Any], args: List[str], prof: Dict[str, Any]) -> bool:
    vals = [args[i] for i in check["args"]]
    kind = check["check"]
    if kind == "amount":
        return parse_amount(vals[0]) is not None
    if kind == "distinct":
        return len(set(vals)) == len(vals)
    if kind == "account_exists":
        return all(v in ledger.accounts for v in vals)
    if kind == "operation_exists":
        return vals[0] in ledger.operations
    if kind == "sufficient_balance":
        return ledger.accounts[vals[0]]["balance"] >= int(vals[1])
    if kind == "max_amount":
        return int(vals[0]) <= prof[check["limit"]]
    raise profile.ProfileError(f"unsupported check {kind!r}")


def _render(template: Dict[str, Any], ctx: Dict[str, Any]) -> Result:
    """Fill exact "{name}" placeholders with typed context values."""
    def fill(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            return ctx.get(value[1:-1], value)
        if isinstance(value, dict):
            return {k: fill(v) for k, v in value.items()}
        if isinstance(value, list):
            return [fill(v) for v in value]
        return value
    return template["status"], fill(template["body"])


# --- handler kinds ---------------------------------------------------------------
def _record_operation(**op: Any) -> str:
    op_id = ledger.next_operation_id()
    ledger.operations[op_id] = dict(op, annulled=False)
    return op_id


def _h_pong(cmd, args):
    return _render(cmd["response"], {})


def _h_create_account(cmd, args):
    acct_id = ledger.next_account_id()
    ledger.accounts[acct_id] = {"name": args[cmd["name_arg"]], "balance": 0}
    return _render(cmd["response"], {"account": acct_id})


def _h_query_account(cmd, args):
    acct_id = args[cmd["account_arg"]]
    balance = ledger.accounts[acct_id]["balance"]
    fmt = cmd.get("balance_format", "decimal")
    val = f"{balance / 100:.2f}" if fmt == "decimal" else balance
    return _render(cmd["response"], {"account": acct_id, "balance": val})


def _h_credit(cmd, args):
    acct_id, amount = args[cmd["account_arg"]], int(args[cmd["amount_arg"]])
    ledger.accounts[acct_id]["balance"] += amount
    op_id = _record_operation(credits={acct_id: amount})
    return _render(cmd["response"], {"account": acct_id, "operation": op_id})


def _h_transfer(cmd, args):
    src, dst = args[cmd["source_arg"]], args[cmd["target_arg"]]
    amount = int(args[cmd["amount_arg"]])
    ledger.accounts[src]["balance"] -= amount
    ledger.accounts[dst]["balance"] += amount
    op_id = _record_operation(credits={src: -amount, dst: amount})
    return _render(cmd["response"], {"operation": op_id})


def _h_annul(cmd, args):
    op_id = args[cmd["operation_arg"]]
    op = ledger.operations[op_id]
    if op["annulled"]:
        return _render(cmd["already_annulled"], {"operation": op_id})
    for acct_id, delta in op["credits"].items():
        ledger.accounts[acct_id]["balance"] -= delta
    op["annulled"] = True
    return _render(cmd["response"], {"operation": op_id})


def _h_refuse(cmd, args):
    # Never performs the action (e.g. HALT): always answers the refusal error.
    raise ProtocolError(cmd["error"])


HANDLERS = {
    "pong": _h_pong,
    "create_account": _h_create_account,
    "query_account": _h_query_account,
    "credit": _h_credit,
    "transfer": _h_transfer,
    "annul": _h_annul,
    "refuse": _h_refuse,
}


def process_message(raw_msg: str) -> Result:
    """Run the profile's precedence pipeline, then the command's checks and handler."""
    prof = profile.get()
    msg = _Msg(raw_msg, prof)
    try:
        for stage in prof["message"]["precedence"]:
            if stage["stage"] == "handler":
                for check in msg.command.get("checks", []):
                    if not _check(check, msg.args, prof):
                        raise ProtocolError(check["error"])
                return HANDLERS[msg.command["kind"]](msg.command, msg.args)
            STAGES[stage["stage"]](msg, stage)
    except ProtocolError as exc:
        return error_response(exc.code, exc.extra)
    raise profile.ProfileError("precedence has no 'handler' stage")
