# Character Dossier Tag Verification

## Scope and Cap Contract

Work order #910 extends the faction dossier's shared tag query to characters.
The baseline and featured rows retain `characters.id`; their tag join uses
`characters.entity_id`. The canonical presence roster still decides which
characters are featured. The shared `entity_tags_current` view owns soft clears,
deprecated tags, and synonyms. The existing faction world-time expiry rule is
shared unchanged; wall-clock `applied_at` is not a story clock.

The renderer appends `Tags: category:tag, category:tag` to character status and
featured-summary lines, preserving personality and emotional state. The scene tag
library and all `prompts/*.md` files are unchanged. The existing description at
`prompts/storyteller_core.md:130` already says the dossier carries character state;
no additional prose sentence is required for this change.

The coordinator amendment is implemented as `[lore.render_limits].character_tags`,
default 8 and validated `ge=1` by `RenderLimits` on `LORESettings`. It caps
attributed tags on each baseline and featured character line in query order.
Tests exercise limits 1, 8, and 12 through both writer and Gaia renderers.
Work order #908 adds its separate limits to this same typed table.

## Real Frontier Cost

Source `save_04` was read only. Its frontier was chunk **49**, at world time
**2189-10-17 18:37:00-04**. The first disposable clone,
`qa640_910_tags_942d9d0c89ad`, restored the existing Pass-2 fingerprint and executed
all seven real pre-generation phases: user input, warm analysis, entity queries,
deep retrieval, Orrery resolution, intertitle, and payload assembly. The input was
`Continue.` and the model override was TEST. Local retrieval models ran; no paid
provider or generation call ran. No story turn was committed.

The unchanged renderer recorded a successful #903 per-attempt guard before the
initial script hit a reporting-only `TypeError` (missing `day` argument to
`read_prompt_windows`). That record and the frozen payload were recovered.
A second clone, `qa640_910_compare_10e257c376b6`, supplied the real setting and
presence reads for the controlled comparison. Removing only the new character
summary fields exactly reproduced the old renderer's full block counts and total.
The after attempt restores those fields in the same frozen payload. Both owned
clones were dropped, including on the initial reporting exception.

| Measurement | Before | After | Delta |
|---|---:|---:|---:|
| Entity dossier | 1,791 | 2,137 | +346 |
| Complete TEST request | 38,883 | 39,237 | +354 |
| Available headroom | 32,117 | 31,763 | -354 |

The entity dossier grows 19.3%; the complete rendered request grows 0.91%.
The TEST guard counts `o200k_base` system text plus user prompt text, without a
paid-provider transport/schema estimate. Independently counted block joins create
a residual in `request framing` (-85 before, -77 after), which explains the
8-token difference between the dossier delta and the complete-request delta.
Every other block is identical, including the scene roster and tag library.
The frozen payload's `trimming` metadata describes the original assembly (no
chunks removed); per-attempt `block_tokens` and `input_tokens` are freshly measured.

`frontier-proof.json` holds the original pre-change record and both controlled
attempts. `usage-cli.txt` is the real CLI ledger output. The comparison run is
`c46a75ce-44d6-45a4-b3c7-7e56b43b6075`, writer attempts 1 and 2 (comparison labels,
not generation retries).

## Rendered Evidence

Actual writer dossier excerpt from the clone:

```text
- Kessa Brin: at None, tidying their own space Tags: bodyform.lineage:human, orrery_travel:route_familiar, orrery_travel:travel_ready
```

The source query resolving the holder was:

```sql
BEGIN READ ONLY;
SELECT c.id, c.name, c.entity_id,
       string_agg(t.category || ':' || t.tag, ', ' ORDER BY t.category, t.tag)
FROM characters c
JOIN entity_tags_current t ON t.entity_id = c.entity_id
WHERE c.name = 'Kessa Brin'
GROUP BY c.id;
COMMIT;
```

Kessa is character **18**, canonical entity **31**; the attribution does not
confuse subtype and canonical IDs. The dedicated PostgreSQL regression also
creates unequal IDs, plus tag rows that are soft-cleared, expired just before
and exactly at the frontier, live just after it, deprecated, and synonyms.

## Commands and Results

All commands ran from this worktree with:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/910-character-tags/nexus/__init__.py
```

No gateway or UI build was needed. No fleet/template migration was applied.
The regular PostgreSQL fixture helper migrated only its disposable databases.

The ignored reproduction scripts and full payload/logs are under
`temp/910-proof/`: `frontier.py` (initial assembly and old-renderer guard) and
`compare.py` (recovered before/after comparison). The initial reporting error is
retained in `frontier.log`, not counted as a passing command.

```sh
PYTHONPATH=$PWD $PY temp/910-proof/compare.py
```

```text
BEFORE ENTITY_DOSSIER 1791 TOTAL 38883
AFTER ENTITY_DOSSIER 2137 TOTAL 39237
UNCHANGED_RENDERER_BASELINE_MATCHED b720f576-753a-4d82-a456-f2f5b084099d
OWNED_CLONE_DROPPED qa640_910_compare_10e257c376b6
```

```sh
PYTHONPATH=$PWD $PY -m nexus.cli usage --run c46a75ce-44d6-45a4-b3c7-7e56b43b6075
```

Full output is in `usage-cli.txt`.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2640 passed, 804 skipped, 9 warnings in 110.70s (0:01:50)
```

These are the requested offline skips, not a PostgreSQL pass. The separately
opted-in PostgreSQL gates actually ran:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore -k 'dossier or entity or tag or render'
```

```text
58 passed, 219 deselected, 5 warnings in 12.46s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster.py tests/test_presence_roster_pg.py
```

```text
33 passed, 5 warnings in 12.50s
```

```sh
PYTHONPATH=$PWD $PY -m black --check nexus/agents/lore/utils/entity_queries.py nexus/agents/lore/logon_utility.py tests/test_lore/test_character_dossier_tags_pg.py tests/test_lore/test_character_dossier_render.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
```

No #885 failure appeared in either requested PostgreSQL gate.

Earlier focused checks:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore/test_character_dossier_tags_pg.py
```

```text
1 passed in 1.52s
```

The first fixture attempt had `NotNullViolation` because `factions.id` has no
sequence default. Supplying the fixture's explicit faction ID corrected it;
the successful run above and final PostgreSQL gate include that correction.

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore/test_character_dossier_render.py tests/test_lore/test_entity_queries.py
```

```text
6 passed, 5 warnings in 0.79s
```

Final disposable-database cleanup verification:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_910_%';
```

```text
 datname
---------
(0 rows)
```

## Capped Frontier Measurement

The frozen chunk-49 payload was rendered again against a fresh read-only-source
clone using the real TEST per-attempt guard. The uncapped comparison uses a
render limit of 10,000; the shipped comparison uses the configured eight.

| Measurement | Before Tags | Uncapped Tags | Capped at Eight |
|---|---:|---:|---:|
| Entity dossier | 1,791 | 2,137 | 2,137 |
| Complete TEST request | 38,883 | 39,237 | 39,237 |

No character in this frontier exceeds eight tags, so the cap does not reduce
this payload. The configured-cap tests establish truncation on longer lists.
`capped-frontier-proof.json` records all three attempts. No generation or paid
call ran, and the disposable clone was dropped.

```sh
PYTHONPATH=$PWD $PY temp/910-proof/capped_compare.py
```

```text
BEFORE ENTITY_DOSSIER 1791 TOTAL 38883
UNCAPPED ENTITY_DOSSIER 2137 TOTAL 39237
CAPPED ENTITY_DOSSIER 2137 TOTAL 39237
UNCHANGED_RENDERER_BASELINE_MATCHED b720f576-753a-4d82-a456-f2f5b084099d
OWNED_CLONE_DROPPED qa640_910_compare_134bd282fae8
```
