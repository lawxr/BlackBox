"""Response shape and format inference engine."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lab.explore.observation import Observation


def infer_balance_format(observations: List[Observation]) -> str:
    """Infer whether balance in query responses is formatted as decimal string or integer."""
    decimal_count = 0
    int_count = 0

    for obs in observations:
        for status, body in obs.trace:
            if status == 200 and isinstance(body, dict):
                saldo = body.get("saldo")
                if saldo is not None:
                    if isinstance(saldo, str) and re.match(r"^\d+\.\d{2}$", saldo):
                        decimal_count += 1
                    elif isinstance(saldo, int) or (isinstance(saldo, str) and saldo.isdigit()):
                        int_count += 1

    if decimal_count > int_count:
        return "decimal"
    return "integer"


def infer_account_id_pattern(observations: List[Observation]) -> Optional[str]:
    """Infer regex/format pattern of account IDs from observed responses."""
    ids: List[str] = []
    for obs in observations:
        for status, body in obs.trace:
            if status in (200, 201) and isinstance(body, dict):
                aid = body.get("cuentaId") or body.get("cuenta_id")
                if isinstance(aid, str):
                    ids.append(aid)

    if not ids:
        return None
    # Check if all start with prefix and fixed digits (e.g. AC-0001)
    if all(re.match(r"^[A-Z]{2}-\d{4}$", aid) for aid in ids):
        prefix = ids[0][:3]
        return f"{prefix}{{n:04d}}"
    return None
