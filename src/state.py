from __future__ import annotations
import threading
from typing import Dict, Any

from src import profile


class LedgerState:
    """In-memory EFSM ledger representing the service's mutable state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Reset the ledger back to the deterministic initial state."""
        with self._lock:
            self.account_counter: int = 0
            self.operation_counter: int = 0
            self.accounts: Dict[str, Dict[str, Any]] = {}
            self.operations: Dict[str, Dict[str, Any]] = {}

    def next_account_id(self) -> str:
        self.account_counter += 1
        return profile.get()["id_formats"]["account"].format(n=self.account_counter)

    def next_operation_id(self) -> str:
        self.operation_counter += 1
        return profile.get()["id_formats"]["operation"].format(n=self.operation_counter)


# Global single-process state instance
ledger = LedgerState()
