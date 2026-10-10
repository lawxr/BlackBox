"""Differential comparison between engine observations and a reference target."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from lab.explore.observation import BudgetExceeded, Observation, Target, TargetStopped, first_divergence
from src import profile


def differential(
    engine_obs: List[Observation],
    reference_target: Target,
) -> Dict[str, Any]:
    """Replay each observation's steps against reference_target and cluster divergences."""
    prof = profile.get()
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")

    clusters: Dict[str, Dict[str, Any]] = {}
    total_compared = 0
    divergent_count = 0

    for obs in engine_obs:
        total_compared += 1
        try:
            ref_trace = reference_target.run(obs.steps, seq=obs.seq, note=f"Diff: {obs.note}")
        except (BudgetExceeded, TargetStopped):
            break

        div_idx = first_divergence(obs.trace, ref_trace)
        if div_idx is None:
            continue

        divergent_count += 1
        orig_resp = obs.trace[div_idx] if div_idx < len(obs.trace) else (None, None)
        ref_resp = ref_trace[div_idx] if div_idx < len(ref_trace) else (None, None)
        orig_status = orig_resp[0]
        ref_status = ref_resp[0]

        step = obs.steps[div_idx] if div_idx < len(obs.steps) else {}
        cmd = "UNKNOWN"
        if msg_field in step and isinstance(step[msg_field], str):
            cmd = step[msg_field].split(sep)[0].strip().upper()
        elif "__method__" in step or "__path__" in step:
            cmd = f"{step.get('__method__', 'HTTP')} {step.get('__path__', '')}"

        cluster_key = f"{cmd}:{orig_status}->{ref_status}"
        if cluster_key not in clusters:
            clusters[cluster_key] = {
                "command": cmd,
                "orig_status": orig_status,
                "ref_status": ref_status,
                "count": 1,
                "shortest_seq": obs.seq,
                "shortest_steps": obs.steps,
                "divergent_step": div_idx,
                "orig_response": orig_resp,
                "ref_response": ref_resp,
            }
        else:
            clusters[cluster_key]["count"] += 1
            if len(obs.steps) < len(clusters[cluster_key]["shortest_steps"]):
                clusters[cluster_key]["shortest_seq"] = obs.seq
                clusters[cluster_key]["shortest_steps"] = obs.steps
                clusters[cluster_key]["divergent_step"] = div_idx
                clusters[cluster_key]["orig_response"] = orig_resp
                clusters[cluster_key]["ref_response"] = ref_resp

    return {
        "total_compared": total_compared,
        "divergent_count": divergent_count,
        "clusters": clusters,
    }
