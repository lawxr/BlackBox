"""Local replica contract checks; only the historical replay is original evidence."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_TOKEN = "local-compatibility-test-token"
VALID_AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
AUTH_CASES = [
    pytest.param({}, id="missing"),
    pytest.param({"Authorization": "Bearer invalid-test-token"}, id="invalid"),
    pytest.param(VALID_AUTH, id="valid"),
]
UNAUTHORIZED = {"error": "E001", "mensaje": "no autorizado"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Import away from the project .env and never rely on ambient credentials.
    monkeypatch.setenv("TEAM_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("USER_TOKEN", "")
    monkeypatch.setenv("TOKEN", "")
    with monkeypatch.context() as import_context:
        import_context.chdir(tmp_path)
        from src import main

    # Patch the consumer too: another test may already have imported the app.
    monkeypatch.setattr(main, "TEAM_TOKEN", TEST_TOKEN)
    main.ledger.reset()
    with TestClient(main.app) as test_client:
        try:
            yield test_client
        finally:
            main.ledger.reset()


@pytest.mark.parametrize("headers", AUTH_CASES)
@pytest.mark.parametrize(
    "method,path,body,expected",
    [
        ("GET", "/health", None, {"ok": True}),
        ("POST", "/__reset", None, {"ok": True}),
        ("POST", "/msg", {"m": "PING;64"}, {"pong": True}),
    ],
)
def test_replica_endpoint_auth(client, headers, method, path, body, expected):
    response = client.request(method, path, headers=headers, json=body)
    authorized = headers == VALID_AUTH
    assert response.status_code == (200 if authorized else 401)
    assert response.json() == (expected if authorized else UNAUTHORIZED)


@pytest.mark.parametrize("headers", AUTH_CASES)
@pytest.mark.parametrize(
    "method,path",
    [("GET", "/unknown"), ("GET", "/msg"), ("POST", "/health"), ("GET", "/__reset")],
)
def test_replica_route_fallback_precedes_auth(client, headers, method, path):
    """Characterize the replica, not an unmeasured rule of the original."""
    response = client.request(method, path, headers=headers)
    assert response.status_code == 404
    assert response.json() == {"error": "E404", "mensaje": "ruta desconocida"}


@pytest.mark.parametrize("headers", AUTH_CASES)
def test_replica_auth_precedes_json_validation(client, headers):
    response = client.post("/msg", headers=headers, content="{")
    authorized = headers == VALID_AUTH
    assert response.status_code == (400 if authorized else 401)
    assert response.json() == (
        {"error": "E100", "mensaje": "json inválido"} if authorized else UNAUTHORIZED
    )


def test_replica_reset_clears_accounts_and_counter(client):
    account = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Lucia;82"})
    assert account.status_code == 201
    assert account.json() == {"cuentaId": "AC-0001"}

    reset = client.post("/__reset", headers=VALID_AUTH)
    assert reset.status_code == 200
    assert reset.json() == {"ok": True}
    missing = client.post("/msg", headers=VALID_AUTH, json={"m": "CONSULTA;AC-0001;14"})
    assert missing.status_code == 404
    assert missing.json() == {"error": "E401", "mensaje": "cuenta inexistente"}

    recreated = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Lucia;82"})
    assert recreated.status_code == 201
    assert recreated.json() == {"cuentaId": "AC-0001"}


@pytest.mark.parametrize("headers", AUTH_CASES[:2])
def test_replica_unauthorized_reset_preserves_state(client, headers):
    account = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Lucia;82"})
    assert account.status_code == 201
    assert account.json() == {"cuentaId": "AC-0001"}
    reset = client.post("/__reset", headers=headers)
    assert reset.status_code == 401
    assert reset.json() == UNAUTHORIZED
    balance = client.post("/msg", headers=VALID_AUTH, json={"m": "CONSULTA;AC-0001;14"})
    assert balance.status_code == 200
    assert balance.json() == {"cuenta_id": "AC-0001", "saldo": "0.00"}


def test_replay_20_historical_examples(client):
    """Replay morning evidence in order; this does not prove the current original."""
    from src import profile
    v1_prof = Path(__file__).resolve().parents[1] / "src" / "profile.v1.json"
    profile.reload(v1_prof)
    try:
        examples_file = Path(__file__).resolve().parents[1] / "pruebas" / "ejemplos.jsonl"
        with examples_file.open(encoding="utf-8") as source:
            examples = [json.loads(line) for line in source if line.strip()]
        assert len(examples) == 20
        assert [item["n"] for item in examples] == list(range(1, 21))

        reset = client.post("/__reset", headers=VALID_AUTH)
        assert reset.status_code == 200
        assert reset.json() == {"ok": True}
        for item in examples:
            response = client.post("/msg", headers=VALID_AUTH, json=item["request"])
            context = f"Historical step {item['n']}: {item['request']}"
            assert response.status_code == item["status"], context
            assert response.json() == item["response"], context
    finally:
        profile.reload()


def test_edge_cases_deposit_and_transfer_validation(client):
    """Test verified business rules: E303, E304, E402, and deposit annulment."""
    # Setup
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Alfa;65"})
    assert r.status_code == 201 and r.json() == {"cuentaId": "AC-0001"}

    # DEPOSITO 10000 -> OP-0001
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "DEPOSITO;AC-0001;10000;50"})
    assert r.status_code == 200 and r.json() == {"status": "recieved", "operacionId": "OP-0001"}

    # Anular non-existent OP-9999 -> 404 E402
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ANULA;OP-9999;51"})
    assert r.status_code == 404 and r.json() == {"error": "E402", "mensaje": "operación inexistente"}

    # Anular deposit OP-0001 -> reverts balance to 0
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ANULA;OP-0001;72"})
    assert r.status_code == 200 and r.json() == {"ok": True, "anulada": "OP-0001"}

    r = client.post("/msg", headers=VALID_AUTH, json={"m": "CONSULTA;AC-0001;14"})
    assert r.status_code == 200 and r.json()["saldo"] == "0.00"

    # Repeating annulment -> 200 ok: false
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ANULA;OP-0001;72"})
    assert r.status_code == 200 and r.json() == {"ok": False, "motivo": "ya anulada"}

    # DEPOSITO 0 or negative -> 400 E303
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "DEPOSITO;AC-0001;0;31"})
    assert r.status_code == 400 and r.json() == {"error": "E303", "mensaje": "monto inválido"}

    r = client.post("/msg", headers=VALID_AUTH, json={"m": "DEPOSITO;AC-0001;-500;46"})
    assert r.status_code == 400 and r.json() == {"error": "E303", "mensaje": "monto inválido"}

    # TRANSFER to self -> 400 E304
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "TRANSFER;AC-0001;AC-0001;1000;64"})
    assert r.status_code == 400 and r.json() == {"error": "E304", "mensaje": "origen y destino iguales"}

    # TRANSFER 0 or negative -> 400 E303
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "TRANSFER;AC-0001;AC-0002;0;44"})
    assert r.status_code == 400 and r.json() == {"error": "E303", "mensaje": "monto inválido"}

    # TRANSFER to self with amount > 100000 still gives E304 (precedence)
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "TRANSFER;AC-0001;AC-0001;120000;39"})
    assert r.status_code == 400 and r.json() == {"error": "E304", "mensaje": "origen y destino iguales"}


def test_unknown_command_levenshtein_suggestions(client):
    """Test verified E301 behavior: suggestion field added when edit distance <= 2."""
    from src.protocol import compute_control

    # Dist 1 from ALTA -> ALTA
    ctrl = compute_control("ALTAA")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"ALTAA;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "ALTA"}

    # Dist 1 from CONSULTA -> CONSULTA
    ctrl = compute_control("CONSULTAR")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"CONSULTAR;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "CONSULTA"}

    # Dist 2 from ANULA -> ANULA
    ctrl = compute_control("AYUDA")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"AYUDA;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "ANULA"}

    # Dist 2 from PING -> PING
    ctrl = compute_control("PINGUI")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"PINGUI;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "PING"}

    # Dist 3 from PING -> no suggestion
    ctrl = compute_control("PINGUIN")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"PINGUIN;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido "}

    # Dist >= 3 (SALDOS) -> no suggestion
    ctrl = compute_control("SALDOS;AC-0001")
    r = client.post("/msg", headers=VALID_AUTH, json={"m": f"SALDOS;AC-0001;{ctrl}"})
    assert r.status_code == 400 and r.json() == {"error": "E301", "mensaje": "comando desconocido "}


def test_control_edge_cases_iso7064(client):
    """Test ISO 7064 MOD 97-10 check value 97 and strict formatting without leading zeroes."""
    # Check value 97 (when rem == 1, check is 97, not 0)
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "AYUDA;97"})
    assert r.status_code == 400 and r.json()["error"] == "E301"

    r = client.post("/msg", headers=VALID_AUTH, json={"m": "AYUDA;0"})
    assert r.status_code == 400 and r.json() == {"error": "E202", "mensaje": "control inválido"}

    # Single digit accepted without leading zero
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Mateo;3"})
    assert r.status_code == 201 and r.json() == {"cuentaId": "AC-0001"}

    # Leading zero rejected with E202 (not E201)
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Mateo;03"})
    assert r.status_code == 400 and r.json() == {"error": "E202", "mensaje": "control inválido"}

    # Length > 2 rejected with E201
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "ALTA;Mateo;003"})
    assert r.status_code == 400 and r.json() == {"error": "E201", "mensaje": "control mal formado"}


def _ctrl(payload):
    from src.protocol import compute_control
    return f"{payload};{compute_control(payload)}"


@pytest.mark.parametrize(
    "amount,status",
    [
        ("1", 200),
        ("9999999999", 200),  # exp seq s_amount_bound: largest accepted
        ("10000000000", 400),
        ("99999999999999999999", 400),  # exp 954
        ("01000", 400),  # seqfuzz sf_2026_46
        ("01", 400),
        ("+5", 400),
        (" 1", 400),
        ("1 ", 400),
        ("1_000", 400),
    ],
)
def test_deposit_amount_syntax_is_strict(client, amount, status):
    client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl("ALTA;Probe")})
    r = client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl(f"DEPOSITO;AC-0001;{amount}")})
    assert r.status_code == status
    if status == 400:
        assert r.json() == {"error": "E303", "mensaje": "monto inválido"}


def test_invalid_amount_precedes_unknown_account_and_same_account(client):
    r = client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl("DEPOSITO;ac-0001; 100")})
    assert (r.status_code, r.json()) == (400, {"error": "E303", "mensaje": "monto inválido"})
    client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl("ALTA;A")})
    r = client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl("TRANSFER;AC-0001;AC-0001;100 ")})
    assert (r.status_code, r.json()) == (400, {"error": "E303", "mensaje": "monto inválido"})


HALT_REFUSED = {
    "error": "E520",
    "mensaje": "operación destructiva: detiene el servicio; reenvía con confirmación",
}


@pytest.mark.parametrize(
    "message,status,body",
    [
        (_ctrl("HALT;x"), 409, HALT_REFUSED),
        (_ctrl("HALT;AC-0001"), 409, HALT_REFUSED),
        (_ctrl("HALT"), 400, {"error": "E302", "mensaje": "aridad inválida"}),
        (_ctrl("halt"), 400, {"error": "E302", "mensaje": "aridad inválida"}),
        (_ctrl("HALT;x;y"), 400, {"error": "E302", "mensaje": "aridad inválida"}),
        ("HALT;x;1", 400, {"error": "E202", "mensaje": "control inválido"}),
        ("HELP;72", 400, {"error": "E301", "mensaje": "comando desconocido ", "sugerencia": "HALT"}),
    ],
)
def test_halt_command_requires_confirmation(client, message, status, body):
    r = client.post("/msg", headers=VALID_AUTH, json={"m": message})
    assert (r.status_code, r.json()) == (status, body)
    assert client.post("/msg", headers=VALID_AUTH, json={"m": "PING;64"}).status_code == 200


def test_fullwidth_digit_is_not_a_control_digit(client):
    # exp 1196: U+FF11 is skipped by the control, so the ASCII-computed control fails (E202)
    client.post("/msg", headers=VALID_AUTH, json={"m": _ctrl("ALTA;Probe")})
    r = client.post("/msg", headers=VALID_AUTH, json={"m": "DEPOSITO;AC-0001;１;28"})
    assert (r.status_code, r.json()) == (400, {"error": "E202", "mensaje": "control inválido"})
