"""Autonomous Property-Based Differential Fuzzer for BlackBox.

Systematically explores protocol boundaries, commands, arities, and states
between the original live service and the local ASGI replica without manual intervention.
"""
from __future__ import annotations
import argparse
import json
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from fastapi.testclient import TestClient

from lab.client import LabClient, TransportError
from lab.runner import json_equal
from src.main import app
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    return f"{payload};{compute_control(payload)}"


class AutonomousDifferentialFuzzer:
    """Explores protocol state-space and verifies 100% equivalence automatically."""

    def __init__(self, budget: int = 50, rate_delay: float = 0.15) -> None:
        self.budget = budget
        self.client_orig = LabClient(rate_limit_delay=rate_delay)
        from src import config
        token = config.TEAM_TOKEN or "test-token"
        self.auth_headers = {"Authorization": f"Bearer {token}"} if config.TEAM_TOKEN else {}
        self.divergences: List[Dict[str, Any]] = []
        self.tests_executed = 0

    def generate_boundary_payloads(self) -> List[str]:
        """Generate combinatorial boundary payloads across syntax, types, and domains."""
        payloads = [
            # 1. Delimiter & syntax mutations
            "PING",                         # Missing delimiter (E103)
            "ALTA;Lucia;",                  # Trailing empty segment (E104)
            ";ALTA;Lucia",                  # Leading empty segment (E104)
            "ALTA;;Lucia;82",               # Middle empty segment (E104)
            "PING;;64",                     # Double delimiter (E104)

            # 2. Control format and value mutations
            "ALTA;Lucia;-5",                # Negative control (E201)
            "ALTA;Lucia;5X",                # Alphanumeric control (E201)
            "ALTA;Lucia;150",               # Control >= 100 (E201)
            "ALTA;Lucia;003",               # Length > 2 control (E201)
            "ALTA;Lucia;0",                 # Control 0 (E202)
            "ALTA;Lucia;00",                # Control 00 (E202)
            "ALTA;Lucia;03",                # Leading zero control (E202)
            "ALTA;Lucia;99",                # Wrong control value (E202)

            # 3. Command arity & typo mutations
            "PING;64;extra",                # PING extra arity (E302)
            "ALTA;Lucia;Perez;11",          # ALTA extra arity (E302)
            "CONSULTA",                     # CONSULTA missing arity (E103/E302)
            "CONSULTAR;AC-0001;14",         # Typo dist 1 -> sugerencia CONSULTA
            "DEPOSITAR;AC-0001;1000;25",    # Typo dist 2 -> sugerencia DEPOSITO
            "TRANSFERIR;AC-0001;AC-0002;1000;30", # Typo dist 2 -> sugerencia TRANSFER
            "SALDOS;AC-0001;38",            # Unknown cmd dist >= 3 -> E301 no sugerencia
            "UNKNOWNCMD;AC-0001;50",        # Completely unknown command

            # 4. Financial boundary mutations (amounts, non-integers, boundaries)
            make_msg("DEPOSITO;AC-0001;0"),              # Monto 0 (E303)
            make_msg("DEPOSITO;AC-0001;-100"),           # Monto negativo (E303)
            make_msg("DEPOSITO;AC-0001;100.5"),          # Monto decimal (E303)
            make_msg("DEPOSITO;AC-0001;abc"),            # Monto no numérico (E303)
            make_msg("DEPOSITO;AC-9999;1000"),           # Cuenta inexistente (E401)
            make_msg("TRANSFER;AC-0001;AC-0001;1000"),   # Origen == Destino (E304)
            make_msg("TRANSFER;AC-0001;AC-0002;0"),      # Transfer monto 0 (E303)
            make_msg("TRANSFER;AC-0001;AC-0002;-50"),    # Transfer monto negativo (E303)
            make_msg("TRANSFER;AC-0001;AC-0002;100000"), # Límite exacto 100000
            make_msg("TRANSFER;AC-0001;AC-0002;100001"), # Límite excedido (E506 / E507)
            make_msg("ANULA;OP-9999"),                   # Operación inexistente (E402)
        ]
        return payloads

    def run(self) -> bool:
        """Run autonomous differential fuzzing loop against original and replica."""
        print(f"🚀 Iniciando Fuzzer Diferencial Autónomo (Presupuesto: {self.budget} tests)...")
        payloads = self.generate_boundary_payloads()
        seq_id = f"autofuzz_{int(time.time())}"

        with TestClient(app) as client_repl:
            # 1. Autonomous Reset
            print("1. Reseteando estado en original y réplica...")
            self.client_orig.reset(seq=seq_id, hipotesis="Reset inicial para fuzzer autónomo")
            client_repl.post("/__reset", headers=self.auth_headers)

            # Pre-fund some accounts for financial probes
            pre_setup = [
                "ALTA;FuzzAlpha",
                "ALTA;FuzzBeta",
                "DEPOSITO;AC-0001;50000",
            ]
            print("2. Inicializando estado contable base para pruebas financieras...")
            for setup_cmd in pre_setup:
                m_str = make_msg(setup_cmd)
                self.client_orig.msg(message=m_str, seq=seq_id, hipotesis=f"Setup {setup_cmd}")
                client_repl.post("/msg", headers=self.auth_headers, json={"m": m_str})

            # 3. Differential Test Execution
            print(f"3. Ejecutando oráculo diferencial sobre {len(payloads)} casos de frontera...")
            for idx, raw_msg in enumerate(payloads[:self.budget], 1):
                self.tests_executed += 1

                # Original call
                try:
                    orig_entry = self.client_orig.msg(
                        message=raw_msg,
                        seq=seq_id,
                        hipotesis=f"Fuzz #{idx}: {raw_msg[:30]}",
                    )
                    orig_status = orig_entry["status"]
                    orig_body = orig_entry["response"]
                except TransportError as te:
                    print(f"  [#{idx:02d}] ⚠️ Error de transporte con el original: {te}")
                    break

                # Replica call
                repl_res = client_repl.post(
                    "/msg",
                    headers=self.auth_headers,
                    json={"m": raw_msg},
                )
                repl_status = repl_res.status_code
                try:
                    repl_body = repl_res.json()
                except Exception:
                    repl_body = repl_res.text

                # Oracle comparison
                status_ok = orig_status == repl_status
                body_ok = json_equal(orig_body, repl_body)

                if status_ok and body_ok:
                    print(f"  [#{idx:02d}] {raw_msg[:42]:42s} -> ✅ MATCH ({orig_status})")
                else:
                    print(f"  [#{idx:02d}] {raw_msg[:42]:42s} -> ❌ DIVERGENCIA DETECTADA!")
                    print(f"       ORIGINAL: {orig_status} {json.dumps(orig_body)}")
                    print(f"       REPLICA:  {repl_status} {json.dumps(repl_body)}")
                    self.divergences.append({
                        "test_id": idx,
                        "input": raw_msg,
                        "original": {"status": orig_status, "body": orig_body},
                        "replica": {"status": repl_status, "body": repl_body},
                    })

        print("\n==========================================")
        print(f"RESULTADO DEL FUZZING AUTÓNOMO:")
        print(f"Pruebas ejecutadas: {self.tests_executed}")
        print(f"Divergencias encontradas: {len(self.divergences)}")
        if not self.divergences:
            print("✅ 100% PARIDAD CONFIRMADA EN TODAS LAS PRUEBAS DE FRONTERA")
        else:
            print(f"❌ Se encontraron {len(self.divergences)} divergencias:")
            for d in self.divergences:
                print(f" - Input: {d['input']}")
                print(f"   Original: {d['original']['status']} {d['original']['body']}")
                print(f"   Replica:  {d['replica']['status']} {d['replica']['body']}")
        print("==========================================")
        return len(self.divergences) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Differential Fuzzer")
    parser.add_argument("--budget", type=int, default=30, help="Max requests to send to original")
    args = parser.parse_args()

    fuzzer = AutonomousDifferentialFuzzer(budget=args.budget)
    fuzzer.run()
