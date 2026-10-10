# R3a brief: probe catalog + learn command (versioning is R3b, not here)

Repo state: branch feat/sequence-fuzzer, HEAD 94bae31, `uv run pytest` = 81 passed.

## Rules
- TDD: write the failing test first, observe RED, then GREEN. Runner `uv run pytest`.
- English code and comments. Stdlib + existing deps only.
- Tests are hermetic: no network, no .env reads.
- Do not commit. Do not edit experimentos.jsonl, audit.jsonl, especificacion.md, README.md.

## Read first
odd/tasks/self-updating-profile.md, src/profile.py, src/profile.json, src/protocol.py, lab/client.py, lab/seqfuzz.py, lab/runner.py, tests/test_log_replay.py, and every script in lab/.

## Build
1. `lab/probes.json`: a list of probes. Each probe: `id`, `description`, `setup` (list of payloads), `request` (payload template using `{ctrl}` for a valid check value or `{bad_ctrl}` for a wrong one, or a raw body), and `observes` (the profile path the response fills, e.g. `errors.E303.message`). Cover every error code, status, response key and command in src/profile.json.
2. `lab/learn.py` CLI:
   - default (plan): no network; print the probes and the request budget.
   - `--live --budget N`: run probes and then a seqfuzz campaign through LabClient; collect messages, keys, statuses and commands suggested via `sugerencia`; write `reports/profile.candidate.json` and `reports/profile.diff.md`. Stop cleanly on rate limit or TransportError. A command whose behavior fits no handler kind is listed under "needs review", never guessed.
   - `--check`: same probes, report drift only, write nothing else (replaces lab/canary.py).
3. Move what is still useful from canary.py, autofuzz.py, probe_*.py and run_differential_sequences.py into learn/seqfuzz/probes.json, then delete those scripts. Keep audit_citations.py. In your report list each deleted file with its replacement.

## Tests (tests/test_learn.py)
Build a stand-in original: the replica app served through httpx MockTransport. Cover: plan mode makes no requests; budget is never exceeded; stop on TransportError; a stand-in whose messages are translated to English produces a candidate under which the replica matches the stand-in on every probe; a stand-in with an extra command produces a "needs review" entry.

## Report
`uv run pytest`: result; `git diff --check`: result; RED/GREEN evidence; files changed or deleted; doubts.