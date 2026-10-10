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
    assert balance.json() == {"cuenta_id": "AC-0001", "saldo": 0}


def test_replay_20_historical_examples(client):
    """Replay morning evidence in order; this does not prove the current original."""
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
