"""Hermetic tests for response shape and format inference engine."""
from __future__ import annotations

from typing import Any, Dict, List
import pytest

from lab.explore.observation import Observation


def test_shapes_infers_decimal_vs_integer_balance():
    from lab.explore import shapes

    # Observations returning decimal string saldo
    obs_decimal = [
        Observation(
            engine="test",
            seq="seq1",
            steps=[{"m": "CONSULTA;AC-0001;14"}],
            trace=[(200, {"cuenta_id": "AC-0001", "saldo": "150.00"})],
        ),
        Observation(
            engine="test",
            seq="seq2",
            steps=[{"m": "CONSULTA;AC-0002;11"}],
            trace=[(200, {"cuenta_id": "AC-0002", "saldo": "0.00"})],
        ),
    ]
    inferred = shapes.infer_balance_format(obs_decimal)
    assert inferred == "decimal"

    # Observations returning integer saldo
    obs_int = [
        Observation(
            engine="test",
            seq="seq1",
            steps=[{"m": "CONSULTA;AC-0001;14"}],
            trace=[(200, {"cuenta_id": "AC-0001", "saldo": 150})],
        ),
        Observation(
            engine="test",
            seq="seq2",
            steps=[{"m": "CONSULTA;AC-0002;11"}],
            trace=[(200, {"cuenta_id": "AC-0002", "saldo": 0})],
        ),
    ]
    inferred_int = shapes.infer_balance_format(obs_int)
    assert inferred_int == "integer"
