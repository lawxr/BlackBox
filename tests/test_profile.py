"""The replica is data-driven: protocol literals come from src/profile.json."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "local-profile-test-token"
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "src" / "profile.json"


@pytest.fixture
def app_with_profile(monkeypatch, tmp_path):
    """Yield a factory: given a profile dict, return a TestClient using it."""
    monkeypatch.setenv("TEAM_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("USER_TOKEN", "")
    monkeypatch.setenv("TOKEN", "")
    with monkeypatch.context() as ctx:
        ctx.chdir(tmp_path)
        from src import main, profile
    monkeypatch.setattr(main, "TEAM_TOKEN", TEST_TOKEN)

    def make(data):
        path = tmp_path / "profile.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("BLACKBOX_PROFILE", str(path))
        profile.reload()
        main.ledger.reset()
        return TestClient(main.app)

    yield make
    monkeypatch.delenv("BLACKBOX_PROFILE", raising=False)
    profile.reload()
    main.ledger.reset()


def _default():
    return json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))


def test_default_profile_is_the_loaded_one(app_with_profile):
    tc = app_with_profile(_default())
    r = tc.post("/msg", headers=AUTH, json={"m": "CONSULTA;AC-0001;14"})
    assert (r.status_code, r.json()) == (404, {"error": "E401", "mensaje": "cuenta inexistente"})


def test_profile_edits_change_replica_output_without_code_edits(app_with_profile):
    data = _default()
    data["errors"]["E401"]["mensaje"] = "account not found"
    data["errors"]["E401"]["status"] = 410
    body = data["commands"]["ALTA"]["response"]["body"]
    body["accountId"] = body.pop("cuentaId")
    tc = app_with_profile(data)

    r = tc.post("/msg", headers=AUTH, json={"m": "CONSULTA;AC-0001;14"})
    assert (r.status_code, r.json()) == (410, {"error": "E401", "mensaje": "account not found"})
    r = tc.post("/msg", headers=AUTH, json={"m": "ALTA;Lucia;82"})
    assert (r.status_code, r.json()) == (201, {"accountId": "AC-0001"})


def test_profile_edits_reach_auth_and_routes(app_with_profile):
    data = _default()
    data["errors"]["E001"]["mensaje"] = "unauthorized"
    data["errors"]["E404"]["status"] = 418
    tc = app_with_profile(data)
    r = tc.post("/msg", json={"m": "PING;64"})
    assert (r.status_code, r.json()) == (401, {"error": "E001", "mensaje": "unauthorized"})
    r = tc.get("/nope", headers=AUTH)
    assert r.status_code == 418


def test_transfer_limit_and_amount_rule_come_from_profile(app_with_profile):
    from src.protocol import compute_control

    data = _default()
    data["transfer_limit"] = 10
    data["amount_pattern"] = "[1-9][0-9]{0,2}"
    tc = app_with_profile(data)

    def m(payload):
        return {"m": f"{payload};{compute_control(payload)}"}

    tc.post("/msg", headers=AUTH, json=m("ALTA;A"))
    tc.post("/msg", headers=AUTH, json=m("ALTA;B"))
    r = tc.post("/msg", headers=AUTH, json=m("DEPOSITO;AC-0001;1000"))
    assert r.json()["error"] == "E303"
    tc.post("/msg", headers=AUTH, json=m("DEPOSITO;AC-0001;500"))
    r = tc.post("/msg", headers=AUTH, json=m("TRANSFER;AC-0001;AC-0002;11"))
    assert r.json()["error"] == "E506"


def test_unknown_profile_handler_kind_is_rejected(app_with_profile):
    from src import profile

    data = _default()
    data["commands"]["ALTA"]["kind"] = "teleport"
    with pytest.raises(profile.ProfileError, match="teleport"):
        app_with_profile(data)


def test_load_profile_precedence_explicit_then_env_then_default(monkeypatch, tmp_path):
    from src import profile

    env_file = tmp_path / "env.json"
    explicit_file = tmp_path / "explicit.json"
    for f, limit in ((env_file, 1), (explicit_file, 2)):
        data = _default()
        data["transfer_limit"] = limit
        f.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.delenv("BLACKBOX_PROFILE", raising=False)
    assert profile.load_profile()["transfer_limit"] == _default()["transfer_limit"]
    monkeypatch.setenv("BLACKBOX_PROFILE", str(env_file))
    assert profile.load_profile()["transfer_limit"] == 1
    assert profile.load_profile(explicit_file)["transfer_limit"] == 2


def test_load_profile_names_missing_top_level_key(tmp_path):
    from src import profile

    data = _default()
    del data["commands"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(profile.ProfileError, match="missing required top-level keys: commands"):
        profile.load_profile(bad)
