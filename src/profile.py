"""Load and validate the protocol profile (single source of truth for protocol literals).

`load_profile` is the only place that resolves and reads a profile file:
explicit path, then the BLACKBOX_PROFILE environment variable, then the default
src/profile.json. `reload()` makes the loaded profile the active one.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

DEFAULT_PATH = Path(__file__).resolve().with_name("profile.json")
ENV_VAR = "BLACKBOX_PROFILE"

HANDLER_KINDS = ("pong", "create_account", "query_account", "credit", "transfer", "annul", "refuse")
CHECK_KINDS = ("amount", "distinct", "account_exists", "operation_exists",
               "sufficient_balance", "max_amount")
ROUTE_KINDS = ("health", "reset", "message")
REQUIRED_KEYS = ("error_keys", "errors", "http", "message", "amount_pattern",
                 "transfer_limit", "id_formats", "commands")


class ProfileError(ValueError):
    """Raised when a profile is missing data or names an unsupported behavior."""


_current: Dict[str, Any] = {}


def resolve_path(path: Optional[Union[str, Path]] = None) -> Path:
    """Explicit path, then $BLACKBOX_PROFILE, then profiles/ACTIVE, then default."""
    if path:
        return Path(path)
    if os.environ.get(ENV_VAR):
        return Path(os.environ[ENV_VAR])
    active_file = Path(__file__).resolve().parents[1] / "profiles" / "ACTIVE"
    if active_file.exists():
        tag = active_file.read_text(encoding="utf-8").strip()
        candidate = active_file.parent / tag / "profile.json"
        if candidate.exists():
            return candidate
    return DEFAULT_PATH


def _validate(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ProfileError("profile must be a JSON object")
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ProfileError(f"profile is missing required top-level keys: {', '.join(missing)}")
    errors = data["errors"]

    def need_error(code: str, where: str) -> None:
        if code not in errors:
            raise ProfileError(f"{where} references undefined error {code!r}")

    for route in data["http"]["routes"]:
        if route["kind"] not in ROUTE_KINDS:
            raise ProfileError(f"unsupported route kind {route['kind']!r}")
    for key in ("unknown_route_error", "invalid_json_error", "missing_message_error"):
        need_error(data["http"][key], f"http.{key}")
    need_error(data["http"]["auth"]["error"], "http.auth")
    for stage in data["message"]["precedence"]:
        if "error" in stage:
            need_error(stage["error"], f"stage {stage['stage']}")
    for name, cmd in data["commands"].items():
        if cmd.get("kind") not in HANDLER_KINDS:
            raise ProfileError(f"command {name}: unsupported handler kind {cmd.get('kind')!r}")
        if cmd["kind"] == "refuse":
            need_error(cmd["error"], f"command {name}")
        for check in cmd.get("checks", []):
            if check["check"] not in CHECK_KINDS:
                raise ProfileError(f"command {name}: unsupported check {check['check']!r}")
            need_error(check["error"], f"command {name}")
    re.compile(data["amount_pattern"])
    if not isinstance(data["transfer_limit"], int):
        raise ProfileError("transfer_limit must be an integer")


def load_profile(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Read and validate a profile; raises ProfileError with the file path on failure."""
    resolved = resolve_path(path)
    try:
        with resolved.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ProfileError(f"cannot read profile {resolved}: {exc}") from exc
    try:
        _validate(data)
    except ProfileError as exc:
        raise ProfileError(f"{resolved}: {exc}") from exc
    except (KeyError, TypeError, re.error) as exc:
        raise ProfileError(f"{resolved}: malformed profile ({exc!r})") from exc
    return data


def reload(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load a profile and make it active; the previous one stays active on error."""
    global _current
    _current = load_profile(path)
    return _current


def get() -> Dict[str, Any]:
    return _current or reload()
