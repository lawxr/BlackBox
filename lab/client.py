from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from src.config import ORIGINAL_URL, TEAM_TOKEN, USER_TOKEN

EXPERIMENTS_PATH = Path("experimentos.jsonl")
AUDIT_PATH = Path("audit.jsonl")


class LabClient:
    """HTTP client for interacting with the original service and recording experiments."""

    def __init__(
        self,
        base_url: str = ORIGINAL_URL,
        token: str = USER_TOKEN or TEAM_TOKEN,
        rate_limit_delay: float = 0.15,  # ~6-7 req/s safe throttle
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.rate_limit_delay = rate_limit_delay
        self._last_req_time: float = 0.0
        self._next_id: int = self._get_next_experiment_id()

    def _get_next_experiment_id(self) -> int:
        if not EXPERIMENTS_PATH.exists():
            return 1
        count = 0
        with open(EXPERIMENTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count + 1

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

        url = f"{self.base_url}{path}"
        req_headers = {}
        if headers is not None:
            req_headers = dict(headers)
        elif self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"

        start_time = time.perf_counter()
        with httpx.Client(timeout=10.0) as client:
            if raw_content is not None:
                resp = client.request(method, url, content=raw_content, headers=req_headers)
            else:
                resp = client.request(method, url, json=payload, headers=req_headers)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        x_req = resp.headers.get("X-Req")
        x_req_val = int(x_req) if x_req and x_req.isdigit() else None
        x_infra = resp.headers.get("X-Frontier-Infra")

        try:
            body = resp.json()
        except Exception:
            body = resp.text

        record_id = self._next_id
        self._next_id += 1

        # Experiment record (official schema)
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

        with open(EXPERIMENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(experiment_entry, ensure_ascii=False) + "\n")

        # Audit record
        audit_entry = {
            "id": record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "latency_ms": latency_ms,
            "status": resp.status_code,
            "x_infra": x_infra,
        }
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

        return experiment_entry

    def reset(self, seq: str, hipotesis: str = "Reset service state") -> Dict[str, Any]:
        return self.send("POST", "/__reset", seq=seq, hipotesis=hipotesis)

    def msg(self, message: str, seq: str, hipotesis: str, conclusion: Optional[str] = None) -> Dict[str, Any]:
        return self.send("POST", "/msg", seq=seq, hipotesis=hipotesis, payload={"m": message}, conclusion=conclusion)
