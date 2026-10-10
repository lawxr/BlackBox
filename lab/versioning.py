"""Versioned profile storage, manifest tracking, and active pointer resolution."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"


def publish_version(
    profile_data: Dict[str, Any],
    manifest_data: Dict[str, Any],
    profiles_dir: Optional[Path | str] = None,
    diff_text: str = "",
) -> Path:
    """Write versioned profile directory and point ACTIVE to it."""
    root = Path(profiles_dir or DEFAULT_PROFILES_DIR)
    root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version_dir = root / timestamp
    version_dir.mkdir(parents=True, exist_ok=True)

    (version_dir / "profile.json").write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
    (version_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    (version_dir / "diff.md").write_text(diff_text or "# Profile Version Diff\n", encoding="utf-8")

    active_file = root / "ACTIVE"
    active_file.write_text(f"{timestamp}\n", encoding="utf-8")

    return version_dir


def resolve_active_profile_path(profiles_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Resolve active profile path if profiles/ACTIVE exists."""
    root = Path(profiles_dir or DEFAULT_PROFILES_DIR)
    active_file = root / "ACTIVE"
    if active_file.exists():
        tag = active_file.read_text(encoding="utf-8").strip()
        candidate = root / tag / "profile.json"
        if candidate.exists():
            return candidate
    return None
