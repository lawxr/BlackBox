"""Hermetic tests for candidate profile synthesis engine with 2-observation consensus."""
from __future__ import annotations

import copy
from typing import Any, Dict, List
import pytest

from lab.explore.observation import Observation
from src import profile


def test_synthesize_adds_new_error_with_two_consistent_observations():
    from lab import synthesize

    base_profile = profile.get()
    obs1 = Observation(
        engine="inputs",
        seq="input_0042",
        steps=[{"__raw__": "A" * 65536}],
        trace=[(413, {"error": "E101", "mensaje": "cuerpo demasiado grande"})],
        exp_ids=[2007],
    )
    obs2 = Observation(
        engine="inputs",
        seq="input_0050",
        steps=[{"__raw__": "A" * 65536}],
        trace=[(413, {"error": "E101", "mensaje": "cuerpo demasiado grande"})],
        exp_ids=[2023],
    )

    candidate, manifest = synthesize.synthesize_profile(base_profile, [obs1, obs2])

    assert "E101" in candidate["errors"]
    assert candidate["errors"]["E101"]["status"] == 413
    assert candidate["errors"]["E101"]["mensaje"] == "cuerpo demasiado grande"
    assert "errors.E101" in manifest["justifications"]
    assert 2007 in manifest["justifications"]["errors.E101"]
    assert 2023 in manifest["justifications"]["errors.E101"]


def test_synthesize_rejects_single_observation_without_consensus():
    from lab import synthesize

    base_profile = profile.get()
    # Only 1 observation: does not meet >= 2 threshold
    obs1 = Observation(
        engine="inputs",
        seq="input_0042",
        steps=[{"__raw__": "A" * 65536}],
        trace=[(413, {"error": "E199", "mensaje": "rare error"})],
        exp_ids=[2007],
    )

    candidate, manifest = synthesize.synthesize_profile(base_profile, [obs1])

    assert "E199" not in candidate["errors"]
    assert "E199" in candidate.get("needs_review", [])


def test_synthesize_updates_transfer_limit_and_shape():
    from lab import synthesize

    base_profile = copy.deepcopy(profile.get())
    base_profile["transfer_limit"] = 100000

    obs1 = Observation(
        engine="boundaries",
        seq="b1",
        steps=[{"m": "TRANSFER;AC-0001;AC-0002;50001;56"}],
        trace=[(422, {"error": "E506", "mensaje": "límite excedido"})],
        exp_ids=[101],
    )
    obs2 = Observation(
        engine="boundaries",
        seq="b2",
        steps=[{"m": "TRANSFER;AC-0001;AC-0002;50000;59"}],
        trace=[(200, {"status": "recieved"})],
        exp_ids=[102],
    )

    candidate, manifest = synthesize.synthesize_profile(
        base_profile,
        [obs1, obs2],
        inferred_boundaries={"transfer_limit": 50000},
        inferred_shapes={"balance_format": "decimal"},
        inferred_precedence={"TRANSFER": ["max_amount", "sufficient_balance"]},
    )

    assert candidate["transfer_limit"] == 50000
    assert candidate["commands"]["CONSULTA"]["balance_format"] == "decimal"
    transfer_checks = [c["check"] for c in candidate["commands"]["TRANSFER"]["checks"]]
    assert transfer_checks.index("max_amount") < transfer_checks.index("sufficient_balance")
