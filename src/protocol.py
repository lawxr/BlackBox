from __future__ import annotations
from typing import Tuple, Any, Dict
from src.state import ledger


def parse_message(raw_msg: str) -> list[str]:
    """Split raw message by semicolon."""
    return raw_msg.split(";")


def dispatch_command(parts: list[str]) -> Tuple[int, Dict[str, Any]]:
    """Dispatch command to corresponding handler.

    Returns:
        Tuple of (http_status_code, response_body_dict)
    """
    if not parts or not parts[0]:
        return 400, {"error": "E301"}

    cmd = parts[0].upper()
    if cmd == "PING":
        return 200, {"pong": True}

    # Placeholder for commands discovered in experiments
    return 400, {"error": "E301"}
