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


import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous canary probe and contract drift watcher."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously in background mode until stopped or drift is detected.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between probe cycles in watch mode (default: 60).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("lab/incident_report.json"),
        help="File path to save the structured incident report upon drift detection.",
    )
    parser.add_argument(
        "--stop-on-drift",
        action="store_true",
        help="Exit immediately with non-zero code upon detecting contract drift.",
    )
    return parser.parse_args()


def save_incident_report(diffs: list[dict], output_path: Path) -> None:
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_divergences": len(diffs),
        "divergences": diffs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n🚨 Reporte forense guardado en: {output_path}")


def main() -> None:
    args = parse_args()
    print(
        f"Iniciando Canary (Modo: {'WATCH cada ' + str(args.interval) + 's' if args.watch else 'ONE-SHOT'})..."
    )

    iteration = 0
    try:
        while True:
            iteration += 1
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"[{now}] Ronda #{iteration}: verificando contrato...", end=" ", flush=True)

            diffs = run_canary_check()

            if diffs:
                print(f"⚠️ ¡DERIVA DE CONTRATO DETECTADA! ({len(diffs)} divergencias)")
                for d in diffs:
                    print(f"  - Sonda: {d.get('probe')} | Detalle: {d}")

                save_incident_report(diffs, args.output)

                if args.stop_on_drift or not args.watch:
                    sys.exit(1)
            else:
                print("OK (100% paridad)")

            if not args.watch:
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nWatcher detenido por el usuario.")


if __name__ == "__main__":
    main()
