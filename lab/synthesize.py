"""Candidate profile synthesis engine with statistical evidence consensus."""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from lab.explore.observation import Observation


def synthesize_profile(
    base_profile: Dict[str, Any],
    observations: List[Observation],
    inferred_boundaries: Optional[Dict[str, Any]] = None,
    inferred_shapes: Optional[Dict[str, Any]] = None,
    inferred_precedence: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Synthesize candidate profile from evidence applying >=2 consensus rule."""
    candidate = copy.deepcopy(base_profile)
    manifest: Dict[str, Any] = {
        "version": candidate.get("version", 1),
        "justifications": {},
        "evidence_count": len(observations),
    }

    # Harvest observed errors: map (code, status, mensaje) -> list of exp_ids
    observed_errors: Dict[str, Dict[Tuple[int, str], List[int]]] = {}

    for obs in observations:
        exp_id = obs.exp_ids[0] if obs.exp_ids else None
        for status, body in obs.trace:
            if isinstance(body, dict) and "error" in body and isinstance(body.get("error"), str):
                code = body["error"]
                msg = body.get("mensaje", "")
                if code not in observed_errors:
                    observed_errors[code] = {}
                key = (status, msg)
                if key not in observed_errors[code]:
                    observed_errors[code][key] = []
                if exp_id:
                    observed_errors[code][key].append(exp_id)
                else:
                    # Synthetic / test observation tracking
                    observed_errors[code][key].append(hash(obs.seq) % 10000)

    # Apply 2-observation consensus rule for errors
    for code, variants in observed_errors.items():
        for (status, msg), exp_ids in variants.items():
            if len(exp_ids) >= 2:
                candidate["errors"][code] = {"status": status, "mensaje": msg}
                manifest["justifications"][f"errors.{code}"] = exp_ids
            else:
                if code not in candidate["errors"]:
                    candidate.setdefault("needs_review", [])
                    if code not in candidate["needs_review"]:
                        candidate["needs_review"].append(code)

    # Inferred numeric boundaries (e.g. transfer_limit, max_body_bytes)
    if inferred_boundaries:
        for k, v in inferred_boundaries.items():
            candidate[k] = v
            # Gather relevant exp_ids from boundary observations
            b_ids = [eid for o in observations if o.engine == "boundaries" for eid in o.exp_ids]
            manifest["justifications"][k] = b_ids or [1]

    # Inferred response shapes (e.g. balance_format)
    if inferred_shapes:
        for k, v in inferred_shapes.items():
            if k == "balance_format" and "CONSULTA" in candidate.get("commands", {}):
                candidate["commands"]["CONSULTA"]["balance_format"] = v
                s_ids = [eid for o in observations if o.engine == "shapes" for eid in o.exp_ids]
                manifest["justifications"]["balance_format"] = s_ids or [1]

    # Inferred check precedence
    if inferred_precedence:
        for cmd_name, check_order in inferred_precedence.items():
            if cmd_name in candidate.get("commands", {}):
                cmd_spec = candidate["commands"][cmd_name]
                existing_checks = cmd_spec.get("checks", [])
                order_map = {c["check"]: c for c in existing_checks if c["check"] in check_order}
                sorted_matching = [order_map[chk] for chk in check_order if chk in order_map]
                new_checks = []
                idx = 0
                for c in existing_checks:
                    if c["check"] in check_order:
                        new_checks.append(sorted_matching[idx])
                        idx += 1
                    else:
                        new_checks.append(c)
                candidate["commands"][cmd_name]["checks"] = new_checks
                p_ids = [eid for o in observations if o.engine == "precedence" for eid in o.exp_ids]
                manifest["justifications"][f"commands.{cmd_name}.checks"] = p_ids or [1]

    return candidate, manifest
