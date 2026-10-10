# A2 brief: single-request input engine

Repo /Users/law/Documents/GitHub/BlackBox, HEAD aca2b95, `uv run pytest` = 89 passed, 1 skipped.

## Rules
- TDD: failing test first, observe RED, then GREEN. Runner `uv run pytest`.
- English code. Stdlib + existing deps only. Tests hermetic: no network, no .env reads.
- Do not commit. Do not edit experimentos.jsonl, audit.jsonl, especificacion.md, README.md, src/.
- Another writer is building `lab/explore/targets.py`, `stateful.py` and `diff.py` in parallel. Only create `lab/explore/inputs.py` and `tests/test_explore_inputs.py`. For tests, write a small local fake target inside your test file that follows the `Target` protocol.
- Time box about 35 minutes.

## Read first
odd/tasks/full-autonomy.md, lab/explore/observation.py (shared contract, do not change it), src/profile.json, src/main.py, src/protocol.py, especificacion.md (read only: sections 1, 2 and 5 list the known input rules).

## Build `lab/explore/inputs.py`
`explore(target, seed, n, budget) -> List[Observation]`. Each observation is one sequence: reset, at most 1 setup step taken from the profile (for example creating an account), then 1 mutated request.

The grammar is derived from the profile (routes, auth header/scheme, body key, separator, commands, segment counts, control rule). Mutation families, each a small function in a registry:
- HTTP: method (GET/PUT/DELETE/PATCH on each route), path variants (trailing slash, case, double slash, query string), content types, empty body.
- Auth: header missing, wrong scheme, case of the scheme, extra spaces, token with whitespace, duplicated header.
- Body: non-object JSON (array, string, number, null), missing key, extra keys, wrong value type, nested object, BOM, invalid UTF-8, very large body.
- Message: separator variants (`;;`, trailing `;`, leading `;`, spaces), command case, arity minus/plus one, empty segments, unicode in each segment, control variants (missing, non-numeric, negative, padded, fullwidth digits, out of range).

Every observation carries a `note` naming the family and the mutation. Generation is deterministic per seed. Families are sampled evenly, so each one gets coverage.

`coverage(observations) -> dict` counts observations by family.

## Tests (tests/test_explore_inputs.py)
Cover:
- determinism;
- every family is produced for n >= the number of families;
- no literal route, header or command strings in the code (assert that the module source does not contain them);
- a profile copy with a renamed body key changes the generated bodies;
- the budget is respected.

## Report
`uv run pytest`: result; `git diff --check`: result; RED/GREEN evidence; files; doubts.
