import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200


def test_reset():
    response = client.post("/__reset")
    assert response.status_code == 200


def test_ping_message():
    response = client.post("/msg", json={"m": "PING;64"})
    assert response.status_code == 200
    assert response.json() == {"pong": True}
