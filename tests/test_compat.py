import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_reset():
    response = client.post("/__reset")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_ping_message():
    response = client.post("/msg", json={"m": "PING;64"})
    assert response.status_code == 200
    assert response.json() == {"pong": True}


def test_replay_20_historical_examples():
    """Replay the 20 historical examples from morning session in exact order."""
    examples_file = Path("pruebas/ejemplos.jsonl")
    assert examples_file.exists(), "ejemplos.jsonl must exist"

    # Reset state before replaying sequence
    reset_resp = client.post("/__reset")
    assert reset_resp.status_code == 200

    with open(examples_file, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) == 20, f"Expected 20 examples, got {len(lines)}"

    for item in lines:
        n = item["n"]
        req_body = item["request"]
        expected_status = item["status"]
        expected_response = item["response"]

        resp = client.post("/msg", json=req_body)
        assert resp.status_code == expected_status, (
            f"Step {n} ({req_body}) status mismatch: got {resp.status_code}, expected {expected_status}. Body: {resp.text}"
        )
        assert resp.json() == expected_response, (
            f"Step {n} ({req_body}) body mismatch: got {resp.json()}, expected {expected_response}"
        )
