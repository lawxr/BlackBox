# Self-updating protocol profile

## Objective
Make the replica data-driven and the lab able to re-learn the original's contract automatically (messages, language, response keys, codes, statuses, commands, limits), with less redundant code and a clean README.

## Hard constraint
The replica never calls the original at runtime (challenge rule: set = 0). "Self-update" therefore means: the lab re-learns from the original and regenerates `src/profile.json`; the replica only reads that file. Applying a new profile requires tests to pass and a redeploy. After 20:00 participant tokens stop working, so learning is only possible before then.

## Design
- `src/profile.json`: single source of truth (routes, auth error, error catalog code -> status/message, command table with arity/argument kinds/handler kind/response keys, amount rule, transfer limit, suggestion distance, precedence).
- `src/` engine: generic validation pipeline + handler kinds (`pong`, `create_account`, `query_account`, `credit`, `transfer`, `annul`, `refuse`) driven by the profile. No literal protocol strings in code.
- `lab/probes.json`: declarative "error forcing" catalog; each probe forces one behavior and states which profile path it observes.
- `lab/learn.py`: runs probes (live, budgeted, logged), harvests messages/keys/statuses, discovers commands via `sugerencia` harvesting, writes `profile.candidate.json` + human-readable diff; `--apply` only when the full suite passes. `canary` becomes `learn --check`.
- Regression oracle: every recorded original sequence in `experimentos.jsonl` is replayed against the replica.
- Clone-and-run workflow (user, 2026-10-10): an engineer clones the repo, sets URL + token, runs one command, and gets a replica matching the observed original; if the original changes, they re-run the same command.
  - Entry point: `uv run python -m lab.learn` (default = dry plan, `--live` to probe, `--apply` to promote).
  - Pipeline: preflight (health, auth, lock, budget) -> probes catalog -> sequence fuzzer -> candidate profile -> oracle replay + full suite -> promote.
  - Versioning: `profiles/<UTC-timestamp>/` holds `profile.json` + `manifest.json` (source URL host, experiment id range, request count, probe catalog hash, profile sha256, parent version) + `diff.md`; `profiles/ACTIVE` names the version `src/` loads. Rollback = change ACTIVE.
  - Precautions: promotion refuses on dirty git tree, failing tests, oracle mismatches, or budget/rate-limit stop; never deletes old versions; one LabClient process at a time.
- Limit (honest): only observed behavior is learned; coverage depends on the probe catalog + fuzzer. A brand-new command semantics that fits no handler kind still needs a human; the learner reports it instead of guessing.

## Constraints
- Own code only; stdlib + existing deps. TDD on (source: user), runner `uv run pytest`.
- Original only via `LabClient`, authorized URL + USER_TOKEN, budgeted, single process at a time.
- Preserve existing `experimentos.jsonl`/`audit.jsonl` content (renumbering of duplicate ids 765-773 awaits user decision).
- Branch `feat/sequence-fuzzer` continues (stacked on 28ca9c2). No deploy, push or PR without the user.

## Tasks
- [x] R1 — Log-replay oracle test + LabClient fixes (id = max id + 1, single-writer lock file). Route: delegated writer.
- [x] R2 — Extract `src/profile.json` and make the engine data-driven; behavior unchanged (all tests + oracle identical). Route: delegated writer.
- [ ] R3 — `lab/probes.json` + `lab/learn.py` (learn/check/apply, command discovery); fold canary/autofuzz/probe_* scripts into it and remove the redundant ones. Route: delegated writer.
- [ ] R3b — Versioned profiles (`profiles/`, manifest, ACTIVE pointer, diff.md, rollback) + promotion gates. Route: delegated writer.
- [ ] R4 — README rewrite (concise: what, run, test, learn loop, deploy contract). Route: inline or delegated.

## Acceptance
- Oracle replays all clean recorded sequences with zero mismatches (known contaminated: sf_2026_45, sf_2026_46).
- Changing a message/key/status in `profile.json` changes replica output without code edits (test).
- `learn` against a fake original whose language changed produces a candidate profile that makes the oracle pass for the fake.

## Progress
- Created 2026-10-10 14:31 local.
- R1+R2 done (uncommitted): oracle replays 140 clean sequences; LabClient id=max+1 and lock; src/profile.json + load_profile (path > BLACKBOX_PROFILE > default); engine equivalence checked on 3000 random sequences. Oracle found exp 1196 (fullwidth digit) -> fixed ASCII-only control digits. 81 passed.
