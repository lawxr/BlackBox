"""Second targeted probe script for remaining edge cases."""
from __future__ import annotations
import json
from lab.client import LabClient
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    ctrl = compute_control(payload)
    return f"{payload};{ctrl}"


def run_probes() -> None:
    client = LabClient()
    seq = "s_edge_cases_2"

    probes = [
        ("TRANSFER;AC-9999;AC-0001;1000", "Transferencia con origen inexistente"),
        ("TRANSFER;AC-9999;AC-8888;1000", "Transferencia con origen y destino inexistentes"),
        ("DEPOSITO;AC-0001;100.5", "Depósito con monto decimal"),
        ("ANULA;OP-0001", "Segunda anulación del mismo depósito"),
    ]

    for payload, hipotesis in probes:
        m_str = make_msg(payload)
        res = client.msg(message=m_str, seq=seq, hipotesis=hipotesis)
        print(f"[{payload}] -> status={res['status']} body={json.dumps(res['response'])}")


if __name__ == "__main__":
    run_probes()
