"""Replay engine: re-sends recorded clean historical sequences, diffs original-now vs original-then, and clusters divergences."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lab.explore.observation import BudgetExceeded, Observation, Step, Target, TargetStopped, first_divergence
from lab.runner import json_equal
from src import profile

_RAW_RE = re.compile(r"^Step \d+ raw=(?P<raw>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"):")


@dataclass
class RecordedSegment:
    seq: str
    start_line: int
    entries: List[Dict[str, Any]] = field(default_factory=list)


def _is_reset(entry: Dict[str, Any]) -> bool:
    hyp = str(entry.get("hipotesis", "")).lower()
    return (
        entry.get("x_req") is None
        and entry.get("request") == {}
        and entry.get("status") == 200
        and entry.get("response") == {"ok": True}
        and ("reset" in hyp or hyp.startswith("canary check"))
    )


def extract_clean_segments(
    log_path: Path | str,
    max_segments: Optional[int] = None,
) -> List[RecordedSegment]:
    """Parse log file and extract clean, non-contaminated segments."""
    p = Path(log_path)
    if not p.exists():
        return []

    raw_lines: List[Tuple[int, Dict[str, Any]]] = []
    with p.open(encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    raw_lines.append((idx, json.loads(line)))
                except json.JSONDecodeError:
                    continue

    open_seg: Dict[str, RecordedSegment] = {}
    segments: List[RecordedSegment] = []
    seg_lines: Dict[str, List[int]] = {}

    for n, entry in raw_lines:
        seq = entry.get("seq", "")
        if not seq or seq == "canary_check" or seq.startswith("diag_") or seq.startswith("input_"):
            continue

        if _is_reset(entry):
            seg = RecordedSegment(seq=seq, start_line=n, entries=[entry])
            open_seg[seq] = seg
            segments.append(seg)
            seg_lines[seq] = [n]
        elif seq in open_seg:
            open_seg[seq].entries.append(entry)
            seg_lines[seq].append(n)

    owner: Dict[int, str] = {n: s for s, lines in seg_lines.items() for n in lines}
    for n, entry in raw_lines:
        owner.setdefault(n, entry.get("seq", ""))
    clean: List[RecordedSegment] = []
    for seg in segments:
        lines = seg_lines.get(seg.seq, [])
        if not lines:
            continue
        span = range(lines[0], lines[-1] + 1)
        if any(owner.get(line_no) != seg.seq for line_no in span if line_no in owner):
            continue
        # Filter segments with at least 1 non-reset step
        non_resets = [e for e in seg.entries if not _is_reset(e)]
        if non_resets:
            clean.append(seg)
            if max_segments and len(clean) >= max_segments:
                break

    return clean


def entry_to_step(entry: Dict[str, Any]) -> Step:
    """Convert a recorded log entry into an exploration Step."""
    routes = profile.get().get("http", {}).get("routes", [])
    path = next((r.get("path", "") for r in routes if r.get("kind") == "message"), "/msg")
    msg_field = profile.get().get("http", {}).get("message_field", "m")

    match = _RAW_RE.match(str(entry.get("hipotesis", "")))
    if match and entry.get("request") == {}:
        raw_val = ast.literal_eval(match.group("raw"))
        return {"__raw__": raw_val, "__path__": path}

    req = entry.get("request", {})
    step: Step = dict(req)
    if "__path__" not in step:
        step["__path__"] = path
    return step


def replay_segments(
    target: Target,
    segments: List[RecordedSegment],
    budget: int = 1000,
) -> Tuple[List[Observation], Dict[str, Any]]:
    """Replay clean historical segments against target, diff against recorded responses, and cluster divergences."""
    observations: List[Observation] = []
    clusters: Dict[str, Dict[str, Any]] = {}
    divergent_segments = 0
    total_segments = 0

    for seg in segments:
        non_reset_entries = [e for e in seg.entries if not _is_reset(e)]
        if not non_reset_entries:
            continue

        steps = [entry_to_step(e) for e in non_reset_entries]
        recorded_trace = [(e.get("status"), e.get("response")) for e in non_reset_entries]

        seq = f"replay_{seg.seq}"
        note = f"historical replay of {seg.seq}@{seg.start_line}"

        try:
            target_trace = target.run(steps, seq=seq, note=note)
        except (BudgetExceeded, TargetStopped):
            break

        total_segments += 1
        obs = Observation(
            engine="replay",
            seq=seq,
            steps=steps,
            trace=target_trace,
            note=note,
            exp_ids=target.last_exp_ids(),
        )
        observations.append(obs)

        div_idx = first_divergence(target_trace, recorded_trace)
        if div_idx is not None:
            divergent_segments += 1
            now_status, now_body = target_trace[div_idx] if div_idx < len(target_trace) else (None, None)
            then_status, then_body = recorded_trace[div_idx] if div_idx < len(recorded_trace) else (None, None)

            step = steps[div_idx] if div_idx < len(steps) else {}
            msg_field = profile.get().get("http", {}).get("message_field", "m")
            sep = profile.get().get("message", {}).get("separator", ";")

            cmd = "UNKNOWN"
            if msg_field in step and isinstance(step[msg_field], str):
                cmd = step[msg_field].split(sep)[0].strip().upper()
            elif "__raw__" in step:
                cmd = "RAW"

            cluster_key = f"{cmd}:{then_status}->{now_status}"
            if cluster_key not in clusters:
                clusters[cluster_key] = {
                    "command": cmd,
                    "then_status": then_status,
                    "now_status": now_status,
                    "count": 1,
                    "divergent_step": div_idx,
                    "sample_step": step,
                    "sample_then": (then_status, then_body),
                    "sample_now": (now_status, now_body),
                    "seq": seg.seq,
                }
            else:
                clusters[cluster_key]["count"] += 1

    summary = {
        "total_segments": total_segments,
        "divergent_segments": divergent_segments,
        "clusters": clusters,
    }
    return observations, summary
