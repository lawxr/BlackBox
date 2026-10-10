"""Protocol error definitions and error precedence mapping."""
from typing import Dict, Any


def make_error(code: str, details: str = "") -> Dict[str, Any]:
    """Format standardized protocol error body."""
    res = {"error": code}
    if details:
        res["details"] = details
    return res
