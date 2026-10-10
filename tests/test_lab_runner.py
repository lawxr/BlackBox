import json
from pathlib import Path
import pytest
import httpx

from lab.client import LabClient
from lab.runner import compare_sequence, SequenceResult, load_ejemplos


def test_compare_sequence_all_match(tmp_path):
    exp_path = tmp_path / "exp.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    responses = [
        httpx.Response(200, json={"ok": True}),  # reset
        httpx.Response(200, json={"pong": True}),  # step 1
        httpx.Response(201, json={"cuentaId": "AC-0001"}),  # step 2
    ]
    idx = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal idx
        resp = responses[idx]
        idx += 1
        return resp

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    steps = [
        {"n": 1, "request": {"m": "PING;64"}, "status": 200, "response": {"pong": True}},
        {"n": 2, "request": {"m": "ALTA;Lucia;82"}, "status": 201, "response": {"cuentaId": "AC-0001"}},
    ]

    result = compare_sequence(client, steps, seq_id="test-match")

    assert result.matched is True
    assert result.passed_steps == 2
    assert result.total_steps == 2
    assert result.stop_reason == "completed"
    assert result.mismatch_step is None


def test_compare_sequence_mismatch_stops_execution(tmp_path):
    exp_path = tmp_path / "exp.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    responses = [
        httpx.Response(200, json={"ok": True}),  # reset
        httpx.Response(400, json={"error": "E202", "mensaje": "control inválido"}),  # step 1 mismatch
    ]
    idx = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal idx
        resp = responses[idx]
        idx += 1
        return resp

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    steps = [
        {"n": 1, "request": {"m": "PING;64"}, "status": 200, "response": {"pong": True}},
        {"n": 2, "request": {"m": "ALTA;Lucia;82"}, "status": 201, "response": {"cuentaId": "AC-0001"}},
    ]

    result = compare_sequence(client, steps, seq_id="test-mismatch")

    assert result.matched is False
    assert result.passed_steps == 0
    assert result.mismatch_step == 1
    assert result.stop_reason == "mismatch"
    # Ensure step 2 was never executed after mismatch at step 1
    assert idx == 2


def test_compare_sequence_stops_on_infra_rate_limit(tmp_path):
    exp_path = tmp_path / "exp.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit"}, headers={"X-Frontier-Infra": "rate-limit"})

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    steps = [
        {"n": 1, "request": {"m": "PING;64"}, "status": 200, "response": {"pong": True}},
    ]

    result = compare_sequence(client, steps, seq_id="test-rate-limit")

    assert result.matched is False
    assert result.stop_reason == "infra_rate_limit"


def test_compare_sequence_stops_on_transport_error(tmp_path):
    exp_path = tmp_path / "exp.jsonl"
    audit_path = tmp_path / "audit.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    client = LabClient(
        base_url="https://fake.url",
        experiments_path=exp_path,
        audit_path=audit_path,
        transport=transport,
    )

    steps = [
        {"n": 1, "request": {"m": "PING;64"}, "status": 200, "response": {"pong": True}},
    ]

    result = compare_sequence(client, steps, seq_id="test-transport-error")

    assert result.matched is False
    assert result.stop_reason == "transport_error"
    assert "Connection refused" in (result.error_detail or "")


def test_load_ejemplos(tmp_path):
    # Non-existing path
    assert load_ejemplos(tmp_path / "non_existing.jsonl") == []

    # Valid JSONL
    sample_file = tmp_path / "sample.jsonl"
    sample_file.write_text('{"n": 1, "request": {"m": "PING;64"}}\n\n{"n": 2}\n', encoding="utf-8")

    loaded = load_ejemplos(sample_file)
    assert len(loaded) == 2
    assert loaded[0]["n"] == 1
    assert loaded[1]["n"] == 2
