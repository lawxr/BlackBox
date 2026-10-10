"""Target runners for the exploration engines (live original vs local replica)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from lab.client import LabClient, TransportError
from lab.explore.observation import BudgetExceeded, Step, Target, TargetStopped
from src import profile


class ReplicaTarget:
    """In-process TestClient running against the local FastAPI replica."""

    def __init__(self, profile_path: Optional[Path | str] = None) -> None:
        self.profile_path = Path(profile_path) if profile_path else None
        self._last_ids: List[int] = []

    def last_exp_ids(self) -> List[int]:
        return self._last_ids

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        from fastapi.testclient import TestClient
        from src import main

        if self.profile_path:
            profile.reload(self.profile_path)

        token = main.TEAM_TOKEN
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._last_ids = []

        with TestClient(main.app) as tc:
            tc.post("/__reset", headers=auth_headers)
            trace = []
            for step in steps:
                method = step.get("__method__", "POST")
                path = step.get("__path__", "/msg")
                headers = dict(auth_headers)
                if "__headers__" in step and step["__headers__"] is not None:
                    for k, v in step["__headers__"].items():
                        if v is None:
                            headers.pop(k, None)
                        else:
                            headers[k] = v

                if "__raw__" in step:
                    raw = step["__raw__"]
                    content = raw.encode("utf-8") if isinstance(raw, str) else raw
                    r = tc.request(method, path, headers=headers, content=content)
                else:
                    payload = {k: v for k, v in step.items() if not k.startswith("__")}
                    r = tc.request(method, path, headers=headers, json=payload)

                try:
                    body = r.json()
                except Exception:
                    body = r.text
                trace.append((r.status_code, body))
            return trace


class LiveTarget:
    """Real HTTP target hitting the original service via LabClient with budget tracking."""

    def __init__(self, client: LabClient, budget: int) -> None:
        self.client = client
        self.budget = budget
        self.used_requests: int = 0
        self._last_ids: List[int] = []

    def last_exp_ids(self) -> List[int]:
        return self._last_ids

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        needed = 1 + len(steps)  # 1 reset + N steps
        if self.used_requests + needed > self.budget:
            raise BudgetExceeded(
                f"Budget exceeded: used {self.used_requests} + needed {needed} > budget {self.budget}"
            )

        self._last_ids = []
        try:
            res_entry = self.client.reset(seq=seq, hipotesis=f"Reset: {note}")
            self.used_requests += 1
            if res_entry.get("id"):
                self._last_ids.append(res_entry["id"])
        except TransportError as te:
            raise TargetStopped(f"TransportError on reset: {te}") from te

        if res_entry.get("status") == 429 or self._infra_flag():
            raise TargetStopped("Rate limit hit on reset")

        trace = []
        for n, step in enumerate(steps, 1):
            method = step.get("__method__", "POST")
            path = step.get("__path__", "/msg")
            auth_headers = {"Authorization": f"Bearer {self.client.token}"} if self.client.token else {}
            headers = dict(auth_headers)
            if step.get("__headers__") is not None:
                for k, v in step["__headers__"].items():
                    if v is None:
                        headers.pop(k, None)
                    else:
                        headers[k] = v
            raw_content = None
            payload = None

            if "__raw__" in step:
                raw = step["__raw__"]
                raw_content = raw.encode("utf-8") if isinstance(raw, str) else raw
            else:
                payload = {k: v for k, v in step.items() if not k.startswith("__")}

            try:
                entry = self.client.send(
                    method=method,
                    path=path,
                    seq=seq,
                    hipotesis=f"Step {n}: {note}",
                    payload=payload,
                    headers=headers,
                    raw_content=raw_content,
                )
                self.used_requests += 1
                if entry.get("id"):
                    self._last_ids.append(entry["id"])
            except TransportError as te:
                raise TargetStopped(f"TransportError on step {n}: {te}") from te

            if entry.get("status") == 429 or self._infra_flag():
                raise TargetStopped("Rate limit hit during step")

            trace.append((entry.get("status"), entry.get("response")))

        return trace

    def _infra_flag(self) -> bool:
        from lab.seqfuzz import _infra_flag

        return _infra_flag(self.client)


class ScopedTarget:
    """Target proxy that enforces a sub-budget on top of another Target."""

    def __init__(self, parent: Target, max_requests: int) -> None:
        self.parent = parent
        self.max_requests = max_requests
        self.used_requests: int = 0

    def last_exp_ids(self) -> List[int]:
        return self.parent.last_exp_ids()

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        needed = 1 + len(steps)
        if self.used_requests + needed > self.max_requests:
            raise BudgetExceeded(
                f"ScopedTarget budget exceeded: used {self.used_requests} + needed {needed} > max {self.max_requests}"
            )
        trace = self.parent.run(steps, seq=seq, note=note)
        self.used_requests += needed
        return trace


class RemoteTarget:
    """Remote HTTP target hitting any external URL (e.g. deployed replica or localhost)."""

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._last_ids: List[int] = []

    def last_exp_ids(self) -> List[int]:
        return self._last_ids

    def run(self, steps: List[Step], seq: str, note: str) -> List[tuple]:
        import httpx

        auth_headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self._last_ids = []

        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            client.post("/__reset", headers=auth_headers)
            trace = []
            for step in steps:
                method = step.get("__method__", "POST")
                path = step.get("__path__", "/msg")
                headers = dict(auth_headers)
                if "__headers__" in step and step["__headers__"] is not None:
                    for k, v in step["__headers__"].items():
                        if v is None:
                            headers.pop(k, None)
                        else:
                            headers[k] = v

                if "__raw__" in step:
                    raw = step["__raw__"]
                    content = raw.encode("utf-8") if isinstance(raw, str) else raw
                    r = client.request(method, path, headers=headers, content=content)
                else:
                    payload = {k: v for k, v in step.items() if not k.startswith("__")}
                    r = client.request(method, path, headers=headers, json=payload)

                try:
                    body = r.json()
                except Exception:
                    body = r.text
                trace.append((r.status_code, body))
            return trace
