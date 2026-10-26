# 817-S4S5 Verification: Classification Ratchet, Generated-Document Registry and Ledger Currency

Branch `claude/817-registry-ratchet-ledger`, cut from `origin/main` at
`c7ae2988`. `git merge origin/main` before the re-stamp commit reported
"Already up to date", so the merge base stays
`c7ae2988d07b443f627a04d3a4eed1816b1cd438`: the 28 new records, the ledger
README and `AGENTS.md` carry it as `verified_commit`, and the baseline, the
record sources and the untracked-name checks below were computed against it.

Commands ran from the worktree root with `$PY=/Users/pythagor/nexus/.venv/bin/python`
and `PYTHONPATH=$PWD`; the import check printed
`/Users/pythagor/nexus/.claude/worktrees/817-S4S5/nexus/__init__.py`.
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` were unset. The
one-minute load before the PostgreSQL run was 18.40 (below 24; no wait). The
gates ran on a working tree whose content equals the final head except for
this evidence file (the re-stamps were in the working tree, uncommitted; the
freshness check counts uncommitted changes).

## Cited Lines at c7ae2988

- `tests/test_doc_front_matter.py:40-50` (`CLASSIFIED`, nine documents),
  `:172-178` (`classified_scope`), `:64-66` (the ledger comment),
  `:67-123` (`DECISION_LEDGER`, ends at 0055).
- `docs/decisions/README.md:4` (source `tests/test_doc_front_matter.py`),
  `:6` (stamp `d70a1991`), `:53-56` (generated documents, unchanged),
  `:73` (end of Scope and Validation), `:103-104` (`keeps execution
  state.`), `:106-162` (Records, ends at 0055).
- `docs/agent_workflow.md:24` (`passes the check again.`);
  `AGENTS.md:34` (source `docs/agent_workflow.md`), `:38` (stamp `a01c162f`).
- `tests/test_cli_reference_doc.py:9,25-26`; `tests/test_orrery/test_catalog.py:5,391-402`.
- `scripts/check_exception_dispositions.py:479-547` (`load_baseline` through
  `check_tree`), the shrink-only model.

## Baseline Computation

`classified_scope(repository_paths(ROOT))` holds 342 files; 64 have front
matter; of the 278 without it, 234 are under `docs/qa/`. Removing
`docs/qa/`, `README.md`, `CLAUDE.md` and the two registered generated
documents leaves 40, exactly the order's list. The merge of `origin/main` was
a no-op, so the set has no delta.

```json
{
  "schema_version": 1,
  "unclassified": [
    "backstory.md",
    "docs/agent_workflow.md",
    "docs/anthropic_structured_outputs.md",
    "docs/chunk_import.md",
    "docs/claim_producer_matrix.md",
    "docs/cli.md",
    "docs/color_scheme.md",
    "docs/database.md",
    "docs/dead_retrieval_subtraction.md",
    "docs/desktop.md",
    "docs/finish_line_milestones.md",
    "docs/generation_attempt_identity.md",
    "docs/geojson-integration.md",
    "docs/image-gallery.md",
    "docs/maptab_rebuild_spec.md",
    "docs/npc_knowledge_mechanics_research.md",
    "docs/offscreen_narration_retirement.md",
    "docs/openai_reasoning_models.md",
    "docs/openai_structured_outputs.md",
    "docs/orrery_audit_dashboard_notes.md",
    "docs/orrery_cooldown_classification.md",
    "docs/orrery_design_plan.md",
    "docs/orrery_dry_runs/chunk_0100.md",
    "docs/orrery_faction_vocabulary.md",
    "docs/orrery_intentions.md",
    "docs/orrery_needs.md",
    "docs/orrery_retrograde_spec.md",
    "docs/orrery_route_graph.md",
    "docs/orrery_state_vocabulary.md",
    "docs/orrery_tag_vocabulary.md",
    "docs/prompt_block_stability.md",
    "docs/prompt_caching_cream_2026_07_27.md",
    "docs/reachability.md",
    "docs/register_drift_study_2026_07_26.md",
    "docs/retrieval_query_bakeoff_2026_05_18.md",
    "docs/runtime.md",
    "docs/settings_scopes.md",
    "docs/skald_bakeoff_2026_07.md",
    "docs/trait_menu.md",
    "user_syntax_reference.md"
  ]
}
```

## Proof Runs

PostgreSQL proof set:

```text
$ NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_doc_front_matter.py tests/test_cli_reference_doc.py tests/test_orrery/test_catalog.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 6 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:64332 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:64333 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:64332 (psycopg2), save_04@local:64333 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
128 passed, 2 skipped, 2 warnings in 48.93s
```

The two skips are `tests/test_orrery/test_card_identity.py:122`: "Set
NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones."

Offline suites (the first ran 10 min 34 s; the harness moved it to the
background and it was awaited to completion):

```text
$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3219 passed, 678 skipped, 8 warnings in 634.66s (0:10:34)

$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 48.00s

$ nice -n 15 $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
54 passed, 5 warnings in 11.92s

$ nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
89 passed, 5 warnings in 7.07s
```

## Source Sweep

New lines against the 817-S3 output are only the five names untracked at
`c7ae2988` (0068, 0075, 0076, 0083). No listed source was removed and none
was added: every table source exists after the merge, and none of the five
untracked names is tracked.

```text
$ $PY docs/qa/817-decision-ledger/source_sweep.py $PWD
0010-the-gaia-seat.md
    UNTRACKED:~/.codex/config.toml (body lines 11)
0018-killed-c003.md
    UNTRACKED:doctrine.md (body lines 27)
0022-killed-c068.md
    UNTRACKED:doctrine.md (body lines 23)
0023-killed-c100.md
    UNTRACKED:doctrine.md (body lines 27)
    UNTRACKED:coverage_critique.md (body lines 27)
0068-incubator-column-comments.md
    UNTRACKED:tests/test_incubator_column_comments_pg.py (body lines 12)
0075-a-behavior-preserving-reachability-index.md
    UNTRACKED:docs/qa/1129-reachability-namespace-index/scaling_benchmark.py (body lines 11)
0076-the-offline-merge-gate.md
    UNTRACKED:.github/workflows/offline-tests.yml (body lines 11)
0083-retiring-old-scripts-and-retired-tag-gates.md
    UNTRACKED:nexus/providers/api_openai.py (body lines 16)
    UNTRACKED:nexus/providers/api_anthropic.py (body lines 16)
tracked files cited but not in sources: 0
exit 0
```

## Quote Audit

```text
$ $PY -S docs/qa/817-decision-ledger/quote_audit_s5.py $PWD
| Record | Source | Relay | Quoted lines | Match |
|---|---|---|---|---|
| 0056 | https://github.com/pythagorakase/nexus/issues/784#issuecomment-6043523766 | L41 | 11 | True |
| 0057 | https://github.com/pythagorakase/nexus/issues/788#issuecomment-6043524251 | L41 | 9 | True |
| 0058 | https://github.com/pythagorakase/nexus/issues/840#issuecomment-6043527972 | L41 | 12 | True |
| 0059 | https://github.com/pythagorakase/nexus/issues/823#issuecomment-6156195936 | L42 | 3 | True |
| 0060 | https://github.com/pythagorakase/nexus/issues/820#issuecomment-6156196220 | L42 | 4 | True |
| 0061 | https://github.com/pythagorakase/nexus/issues/824#issuecomment-6421993908 | L43 | 2 | True |
| 0062 | https://github.com/pythagorakase/nexus/issues/816#issuecomment-6421994645 | L43 | 2 | True |
| 0063 | https://github.com/pythagorakase/nexus/issues/815#issuecomment-6421995432 | L43 | 1 | True |
| 0064 | https://github.com/pythagorakase/nexus/issues/842#issuecomment-6421996124 | L43 | 1 | True |
| 0065 | https://github.com/pythagorakase/nexus/issues/813#issuecomment-6423067570 | C | 1 | True |
| 0066 | https://github.com/pythagorakase/nexus/issues/1102#issuecomment-6423072099 | C | 7 | True |
| 0067 | https://github.com/pythagorakase/nexus/issues/821#issuecomment-6423073509 | C | 3 | True |
| 0068 | https://github.com/pythagorakase/nexus/issues/1106#issuecomment-6423079194 | C | 4 | True |
| 0069 | https://github.com/pythagorakase/nexus/issues/842#issuecomment-6423079832 | C | 11 | True |
| 0070 | https://github.com/pythagorakase/nexus/issues/845#issuecomment-6423081217 | C | 9 | True |
| 0071 | https://github.com/pythagorakase/nexus/issues/812#issuecomment-6423082662 | C | 5 | True |
| 0072 | https://github.com/pythagorakase/nexus/issues/817#issuecomment-6423083545 | C | 2 | True |
| 0073 | https://github.com/pythagorakase/nexus/issues/815#issuecomment-6423086585 | C | 12 | True |
| 0074 | https://github.com/pythagorakase/nexus/issues/1126#issuecomment-6423092502 | C | 9 | True |
| 0075 | https://github.com/pythagorakase/nexus/issues/1129#issuecomment-6423094037 | C | 4 | True |
| 0076 | https://github.com/pythagorakase/nexus/issues/816#issuecomment-6423096474 | C | 8 | True |
| 0077 | https://github.com/pythagorakase/nexus/issues/1069#issuecomment-6423099961 | C | 7 | True |
| 0078 | https://github.com/pythagorakase/nexus/issues/1091#issuecomment-6423107274 | C | 7 | True |
| 0079 | https://github.com/pythagorakase/nexus/issues/824#issuecomment-6423109883 | C | 11 | True |
| 0080 | https://github.com/pythagorakase/nexus/issues/848#issuecomment-6423111652 | C | 5 | True |
| 0081 | https://github.com/pythagorakase/nexus/issues/802#issuecomment-6423123761 | C | 6 | True |
| 0082 | https://github.com/pythagorakase/nexus/issues/810#issuecomment-6423201171 | C | 1 | True |
| 0083 | https://github.com/pythagorakase/nexus/issues/811#issuecomment-6423208720 | C | 11 | True |
all 28 records match
exit 0
```

A planted one-byte change (`Reversal cost: Trivial.` to `trivial.` in
0073) made the audit print `0073: quoted block differs from comment
6423086585` and exit 1; the record was restored.

## Red Runs

Each plant was reverted before commit.

```text
(a)
E         Left contains one more item: 'docs/ratchet_plant.md: unclassified and not in config/doc_classification_baseline.json; add front matter (docs/decisions/README.md)'
1 failed, 5 warnings in 0.45s

(b)
E         Left contains one more item: 'docs/hybrid_search.md: unclassified and not in config/doc_classification_baseline.json; add front matter (docs/decisions/README.md)'
E         {'docs/hybrid_search.md': None} != {'docs/hybrid_search.md': 'historical'}
FAILED tests/test_doc_front_matter.py::test_unclassified_documents_are_baselined
FAILED tests/test_doc_front_matter.py::test_issue_817_classifications_hold - ...
2 failed, 5 warnings in 0.50s

(c)
        ), f"{doc_path} does not exist. Run: {ORRERY_CATALOG.regenerate}"
E       AssertionError: /Users/pythagor/nexus/.claude/worktrees/817-S4S5/docs/orrery_packages_plant.md does not exist. Run: python -m nexus.agents.orrery.catalog --write
1 failed, 5 warnings in 0.29s

(d)
E         Left contains one more item: "docs/decisions/README.md: the Records list lacks '- [0083: Retiring Old Scripts and Retired-Tag Gates](0083-retiring-old-scripts-and-retired-tag-gates.md)'"
1 failed, 5 warnings in 0.42s

(e)
E         {'0064': ('parked', 842, 'canonical')} != {'0064': ('decision', 842, 'canonical')}
1 failed, 5 warnings in 0.45s
```

(a) planted an untracked `docs/ratchet_plant.md` without front matter;
(b) removed the front matter of `docs/hybrid_search.md` (ratchet and the
`CLASSIFIED` pin both fail); (c) set `ORRERY_CATALOG.path` to
`docs/orrery_packages_plant.md` (`test_orrery_packages_md_is_up_to_date`);
(d) removed the 0083 Records line (`test_decision_ledger_follows_the_record_format`);
(e) set 0064's Kind to `parked` (`test_decision_ledger_backfill_holds`).
No red run plants baseline growth on the checkout: `origin/main` lacks the
baseline until this branch lands, so `prior` is `None` here;
`test_baseline_growth_is_checked_against_the_merge_base` proves growth.

## Static Checks

Head versions of the five changed or added Python files:

```text
## head black
All done! ✨ 🍰 ✨
5 files would be left unchanged.
## head flake8
flake8 exit 0
## head mypy
Success: no issues found in 5 source files
```

`origin/main` versions of the three pre-existing files, placed in the
worktree for the run and restored afterwards:

```text
## base (origin/main versions placed in the worktree) mypy --explicit-package-bases
Success: no issues found in 3 source files
## base flake8 (in worktree)
flake8 exit 0
```

No new diagnostics; no pre-existing ones.

```text
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
exit 0
```
