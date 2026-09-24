# Dossier Truth Verification

Work Order 916-B; branch `claude/916-dossier-truth`. Coordinator amendment: omit absent activity as well as absent location, without placeholder text. No schema or configuration changes.

## Frontier Proof

`probe.py` snapshots save_04 into a uniquely named `qa640_916_dossier_*` database, restores chunk 49's existing Pass-2 baseline, runs real LORE assembly with LOGON disabled, and measures real TEST requests for both seats. It drops the clone on exit. No gateway or paid inference was used.

The source is read only. The import check printed:

```text
/Users/pythagor/nexus/.claude/worktrees/916-dossier-truth/nexus/__init__.py
```

Both seats have byte-identical dossiers within each capture. See `before-*-dossier.txt` and `after-*-dossier.txt`; complete requests are also archived. Examples from the writer dossier:

| Before | After |
| --- | --- |
| `Davin Sol: at 1, …` | `Davin Sol: at Lantern Quay Memorial Hall, …` |
| `Hale Morrow: at None, pacing the near ground` | `Hale Morrow: pacing the near ground` |
| `Nera Voss: at None, None` | `Nera Voss` |
| `Unknown → Unknown: spouse (valence +0e-20)` | `Ren Vale → Elian Rook: spouse (valence +0.00)` |
| `Unknown → Unknown: complex (valence -0.18181818181818181818)` | `Ivo Senn → Ressa Morn: complex (valence -0.18)` |

| Seat | Dossier Before | Dossier After | Request Before | Request After |
| --- | ---: | ---: | ---: | ---: |
| Writer | 2182 | 2182 | 37284 | 37284 |
| Gaia | 2182 | 2182 | 34676 | 34676 |

These are TEST token-counter measurements. `before.json` and `after.json` contain every block count. All block counts and block kinds are unchanged from the original before-capture. The amendment removes two dossier tokens per seat relative to the accepted first implementation. Featured-character details and the following place/faction details are byte-identical. The relationship cap remains configured and the captured five relationship types retain their original order.

Both restores and both live configuration fingerprint computations agree:

```text
a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7
```

## Implementation Evidence

- `nexus/agents/lore/utils/entity_queries.py:103`: left join resolves baseline `current_location_name`; featured query retains the existing location field and details.
- `nexus/agents/lore/utils/entity_queries.py:393`: canonical character names resolve through scalar subqueries, preserving the relationship scan rather than introducing join-order effects into the existing cap. A relationship touching a featured character with an absent counterpart is also fetched, logged, and excluded. Defect identity is the table's composite primary key `(character1_id, character2_id)`.
- `nexus/agents/lore/utils/turn_cycle.py:621`: shared assembly resolves and filters relationships once before either seat renders.
- `nexus/agents/lore/logon_utility.py:2509`: only present location/activity segments contribute to the status; absent status omits the colon while retaining tags. `after-skald_writer-dossier.txt:17` and `after-gaia-dossier.txt:17` both contain exactly `- Nera Voss`.
- `tests/test_lore/test_character_dossier_render.py:148` and `tests/test_lore/test_character_dossier_tags_pg.py:298`: exact-line assertions cover NULL activity with and without a location in both seats; offline coverage also checks tags without any status.
- `nexus/agents/lore/logon_utility.py:2621`: existing render cap and signed `.2f` valence formatting apply to both seats.
- The real PostgreSQL regression test uses template schema, `characters`, `places`, `character_relationships`, entity/tag views, roster and provenance tables. All mutations occur in disposable fixture databases. A deliberately removed FK inside an uncommitted disposable transaction allows an absent endpoint to exercise the defect path; its ID is logged once, with no relationship line in either seat.

## Validation

Commands run from the worktree root. `$PY` denotes `/Users/pythagor/nexus/.venv/bin/python`.

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
PYTHONPATH=$PWD $PY docs/qa/916-dossier-truth/probe.py --phase after
```

Only `--phase after` was rerun for the amendment; the original before-captures are untouched. The refreshed capture ends with:

```text
PASS: restored fingerprint; both seats have identical dossiers; TEST only
```

The following gates were rerun after the amendment. Offline skips are not PostgreSQL proof; the explicit PostgreSQL gate actually runs the selected tests.

```sh
$PY -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2718 passed, 900 skipped, 9 warnings in 121.40s (0:02:01)
```

```sh
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_lore -k 'dossier or entity or relationship or render'
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
95 passed, 232 deselected, 5 warnings in 26.24s
```

```sh
$PY -m black --check nexus/agents/lore/utils/entity_queries.py nexus/agents/lore/utils/turn_cycle.py nexus/agents/lore/logon_utility.py tests/test_lore/test_character_dossier_render.py tests/test_lore/test_character_dossier_tags_pg.py tests/test_lore/test_logon_prompt_formatting.py docs/qa/916-dossier-truth/probe.py
```

```text
All done! ✨ 🍰 ✨
7 files would be left unchanged.
```

`git diff --check` passed with no output. The accepted implementation commits remain intact; amendment commit runs the standard hooks. No #885 exemptions were needed.

## Cleanup and Coordinator Questions

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_916_dossier_%';
```

```text
 datname 
---------
(0 rows)
```

No services were started. No fleet/template migrations, save writes, or paid provider calls were made. Nothing deferred; no open questions. The coordinator owns review and landing.
