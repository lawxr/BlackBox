"""Canary monitor to detect the scheduled 15:30 service change/incident."""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from lab.client import LabClient
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    return f"{payload};{compute_control(payload)}"


# Baseline probes with expected statuses and response subsets
CANARY_PROBES = [
    {"m": "PING;64", "expected_status": 200, "expected_body": {"pong": True}},
    {"m": make_msg("ALTA;Canario"), "expected_status": 201, "key": "cuentaId"},
    {"m": make_msg("CONSULTA;AC-0001"), "expected_status": 200, "expected_body": {"cuenta_id": "AC-0001", "saldo": 0}},
    {"m": make_msg("DEPOSITO;AC-0001;50000"), "expected_status": 200, "expected_body": {"status": "recieved", "operacionId": "OP-0001"}},
    {"m": make_msg("TRANSFER;AC-0001;AC-0001;1000"), "expected_status": 400, "expected_body": {"error": "E304", "mensaje": "origen y destino iguales"}},
    {"m": make_msg("TRANSFER;AC-0001;AC-9999;1000"), "expected_status": 404, "expected_body": {"error": "E401", "mensaje": "cuenta inexistente"}},
    {"m": make_msg("DEPOSITO;AC-0001;0"), "expected_status": 400, "expected_body": {"error": "E303", "mensaje": "monto inválido"}},
    {"m": make_msg("ANULA;OP-0001"), "expected_status": 200, "expected_body": {"ok": True, "anulada": "OP-0001"}},
]


def run_canary_check() -> list[dict]:
    """Execute one round of canary checks and return any divergences."""
    client = LabClient()
    timestamp = datetime.now(timezone.utc).isoformat()
    divergences = []

    # Reset before check
    client.reset(seq="canary", hipotesis=f"Canary check at {timestamp}")

    for step in CANARY_PROBES:
        m_str = step["m"]
        res = client.msg(message=m_str, seq="canary", hipotesis=f"Canary probe {m_str}")
        status = res["status"]
        body = res["response"]

        if status != step["expected_status"]:
            divergences.append({
                "probe": m_str,
                "expected_status": step["expected_status"],
                "actual_status": status,
                "body": body,
            })
            continue

        if "expected_body" in step:
            for k, v in step["expected_body"].items():
                if body.get(k) != v:
                    divergences.append({
                        "probe": m_str,
                        "field": k,
                        "expected": v,
                        "actual": body.get(k),
                        "body": body,
                    })

    return divergences


if __name__ == "__main__":
    print(f"Running canary check at {datetime.now(timezone.utc).isoformat()}...")
    diffs = run_canary_check()
    if diffs:
        print(f"⚠️ DIVERGENCIA DETECTADA ({len(diffs)} diferencias):")
        for d in diffs:
            print(json.dumps(d, ensure_ascii=False))
    else:
        print("✅ Servicio estable: todas las sondas canario coinciden al 100%.")
