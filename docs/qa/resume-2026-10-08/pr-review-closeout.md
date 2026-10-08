# PR 1115–1118 review closeout

Fresh GitHub audit on 2026-10-08: all four PRs are OPEN, CLEAN/MERGEABLE, their head check rollups are SUCCESS, and all inline threads are resolved. The parent is running the combined gate at integration `027ca3d7`; this audit does not declare that gate passed.

| PR | Current head | Initial Claude review | Inline status |
|---|---|---|---|
| [1115](https://github.com/pythagorakase/nexus/pull/1115) | `5cff344d` | [37683818180](https://github.com/pythagorakase/nexus/actions/runs/37683818180), success | Three source-declaration concerns verified, replied and resolved now |
| [1116](https://github.com/pythagorakase/nexus/pull/1116) | `e79dfda0` | [37728133349](https://github.com/pythagorakase/nexus/actions/runs/37728133349), success | No inline threads |
| [1117](https://github.com/pythagorakase/nexus/pull/1117) | `f192fccd` | [37729705811](https://github.com/pythagorakase/nexus/actions/runs/37729705811), success | Three threads already resolved with prior concrete replies |
| [1118](https://github.com/pythagorakase/nexus/pull/1118) | `cf61a440` | [37730020784](https://github.com/pythagorakase/nexus/actions/runs/37730020784), success | Mapping-key redaction, coincident roots and read errors verified, replied and resolved now |

Initial Claude review heads were respectively `5830781b`, `78a92f35`, `7ac530a1`, and `e7f7a29d`. These are successful initial reviews, not fresh approval of the fix heads. The workflow-dispatch run's `head_sha=b0da93ea` is the default-branch workflow revision, not the reviewed PR revision. Later orchestration successes and comment-triggered skipped jobs are not new Claude reviews. Repository policy expects actionable feedback to be addressed and validated; it does not demand an unsolicited rereview after each fix.

#1115: 0009 now includes config/CLI; 0019 includes reader/LOGON; 0023 includes storyteller prompt. Source additions are pinned by the order-table checker, stamps are current, and implementation `4e29ad97` has fresh source/table/quote audits plus 120 passing document/reachability tests. Exact ledger equality and the prescribed Reason bullet are retained coordinator rulings, not overlooked review requests. Historical whole-suite evidence is labelled historical.

#1118: current code follows schema structure for safe location names, collapses identical resolved receipt roots, and wraps both invalid UTF-8 and filesystem read errors. Named regression tests cover real invalid TOML, subprocess envelopes, counts and unchanged files. Focused proof: 588 passed/18 PostgreSQL skips; exact implementation `9f728a2a` receipt/document rerun 58 passed. Retained repeated-write/pruning/path behavior is explicitly documented, not newly claimed fixed.

#1116 caveats: the remaining initial-review `--manifest` note is real—an operator can load an alternate release/count set that runtime readers reject against the repository manifest. Use the default pinned manifest at fleet landing; the initial reviewer treated this as a minor interface note. Non-psycopg failures during a multi-target load can abort with a traceback, which is fail-loud behavior; no silent success is claimed. The earlier documentation conflict about a single replay exception is fixed in current `docs/database.md`, which names both IDF rebuild and pinned Natural Earth replacement. Neither caveat is an unresolved inline blocker.

Raw evidence is under `review-closeout-1115-1118/`: the original REST/GraphQL snapshots, `initial-claude-runs.json`, six reply bodies/URLs and resolution responses in `actions.json`, and fresh `after-closeout.json`. No merge or new review was requested. All six public replies end with the required attribution.

Codex — GPT-6
