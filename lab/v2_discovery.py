"""Automated v2 differential discovery script for incident #FR-0153.

Tests targeted hypotheses against the live original service using LabClient
to identify the exact 3 behavioral changes between v1 and v2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lab.client import LabClient, TransportError
from src.protocol import compute_control


def send_cmd(client: LabClient, seq: str, payload_template: str, hipotesis: str) -> Dict[str, Any]:
    ctrl = compute_control(payload_template)
    msg_str = f"{payload_template};{ctrl}"
    return client.msg(message=msg_str, seq=seq, hipotesis=hipotesis)


def run_discovery(client: LabClient) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    print("==================================================")
    print("RUNNING AUTOMATED V2 DIFFERENTIAL DISCOVERY")
    print("==================================================")

    # -------------------------------------------------------------
    # Area 1: CONSULTA Balance Format
    # -------------------------------------------------------------
    client.reset("v2_disc_consulta", "Reset for CONSULTA balance format discovery")
    send_cmd(client, "v2_disc_consulta", "ALTA;UserA", "Create account")
    c0 = send_cmd(client, "v2_disc_consulta", "CONSULTA;AC-0001", "Query initial balance")
    send_cmd(client, "v2_disc_consulta", "DEPOSITO;AC-0001;1000", "Deposit 1000 cents")
    c1 = send_cmd(client, "v2_disc_consulta", "CONSULTA;AC-0001", "Query balance after 1000")

    initial_saldo = c0.get("response", {}).get("saldo")
    after_saldo = c1.get("response", {}).get("saldo")

    if isinstance(initial_saldo, str) and "." in initial_saldo:
        findings.append({
            "change_id": "CHANGE-1",
            "area": "CONSULTA balance format",
            "v1": "saldo returned integer (e.g. 0)",
            "v2": f"saldo returns 2-decimal string representation of cents (initial={initial_saldo!r}, after={after_saldo!r})",
            "evidence": {"initial": c0.get("response"), "after": c1.get("response")},
        })

    # -------------------------------------------------------------
    # Area 2: TRANSFER Maximum Limit
    # -------------------------------------------------------------
    client.reset("v2_disc_limit", "Reset for transfer limit boundary discovery")
    send_cmd(client, "v2_disc_limit", "ALTA;Sender", "Create sender")
    send_cmd(client, "v2_disc_limit", "ALTA;Receiver", "Create receiver")
    send_cmd(client, "v2_disc_limit", "DEPOSITO;AC-0001;500000", "Deposit 500000 cents")

    t_50k = send_cmd(client, "v2_disc_limit", "TRANSFER;AC-0001;AC-0002;50000", "Transfer 50000")
    t_50k1 = send_cmd(client, "v2_disc_limit", "TRANSFER;AC-0001;AC-0002;50001", "Transfer 50001")
    t_100k = send_cmd(client, "v2_disc_limit", "TRANSFER;AC-0001;AC-0002;100000", "Transfer 100000")

    if t_50k.get("status") == 200 and t_50k1.get("status") == 422:
        findings.append({
            "change_id": "CHANGE-2",
            "area": "TRANSFER limit threshold",
            "v1": "transfer limit was 100000 (status 200 on 100000)",
            "v2": f"transfer limit lowered to 50000 (50000 -> {t_50k.get('status')}, 50001 -> {t_50k1.get('status')} {t_50k1.get('response')})",
            "evidence": {"t_50k": t_50k.get("status"), "t_50k1": t_50k1.get("status"), "t_100k": t_100k.get("status")},
        })

    # -------------------------------------------------------------
    # Area 3: TRANSFER Precedence (max_amount vs sufficient_balance)
    # -------------------------------------------------------------
    # When balance is insufficient (0) AND transfer amount exceeds transfer limit (60000):
    # In v1: sufficient_balance was evaluated first -> E507
    # In v2: max_amount is evaluated first -> E506
    client.reset("v2_disc_precedence", "Reset for TRANSFER precedence check")
    send_cmd(client, "v2_disc_precedence", "ALTA;UserA", "Create UserA (balance 0)")
    send_cmd(client, "v2_disc_precedence", "ALTA;UserB", "Create UserB")
    t_prec = send_cmd(
        client,
        "v2_disc_precedence",
        "TRANSFER;AC-0001;AC-0002;60000",
        "Transfer 60000 (>50000 limit AND >0 balance)",
    )
    prec_err = t_prec.get("response", {}).get("error")
    if prec_err == "E506":
        findings.append({
            "change_id": "CHANGE-3",
            "area": "TRANSFER check precedence (limit vs balance)",
            "v1": "sufficient_balance (E507) evaluated before max_amount (E506)",
            "v2": "max_amount (E506) evaluated before sufficient_balance (E507) -> returns E506",
            "evidence": t_prec.get("response"),
        })

    print(f"\nDiscovered {len(findings)} confirmed changes:")
    for f in findings:
        print(f"[{f['change_id']}] {f['area']}:")
        print(f"    v1: {f['v1']}")
        print(f"    v2: {f['v2']}")

    return findings


def main() -> int:
    with LabClient(rate_limit_delay=0.15) as client:
        findings = run_discovery(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
