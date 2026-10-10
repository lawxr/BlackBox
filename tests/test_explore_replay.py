"""Hermetic tests for the historical sequence replay engine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from lab.explore.observation import Step
from lab.explore.replay import RecordedSegment, extract_clean_segments, replay_segments


class MockTarget:
    def __init__(self, responses: List[tuple]) -> None:
        self.responses = responses
        self.calls: List[tuple] = []

    def last_exp_ids(self) -> List[int]:
        return [101]

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        self.calls.append((steps, seq, note))
        return self.responses[: len(steps)]


def test_extract_clean_segments(tmp_path):
    log_file = tmp_path / "test_exp.jsonl"
    lines = [
        # Segment 1: clean
        {"seq": "seq_1", "hipotesis": "Reset", "request": {}, "status": 200, "response": {"ok": True}},
        {"seq": "seq_1", "hipotesis": "Step 1", "request": {"m": "PING;val;42"}, "status": 200, "response": {"ok": True, "eco": "val"}},
        # Segment 2: contaminated by seq_3
        {"seq": "seq_2", "hipotesis": "Reset", "request": {}, "status": 200, "response": {"ok": True}},
        {"seq": "seq_3", "hipotesis": "Interrupt", "request": {"m": "PING"}, "status": 400, "response": {"error": "E103"}},
        {"seq": "seq_2", "hipotesis": "Step 1", "request": {"m": "PING;val;42"}, "status": 200, "response": {"ok": True}},
    ]
    log_file.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")

    segments = extract_clean_segments(log_file)
    assert len(segments) == 1
    assert segments[0].seq == "seq_1"


def test_replay_segments_clusters_divergences():
    seg = RecordedSegment(
        seq="v1_run",
        start_line=1,
        entries=[
            {"seq": "v1_run", "hipotesis": "Reset", "request": {}, "status": 200, "response": {"ok": True}},
            # Then response was 200
            {"seq": "v1_run", "hipotesis": "Step 1", "request": {"m": "TRANSFER;AC-0001;AC-0002;60000;42"}, "status": 200, "response": {"ok": True}},
        ],
    )
    # Now target returns 422 E506 (limit exceeded in v2)
    mock_target = MockTarget(responses=[(422, {"error": "E506", "mensaje": "límite superado"})])

    obs, summary = replay_segments(mock_target, [seg], budget=10)
    assert len(obs) == 1
    assert summary["total_segments"] == 1
    assert summary["divergent_segments"] == 1
    assert "TRANSFER:200->422" in summary["clusters"]
    assert summary["clusters"]["TRANSFER:200->422"]["count"] == 1
