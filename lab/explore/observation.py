"""Shared contract between exploration engines, targets and the learner."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

# A step is what a target sends: {"m": "..."} or another JSON body, or
# {"__raw__": "..."} for a non-JSON body. Optional "__method__"/"__path__"/
# "__headers__" keys override the default POST /msg request.
Step = Dict[str, Any]


@dataclass
class Observation:
    engine: str
    seq: str
    steps: List[Step]
    trace: List[tuple]  # [(status, body)] aligned with steps
    note: str = ""  # human-readable reason for this sequence (logged as hipotesis)
    exp_ids: List[int] = field(default_factory=list)  # filled for live targets


class BudgetExceeded(Exception):
    """The target refused to send because the request budget is spent."""


class TargetStopped(Exception):
    """The target stopped on transport error or rate limit; results so far are valid."""


class Target(Protocol):
    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        """Reset, send every step in order, return [(status, body)].

        May raise BudgetExceeded before sending anything, or TargetStopped.
        """

    def last_exp_ids(self) -> List[int]:
        """Experiment ids of the last `run` (empty for non-live targets)."""


def first_divergence(a: List[tuple], b: List[tuple]) -> Optional[int]:
    """Index of the first step where two traces differ under the evaluator rule."""
    from lab.runner import json_equal

    for i, (x, y) in enumerate(zip(a, b)):
        if x[0] != y[0] or not json_equal(x[1], y[1]):
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return None
