"""Regression oracle: replay every clean recorded original sequence against the replica.

The original's answers live in experimentos.jsonl. A segment starts at a recorded
reset and owns the following entries of the same `seq`. Only /msg steps (entries
carrying an X-Req value) are replayed; route/auth probes without X-Req are skipped.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from lab.runner import json_equal

LOG_PATH = Path(__file__).resolve().parents[1] / "experimentos.jsonl"
TEST_TOKEN = "local-log-replay-test-token"
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}

# Why sequences are left out of the oracle (reasons are generic; specific seqs
# observed on the current log are listed for traceability).
EXCLUSION_RULES = {
    "contaminated": "another seq's entries appear between the segment's first and last line "
                    "(concurrent writers shared the original's state)",
    "no_reset": "entries recorded before any reset of their seq; initial state unknown",
    "canary_probe": "declarative probe checks, not a stateful sequence",
}
KNOWN_CONTAMINATED = {"sf_2026_45", "sf_2026_46", "canary@766"}

# Real replica divergences found by this oracle, pending a deliberate protocol fix.
# Keyed by log line; tracked by a strict xfail so a fix is noticed immediately.
KNOWN_MISMATCHES: dict[int, str] = {}

_RAW_RE = re.compile(r"^Step \d+ raw=(?P<raw>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"):")


@dataclass
class Segment:
    seq: str
    start: int  # 1-based log line of the reset
    lines: List[int] = field(default_factory=list)
    entries: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.seq}@{self.start}"


def _is_reset(entry: Dict[str, Any]) -> bool:
    hyp = str(entry.get("hipotesis", "")).lower()
    return (
        entry.get("x_req") is None
        and entry.get("request") == {}
        and entry.get("status") == 200
        and entry.get("response") == {"ok": True}
        and ("reset" in hyp or hyp.startswith("canary check"))
    )


def load_log(path: Path = LOG_PATH) -> List[Tuple[int, Dict[str, Any]]]:
    with path.open(encoding="utf-8") as f:
        return [(n, json.loads(line)) for n, line in enumerate(f, 1) if line.strip()]


def split_segments(log: List[Tuple[int, Dict[str, Any]]]):
    """Return (clean segments, {label_or_seq: reason})."""
    open_seg: Dict[str, Segment] = {}
    segments: List[Segment] = []
    excluded: Dict[str, str] = {}
    for n, entry in log:
        seq = entry["seq"]
        if seq == "canary_check":
            excluded.setdefault(seq, "canary_probe")
            continue
        if _is_reset(entry):
            seg = Segment(seq, n)
            open_seg[seq] = seg
            segments.append(seg)
        elif seq not in open_seg:
            excluded.setdefault(seq, "no_reset")
            continue
        seg = open_seg[seq]
        seg.lines.append(n)
        seg.entries.append(entry)

    owner = {n: seg.seq for seg in segments for n in seg.lines}
    for n, entry in log:
        owner.setdefault(n, entry["seq"])
    clean = []
    for seg in segments:
        span = range(seg.lines[0], seg.lines[-1] + 1)
        if any(owner[n] != seg.seq for n in span if n in owner):
            excluded[seg.label] = "contaminated"
        else:
            clean.append(seg)
    return clean, excluded


def _step_request(entry: Dict[str, Any]) -> Tuple[str, Any]:
    """('raw', bytes) when the body was sent as raw content, else ('json', payload)."""
    match = _RAW_RE.match(str(entry.get("hipotesis", "")))
    if match and entry.get("request") == {}:
        return "raw", ast.literal_eval(match.group("raw")).encode()
    return "json", entry.get("request")


def _parse(resp) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def replay(tc: TestClient, seg: Segment, only: Optional[set] = None,
           skip: Optional[set] = None) -> List[str]:
    """Replay a segment from a fresh reset; compare only lines in `only` (if given)."""
    from src import profile
    v1_prof = Path(__file__).resolve().parents[1] / "src" / "profile.v1.json"
    v2_prof = Path(__file__).resolve().parents[1] / "src" / "profile.json"
    profile.reload(v1_prof if seg.start <= 1248 else v2_prof)

    mismatches = []
    tc.post("/__reset", headers=AUTH)
    for n, entry in zip(seg.lines, seg.entries):
        if entry.get("x_req") is None:
            continue  # reset, route or auth probe: not a /msg step
        kind, body = _step_request(entry)
        if kind == "raw":
            r = tc.post("/msg", headers=AUTH, content=body)
        else:
            r = tc.post("/msg", headers=AUTH, json=body)
        actual = _parse(r)
        if (only is not None and n not in only) or (skip and n in skip):
            continue
        if r.status_code != entry["status"] or not json_equal(actual, entry["response"]):
            mismatches.append(
                f"{seg.label} line {n} request={body!r}\n"
                f"    original: {entry['status']} {entry['response']!r}\n"
                f"    replica:  {r.status_code} {actual!r}"
            )
    return mismatches


@pytest.fixture
def tc(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAM_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("USER_TOKEN", "")
    monkeypatch.setenv("TOKEN", "")
    v1_prof = Path(__file__).resolve().parents[1] / "src" / "profile.v1.json"
    monkeypatch.setenv("BLACKBOX_PROFILE", str(v1_prof))
    from src import profile
    profile.reload(v1_prof)
    with monkeypatch.context() as ctx:
        ctx.chdir(tmp_path)
        from src import main
    monkeypatch.setattr(main, "TEAM_TOKEN", TEST_TOKEN)
    main.ledger.reset()
    with TestClient(main.app) as client:
        yield client
    main.ledger.reset()
    profile.reload()


def test_segmentation_excludes_known_contamination():
    clean, excluded = split_segments(load_log())
    labels = {s.label for s in clean}
    excluded_seqs = {k.split("@")[0] for k, v in excluded.items() if v == "contaminated"}
    assert {"sf_2026_45", "sf_2026_46"} <= excluded_seqs
    assert excluded.get("canary@766") == "contaminated"
    assert not any(l.startswith(("sf_2026_45@", "sf_2026_46@")) for l in labels)
    assert set(excluded.values()) <= set(EXCLUSION_RULES)
    assert len(clean) > 100


def test_raw_body_is_recovered_from_hypothesis():
    entry = {"hipotesis": "Step 1 raw='PING;1': seqfuzz", "request": {}}
    assert _step_request(entry) == ("raw", b"PING;1")
    entry = {"hipotesis": "Step 2: seqfuzz", "request": {}}
    assert _step_request(entry) == ("json", {})


def test_replica_matches_every_clean_recorded_sequence(tc):
    clean, _ = split_segments(load_log())
    skip = set(KNOWN_MISMATCHES)
    mismatches = [m for seg in clean for m in replay(tc, seg, skip=skip)]
    assert not mismatches, f"{len(mismatches)} mismatches:\n" + "\n".join(mismatches)


@pytest.mark.xfail(strict=True, reason="; ".join(KNOWN_MISMATCHES.values()))
@pytest.mark.parametrize("line", sorted(KNOWN_MISMATCHES))
def test_known_mismatch_still_diverges(tc, line):
    clean, _ = split_segments(load_log())
    seg = next(s for s in clean if line in s.lines)
    assert not replay(tc, seg, only={line})
