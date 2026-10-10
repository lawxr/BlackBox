# A1 brief: targets + profile-derived stateful engine

Repo /Users/law/Documents/GitHub/BlackBox, HEAD aca2b95, `uv run pytest` = 89 passed, 1 skipped.

## Rules
- TDD: failing test first, observe RED, then GREEN. Runner `uv run pytest`.
- English code. Stdlib + existing deps only. Tests hermetic: no network, no .env reads.
- Do not commit. Do not edit experimentos.jsonl, audit.jsonl, especificacion.md, README.md, src/.
- Another writer is building `lab/explore/inputs.py` in parallel. Do not create or edit that file or tests/test_explore_inputs.py.
- Time box about 40 minutes.

## Read first
odd/tasks/full-autonomy.md, lab/explore/observation.py (shared contract, do not change its public names), src/profile.json, src/profile.py, src/protocol.py, lab/seqfuzz.py, lab/client.py, lab/runner.py.

## Build
1. `lab/explore/targets.py`:
   - `ReplicaTarget(profile_path=None)`: in-process TestClient, reset first, auth like tests/test_compat.py.
   - `LiveTarget(client, budget)`: uses LabClient, counts resets, raises `BudgetExceeded` before a run that would exceed the budget, raises `TargetStopped` on TransportError, 429 or the X-Frontier-Infra audit flag (reuse the logic in seqfuzz.py `_infra_flag`). Logs `note` as the hipotesis. `last_exp_ids()` returns the ids written.
   - Both honor `__raw__`, `__method__`, `__path__`, `__headers__` step keys.
2. `lab/explore/stateful.py`: the generator reads commands, segment counts, argument kinds, id formats and numeric limits from the profile. No literal command names, limits or ids in the code. The state model (accounts, balances, ops, annulled) is updated from the target's real answers, not assumptions. Length weights favour 6-12 steps. Mutations: reuse seqfuzz's operators where generic. Values near every profile limit (limit-1, limit, limit+1). Chains: transfer then annul, annul twice, consult after annul, operations after failed operations, many ALTA then old ids.
   `explore(target, seed, n, budget) -> List[Observation]`.
3. `lab/explore/diff.py`: `differential(engine_obs, reference_target) -> report`. Replays each observation's steps on the reference target, finds `first_divergence`, clusters by (command, original status/code, reference status/code) and keeps the shortest example per cluster.
4. CLI `python -m lab.explore.stateful --seed N --n N --budget N --report path [--live]`. Without `--live`, use ReplicaTarget against itself as a smoke run.
5. Make lab/seqfuzz.py a thin wrapper over these, or say why not. Keep its tests green.

## Tests (tests/test_explore_stateful.py)
Cover:
- determinism per seed;
- no literal limit: a profile copy with a changed transfer_limit changes the generated amounts;
- the model follows the target (a fake that rejects an ALTA leaves no account in the model);
- the budget is never exceeded, resets included;
- stop on TransportError;
- the differential finds a divergence planted in a fake target at the right step.

## Report
`uv run pytest`: result; `git diff --check`: result; RED/GREEN evidence; files; doubts.
