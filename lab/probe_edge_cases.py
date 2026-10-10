"""Controlled probe script to test financial edge cases on the original service."""
from __future__ import annotations
import json
from lab.client import LabClient
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    ctrl = compute_control(payload)
    return f"{payload};{ctrl}"


def run_probes() -> None:
    client = LabClient()
    seq = "s_edge_cases"

    print("--- 1. Reset ---")
    res = client.reset(seq=seq, hipotesis="Reset para campaña de casos borde")
    print(f"Reset: status={res['status']}, body={res['response']}")

    probes = [
        ("ALTA;Alfa", "Alta de primera cuenta"),
        ("ALTA;Alfa", "Alta duplicada con mismo nombre"),
        ("ALTA;Beta", "Alta de segunda/tercera cuenta"),
        ("DEPOSITO;AC-0001;10000", "Depósito inicial de 10000 en AC-0001"),
        ("CONSULTA;AC-0001", "Consulta saldo inicial AC-0001"),
        ("ANULA;OP-9999", "Anular operación inexistente OP-9999"),
        ("ANULA;OP-0001", "Anular operación de depósito OP-0001"),
        ("CONSULTA;AC-0001", "Consulta saldo AC-0001 tras anular depósito"),
        ("DEPOSITO;AC-0001;0", "Depósito con monto 0"),
        ("DEPOSITO;AC-0001;-500", "Depósito con monto negativo -500"),
        ("TRANSFER;AC-0001;AC-9999;1000", "Transferencia a cuenta destino inexistente AC-9999"),
        ("TRANSFER;AC-0001;AC-0001;1000", "Transferencia de cuenta a sí misma"),
        ("TRANSFER;AC-0001;AC-0002;0", "Transferencia con monto 0"),
        ("TRANSFER;AC-0001;AC-0002;-100", "Transferencia con monto negativo -100"),
        ("CONSULTA;AC-0001", "Consulta saldo final AC-0001"),
    ]

    for payload, hipotesis in probes:
        m_str = make_msg(payload)
        res = client.msg(message=m_str, seq=seq, hipotesis=hipotesis)
        print(f"[{payload}] (m={m_str}) -> status={res['status']} body={json.dumps(res['response'])}")


if __name__ == "__main__":
    run_probes()
