"""Run differential sequences (T5 & T6) comparing original black box vs local replica."""
from __future__ import annotations
import json
from typing import List, Tuple
from fastapi.testclient import TestClient

from lab.client import LabClient
from lab.runner import json_equal
from src.main import app, ledger
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    return f"{payload};{compute_control(payload)}"


TEST_SEQUENCES: List[Tuple[str, List[str]]] = [
    (
        "seq_t5_1_funding",
        [
            "ALTA;Carlos",
            "ALTA;Diana",
            "DEPOSITO;AC-0001;80000",
            "DEPOSITO;AC-0002;30000",
            "CONSULTA;AC-0001",
        ],
    ),
    (
        "seq_t5_2_interleaved_transfers",
        [
            "ALTA;Elena",
            "ALTA;Fabio",
            "DEPOSITO;AC-0001;95000",
            "TRANSFER;AC-0001;AC-0002;95000",
            "TRANSFER;AC-0001;AC-0002;1000",  # E507 saldo insuficiente
        ],
    ),
    (
        "seq_t6_1_chained_transfers_annulment",
        [
            "ALTA;Gabriel",
            "ALTA;Helena",
            "ALTA;Ignacio",
            "DEPOSITO;AC-0001;50000",
            "TRANSFER;AC-0001;AC-0002;20000",
            "TRANSFER;AC-0002;AC-0003;15000",
            "ANULA;OP-0003",
            "CONSULTA;AC-0003",
        ],
    ),
    (
        "seq_t6_2_mixed_syntax_and_business_errors",
        [
            "ALTA;Julia",
            "PING;99",
            "DEPOSITO;AC-0001;10000",
            "DEPOSITAR;AC-0001;10000",  # E301 con sugerencia DEPOSITO
            "DEPOSITO;AC-0001;-50",      # E303 monto inválido
            "CONSULTA;AC-0001",
            "ANULA;OP-0001",
            "CONSULTA;AC-0001",
            "ANULA;OP-0001",            # ya anulada
            "ANULA;OP-9999",            # E402 operación inexistente
        ],
    ),
    (
        "seq_t6_3_deep_12_step_ledger",
        [
            "ALTA;Karin",
            "ALTA;Lucas",
            "ALTA;Maria",
            "DEPOSITO;AC-0001;75000",
            "DEPOSITO;AC-0002;25000",
            "TRANSFER;AC-0001;AC-0003;30000",
            "TRANSFER;AC-0002;AC-0003;20000",
            "CONSULTA;AC-0003",
            "ANULA;OP-0004",
            "CONSULTA;AC-0003",
            "CONSULTA;AC-0002",
            "CONSULTA;AC-0001",
        ],
    ),
]


def run_differential_suite() -> bool:
    orig_client = LabClient()
    total_passed = 0
    total_steps = 0
    all_ok = True

    # Use in-process TestClient with unauthenticated/dummy token matching replica check_auth
    from src import config
    token = config.TEAM_TOKEN or "test-token"
    auth_headers = {"Authorization": f"Bearer {token}"}
    if not config.TEAM_TOKEN:
        auth_headers = {}

    with TestClient(app) as repl_client:
        for seq_id, steps in TEST_SEQUENCES:
            print(f"\n==========================================")
            print(f"▶ Ejecutando secuencia: {seq_id} ({len(steps)} pasos)")
            print(f"==========================================")

            # 1. Reset both
            orig_client.reset(seq=seq_id, hipotesis=f"Reset diferencial {seq_id}")
            repl_client.post("/__reset", headers=auth_headers)

            for idx, raw_cmd in enumerate(steps, 1):
                total_steps += 1
                m_str = make_msg(raw_cmd)

                # Send to original
                orig_res = orig_client.msg(
                    message=m_str,
                    seq=seq_id,
                    hipotesis=f"Paso {idx}: {raw_cmd}",
                )
                orig_status = orig_res["status"]
                orig_body = orig_res["response"]

                # Send to replica
                repl_res = repl_client.post(
                    "/msg",
                    headers=auth_headers,
                    json={"m": m_str},
                )
                repl_status = repl_res.status_code
                try:
                    repl_body = repl_res.json()
                except Exception:
                    repl_body = repl_res.text

                # Compare
                status_match = orig_status == repl_status
                body_match = json_equal(orig_body, repl_body)

                if status_match and body_match:
                    total_passed += 1
                    print(f"  [Paso {idx:02d}] {raw_cmd:32s} -> ✅ MATCH ({orig_status})")
                else:
                    all_ok = False
                    print(f"  [Paso {idx:02d}] {raw_cmd:32s} -> ❌ MISMATCH!")
                    print(f"     ORIGINAL: status={orig_status}, body={orig_body}")
                    print(f"     REPLICA:  status={repl_status}, body={repl_body}")
                    break

    print(f"\n------------------------------------------")
    print(f"RESULTADO FINAL: {total_passed}/{total_steps} pasos coincidentes.")
    print(f"Estado de paridad: {'✅ 100% PARIDAD TOTAL' if all_ok else '❌ DIVERGENCIAS DETECTADAS'}")
    print(f"------------------------------------------")
    return all_ok


if __name__ == "__main__":
    run_differential_suite()
