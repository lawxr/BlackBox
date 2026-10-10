"""Hermetic tests for generic numeric boundary binary-search exploration engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import pytest

from lab.explore.observation import BudgetExceeded, Step
from src import profile


class FakeBoundaryTarget:
    def __init__(self, transfer_limit: int = 50000, max_body_size: int = 32768) -> None:
        self.transfer_limit = transfer_limit
        self.max_body_size = max_body_size
        self.used = 0

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        self.used += 1 + len(steps)
        trace = []
        for s in steps:
            if "__raw__" in s:
                raw_len = len(s["__raw__"])
                if raw_len > self.max_body_size:
                    trace.append((413, {"error": "E101", "mensaje": "cuerpo demasiado grande"}))
                else:
                    trace.append((200, {"ok": True}))
                continue

            msg = s.get("m", "")
            if "TRANSFER" in msg:
                # parts: TRANSFER;SRC;DST;AMOUNT;CTRL
                parts = msg.split(";")
                amt = int(parts[3])
                if amt > self.transfer_limit:
                    trace.append((422, {"error": "E506", "mensaje": "límite excedido"}))
                else:
                    trace.append((200, {"status": "recieved"}))
            else:
                trace.append((200, {"ok": True}))
        return trace

    def last_exp_ids(self) -> List[int]:
        return []


def test_boundaries_binary_searches_transfer_limit():
    from lab.explore import boundaries

    fake = FakeBoundaryTarget(transfer_limit=35000)
    found_limit, obs = boundaries.search_transfer_limit(fake, low=1000, high=100000)

    assert found_limit == 35000
    assert len(obs) <= 18  # binary search finishes in ~17 steps
    assert fake.used < 100


def test_boundaries_binary_searches_body_size():
    from lab.explore import boundaries

    fake = FakeBoundaryTarget(max_body_size=16384)
    found_size, obs = boundaries.search_body_size(fake, low=1024, high=65536)

    assert found_size == 16384
    assert len(obs) > 0
    assert fake.used < 50
