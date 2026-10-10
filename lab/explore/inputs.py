"""Single-request input mutation exploration engine driven dynamically by the protocol profile."""
from __future__ import annotations

import json
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

from lab.explore.observation import BudgetExceeded, Observation, Step, Target, TargetStopped
from src import profile
from src.protocol import compute_control

MutationResult = Tuple[List[Step], str]
MutationFn = Callable[[Dict[str, Any], random.Random], MutationResult]


def _msg_route_path(routes: List[Dict[str, Any]]) -> str:
    for r in routes:
        if r.get("kind") == "message":
            return r.get("path", "")
    return routes[0].get("path", "") if routes else ""


def _build_valid_step(prof: Dict[str, Any], rng: random.Random) -> Tuple[Step, str]:
    commands = prof.get("commands", {})
    cmd_names = list(commands.keys())
    if not cmd_names:
        return {}, ""
    cmd_name = rng.choice(cmd_names)
    spec = commands[cmd_name]
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    routes = prof.get("http", {}).get("routes", [])
    path = _msg_route_path(routes)

    segments = spec.get("segments", 2)
    uses_ctrl = spec.get("control", True)

    parts = [cmd_name]
    num_args = (segments - 1) if uses_ctrl else segments
    for idx in range(1, num_args):
        if "amount_arg" in spec and spec["amount_arg"] == idx:
            parts.append("100")
        else:
            parts.append(f"val{idx}")

    payload = sep.join(parts)
    if uses_ctrl:
        ctrl = compute_control(payload)
        msg_str = f"{payload}{sep}{ctrl}"
    else:
        msg_str = payload

    step: Step = {msg_field: msg_str}
    if path:
        step["__path__"] = path
    return step, msg_str


# --- HTTP Mutations ---

def _mutate_http_method(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    route = rng.choice(routes) if routes else {"path": "", "method": "POST"}
    expected = route.get("method", "POST")
    candidates = [m for m in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] if m != expected]
    method = rng.choice(candidates)
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__method__"] = method
    step["__path__"] = route.get("path", "")
    return [step], "http:method"


def _mutate_http_trailing_slash(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    route = rng.choice(routes) if routes else {"path": "", "method": "POST"}
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__path__"] = f"{route.get('path', '')}/"
    step["__method__"] = route.get("method", "POST")
    return [step], "http:trailing_slash"


def _mutate_http_case(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    route = rng.choice(routes) if routes else {"path": "", "method": "POST"}
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__path__"] = route.get("path", "").upper()
    step["__method__"] = route.get("method", "POST")
    return [step], "http:path_case"


def _mutate_http_double_slash(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    route = rng.choice(routes) if routes else {"path": "", "method": "POST"}
    p = route.get("path", "")
    double_p = "/" + p if p.startswith("/") else "//" + p
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__path__"] = double_p
    step["__method__"] = route.get("method", "POST")
    return [step], "http:double_slash"


def _mutate_http_query_string(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    route = rng.choice(routes) if routes else {"path": "", "method": "POST"}
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__path__"] = f"{route.get('path', '')}?debug=true"
    step["__method__"] = route.get("method", "POST")
    return [step], "http:query_string"


def _mutate_http_content_type(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    ct = rng.choice(["text/plain", "application/xml", "multipart/form-data"])
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Content-Type": ct}
    return [step], "http:content_type"


def _mutate_http_empty_body(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    path = _msg_route_path(routes)
    step: Step = {"__raw__": ""}
    if path:
        step["__path__"] = path
    return [step], "http:empty_body"


# --- Auth Mutations ---

def _mutate_auth_missing(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": None}
    return [step], "auth:header_missing"


def _mutate_auth_wrong_scheme(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    scheme = prof.get("http", {}).get("auth", {}).get("scheme", "Bearer")
    alt_scheme = "Basic" if scheme == "Bearer" else "Bearer"
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": f"{alt_scheme} dummy_token"}
    return [step], "auth:wrong_scheme"


def _mutate_auth_scheme_case(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    scheme = prof.get("http", {}).get("auth", {}).get("scheme", "Bearer")
    alt_scheme = scheme.lower() if rng.choice([True, False]) else scheme.upper()
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": f"{alt_scheme} dummy_token"}
    return [step], "auth:scheme_case"


def _mutate_auth_extra_spaces(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    scheme = prof.get("http", {}).get("auth", {}).get("scheme", "Bearer")
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": f"{scheme}   dummy_token"}
    return [step], "auth:extra_spaces"


def _mutate_auth_token_whitespace(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    scheme = prof.get("http", {}).get("auth", {}).get("scheme", "Bearer")
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": f"{scheme} dummy token with spaces"}
    return [step], "auth:token_whitespace"


def _mutate_auth_empty_token(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    scheme = prof.get("http", {}).get("auth", {}).get("scheme", "Bearer")
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["__headers__"] = {"Authorization": f"{scheme}"}
    return [step], "auth:empty_token"


# --- Body Mutations ---

def _mutate_body_array(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    _, valid_msg = _build_valid_step(prof, rng)
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {"__raw__": json.dumps([valid_msg])}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:non_object_array"


def _mutate_body_string(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    _, valid_msg = _build_valid_step(prof, rng)
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {"__raw__": json.dumps(valid_msg)}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:non_object_string"


def _mutate_body_number(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {"__raw__": "12345"}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:non_object_number"


def _mutate_body_null(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {"__raw__": "null"}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:non_object_null"


def _mutate_body_missing_key(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {"__raw__": "{}"}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:missing_key"


def _mutate_body_extra_keys(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    base_step, _ = _build_valid_step(prof, rng)
    step = dict(base_step)
    step["extra_unexpected_field"] = 999
    return [step], "body:extra_keys"


def _mutate_body_wrong_type(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    msg_field = prof.get("http", {}).get("message_field", "m")
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {msg_field: 12345}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:wrong_type"


def _mutate_body_nested_object(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    msg_field = prof.get("http", {}).get("message_field", "m")
    routes = prof.get("http", {}).get("routes", [])
    _, valid_msg = _build_valid_step(prof, rng)
    step: Step = {msg_field: {"nested_field": valid_msg}}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:nested_object"


def _mutate_body_bom(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    base_step, _ = _build_valid_step(prof, rng)
    routes = prof.get("http", {}).get("routes", [])
    payload = {k: v for k, v in base_step.items() if not k.startswith("__")}
    raw = b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")
    step: Step = {"__raw__": raw}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:bom"


def _mutate_body_invalid_utf8(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    msg_field = prof.get("http", {}).get("message_field", "m")
    routes = prof.get("http", {}).get("routes", [])
    raw = b'{"' + msg_field.encode("utf-8") + b'": "\xff\xfe\xfd"}'
    step: Step = {"__raw__": raw}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:invalid_utf8"


def _mutate_body_large(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    msg_field = prof.get("http", {}).get("message_field", "m")
    routes = prof.get("http", {}).get("routes", [])
    step: Step = {msg_field: "A" * 65536}
    path = _msg_route_path(routes)
    if path:
        step["__path__"] = path
    return [step], "body:large"


# --- Message Mutations ---

def _mutate_msg_double_sep(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    step = dict(base_step)
    step[msg_field] = valid_msg.replace(sep, f"{sep}{sep}", 1)
    return [step], "message:double_separator"


def _mutate_msg_trailing_sep(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    step = dict(base_step)
    step[msg_field] = f"{valid_msg}{sep}"
    return [step], "message:trailing_separator"


def _mutate_msg_leading_sep(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    step = dict(base_step)
    step[msg_field] = f"{sep}{valid_msg}"
    return [step], "message:leading_separator"


def _mutate_msg_spaces_sep(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    step = dict(base_step)
    step[msg_field] = valid_msg.replace(sep, f" {sep} ", 1)
    return [step], "message:spaces_around_separator"


def _mutate_msg_command_case(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[0] = parts[0].lower()
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:command_case"


def _mutate_msg_arity_minus_one(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    if len(parts) > 2:
        parts.pop(1)
    else:
        parts = [parts[0]]
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:arity_minus_one"


def _mutate_msg_arity_plus_one(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts.insert(1, "extra")
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:arity_plus_one"


def _mutate_msg_empty_segment(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    if len(parts) > 1:
        parts[1] = ""
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:empty_segment"


def _mutate_msg_unicode_segment(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[0] = parts[0] + "\u00f1"
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:unicode_segment"


def _mutate_msg_control_missing(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    payload_only = sep.join(parts[:-1]) if len(parts) > 1 else valid_msg
    step = dict(base_step)
    step[msg_field] = payload_only
    return [step], "message:control_missing"


def _mutate_msg_control_non_numeric(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[-1] = "XX"
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:control_non_numeric"


def _mutate_msg_control_negative(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[-1] = "-10"
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:control_negative"


def _mutate_msg_control_padded(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[-1] = "000" + parts[-1]
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:control_padded"


def _mutate_msg_control_fullwidth(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[-1] = "\uff10\uff11"
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:control_fullwidth"


def _mutate_msg_control_out_of_range(prof: Dict[str, Any], rng: random.Random) -> MutationResult:
    sep = prof.get("message", {}).get("separator", ";")
    msg_field = prof.get("http", {}).get("message_field", "m")
    base_step, valid_msg = _build_valid_step(prof, rng)
    parts = valid_msg.split(sep)
    parts[-1] = "999"
    step = dict(base_step)
    step[msg_field] = sep.join(parts)
    return [step], "message:control_out_of_range"


# --- Registry ---

MUTATION_REGISTRY: Dict[str, List[MutationFn]] = {
    "http": [
        _mutate_http_method,
        _mutate_http_trailing_slash,
        _mutate_http_case,
        _mutate_http_double_slash,
        _mutate_http_query_string,
        _mutate_http_content_type,
        _mutate_http_empty_body,
    ],
    "auth": [
        _mutate_auth_missing,
        _mutate_auth_wrong_scheme,
        _mutate_auth_scheme_case,
        _mutate_auth_extra_spaces,
        _mutate_auth_token_whitespace,
        _mutate_auth_empty_token,
    ],
    "body": [
        _mutate_body_array,
        _mutate_body_string,
        _mutate_body_number,
        _mutate_body_null,
        _mutate_body_missing_key,
        _mutate_body_extra_keys,
        _mutate_body_wrong_type,
        _mutate_body_nested_object,
        _mutate_body_bom,
        _mutate_body_invalid_utf8,
        _mutate_body_large,
    ],
    "message": [
        _mutate_msg_double_sep,
        _mutate_msg_trailing_sep,
        _mutate_msg_leading_sep,
        _mutate_msg_spaces_sep,
        _mutate_msg_command_case,
        _mutate_msg_arity_minus_one,
        _mutate_msg_arity_plus_one,
        _mutate_msg_empty_segment,
        _mutate_msg_unicode_segment,
        _mutate_msg_control_missing,
        _mutate_msg_control_non_numeric,
        _mutate_msg_control_negative,
        _mutate_msg_control_padded,
        _mutate_msg_control_fullwidth,
        _mutate_msg_control_out_of_range,
    ],
}

FAMILIES = ["http", "auth", "body", "message"]


def explore(
    target: Target,
    seed: int = 42,
    n: int = 40,
    budget: int = 1000,
) -> List[Observation]:
    """Execute single-request mutation sequences deterministically derived from profile."""
    rng = random.Random(seed)
    prof = profile.get()
    observations: List[Observation] = []
    used_requests = 0

    for i in range(n):
        family = FAMILIES[i % len(FAMILIES)]
        mut_fn = rng.choice(MUTATION_REGISTRY[family])
        steps, note = mut_fn(prof, rng)

        needed = 1 + len(steps)
        if used_requests + needed > budget:
            break

        seq = f"input_{i:04d}"
        try:
            trace = target.run(steps, seq=seq, note=note)
        except (BudgetExceeded, TargetStopped):
            break

        used_requests += needed
        observations.append(
            Observation(
                engine="inputs",
                seq=seq,
                steps=steps,
                trace=trace,
                note=note,
                exp_ids=target.last_exp_ids(),
            )
        )

    return observations


def coverage(observations: List[Observation]) -> Dict[str, int]:
    """Count generated observations by mutation family."""
    counts: Dict[str, int] = {f: 0 for f in FAMILIES}
    for o in observations:
        family = o.note.split(":")[0] if ":" in o.note else o.note
        counts[family] = counts.get(family, 0) + 1
    return counts
