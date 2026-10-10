"""Hermetic tests for check precedence exploration engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import pytest

from lab.explore.observation import Step
from src import profile


class FakePrecedenceTarget:
    def __init__(self, check_order: List[str]) -> None:
        # e.g. ["max_amount", "sufficient_balance"]
        self.check_order = check_order

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        trace = []
        for s in steps:
            msg = s.get("m", "")
            if "TRANSFER" in msg:
                # violating both max_amount (amt=60000 > limit 50000) and sufficient_balance (amt > balance 1000)
                # Returns the first error according to check_order
                first_check = self.check_order[0]
                if first_check == "max_amount":
                    trace.append((422, {"error": "E506", "mensaje": "límite excedido"}))
                elif first_check == "sufficient_balance":
                    trace.append((422, {"error": "E507", "mensaje": "saldo insuficiente"}))
                else:
                    trace.append((200, {"ok": True}))
            else:
                trace.append((200, {"ok": True}))
        return trace

    def last_exp_ids(self) -> List[int]:
        return []


def test_precedence_discovers_order_of_transfer_checks():
    from lab.explore import precedence

    fake_v2 = FakePrecedenceTarget(check_order=["max_amount", "sufficient_balance"])
    order_v2, obs_v2 = precedence.determine_transfer_checks_order(fake_v2)
    assert order_v2 == ["max_amount", "sufficient_balance"]

    fake_v1 = FakePrecedenceTarget(check_order=["sufficient_balance", "max_amount"])
    order_v1, obs_v1 = precedence.determine_transfer_checks_order(fake_v1)
    assert order_v1 == ["sufficient_balance", "max_amount"]
