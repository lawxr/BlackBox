# Stateful sequence differential fuzzer

## Objective
Find the unknown divergences behind the ~25 failing hidden tests by generating random, seeded, state-aware request sequences shaped like the evaluation set (40 single-step, 45 of 2-5 steps, 15 of 6-12 steps) and comparing original vs replica with the evaluator's equality rule.

## Why
`lab/autofuzz.py` replays a fixed hand-written list of 32 messages in one sequence; it cannot discover behaviors nobody thought of.

## Scope and constraints
- Own code only (no third-party fuzzing/property-based libraries); challenge rule "no uses herramientas que hagan el trabajo por ti".
- Original calls only to the authorized URL with USER_TOKEN, through `LabClient` (every request logged in `experimentos.jsonl`/`audit.jsonl`), throttled, hard request budget, stop on `X-Frontier-Infra` or `TransportError`, no blind retries.
- Replica runs in-process (TestClient); the replacement runtime never calls the original.
- Runtime fixes only after a divergence is observed and recorded.
- TDD on (source: user, previous session); runner `uv run pytest`.

## Tasks
- [ ] F1 — `lab/seqfuzz.py`: seeded generator + differential executor + divergence clustering report; hermetic tests with fake transport. Route: delegated writer (2 non-trivial files).
- [ ] F2 — Run a budgeted live campaign (needs user confirmation of budget); triage clusters.
- [ ] F3 — Fix replica per confirmed cluster, add regression tests, update specification with cited experiment IDs.

## Acceptance
- Same seed => same sequences; evaluator equality (JSON key order free, arrays ordered, otherwise exact text).
- Budget never exceeded; partial runs leave valid logs.

## Progress
- Created 2026-10-10.
- F2 budget authorized by user: 600 original requests (resets included), authorized URL + USER_TOKEN only.
