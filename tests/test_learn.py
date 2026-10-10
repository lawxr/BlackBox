"""Tests for lab.learn and lab/probes.json.

Hermetic tests: no network, in-process replica served through httpx MockTransport.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import httpx
import pytest

from lab import learn
from src import profile
from src.main import app

ENGLISH_ERRORS = {
    "E001": "unauthorized",
    "E100": "invalid json",
    "E102": "missing m",
    "E103": "missing control",
    "E104": "empty segment",
    "E201": "control malformed",
    "E202": "control invalid",
    "E301": "unknown command",
    "E302": "invalid arity",
    "E303": "invalid amount",
    "E304": "same source and destination",
    "E401": "account does not exist",
    "E402": "operation does not exist",
    "E404": "unknown route",
    "E506": "limit exceeded",
    "E507": "insufficient balance",
    "E520": "destructive operation",
}


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch, tmp_path):
    token = "test-learn-token"
    monkeypatch.setenv("TEAM_TOKEN", token)
    monkeypatch.setenv("USER_TOKEN", token)
    monkeypatch.setenv("TOKEN", "")

    from src import config, main
    monkeypatch.setattr(config, "TEAM_TOKEN", token)
    monkeypatch.setattr(config, "USER_TOKEN", token)
    monkeypatch.setattr(main, "TEAM_TOKEN", token)

    from lab import client
    monkeypatch.setattr(client, "EXPERIMENTS_PATH", tmp_path / "experimentos.jsonl")
    monkeypatch.setattr(client, "AUDIT_PATH", tmp_path / "audit.jsonl")
    main.ledger.reset()



def make_stand_in_transport(
    error_translations: Dict[str, str] | None = None,
    extra_suggestion: str | None = None,
    fail_on_request: bool = False,
    request_log: List[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """MockTransport wrapping the ASGI replica with customizable behavior."""
    from fastapi.testclient import TestClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request_log is not None:
            request_log.append(request)
        if fail_on_request:
            raise httpx.ConnectError("Simulated network failure")

        with TestClient(app) as tc:
            headers = dict(request.headers)
            path = request.url.path
            response = tc.request(
                method=request.method,
                url=path,
                headers=headers,
                content=request.content,
            )

            # Inspect and potentially transform response body
            if response.status_code >= 400 and (error_translations or extra_suggestion):
                try:
                    body = response.json()
                except Exception:
                    body = None

                if isinstance(body, dict):
                    code = body.get("error")
                    if code and error_translations and code in error_translations:
                        body["mensaje"] = error_translations[code]
                    if extra_suggestion and code == "E301":
                        body["sugerencia"] = extra_suggestion

                    new_content = json.dumps(body, ensure_ascii=False).encode("utf-8")
                    res_headers = dict(response.headers)
                    res_headers["content-length"] = str(len(new_content))
                    return httpx.Response(
                        status_code=response.status_code,
                        headers=res_headers,
                        content=new_content,
                        request=request,
                    )

            return httpx.Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=response.content,
                request=request,
            )

    return httpx.MockTransport(handler)


def test_plan_mode_makes_no_requests(capsys):
    """Plan mode must make no network requests and print probes + budget."""
    requests: List[httpx.Request] = []
    transport = make_stand_in_transport(request_log=requests)

    ret = learn.main(["--plan"], transport=transport)
    assert ret == 0
    assert len(requests) == 0

    out = capsys.readouterr().out
    assert "probes" in out.lower()
    assert "budget" in out.lower()


def test_budget_is_never_exceeded(tmp_path):
    """Execution must strictly respect the budget limit."""
    requests: List[httpx.Request] = []
    transport = make_stand_in_transport(request_log=requests)

    budget = 5
    candidate_path = tmp_path / "candidate.json"
    diff_path = tmp_path / "diff.md"

    ret = learn.main(
        [
            "--live",
            "--budget",
            str(budget),
            "--candidate-out",
            str(candidate_path),
            "--diff-out",
            str(diff_path),
        ],
        transport=transport,
    )
    assert ret == 0
    assert len(requests) <= budget


def test_stop_on_transport_error(tmp_path):
    """TransportError must be handled cleanly without crashing."""
    transport = make_stand_in_transport(fail_on_request=True)

    candidate_path = tmp_path / "candidate.json"
    diff_path = tmp_path / "diff.md"

    ret = learn.main(
        [
            "--live",
            "--budget",
            "10",
            "--candidate-out",
            str(candidate_path),
            "--diff-out",
            str(diff_path),
        ],
        transport=transport,
    )
    # Exits cleanly reporting the stop
    assert ret == 0


def test_english_stand_in_produces_matching_candidate(tmp_path):
    """A stand-in with English messages produces a candidate matching the stand-in on all probes."""
    # Build complete English dictionary for all 17 protocol errors
    english_errors = {
        "E001": "unauthorized",
        "E100": "invalid json",
        "E102": "missing m",
        "E103": "missing control",
        "E104": "empty segment",
        "E201": "control malformed",
        "E202": "control invalid",
        "E301": "unknown command",
        "E302": "invalid arity",
        "E303": "invalid amount",
        "E304": "same source and destination",
        "E401": "account does not exist",
        "E402": "operation does not exist",
        "E404": "unknown route",
        "E506": "limit exceeded",
        "E507": "insufficient balance",
        "E520": "destructive operation",
    }
    transport = make_stand_in_transport(error_translations=english_errors)

    candidate_path = tmp_path / "candidate.json"
    diff_path = tmp_path / "diff.md"

    ret = learn.main(
        [
            "--live",
            "--budget",
            "200",
            "--candidate-out",
            str(candidate_path),
            "--diff-out",
            str(diff_path),
        ],
        transport=transport,
    )
    assert ret == 0
    assert candidate_path.exists()

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    for code, eng_msg in english_errors.items():
        assert candidate["errors"][code]["mensaje"] == eng_msg

    # Reload replica with candidate profile
    profile.reload(candidate_path)
    try:
        # Re-probe replica through check mode to verify 100% match
        check_ret = learn.main(["--check"], transport=transport)
        assert check_ret == 0
    finally:
        profile.reload()  # restore default


def test_stand_in_with_extra_command_produces_needs_review(tmp_path):
    """An unclassifiable suggested command is listed under needs review."""
    transport = make_stand_in_transport(extra_suggestion="NOVEDAD")

    candidate_path = tmp_path / "candidate.json"
    diff_path = tmp_path / "diff.md"

    ret = learn.main(
        [
            "--live",
            "--budget",
            "100",
            "--candidate-out",
            str(candidate_path),
            "--diff-out",
            str(diff_path),
        ],
        transport=transport,
    )
    assert ret == 0

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert "needs_review" in candidate
    assert "NOVEDAD" in candidate["needs_review"]

    diff_content = diff_path.read_text(encoding="utf-8")
    assert "NOVEDAD" in diff_content
    assert "needs review" in diff_content.lower()


def test_check_mode_reports_drift():
    """Check mode returns 1 when drift is detected."""
    # Drifting stand-in (different message for E303)
    transport = make_stand_in_transport(error_translations={"E303": "drifted message"})
    ret = learn.main(["--check"], transport=transport)
    assert ret == 1
