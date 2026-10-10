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
- [x] F1 — `lab/seqfuzz.py`: seeded generator + differential executor + divergence clustering report; hermetic tests with fake transport. Route: delegated writer (2 non-trivial files).
- [x] F2 — Run a budgeted live campaign (needs user confirmation of budget); triage clusters.
- [x] F3 — Fix replica per confirmed cluster, add regression tests, update specification with cited experiment IDs.

## Acceptance
- Same seed => same sequences; evaluator equality (JSON key order free, arrays ordered, otherwise exact text).
- Budget never exceeded; partial runs leave valid logs.

## Progress
- Created 2026-10-10.
- F2 budget authorized by user: 600 original requests (resets included), authorized URL + USER_TOKEN only.
- F1: commit a6bd0b4 (13 hermetic tests; full suite 50 passed).
- F2: seed 2026, 100 sequences, 451 original requests (exp 764-1121) + 80 targeted probes (seqs s_amount_halt_probe, s_amount_bound, s_halt_shape). 7 divergences, 5 clusters.
- F3: commit 4ef838f: strict amount `[1-9][0-9]{0,9}`, E303 before E304/E401, hidden HALT -> 409 E520. 68 passed. 6/7 divergences replay clean; sf_2026_45 was contaminated by a concurrent canary run on the same token (ALTA AC-0002).
- Open: concurrent canary + seqfuzz produced duplicate log ids 765-773 (ids drift from line numbers after 765). Needs user decision before renumbering.
