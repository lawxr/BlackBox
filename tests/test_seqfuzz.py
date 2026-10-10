"""Hermetic tests for the stateful sequence differential fuzzer (no network)."""
import random

import httpx
import pytest

from lab import seqfuzz
from lab.client import LabClient
from src.protocol import compute_control

TEST_TOKEN = "local-seqfuzz-test-token"


@pytest.fixture(autouse=True)
def replica_auth(monkeypatch):
    from src import main

    monkeypatch.setattr(main, "TEAM_TOKEN", TEST_TOKEN)
    main.ledger.reset()
    yield
    main.ledger.reset()


def make_client(tmp_path, handler):
    return LabClient(
        base_url="https://fake.invalid",
        token="t",
        rate_limit_delay=0,
        experiments_path=tmp_path / "exp.jsonl",
        audit_path=tmp_path / "audit.jsonl",
        transport=httpx.MockTransport(handler),
    )


def replica_mirror_handler():
    """Fake original that answers exactly like the replica (forwards in-process)."""
    from fastapi.testclient import TestClient
    from src import main

    tc = TestClient(main.app)
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    def handler(request):
        r = tc.request(request.method, request.url.path, content=request.content, headers=headers)
        return httpx.Response(r.status_code, content=r.content, headers={"content-type": "application/json"})

    return handler


def has_valid_ctrl(m):
    if ";" not in m:
        return False
    payload, ctrl = m.rsplit(";", 1)
    return ctrl == str(compute_control(payload))


def test_campaign_is_deterministic_per_seed():
    a = seqfuzz.generate_campaign(7, 5, 5, 3)
    b = seqfuzz.generate_campaign(7, 5, 5, 3)
    c = seqfuzz.generate_campaign(8, 5, 5, 3)
    assert a == b
    assert a != c


def test_campaign_length_distribution():
    camp = seqfuzz.generate_campaign(3, 10, 20, 10)
    assert len(camp) == 40
    lengths = [len(s["steps"]) for s in camp]
    assert all(n == 1 for n in lengths[:10])
    assert all(2 <= n <= 5 for n in lengths[10:30])
    assert all(6 <= n <= 12 for n in lengths[30:])
    assert [s["id"] for s in camp][:2] == ["sf_3_0", "sf_3_1"]
    assert all(s["hipotesis"] for s in camp)


def test_valid_control_ratio_within_tolerance():
    rng = random.Random(11)
    msgs = []
    for _ in range(400):
        msgs += [s["m"] for s in seqfuzz.generate_sequence(rng, 5) if isinstance(s.get("m"), str)]
    ratio = sum(has_valid_ctrl(m) for m in msgs) / len(msgs)
    assert 0.5 <= ratio <= 0.7


def test_malformed_bodies_appear():
    rng = random.Random(5)
    steps = [s for _ in range(300) for s in seqfuzz.generate_sequence(rng, 4)]
    assert any("__raw__" in s for s in steps)
    assert any(not isinstance(s.get("m"), str) and "__raw__" not in s for s in steps)


def test_generator_is_state_aware():
    rng = random.Random(2)
    referenced_existing = 0
    for _ in range(200):
        steps = seqfuzz.generate_sequence(rng, 8)
        created = 0
        for s in steps:
            m = s.get("m")
            if not isinstance(m, str):
                continue
            parts = m.split(";")
            if parts[0] == "ALTA" and has_valid_ctrl(m) and len(parts) == 3:
                created += 1
            for p in parts[1:-1]:
                if p.startswith("AC-") and len(p) == 7 and p[3:].isdigit():
                    if 1 <= int(p[3:]) <= created:
                        referenced_existing += 1
    assert referenced_existing > 100


def test_run_replica_resets_and_returns_traces():
    steps = [{"m": "ALTA;Lucia;" + str(compute_control("ALTA;Lucia"))}, {"m": "PING;1"}, {"__raw__": "{"}]
    first = seqfuzz.run_replica(steps)
    second = seqfuzz.run_replica(steps)
    assert first == second
    assert first[0][0] == 201
    assert first[1] == (200, {"pong": True})
    assert first[2][0] == 400


def test_budget_never_exceeded_including_resets(tmp_path):
    calls = []
    mirror = replica_mirror_handler()

    def handler(request):
        calls.append(request.url.path)
        return mirror(request)

    camp = seqfuzz.generate_campaign(1, 5, 5, 3)
    report = seqfuzz.diff_campaign(make_client(tmp_path, handler), camp, budget=20)
    assert len(calls) <= 20
    assert report["requests_used"] == len(calls)
    assert report["stop_reason"] == "budget"
    assert report["divergences"] == []
    assert calls.count("/__reset") == report["sequences_run"]


def test_stops_on_transport_error(tmp_path):
    n = {"i": 0}

    def handler(request):
        n["i"] += 1
        if n["i"] == 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    camp = seqfuzz.generate_campaign(1, 0, 3, 0)
    report = seqfuzz.diff_campaign(make_client(tmp_path, handler), camp, budget=100)
    assert report["stop_reason"] == "transport_error"
    assert n["i"] == 3
    assert report["divergences"] == []


def test_stops_on_rate_limit(tmp_path):
    n = {"i": 0}

    def handler(request):
        n["i"] += 1
        return httpx.Response(429, json={"error": "rl"}, headers={"X-Frontier-Infra": "rate-limit"})

    report = seqfuzz.diff_campaign(make_client(tmp_path, handler), seqfuzz.generate_campaign(1, 2, 0, 0), budget=100)
    assert report["stop_reason"] == "infra_rate_limit"
    assert n["i"] == 1


def test_divergence_recorded_at_correct_step(tmp_path):
    mirror = replica_mirror_handler()
    n = {"msg": 0}

    def handler(request):
        if request.url.path == "/msg":
            n["msg"] += 1
            if n["msg"] == 2:
                return httpx.Response(400, json={"error": "E999", "mensaje": "x"})
        return mirror(request)

    seq = {"id": "sf_x_0", "hipotesis": "h", "steps": [{"m": "PING;1"}, {"m": "ALTA;Ana;5"}, {"m": "PING;2"}]}
    report = seqfuzz.diff_campaign(make_client(tmp_path, handler), [seq], budget=10)
    assert len(report["divergences"]) == 1
    d = report["divergences"][0]
    assert d["step"] == 2
    assert len(d["original"]) == 3 and len(d["replica"]) == 3
    assert d["signature"] == ["ALTA", 400, "E999", 400, "E202"]


def test_cluster_groups_by_signature_and_keeps_minimal_example():
    def div(sig, n):
        return {"signature": sig, "seq_id": f"s{n}", "steps": [{}] * n, "step": 1}

    divs = [div(["ALTA", 201, None, 400, "E202"], 5), div(["ALTA", 201, None, 400, "E202"], 2), div(["PING", 200, None, 400, "E302"], 3)]
    clusters = seqfuzz.cluster(divs)
    assert len(clusters) == 2
    top = clusters[0]
    assert top["count"] == 2
    assert top["example"]["seq_id"] == "s2"


def test_dry_run_makes_no_network(monkeypatch, capsys, tmp_path):
    def forbidden(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(LabClient, "send", forbidden)
    report = tmp_path / "r.json"
    rc = seqfuzz.main(["--seed", "1", "--dry-run", "--single", "2", "--short", "1", "--long", "1", "--report", str(report)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "sf_1_0" in out and "sf_1_3" in out
    assert not report.exists()


def test_cli_without_live_refuses_network(capsys):
    assert seqfuzz.main(["--seed", "1"]) == 2
    assert "--live" in capsys.readouterr().err
