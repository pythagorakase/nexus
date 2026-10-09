# Remaining Wave A: Shared Integration Verification

**Full Python gate passed: 7056 passed, 72 skipped, 41 warnings.** All three serial pieces
exited zero and reported the required secret-store, receipt-isolation and
owner-target summaries. This is evidence for the assembled integration, not
a claim that each standalone feature branch ran a separate full gate.

Tested head: `2cc9a5fcff76e0c643ca41490eb2508b870b4850`. Tested tree: `3804225e54624e7739c6f6d143cc00b804892a3b`.
The frozen comparison base was `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The completed runner records
`2026-10-08T22:36:27.619288+00:00` through `2026-10-09T00:28:53.513912+00:00`, and imported
`/Users/pythagor/.codex/worktrees/resume-claude-integration/nexus/nexus/__init__.py`. The assembly-time [checkout capture](final-head-state.json)
confirms that exact integration was still clean and contained these inputs:

| Lane | Included input |
| --- | --- |
| 820 | `4fffb85b6008e76c3d14ce750666cf73bc802c6e` |
| 815 | `5fcc76e43428a570f095e10d8944fdc93b321e27` |
| 812 | `1b87677113eb0b30003d3b1713e9dd1a89ab4454` |
| 777 | `149704d16fa126b8ac9d142a22bf51b42a669552` |

820 is only the carrier of this common evidence. Its source head at assembly
was `4fffb85b6008e76c3d14ce750666cf73bc802c6e`; this directory adds no production, configuration, UI,
test or baseline changes. The [provenance manifest](artifact-provenance.json)
records the source and SHA-256 of retained inputs and generated payloads.
The final completion record hashes that manifest as well; no file claims to
contain its own hash.
`COMPLETE.json` is written last; its absence means assembly did not complete.

## Complete Serial Gate

The [raw runner](run_next_combined_gate_resumed.py.txt) used the integration
checkout as cwd and exact PYTHONPATH, the shared interpreter, nice15 and the
load cap. It cleared inherited pytest-selection/plugin, runtime routing,
database-target/template and paid/corpus/secret-store opt-ins. It checked the
same clean head before and after each piece. Exact commands:

```sh
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_api
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery
```

Counts below are parsed from each raw log's final pytest summary, not inferred
from prior runs or manually entered. The [metadata](assembly-metadata.json)
retains those literal summary lines and command arrays alongside the table.

| Piece | Final summary | Exit | Guards |
| --- | --- | --- | --- |
| [core](core.txt) | 3686 passed, 52 skipped, 30 warnings in 1877.30s (0:31:17) | 0 | All three present |
| [api](api.txt) | 897 passed, 4 skipped, 9 warnings in 732.01s (0:12:12) | 0 | All three present |
| [orrery](orrery.txt) | 2473 passed, 16 skipped, 2 warnings in 4130.57s (1:08:50) | 0 | All three present |
| Combined | **7056 passed, 72 skipped, 41 warnings** | All zero | All three in each piece |

The [completed raw result](results.json) records state `passed`. These three
invocations partition the full `tests/` suite once; offline tests are included
in the PostgreSQL-enabled run. No separate whole-suite offline run is claimed.
UI state-surface regeneration and the full UI test suite remain separately
documented in the 777 lane; this Python gate does not certify those checks.

## Earlier Failed Attempt

The [earlier raw result](historical-failed-attempt/results.json) and
[core transcript](historical-failed-attempt/core.txt) remain distinct history:
`849eeef4d673277b6f88f9412e2c0643a916e7d7`, core exit1, `1 failed, 3685 passed, 52 skipped, 30 warnings in 1840.34s (0:30:40)`. API and Orrery were
not started in that attempt. Its passes are not added to the current totals.
The retained [runner](historical-failed-attempt/run_next_combined_gate.py.txt)
is the exact earlier source.

The sole recorded failure was the new UI endpoint's docstring triggering the
existing prompt-prose lint. [The repair diff](historical-failed-attempt/repair.diff)
changes that docstring only. The existing
[777 evidence at the included head](https://github.com/pythagorakase/nexus/blob/149704d16fa126b8ac9d142a22bf51b42a669552/docs/qa/777-shell-ui-bundle/verification.md)
retains the focused repair proof and original stopped-gate disposition. The
current three-piece result supersedes the failed attempt only for Python gate
completion; historical logs and their original claims were not rewritten.

## Existing Focused and Manual Evidence

- [820: existing lane evidence](https://github.com/pythagorakase/nexus/blob/4fffb85b6008e76c3d14ce750666cf73bc802c6e/docs/qa/820-home-anchors/verification.md).
- [815: existing lane evidence](https://github.com/pythagorakase/nexus/blob/5fcc76e43428a570f095e10d8944fdc93b321e27/docs/qa/815-chunk-range/verification.md).
- [812: existing lane evidence](https://github.com/pythagorakase/nexus/blob/1b87677113eb0b30003d3b1713e9dd1a89ab4454/docs/qa/812-models-plan-fetch/verification.md).
- [777: existing lane evidence](https://github.com/pythagorakase/nexus/blob/149704d16fa126b8ac9d142a22bf51b42a669552/docs/qa/777-shell-ui-bundle/verification.md).

Those records retain their original source heads and exact outcomes. Their
links do not imply a new download, model verification, browser run or focused
test repetition during evidence assembly. Subsequent freshness stamps or
landing merge resolutions require a separate delta record; they do not change
which commit this full gate tested.

## Guard Evidence and Limits

Each completed piece contains:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
```

The audit covers instrumented psycopg2/asyncpg calls in the pytest process.
Fixture-registered private clusters may admit save-style database names;
those are distinct from owner-server slots. The C-level
`psycopg2.extensions.ReplicationConnection` class, unaudited child processes,
other drivers and unswept captured constructors remain outside interception.
Fixture `pg_dump`/`psql` reads of the owner template are outside this driver
audit. These lines do not establish machine-wide absence of database access.
The secret-store guard is instrumentation, not an OS sandbox; its documented
child/exec/native-call limits still apply. Exact limitations are in
`docs/agent_workflow.md` and `tests/dbname_audit.py` at the tested commit.

Paid/live and corpus opt-ins were unset. Skipped opt-in probes are not claimed
executed. No migration, fleet application, owner model change, service startup
or paid inference is part of this evidence assembly. Owner service operations
remain separate from publication and this gate.

Codex — GPT-6
