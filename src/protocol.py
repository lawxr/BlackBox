from __future__ import annotations
from typing import Tuple, Any, Dict
from src.state import ledger


def compute_control(payload: str) -> int:
    """Calculate the exact ISO 7064 MOD 97-10 check value for the protocol payload."""
    digits: list[str] = []
    for ch in payload.upper():
        if ch.isdigit():
            digits.append(ch)
        elif "A" <= ch <= "Z":
            digits.append(str(ord(ch) - ord("A") + 1))
    if not digits:
        return 98 % 97
    num_str = "".join(digits)
    return (98 - (int(num_str) * 100)) % 97


def process_message(raw_msg: str) -> Tuple[int, Dict[str, Any]]:
    """Validate message integrity, format, and control before dispatching."""
    if ";" not in raw_msg:
        return 400, {"error": "E103", "mensaje": "falta control"}

    parts = raw_msg.split(";")
    if any(len(p) == 0 for p in parts):
        return 400, {"error": "E104", "mensaje": "segmento vacío"}

    cmd = parts[0].upper()

    # PING command has special semantics: ignores control value/format
    if cmd == "PING":
        if len(parts) != 2:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        return 200, {"pong": True}

    # Validate control format on last segment
    ctrl_str = parts[-1]
    if not ctrl_str.isdigit() or int(ctrl_str) < 0 or int(ctrl_str) >= 100:
        return 400, {"error": "E201", "mensaje": "control mal formado"}

    # Validate control value
    payload = raw_msg.rsplit(";", 1)[0]
    expected_ctrl = compute_control(payload)
    if int(ctrl_str) != expected_ctrl:
        return 400, {"error": "E202", "mensaje": "control inválido"}

    return dispatch_command(cmd, parts[:-1])


def dispatch_command(cmd: str, args: list[str]) -> Tuple[int, Dict[str, Any]]:
    """Execute business commands once integrity and control are verified."""
    if cmd == "ALTA":
        if len(args) != 2:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        name = args[1]
        acct_id = ledger.next_account_id()
        ledger.accounts[acct_id] = {"name": name, "balance": 0}
        return 201, {"cuentaId": acct_id}

    if cmd == "CONSULTA":
        if len(args) != 2:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        acct_id = args[1]
        if acct_id not in ledger.accounts:
            return 404, {"error": "E401", "mensaje": "cuenta inexistente"}
        return 200, {"cuenta_id": acct_id, "saldo": ledger.accounts[acct_id]["balance"]}

    if cmd == "DEPOSITO":
        if len(args) != 3:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        acct_id = args[1]
        try:
            amount = int(args[2])
            if amount <= 0:
                return 400, {"error": "E303", "mensaje": "monto inválido"}
        except ValueError:
            return 400, {"error": "E303", "mensaje": "monto inválido"}
        if acct_id not in ledger.accounts:
            return 404, {"error": "E401", "mensaje": "cuenta inexistente"}
        ledger.accounts[acct_id]["balance"] += amount
        op_id = ledger.next_operation_id()
        ledger.operations[op_id] = {
            "kind": "DEPOSITO",
            "target": acct_id,
            "amount": amount,
            "annulled": False,
        }
        return 200, {"status": "recieved", "operacionId": op_id}

    if cmd == "TRANSFER":
        if len(args) != 4:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        src_id, dst_id = args[1], args[2]
        try:
            amount = int(args[3])
            if amount <= 0:
                return 400, {"error": "E303", "mensaje": "monto inválido"}
        except ValueError:
            return 400, {"error": "E303", "mensaje": "monto inválido"}
        if src_id == dst_id:
            return 400, {"error": "E304", "mensaje": "origen y destino iguales"}
        if src_id not in ledger.accounts or dst_id not in ledger.accounts:
            return 404, {"error": "E401", "mensaje": "cuenta inexistente"}
        if ledger.accounts[src_id]["balance"] < amount:
            return 422, {"error": "E507", "mensaje": "saldo insuficiente"}
        if amount > 100000:
            return 422, {"error": "E506", "mensaje": "límite excedido"}
        ledger.accounts[src_id]["balance"] -= amount
        ledger.accounts[dst_id]["balance"] += amount
        op_id = ledger.next_operation_id()
        ledger.operations[op_id] = {
            "kind": "TRANSFER",
            "source": src_id,
            "target": dst_id,
            "amount": amount,
            "annulled": False,
        }
        return 200, {"status": "recieved", "operacionId": op_id}

    if cmd == "ANULA":
        if len(args) != 2:
            return 400, {"error": "E302", "mensaje": "aridad inválida"}
        op_id = args[1]
        if op_id not in ledger.operations:
            return 404, {"error": "E402", "mensaje": "operación inexistente"}
        op = ledger.operations[op_id]
        if op["annulled"]:
            return 200, {"ok": False, "motivo": "ya anulada"}
        # Revert operations
        if op["kind"] == "TRANSFER":
            src_id = op["source"]
            dst_id = op["target"]
            amount = op["amount"]
            ledger.accounts[dst_id]["balance"] -= amount
            ledger.accounts[src_id]["balance"] += amount
        elif op["kind"] == "DEPOSITO":
            target_id = op["target"]
            amount = op["amount"]
            ledger.accounts[target_id]["balance"] -= amount
        op["annulled"] = True
        return 200, {"ok": True, "anulada": op_id}

    # Unknown command handling with Levenshtein distance <= 2 suggestions
    known_commands = ["PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"]
    best_cmd = None
    min_dist = 3  # Suggest only when distance is <= 2
    for candidate in known_commands:
        dist = compute_levenshtein(cmd, candidate)
        if dist < min_dist:
            min_dist = dist
            best_cmd = candidate

    err_payload: Dict[str, Any] = {"error": "E301", "mensaje": "comando desconocido "}
    if best_cmd is not None:
        err_payload["sugerencia"] = best_cmd
    return 400, err_payload


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
