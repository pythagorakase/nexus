# Nine-lane integration verification

**Full gate passed: 6984 passed, 72 skipped, 41 warnings.** All three serial
pieces exited 0 and reported the required secret-store guard, untouched receipts
and no owner-target audit findings. The integration head and tree remained
unchanged and clean through completion. This verifies the assembled code;
owner-fleet application remains separate.

The immutable tested integration is
`f291dc792e4b071a4cc4940101f6c40871ea8b7b`, based on
`afd034f360e625f8bc4ffa8a717dda28422b19c7`. The checkout is
`/Users/pythagor/.codex/worktrees/resume-claude-integration/nexus`. The captured
[state](state-at-draft.json) records these feature heads:

| Lane | Feature head | PR at capture |
|---|---|---|
| 822: story identity | `f192fccd951c96689b5b76c2ff7d1680e3f97254` | [1117](https://github.com/pythagorakase/nexus/pull/1117) |
| 840: Natural Earth | `e79dfda0c37826b673042a93eedca252708b935e` | [1116](https://github.com/pythagorakase/nexus/pull/1116) |
| 836: unified references | `9f7d5a8cef1f2092d5ac637b39ee047f8b9fc123` | Pending |
| 806: failure receipts | `cf61a440da7f3236226c717d031a493cbc25f5c5` | [1118](https://github.com/pythagorakase/nexus/pull/1118) |
| 812: one runtime embedder | `060972651214b96c45ec94657ec35d363261f973` | Pending |
| 785: travel | `9e207e558d250636b9a1a571b03178fefb62d8f9` | Pending |
| 810: migration-owned DDL | `487f3a08564979505b8913c7e95c4d4363b7662e` | Pending |
| 816: isolated TEST database | `a6ed8862ca875a069cbefd52bcae8e65d90e9337` | Pending |
| 817: decision ledger | `5cff344d54688d5e6b35e4dad83e369c9f45cfd3` | [1115](https://github.com/pythagorakase/nexus/pull/1115) |

The [artifact manifest](artifact-provenance.json) records source paths and SHA256
hashes for the copied evidence. Historical reports retain their original heads
and results; their inclusion does not turn them into a final-head rerun.

## Integration and independent review

`git show --remerge-diff` identifies three resolved conflicts in the first-parent
integration history. The [resolution diff](merge-resolutions.diff) preserves:

- `a9a95f7f`, `docs/database.md`: both story-identity and Natural Earth sections.
- `853b57b8`, `config/reachability_baseline.json`: both #822 identity and #806
  receipts reasons for production reachability.
- `fdba1aee`, `tests/conftest.py`: both receipt snapshots/private storage and the
  never-created default TEST database route, installed before collection and
  the secret-store guard.

The [816/812 source review](review-816-812.md) at `b6898060` found no blocking
interaction: runtime/offline model registries, the TEST overlay, receipt hooks,
schema copying and inherited child-process isolation remain intact. The
[810/812/836 review](review-810-812-836.md) at `027ca3d7` found one concrete
reseed defect, addressed below; it found no other blocking interaction. Preserve
that report as the historical finding, not as an outstanding current defect.
The [ledger source review](review-ledger-integration.md) covers exact final
integration `f291dc79` and found no stale unquoted implementation/status claim.
These are source reviews; they do not substitute for the full gate.

The [PR review closeout](pr-review-closeout.md) and its captured API responses
record successful initial Claude reviews for PRs 1115–1118, actionable fixes,
and zero unresolved inline threads at capture. Initial reviews were on earlier
heads; no fresh post-fix Claude approval is claimed. Use the default pinned
Natural Earth manifest at landing, as the closeout note explains.

## 816 × 836 regression and repair

Real TEST reseeding uses `TRUNCATE ... CASCADE`, which removes the authoritative
junction rows without firing their row-level mirror triggers. Unified references
survived. Fix `9765bf1a` conditionally clears the unified table inside the same
transaction before truncation; pre-148 targets remain supported. The companion
836 documentation now names this explicit truncation cleanup.

At integration `188d9aab`, the new test applies real migration 148, writes one
reference of each kind through the production writer, verifies parity, and
executes two actual seeder CLI runs. It requires empty source/mirror references
while preserving the original chunk and all three entities.

- [Mutation harness](reseed-148-mutation.py.txt) removed only the cleanup and
  restored the seeder byte-for-byte in `finally`.
- [Red](reseed-148-red.txt): **1 failed**, at the intended post-reseed parity
  assertion. The real seed command itself succeeded.
- [Green](reseed-148-green.txt): **19 passed, 4 skipped**; the four skips are
  owner-corpus probes requiring `NEXUS_RUN_CORPUS=1`. The actual cross-slice
  regression ran and passed.
- [Pre-148 proof](reseed-pre148.txt): **2 passed, 1 skipped**; only the
  migration-148-specific regression skipped because that standalone checkout
  lacked the migration. A successful real CLI reseed ran there too.

Both integrated transcripts contain the secret-store guard, untouched-receipts
and no-owner-target summary lines. The full commands and provenance are in the
retained [lane verification](816-verification.md). The earlier whole-suite
attempt at `027ca3d7` was interrupted for this confirmed defect and has no passing
result; its interrupt-time pytest teardown error is not current-gate evidence.

## Runtime model verification

[Read-only model verification](models-verify.json) succeeded against the
integration checkout's artifact lock for **Octen-Embedding-4B** and
**deberta-v3-trecdl22** at `027ca3d7`. Changes through `f291dc79` are confined to
the reseed repair, its tests, migration comments and evidence, as recorded in
[the intervening file list](models-verify-head-diff.txt); model configuration,
lock and verifier code are unchanged. This is carried-forward artifact proof,
not a claim that a second model verification ran. No model download or lock
rewrite was part of that verification.

## Serial PostgreSQL full gate

The [runner](run_combined_gate.py.txt) began at `2026-10-08T16:23:27.112147+00:00`
and completed at `2026-10-08T17:30:33.804223+00:00`.
It requires a clean tree and the same head before each piece, refuses host load
above 24 before starting a piece, uses the main checkout's existing interpreter
with exact integration `PYTHONPATH`, and runs one piece at a time with nice 15.
It unsets `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`,
`NEXUS_RUN_LIVE_LLM`, and `NEXUS_RUN_CORPUS`, and sets `NEXUS_RUN_POSTGRES=1`.

With that environment and the integration checkout as the working directory,
the three commands are:

```sh
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_api
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery
```

| Piece | Captured result | Exit | Required summary checks |
|---|---|---|---|
| [Core](core.txt) | 3624 passed, 52 skipped, 30 warnings | 0 | All three present |
| [API](api.txt) | 887 passed, 4 skipped, 9 warnings | 0 | All three present |
| [Orrery](orrery.txt) | 2473 passed, 16 skipped, 2 warnings | 0 | All three present |
| Combined | **6984 passed, 72 skipped, 41 warnings** | 0 for each piece | All three in each piece |

The [final runner result](finalresults.json) records `state: passed`, exit 0 and
all guard checks for every piece. The [final checkout capture](final-head-state.json)
confirms exact `f291dc79`, an empty `git status --porcelain`, all nine feature
heads included, and `origin/main` still at `afd034f3`. The earlier
[draft result](results-at-draft.json) and [draft state](state-at-draft.json) are
retained as explicitly historical snapshots, superseded by these final results.

These three invocations partition the full `tests/` suite once. Offline tests
were included in this PostgreSQL-enabled gate; no separate whole-suite offline
run was performed or claimed. No extra pytest run was started to assemble this
document.

The Orrery transcript also records the #840 disposable-fixture timing:
`load_reference` **7.42 s**; `initialize_slot_database` from a loaded clone
**1.90 s**, versus **1.04 s** from an empty clone. These are measurements of that
test run, not an extrapolated fleet-loading or gate-duration estimate.

## Guard evidence and limits

Each completed piece reports:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
```

Core also lists fixture-registered disposable clusters and two admitted
`save_04` names on those private endpoints. Those names do not identify owner
slots on the owner server. All three completed pieces explicitly report
`psycopg2.extensions.ReplicationConnection` as an unaudited connection class.
The audit covers instrumented psycopg2/asyncpg paths in that pytest process;
standalone `pg_dump`/`psql`, unaudited child processes, other drivers, C-level
connection paths and unswept constructor references are outside its boundary.
The secret-store guard likewise is instrumentation, not an operating-system
sandbox. See `tests/dbname_audit.py` and `docs/agent_workflow.md` at the tested
commit for the exact limitations. Guard lines must not be represented as a
machine-wide proof of no database access.

Corpus and paid/live-LLM opt-ins were unset; skipped corpus probes are not
claimed executed. Owner-template reads used by fixture copying are distinct
from owner writes. This evidence does **not** claim owner-fleet migrations,
story-identity backfill, Natural Earth loading, restarts or index changes have
been performed. Backup/restore proof, fleet application and post-template-load
checks belong to the separate landing plan. All full-gate assertions remain
scoped to the tested integration head and the recorded guard boundaries.

Codex — GPT-6
