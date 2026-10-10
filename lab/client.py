from __future__ import annotations
import atexit
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from src.config import ORIGINAL_URL, TEAM_TOKEN, USER_TOKEN

EXPERIMENTS_PATH = Path("experimentos.jsonl")
AUDIT_PATH = Path("audit.jsonl")


class TransportError(Exception):
    """Raised when an HTTP transport or network timeout error occurs."""
    pass


class LabLockError(RuntimeError):
    """Raised when another LabClient already writes to the same experiments log."""
    pass


class LabClient:
    """HTTP client for interacting with the original service and recording experiments."""

    def __init__(
        self,
        base_url: str = ORIGINAL_URL,
        token: str = USER_TOKEN or TEAM_TOKEN,
        rate_limit_delay: float = 0.15,  # ~6-7 req/s safe throttle
        experiments_path: Path = EXPERIMENTS_PATH,
        audit_path: Path = AUDIT_PATH,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.rate_limit_delay = rate_limit_delay
        self.experiments_path = Path(experiments_path)
        self.audit_path = Path(audit_path)
        self.transport = transport
        self._last_req_time: float = 0.0
        self._lock_path = self.experiments_path.with_name(self.experiments_path.name + ".lock")
        self._locked = False
        self._acquire_lock()
        self._next_id: int = self._get_next_experiment_id()

    def _acquire_lock(self) -> None:
        """Single writer per log: create the lock file atomically or fail fast."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise LabLockError(
                f"{self._lock_path} exists: another LabClient is writing to "
                f"{self.experiments_path}. Stop it, or delete the stale lock if no writer runs."
            ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n")
        self._locked = True
        atexit.register(self.close)

    def close(self) -> None:
        """Release the writer lock (idempotent)."""
        if not self._locked:
            return
        self._locked = False
        atexit.unregister(self.close)
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "LabClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _get_next_experiment_id(self) -> int:
        """Next id = max recorded id + 1 (robust to duplicates and gaps)."""
        if not self.experiments_path.exists():
            return 1
        max_id = 0
        with open(self.experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec_id = json.loads(line).get("id")
                except (ValueError, AttributeError):
                    continue
                if isinstance(rec_id, int) and rec_id > max_id:
                    max_id = rec_id
        return max_id + 1

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_req_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_req_time = time.time()

    def send(
        self,
        method: str,
        path: str,
        seq: str,
        hipotesis: str,
        payload: Optional[Dict[str, Any]] = None,
        conclusion: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        raw_content: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        self._throttle()

        # Pre-send verification: ensure destination directories exist and paths are writable
        self.experiments_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

        url = f"{self.base_url}{path}"
        req_headers: Dict[str, str] = {}
        if headers is not None:
            req_headers = dict(headers)
        elif self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"

        record_id = self._next_id
        self._next_id += 1

        start_time = time.perf_counter()
        resp: Optional[httpx.Response] = None
        err_kind: Optional[str] = None
        err_msg: str = ""

        try:
            with httpx.Client(timeout=10.0, transport=self.transport) as client:
                if raw_content is not None:
                    resp = client.request(method, url, content=raw_content, headers=req_headers)
                else:
                    resp = client.request(method, url, json=payload, headers=req_headers)
        except httpx.TimeoutException as te:
            err_kind = "timeout"
            err_msg = str(te)
        except httpx.RequestError as re:
            err_kind = "transport_error"
            err_msg = str(re)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Handle uncertain transport outcomes (timeout / transport error)
        if resp is None:
            audit_entry = {
                "id": record_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": method,
                "path": path,
                "latency_ms": latency_ms,
                "status": None,
                "error": err_kind,
                "x_infra": None,
            }
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

            experiment_entry = {
                "id": record_id,
                "seq": seq,
                "x_req": None,
                "hipotesis": hipotesis,
                "request": payload if payload is not None else {},
                "status": None,
                "response": None,
                "conclusion": err_kind,
            }
            with open(self.experiments_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(experiment_entry, ensure_ascii=False) + "\n")

            raise TransportError(f"HTTP {err_kind}: {err_msg}")

        # Normal response handling
        x_req = resp.headers.get("X-Req")
        x_req_val = int(x_req) if x_req and x_req.isdigit() else None
        x_infra = resp.headers.get("X-Frontier-Infra")

        try:
            body = resp.json()
        except Exception:
            body = resp.text

        experiment_entry = {
            "id": record_id,
            "seq": seq,
            "x_req": x_req_val,
            "hipotesis": hipotesis,
            "request": payload if payload is not None else {},
            "status": resp.status_code,
            "response": body,
        }
        if conclusion is not None:
            experiment_entry["conclusion"] = conclusion

        with open(self.experiments_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(experiment_entry, ensure_ascii=False) + "\n")

        audit_entry = {
            "id": record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "latency_ms": latency_ms,
            "status": resp.status_code,
            "x_infra": x_infra,
        }
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

        return experiment_entry

    def reset(self, seq: str, hipotesis: str = "Reset service state") -> Dict[str, Any]:
        return self.send("POST", "/__reset", seq=seq, hipotesis=hipotesis)

    def msg(self, message: str, seq: str, hipotesis: str, conclusion: Optional[str] = None) -> Dict[str, Any]:
        return self.send("POST", "/msg", seq=seq, hipotesis=hipotesis, payload={"m": message}, conclusion=conclusion)
