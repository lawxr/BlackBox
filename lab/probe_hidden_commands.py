"""Dictionary fuzzer to discover potential hidden commands on the original service."""
from __future__ import annotations
import json
from lab.client import LabClient
from src.protocol import compute_control


def make_msg(payload: str) -> str:
    return f"{payload};{compute_control(payload)}"


CANDIDATE_COMMANDS = [
    # Basic financial operations
    "RETIRO;AC-0001;1000",
    "EXTRACCION;AC-0001;1000",
    "BAJA;AC-0001",
    "SALDO;AC-0001",
    "EXTRACTO;AC-0001",
    "MOVIMIENTOS;AC-0001",
    "HISTORIAL;AC-0001",
    "BLOQUEO;AC-0001",
    "PAGO;AC-0001;1000",
    "DEBITO;AC-0001;1000",
    "CREDITO;AC-0001;1000",
    # System / admin operations
    "STATUS",
    "ESTADO",
    "INFO",
    "VERSION",
    "HELP",
    "AYUDA",
    "RESET",
    "ECHO;test",
    # English equivalents
    "WITHDRAW;AC-0001;1000",
    "DEPOSIT;AC-0001;1000",
    "QUERY;AC-0001",
    "CANCEL;OP-0001",
    "BALANCE;AC-0001",
]


def test_candidates() -> None:
    client = LabClient()
    seq = "s_dict_fuzz"

    print("Checking candidate commands against original service...")
    found_commands = []

    for payload in CANDIDATE_COMMANDS:
        # If no args, need at least 2 segments for valid protocol format: CMD;ctrl
        m_str = make_msg(payload)
        res = client.msg(message=m_str, seq=seq, hipotesis=f"Probar si existe comando {payload.split(';')[0]}")
        status = res["status"]
        body = res["response"]

        err_code = body.get("error") if isinstance(body, dict) else None
        if err_code == "E301":
            # Expected unknown command
            pass
        else:
            print(f"🌟 POSIBLE COMANDO VÁLIDO ENCONTRADO: [{payload}] -> {status} {body}")
            found_commands.append((payload, status, body))

    if not found_commands:
        print("✅ Ninguno de los 24 comandos candidatos fue reconocido: todos devuelven E301 comando desconocido.")
    else:
        print(f"⚠️ Se encontraron {len(found_commands)} comandos válidos!")


if __name__ == "__main__":
    test_candidates()
