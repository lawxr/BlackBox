# Full autonomy: learn the black box without hand-written hypotheses

## Objective
`uv run python -m lab.learn --live` discovers the original's contract from generic exploration, promotes a versioned profile only through gates, and the replica passes the hidden set. Secondary target: raise the hidden score from 84/100 (run 02, 16:23, v2) using the one remaining run only for the final check.

## Evidence (run 02, 84/100)
- Easy 40/40, regular 35/40, hard (6-12 steps) 9/20. Failures: 14 status, 2 body; 5 fail on the first request, 11 later in the sequence.
- Reading: the 11 later failures are state semantics over long chains (balances, ANULA effects, op/account ids after errors, TRANSFER with v2 limit/precedence). The 5 first-request failures are single-request input handling (routes, methods, auth variants, raw/malformed bodies, arity/control edge cases). This is inference from counts, not observed; the hidden cases are not visible.
- Current tools would not have found the v2 changes on their own: `learn.py` only harvests messages/statuses of known codes; `v2_discovery.py` is hand-written hypotheses; `seqfuzz.py` hardcodes commands and the 100000 limit; there is no original-vs-original diff.

## Constraints
- Replica never calls the original at runtime. Own code only, stdlib + existing deps. TDD on, runner `uv run pytest` (89 passed, 1 skipped at aca2b95).
- Original only via `LabClient` (one process, lock), authorized URL + USER_TOKEN, every request logged with a hypothesis. Daily cap 8000/token, 10 req/s; already used about 1400. Tokens stop at 20:00 local (now 16:25).
- 1 hidden run left: use it once, after all gates pass and the replica is deployed.

## Architecture (all driven by `src/profile.json`)
- `lab/explore/` engines, each emits observations `{probe, request, status, body, exp_id}`:
  1. `replay`: re-send recorded clean sequences, diff original-now vs original-then, cluster by first divergent step. Detects version drift with no hypothesis.
  2. `boundaries`: for every numeric parameter in the profile (amount cap, transfer limit, id width, name length) binary-search the accept/reject edge.
  3. `precedence`: for every command, build inputs violating each pair of checks at once; the returned code fixes their order. Also order of global stages (route, auth, body, control, arity).
  4. `shapes`: infer each response field's type/format (int, decimal string, id pattern, bool) from observed bodies.
  5. `stateful`: profile-derived seqfuzz (commands, arities, limits read from the profile; model updated from real original answers, not from assumptions), long chains 6-12 weighted up.
  6. `inputs`: single-request grammar mutations: methods, paths, headers, auth schemes, content types, raw bodies, unicode, whitespace, separators, case, arity.
- `lab/learn.py` orchestrates: preflight (health, auth, lock, budget) -> engines -> synthesize candidate profile (each field with the exp ids that justify it) -> gates -> versioned write.
- Synthesis rule: a field changes only if at least 2 observations agree and none contradicts. Conflicts or unknown semantics go to `needs_review` (never guessed).
- Versioning: `profiles/<UTC>/{profile.json, manifest.json, diff.md}`, `profiles/ACTIVE`; `load_profile` resolves explicit path > `BLACKBOX_PROFILE` > ACTIVE > `src/profile.json`. `--apply` needs a clean tree, full suite green, oracle green for the evidence of that version, no budget/rate-limit stop. `--activate <version>` rolls back. Replaces `src/profile.v1.json` and the hardcoded 1248 cutoff in the oracle (manifest carries the exp id range).
- Retire: `v2_discovery.py` (folded into replay + boundaries + precedence), `lab/incident_report.json` (stale false alarm).

## Phases (ordered by expected score gain per hour)
- [ ] A1 (about 45 min, about 1200 req) `stateful` engine profile-derived + live run against v2 weighted to 6-12 steps. Diff original vs replica; fix clusters via profile, engine only if no field fits. Target: hard 9/20 -> 15+.
- [ ] A2 (about 30 min, about 600 req) `inputs` engine + live run. Target: the 5 first-request failures.
- [ ] A3 (about 40 min, about 400 req) `boundaries` + `precedence` + `shapes` engines; live run; confirm v2 limit/order/format and find any other boundary.
- [ ] A4 (about 30 min, about 1145 req) `replay` engine; run it once against v2 to prove it rediscovers the 3 v2 changes with no hints (acceptance test of autonomy). Hermetic test with a fake v1 -> v2 transport.
- [ ] A5 (about 30 min, no network) versioned profiles + gates + oracle split by manifest; migrate v1/v2 profiles.
- [ ] A6 (about 20 min) spec section 6 + debrief text + README (clone, configure, run, re-run on change).
- [ ] A7 deploy, /evento revalidation, then the last hidden run.
- Live phases must finish before 19:30 local. Budget ceiling 3500 requests total (about 4900 left under the 8000 cap).

## Acceptance
- Hermetic: a fake original that changes one limit, one check order, one response format and one message produces a candidate profile that matches it, with exp ids per changed field, and `needs_review` for a new command.
- Live: A4 replay rediscovers the 3 v2 changes without `v2_discovery.py`.
- Gates block promotion on any oracle mismatch.

## Decisions needed
- Live budget 3500 requests to v2 before 19:30.
- Last hidden run: only at the end (A7), or after A1+A2 if score gain is the priority.

## Progress
- Created 2026-10-10 16:27 local. HEAD aca2b95, 89 passed, no live writer, no lock.
- 16:30 user: keep the last hidden run for the end (A7); focus on autonomy and score. Budget ceiling 3500 requests to live v2.
- 16:55 Live exploration campaign (A1 + A2) completed against live v2 service (730 requests used, well under 3500 budget):
  - A1 (Stateful chains, 60 sequences, ~520 req): Verified long chains (6-12 steps). Discovered critical ISO 7064 check value bug: when `(num * 100) % 97 == 0`, check digit is `98` (not `1`). Fixed in `src/protocol.py`. Parity on valid chains confirmed.
  - A2 (Single-request grammar mutations, 100 sequences, 200 req): 4 families tested evenly (25 each). Discovered:
    1. Body size limit: returns `413 {"error": "E101", "mensaje": "cuerpo demasiado grande"}` (E101 was missing from profile).
    2. Leading UTF-8 BOM (`\xef\xbb\xbf`): rejected with `400 {"error": "E100", "mensaje": "json inválido"}`.
    3. Auth, HTTP, and Message grammar behavior mapped with 100% parity on all other mutations.
- Next: Phase A3 (`boundaries`, `precedence`, `shapes` engines) to binary-search the exact body size limit and other numeric bounds.
