"""Hermetic tests for the single-request input mutation exploration engine."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

import pytest

from lab.explore import observation
from lab.explore.observation import BudgetExceeded, Step, TargetStopped
from src import profile


class FakeTarget:
    """In-memory fake target tracking steps and budgets."""

    def __init__(self, budget: int = 1000) -> None:
        self.budget = budget
        self.used: int = 0
        self.history: List[Dict[str, Any]] = []

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        needed = 1 + len(steps)
        if self.used + needed > self.budget:
            raise BudgetExceeded("fake budget spent")
        self.used += needed
        self.history.append({"seq": seq, "note": note, "steps": steps})
        return [(200, {"ok": True})] * len(steps)

    def last_exp_ids(self) -> List[int]:
        return []


def test_no_literal_strings_in_inputs_source():
    source_path = Path(__file__).resolve().parents[1] / "lab" / "explore" / "inputs.py"
    assert source_path.exists(), "lab/explore/inputs.py must exist"
    source = source_path.read_text(encoding="utf-8")

    forbidden_literals = [
        "PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA", "HALT",
        "/msg", "/__reset", "/health",
    ]
    for lit in forbidden_literals:
        assert f'"{lit}"' not in source and f"'{lit}'" not in source, f"Found literal {lit!r} in inputs.py"


def test_determinism_per_seed():
    from lab.explore import inputs

    target1 = FakeTarget()
    obs1 = inputs.explore(target1, seed=42, n=20, budget=100)

    target2 = FakeTarget()
    obs2 = inputs.explore(target2, seed=42, n=20, budget=100)

    target3 = FakeTarget()
    obs3 = inputs.explore(target3, seed=99, n=20, budget=100)

    assert len(obs1) == len(obs2)
    assert [o.steps for o in obs1] == [o.steps for o in obs2]
    assert [o.note for o in obs1] == [o.note for o in obs2]
    assert [o.steps for o in obs1] != [o.steps for o in obs3]


def test_every_family_is_covered_for_sufficient_n():
    from lab.explore import inputs

    target = FakeTarget()
    obs = inputs.explore(target, seed=1, n=40, budget=200)
    cov = inputs.coverage(obs)

    expected_families = {"http", "auth", "body", "message"}
    assert expected_families.issubset(set(cov.keys()))
    for fam in expected_families:
        assert cov[fam] > 0, f"Family {fam} has 0 coverage"


def test_renamed_body_key_in_profile_changes_generated_bodies(tmp_path):
    from lab.explore import inputs

    base_data = profile.get()
    alt_data = copy.deepcopy(base_data)
    alt_data["http"]["message_field"] = "custom_payload_field"

    alt_file = tmp_path / "alt_profile.json"
    alt_file.write_text(__import__("json").dumps(alt_data), encoding="utf-8")

    profile.reload(alt_file)
    try:
        target = FakeTarget()
        obs = inputs.explore(target, seed=7, n=30, budget=200)
        body_steps = [s for o in obs for s in o.steps if "custom_payload_field" in s]
        assert len(body_steps) > 0, "Expected generated steps to use renamed body key"
    finally:
        profile.reload()


def test_budget_is_respected():
    from lab.explore import inputs

    target = FakeTarget(budget=15)
    obs = inputs.explore(target, seed=1, n=100, budget=15)
    assert target.used <= 15
    assert len(obs) > 0
