# Incident FR-0153: original moved to v2 (3 behaviors changed)

## Objective
Find the 3 changed behaviors, log them in `experimentos.jsonl`, make the replica answer like v2, and explain them (what, since when, how detected) in especificacion.md section 6 and the debrief. Conformance tests run against v2.

## Facts
- Ticket opened 2026-10-10 15:30 local (20:30 UTC). Last logged request: id 1248 at 20:22:35 UTC (15:22 local), so the whole log (ids 1-1248) is v1 evidence.
- v1 corpus usable as a probe set: 145 clean reset-started sequences = 1145 requests (oracle `split_segments`). Plus standalone route/auth/raw entries the oracle skips (`x_req` null), which must also be re-run: auth, routes and health may be among the changes.
- Daily limit 8000 requests per token; 10 req/s. Tokens stop at 20:00 local.
- Another agent is doing R3 (probes/learn). Risk: both touch `src/profile.json` and `lab/`. LabClient lock allows only one live writer.

## Method
1. Preflight (about 3 requests): `GET /health`, PING, one reset. Compare with v1 answers and note any version marker. Check nothing else is writing to the log.
2. Differential replay (about 1200 requests): re-send every clean v1 sequence and standalone probe to v2 in the same order, with seq `v2r_<orig seq>` and hipotesis "v2 replay of <seq>@<line>: does v2 still answer like v1 exp <id>?". Compare each answer to the recorded v1 answer with evaluator equality. A mismatch is a candidate change. The replica is not used here, so v1 evidence is compared against v2 evidence directly.
3. Cluster by (command, step kind, v1 status/code, v2 status/code). Expect 3 clusters. One change can show up in many sequences: for example, if ALTA changes, every later step diverges. Use the first divergent step of each sequence.
4. If there are fewer than 3 clusters, run targeted probes (budget 800) where the v1 corpus is thin: unknown routes, auth variants, raw bodies, HELP/suggestion text, transfer limit, ANULA chains, ID format, long sequences (6-12). Then a seqfuzz campaign with a new seed (budget 1000).
5. Confirm each change with a minimal sequence run twice. Pin its exact boundary (as done for the amount cap) and its error precedence.
6. Replica: TDD tests from the v2 evidence, then change `src/profile.json` (engine code only if no profile field fits). Keep the v1 profile as a version (needs R3b). Interim: commit it as `profiles/v1/`.
7. Version-aware oracle: v1 log ids (1-1248) replay against the v1 profile, v2 ids against the v2 profile. The deployed replica uses v2.
8. Docs: in especificacion.md section 6, one row per change (DRIFT-1xx): v1 behavior, v2 behavior, first v2 experiment id and timestamp, detection method, exp ids. Update the affected rows in other sections and mark them superseded. Debrief: 3 short paragraphs (what changed, since when, how we found it, how the replica follows).
9. Deploy, revalidate in /evento, and record the passing count.

## Budget
Total ceiling 3000 live requests (preflight + replay + probes + fuzz), well under the 8000/day limit. Stop on rate limit or TransportError.

## Decisions needed from the user
- Approve the live budget (3000).
- Where the debrief goes (a file in the repo? which name?) and in what format.
- Coordination with the R3 agent: pause its writes to `src/profile.json` while the incident is fixed, or have it rebase afterwards.

## Tasks
- [ ] I1 Preflight + replay script (`lab/replay_v1.py` or a `seqfuzz` mode), hermetic tests with a fake v2.
- [ ] I2 Live replay and clustering.
- [ ] I3 Targeted probes / fuzz if fewer than 3 clusters.
- [ ] I4 Replica v2 + versioned profiles + oracle split.
- [ ] I5 Spec section 6 + debrief + deploy/revalidate.

## Progress
- Created 2026-10-10 15:35 local.
