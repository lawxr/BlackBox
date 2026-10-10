import json
from pathlib import Path
import pytest
import httpx

from lab.client import LabClient, TransportError


def test_lab_client_success_recording(tmp_path):
    exp_path = tmp_path / "experimentos.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"pong": True}, headers={"X-Req": "42"})

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        token="secret-token",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    result = client.send(
        method="POST",
        path="/msg",
        seq="seq-1",
        hipotesis="Test mock success",
        payload={"m": "PING;64"},
        conclusion="Success",
    )

    assert result["status"] == 200
    assert result["response"] == {"pong": True}
    assert result["x_req"] == 42
    assert result["id"] == 1

    # Verify experiments.jsonl entry
    assert exp_path.exists()
    with exp_path.open(encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 1
    exp_entry = lines[0]
    assert exp_entry["id"] == 1
    assert exp_entry["seq"] == "seq-1"
    assert exp_entry["x_req"] == 42
    assert exp_entry["status"] == 200
    assert exp_entry["response"] == {"pong": True}
    assert "secret-token" not in json.dumps(exp_entry)

    # Verify audit.jsonl entry
    assert audit_path.exists()
    with audit_path.open(encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 1
    audit_entry = lines[0]
    assert audit_entry["id"] == 1
    assert audit_entry["method"] == "POST"
    assert audit_entry["path"] == "/msg"
    assert audit_entry["status"] == 200
    assert "secret-token" not in json.dumps(audit_entry)


def test_lab_client_timeout_leaves_durable_attempt(tmp_path):
    exp_path = tmp_path / "experimentos.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        token="secret-token",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    with pytest.raises(TransportError) as exc_info:
        client.send(
            method="POST",
            path="/msg",
            seq="seq-timeout",
            hipotesis="Test timeout durable record",
            payload={"m": "PING;64"},
        )

    assert "Connection timed out" in str(exc_info.value)

    # Durable audit record must exist
    assert audit_path.exists()
    with audit_path.open(encoding="utf-8") as f:
        audit_lines = [json.loads(line) for line in f if line.strip()]
    assert len(audit_lines) == 1
    audit_record = audit_lines[0]
    assert audit_record["status"] is None
    assert audit_record["error"] == "timeout"
    assert "secret-token" not in json.dumps(audit_record)

    # Durable experiment record must exist with uncertain/null status
    assert exp_path.exists()
    with exp_path.open(encoding="utf-8") as f:
        exp_lines = [json.loads(line) for line in f if line.strip()]
    assert len(exp_lines) == 1
    exp_record = exp_lines[0]
    assert exp_record["status"] is None
    assert exp_record["response"] is None
    assert exp_record["conclusion"] == "timeout"


def test_lab_client_bodyless_vs_payload_distinguishable(tmp_path):
    exp_path = tmp_path / "experimentos.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    # Bodyless reset
    client.send(method="POST", path="/__reset", seq="seq-reset", hipotesis="Reset state")
    # Payload msg
    client.send(method="POST", path="/msg", seq="seq-msg", hipotesis="Ping", payload={"m": "PING;64"})

    with exp_path.open(encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert lines[0]["request"] == {}  # Bodyless
    assert lines[1]["request"] == {"m": "PING;64"}
