"""Hermetic tests for versioned profiles, manifests, and automated gates."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src import profile


def test_versioning_creates_version_dir_and_active_pointer(tmp_path):
    from lab import versioning

    base = profile.get()
    manifest = {
        "version": 2,
        "justifications": {"transfer_limit": [101, 102]},
    }

    profiles_root = tmp_path / "profiles"
    ver_dir = versioning.publish_version(
        profile_data=base,
        manifest_data=manifest,
        profiles_dir=profiles_root,
        diff_text="# Diff report",
    )

    assert ver_dir.exists()
    assert (ver_dir / "profile.json").exists()
    assert (ver_dir / "manifest.json").exists()
    assert (ver_dir / "diff.md").exists()

    active_file = profiles_root / "ACTIVE"
    assert active_file.exists()
    assert active_file.read_text(encoding="utf-8").strip() == ver_dir.name


def test_profile_resolution_respects_active_pointer(tmp_path, monkeypatch):
    from lab import versioning

    profiles_root = tmp_path / "profiles"
    custom_profile = dict(profile.get())
    custom_profile["transfer_limit"] = 12345

    ver_dir = versioning.publish_version(
        profile_data=custom_profile,
        manifest_data={"version": 3},
        profiles_dir=profiles_root,
    )

    # When BLACKBOX_PROFILE is not set and profiles/ACTIVE exists
    resolved = versioning.resolve_active_profile_path(profiles_dir=profiles_root)
    assert resolved == ver_dir / "profile.json"
