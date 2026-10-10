from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from lab.client import LabClient, TransportError


@dataclass
class SequenceResult:
    matched: bool
    total_steps: int
    passed_steps: int
    mismatch_step: Optional[int] = None
    stop_reason: str = "completed"
    error_detail: Optional[str] = None


def load_ejemplos(path: Path | str = "pruebas/ejemplos.jsonl") -> List[Dict[str, Any]]:
    """Load reference examples recorded from the morning service."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def json_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON responses where object key order is irrelevant but array order matters."""
    if type(actual) != type(expected):
        return False
    if isinstance(actual, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(json_equal(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list):
        if len(actual) != len(expected):
            return False
        return all(json_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


def compare_sequence(
    client: LabClient,
    steps: List[Dict[str, Any]],
    seq_id: str,
) -> SequenceResult:
    """Execute sequence after reset and verify step-by-step equivalence."""
    total_steps = len(steps)
    passed_steps = 0

    def _fail(reason: str, detail: Optional[str] = None, step: Optional[int] = None) -> SequenceResult:
        return SequenceResult(
            matched=False,
            total_steps=total_steps,
            passed_steps=passed_steps,
            mismatch_step=step,
            stop_reason=reason,
            error_detail=detail,
        )

    # 1. Reset state
    try:
        reset_res = client.reset(seq=seq_id, hipotesis=f"Reset para secuencia {seq_id}")
    except TransportError as te:
        return _fail("transport_error", str(te))

    # Check if reset hit rate-limit
    if reset_res.get("status") == 429:
        return _fail("infra_rate_limit", "Rate limit hit on reset")

    # 2. Iterate steps
    for step in steps:
        step_n = step.get("n", passed_steps + 1)
        req_payload = step.get("request", {})
        expected_status = step.get("status", 200)
        expected_response = step.get("response")

        try:
            res = client.send(
                method="POST",
                path="/msg",
                seq=seq_id,
                hipotesis=f"Paso {step_n} de secuencia {seq_id}",
                payload=req_payload,
            )
        except TransportError as te:
            return _fail("transport_error", str(te), step_n)

        # Check rate-limit
        if res.get("status") == 429:
            return _fail("infra_rate_limit", "Rate limit hit during step", step_n)

        actual_status = res.get("status")
        actual_response = res.get("response")

        status_ok = actual_status == expected_status
        body_ok = json_equal(actual_response, expected_response)

        if not (status_ok and body_ok):
            return _fail(
                "mismatch",
                f"Expected {expected_status} {expected_response}, got {actual_status} {actual_response}",
                step_n,
            )

        passed_steps += 1

    return SequenceResult(
        matched=True,
        total_steps=total_steps,
        passed_steps=passed_steps,
        stop_reason="completed",
    )
