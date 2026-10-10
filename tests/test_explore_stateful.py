"""Hermetic tests for profile-derived stateful exploration engine and differential diff."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from lab.explore.observation import BudgetExceeded, Step, TargetStopped
from src import profile


class FakeStatefulTarget:
    """In-memory fake target tracking steps and budgets."""

    def __init__(self, budget: int = 1000, reject_alta: bool = False, diverge_at: Optional[int] = None) -> None:
        self.budget = budget
        self.used: int = 0
        self.reject_alta = reject_alta
        self.diverge_at = diverge_at
        self.history: List[Dict[str, Any]] = []

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        needed = 1 + len(steps)
        if self.used + needed > self.budget:
            raise BudgetExceeded("fake budget spent")
        self.used += needed
        self.history.append({"seq": seq, "note": note, "steps": steps})

        trace = []
        for i, step in enumerate(steps):
            if self.diverge_at is not None and i == self.diverge_at:
                trace.append((500, {"error": "diverged"}))
                continue
            raw_msg = step.get("m", "")
            if self.reject_alta and "ALTA" in raw_msg:
                trace.append((400, {"error": "E100"}))
            elif "ALTA" in raw_msg:
                trace.append((201, {"cuentaId": f"AC-{i+1:04d}"}))
            elif "CONSULTA" in raw_msg:
                trace.append((200, {"cuenta_id": "AC-0001", "saldo": "100.00"}))
            elif "DEPOSITO" in raw_msg:
                trace.append((200, {"ok": True, "op_id": f"OP-{i+1:04d}"}))
            elif "TRANSFER" in raw_msg:
                trace.append((200, {"ok": True, "op_id": f"OP-{i+1:04d}"}))
            elif "ANULA" in raw_msg:
                trace.append((200, {"ok": True}))
            else:
                trace.append((200, {"ok": True}))
        return trace

    def last_exp_ids(self) -> List[int]:
        return []


def test_no_literal_limits_in_code_and_amounts_adapt_to_profile(tmp_path):
    source_path = Path(__file__).resolve().parents[1] / "lab" / "explore" / "stateful.py"
    assert source_path.exists(), "lab/explore/stateful.py must exist"
    source = source_path.read_text(encoding="utf-8")

    # Hardcoded limits must not exist in source code
    assert "100000" not in source, "Found hardcoded 100000 limit in stateful.py"
    assert "50000" not in source, "Found hardcoded 50000 limit in stateful.py"

    from lab.explore import stateful

    base_data = profile.get()
    alt_data = copy.deepcopy(base_data)
    alt_data["transfer_limit"] = 25000

    alt_file = tmp_path / "alt_profile.json"
    alt_file.write_text(json.dumps(alt_data), encoding="utf-8")

    profile.reload(alt_file)
    try:
        target = FakeStatefulTarget()
        obs = stateful.explore(target, seed=42, n=30, budget=500)
        all_steps = [s for o in obs for s in o.steps]
        messages = [s.get("m", "") for s in all_steps if "m" in s]
        found_near_alt = any("24999" in m or "25000" in m or "25001" in m for m in messages)
        assert found_near_alt, "Expected amounts near profile transfer_limit (25000)"
    finally:
        profile.reload()


def test_determinism_per_seed():
    from lab.explore import stateful

    target1 = FakeStatefulTarget()
    obs1 = stateful.explore(target1, seed=42, n=15, budget=300)

    target2 = FakeStatefulTarget()
    obs2 = stateful.explore(target2, seed=42, n=15, budget=300)

    target3 = FakeStatefulTarget()
    obs3 = stateful.explore(target3, seed=99, n=15, budget=300)

    assert len(obs1) == len(obs2)
    assert [o.steps for o in obs1] == [o.steps for o in obs2]
    assert [o.steps for o in obs1] != [o.steps for o in obs3]


def test_model_follows_target_rejects_alta():
    from lab.explore import stateful

    model = stateful.StateModel()
    prof = profile.get()

    # Successful creation
    step_alta = {"m": "ALTA;Alice;88"}
    model.update(step_alta, 201, {"cuentaId": "AC-0001"}, prof)
    assert len(model.accounts) == 1
    assert "AC-0001" in model.accounts

    # Rejected creation
    step_alta_bad = {"m": "ALTA;Bob;88"}
    model.update(step_alta_bad, 400, {"error": "E100"}, prof)
    assert len(model.accounts) == 1
    assert "Bob" not in model.accounts


def test_budget_is_never_exceeded_resets_included():
    from lab.explore import stateful

    target = FakeStatefulTarget(budget=25)
    obs = stateful.explore(target, seed=1, n=50, budget=25)
    assert target.used <= 25
    assert len(obs) > 0


def test_stop_on_transport_error():
    from lab.explore import stateful

    class CrashingTarget(FakeStatefulTarget):
        def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
            raise TargetStopped("simulated network failure")

    target = CrashingTarget()
    obs = stateful.explore(target, seed=1, n=10, budget=100)
    assert len(obs) == 0


def test_differential_finds_planted_divergence_at_correct_step():
    from lab.explore import diff, stateful

    target_normal = FakeStatefulTarget()
    obs = stateful.explore(target_normal, seed=42, n=5, budget=100)
    assert len(obs) > 0

    # Target divergent at step 2 of every sequence
    target_divergent = FakeStatefulTarget(diverge_at=2)
    report = diff.differential(obs, target_divergent)

    assert report["divergent_count"] > 0
    first_cluster = list(report["clusters"].values())[0]
    assert first_cluster["divergent_step"] == 2
    assert first_cluster["ref_status"] == 500
