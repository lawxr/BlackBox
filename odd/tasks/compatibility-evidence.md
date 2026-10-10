# Compatibility evidence baseline

## Objective
Make compatibility evidence reproducible: hermetic local checks, evidence-scoped specification, reliable experiment recording and focused differential sequences.

## Scope and constraints
- Base: `d246edc`; Gemini has finished and the initial worktree is clean.
- Authorized: local lab improvements, tests, evidence analysis, specification corrections and work-unit commits. User additionally authorized experiments/resets at `https://caja-negra-production-c64f.up.railway.app` using only `USER_TOKEN` from `.env`.
- Excluded: deployment, other remote destinations/credentials, push and PR creation. Runtime changes require concrete compatibility evidence first.
- Preserve existing `experimentos.jsonl`, `audit.jsonl` and historical examples. New original observations may be appended only during an explicitly launched campaign; never invent experiments or resets.
- The replacement must never call the original or another replacement.
- Existing Spanish specification stays Spanish; new test code and this tracker use English.

## Tasks
- [x] T1 — Make compatibility tests hermetic with a synthetic token, explicit valid/invalid/missing authentication, independent state, and authenticated replay of the 20 historical examples.
  - Route: delegated; reading prepares test edits and requires runtime/config context.
  - Acceptance: all tests pass with ambient token variables both unset and set; exact status/body assertions; no outbound network calls.
  - Rollback: test-only changes; runtime behavior unchanged.
  - Outcome: 28 in-process checks pass in both token environments. The fixture uses a synthetic token, imports away from project `.env`, and resets ledger state before and after each test. Auth/fallback checks describe the replica only; the ordered 20-step replay uses historical evidence.
  - Commit: `2399326`; parent verification and native assessment recorded below.
- [x] T2 — Correct specification confidence and citations; give each command its own block; distinguish historical evidence, current experiments and untested replica defaults.
  - Route: delegated; evidence analysis spans specification, logs, audit, examples and source.
  - Acceptance: every cited experiment exists and supports its stated scope; no claim of current financial behavior, multi-token isolation or drift stability without evidence.
  - Rollback: specification-only changes; original evidence remains untouched.
  - Outcome: 49 evidence-scoped behavior rows across all seven required sections and six command blocks. Financial behavior remains historical/probable; untested replica behavior is explicitly assumed.
  - Verification: own local citation audit resolved 107 experiment IDs and 17 morning-example IDs; observed exact JSON snippets match their cited records. All 354 audit statuses match experiments; 320 ALTA outcomes fit the candidate checksum without claiming a standard or Unicode support.
  - Commit: `f9f72e7`; verification record `58fb39b`.
- [x] T3 — Preserve experiment intent before sending and retain exact request representation, including uncertain transport outcomes.
  - Route: delegated; lab source plus new focused tests, with preparation reading owned by the writer.
  - Acceptance: timeout leaves a durable sanitized attempt; failed pre-send logging prevents network; response records remain compatible; raw JSON and bodyless reset are distinguishable; no automatic retry or fabricated response.
  - Checks: observed RED then GREEN for new fake-transport tests; one full local suite at closure; `git diff --check`. Existing original behavior is not reprobed.
  - Rollback: lab logger and its tests/docs only; production runtime and existing experiment records unchanged.
  - Outcome: `LabClient` supports hermetic transport injection, configurable audit/experiments paths, pre-send directory checks, explicit `TransportError`, durable uncertain recording on timeout/transport failures without blind retries or fabricated data, and distinguishable bodyless vs payload representations.
- [x] T4 — Add sequential reset-and-replay comparison for status and exact JSON/text responses, stopping on infrastructure or uncertain outcomes.
  - Route: delegated; runner and focused tests. Schedule after T3 is verified.
  - Outcome: `SequenceResult` and `compare_sequence` implemented in `lab/runner.py`. Executes reset then step-by-step sequence comparisons with key-order-agnostic JSON comparison, early stopping on mismatches, rate-limits (`infra_rate_limit`) or `TransportError`.
- [ ] T5 — Run one hypothesis-driven current-version campaign and update only conclusions supported by its new evidence.
  - Route: delegated execution with exact authorized original URL and USER_TOKEN from `.env`, one client, no blind retries, secrets never printed. Do not repeat established probes without a named uncertainty.

## Verification
- Baseline: `env UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 4 passed, 1 dependency deprecation warning.
- Same baseline with `TEAM_TOKEN=inspection-local-test-token USER_TOKEN= TOKEN=` => 4 failed (401); tests omit authorization.
- Runner: `uv run pytest` (README).
- TDD: enabled explicitly by the user for further improvements. Source: current conversation. Runner: `uv run pytest`; RED -> GREEN -> REFACTOR for new/changed behavior, reuse prior verified findings, avoid redundant original investigations.
- Required: both baseline environment variants above pass; `git diff --check`; structural review of evidence citations and command blocks.
- Runtime harness: in-process FastAPI TestClient, no network or hosting required.

## Delivery and review
- Feature branch: `feat/compatibility-evidence`.
- Completed baseline: 317 authored changed lines. Next lab task forecast: approximately 150-250 more; delivery strategy `ask-on-risk`. Chain strategy must be resolved before the next commit above the accumulated delivery threshold; do not silently choose one or create a PR.
- One work-unit commit per task; no push or PR authorized.
- RDD: on by default (read-only mode status); first review boundary `d246edc`.
- Record native risk and due outcome after each commit. Review consent remains user-owned.

## Progress
- T1 implemented in `tests/test_compat.py`; runtime, evidence logs and historical examples unchanged. No remote calls or credential reads.
- T1 verification: `env -u TEAM_TOKEN -u USER_TOKEN -u TOKEN UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 28 passed, 1 dependency deprecation warning.
- T1 verification: `env TEAM_TOKEN=inspection-local-test-token USER_TOKEN= TOKEN= UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 28 passed, 1 dependency deprecation warning.
- T1 verification: `git diff --check` => exit 0.
- Engram: initial project writes failed with `unknown_project`; writes now succeed. No authoritative session identity supplied, so mutation calls omit session_id.
- T1 work-unit commit: `2399326`; parent reran the synthetic-token pytest command => 28 passed, 1 warning.
- T1 native assessment against `d246edc`: medium, 188 authored changed lines, `review_due=false`, reason `under_budget`; pending review slice boundary remains `d246edc`.
- An initial assessment before staging failed on untracked inventory after sandbox blocked Git writes; it was not treated as low risk. Git write escalation succeeded, and assessment of the committed candidate above completed normally.
- T2 complete locally: specification separates experiment IDs, historical example IDs and replica-only defaults. Missing raw payload in experiment 12, reset/sequence gaps, absent current financial evidence and unverified drift are explicitly disclosed.
- T2 verification: `git diff --check` => exit 0; seven required section tables and six command blocks confirmed. Tests not rerun for this passive documentation-only task; T1 checks remain the runtime evidence.
- T2 specification diff: 78 additions + 38 deletions = 116 authored changed lines; tracker changes recorded separately by parent before commit.
- T2 work-unit commit: `f9f72e7`; parent read back the complete specification and confirmed the seven sections, six command blocks and explicit evidence limitations.
- T2 native assessment against `d246edc`: medium, 314 authored changed lines, `review_due=false`, reason `under_budget`. Initial sandbox denial of its temporary Git index was resolved through approved escalation; no review approval is claimed.
- Engram recovery: discovery saves succeeded (714 and 716); full current tracker is mirrored under `odd/compatibility-evidence/tasks` and must be read back before closing.
- Remaining: original financial behavior has no current successful experiment coverage; raw logging and reset/sequence gaps remain; public deployment is unverified.
- Authorization update: user approved original experiments/resets with USER_TOKEN from `.env`; then approved focused TDD. Prior no-remote statements describe the completed baseline, not current authority.
- T3 complete locally: `tests/test_lab_client.py` added with 3 tests using `httpx.MockTransport`; observed RED on `TransportError` collection then GREEN after implementation (3 passed in 0.19s). Full suite `uv run pytest` passes (31 passed, 1 warning in 0.34s). `git diff --check` => exit 0. Commit: `19ae172`.
- T4 complete locally: `lab/runner.py` implemented with `SequenceResult` and `compare_sequence`; `tests/test_lab_runner.py` added with 3 tests covering match, mismatch stop and rate-limit stop; observed RED then GREEN (3 passed in 0.50s). Full suite `uv run pytest` passes (34 passed, 1 warning in 0.81s). `git diff --check` => exit 0.
- Next: T4 work-unit commit; then T5.
