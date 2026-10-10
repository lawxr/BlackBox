# Compatibility evidence baseline

## Objective
Make local compatibility checks independent of ambient credentials and align the specification with recorded evidence before further experiments or deployment.

## Scope and constraints
- Base: `d246edc`; Gemini has finished and the initial worktree is clean.
- Authorized: local tests, evidence analysis, specification corrections, work-unit commits.
- Excluded: protocol/runtime changes, remote calls, reading real tokens, deployment, push and PR creation.
- Preserve `experimentos.jsonl`, `audit.jsonl` and historical examples unchanged. Never invent experiments or resets.
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
  - Commit: pending parent structural review and work-unit commit.

## Verification
- Baseline: `env UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 4 passed, 1 dependency deprecation warning.
- Same baseline with `TEAM_TOKEN=inspection-local-test-token USER_TOKEN= TOKEN=` => 4 failed (401); tests omit authorization.
- Runner: `uv run pytest` (README).
- TDD configuration: not explicitly configured; unresolved for future production changes. This slice changes tests and documentation only, not production behavior. Preserve observed failing baseline, then verify corrected tests.
- Required: both baseline environment variants above pass; `git diff --check`; structural review of evidence citations and command blocks.
- Runtime harness: in-process FastAPI TestClient, no network or hosting required.

## Delivery and review
- Feature branch: `feat/compatibility-evidence`.
- Forecast: approximately 300 authored changed lines, excluding this recovery record; delivery strategy `ask-on-risk`.
- One work-unit commit per task; no push or PR authorized.
- RDD: on by default (read-only mode status); first review boundary `d246edc`.
- Record native risk and due outcome after each commit. Review consent remains user-owned.

## Progress
- T1 implemented in `tests/test_compat.py`; runtime, evidence logs and historical examples unchanged. No remote calls or credential reads.
- T1 verification: `env -u TEAM_TOKEN -u USER_TOKEN -u TOKEN UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 28 passed, 1 dependency deprecation warning.
- T1 verification: `env TEAM_TOKEN=inspection-local-test-token USER_TOKEN= TOKEN= UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/blackbox-inspect-uv PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider` => 28 passed, 1 dependency deprecation warning.
- T1 verification: `git diff --check` => exit 0.
- Engram mirror: pending; project lookup/write fails with `unknown_project` despite current-project detection resolving `blackbox`. No session identity supplied.
- T1 work-unit commit: `2399326`; parent reran the synthetic-token pytest command => 28 passed, 1 warning.
- T1 native assessment against `d246edc`: medium, 188 authored changed lines, `review_due=false`, reason `under_budget`; pending review slice boundary remains `d246edc`.
- An initial assessment before staging failed on untracked inventory after sandbox blocked Git writes; it was not treated as low risk. Git write escalation succeeded, and assessment of the committed candidate above completed normally.
- T2 complete locally: specification separates experiment IDs, historical example IDs and replica-only defaults. Missing raw payload in experiment 12, reset/sequence gaps, absent current financial evidence and unverified drift are explicitly disclosed.
- T2 verification: `git diff --check` => exit 0; seven required section tables and six command blocks confirmed. Tests not rerun for this passive documentation-only task; T1 checks remain the runtime evidence.
- T2 specification diff: 78 additions + 38 deletions = 116 authored changed lines; tracker changes recorded separately by parent before commit.
- Engram recovery: discovery save succeeded without a session ID (observation 714, resolved project `blackbox`); full tracker mirror remains pending parent retry.
- Next: parent structural review, tracker mirror and T2 work-unit commit. Remote experiments and deployment require explicit destination/credential authorization later.
