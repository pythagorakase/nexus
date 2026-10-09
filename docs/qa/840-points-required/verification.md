# Required Place Points: Source Checkpoint

Status: source, migration and regression cases are authored. Runtime proof is
pending; this document claims no passing test, migrated owner database, fleet
survey, model call or live service result.

Base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The frozen840-S2 order
and coordinator's migration refresh govern this change. Migration149 remains
reserved here;150 and151 belong to the later recorded lanes. Migrations144–148
are already landed at this base, so their former sequence-gap exception no
longer applies.

## Behavior and Source Review

Place declarations require coordinates. Retrograde's expansion wire requires
`new_place_points` and validates exactly one normalized entry for each referenced
place outside the packet's first-class starting set, regardless of whether a
stored row later resolves it. Persistence copies points only to new place stubs,
retains existing points, and blocks a packet-known place that has no stored row
and no authored point. The low-level insert retains its own refusal guard.

The reusable Domain input permits an absent point for already resolved targets;
the provider-derived Domain grammar requires one. Both audit and apply refuse a
new name-only Domain without a point. Trait compilation, Retrograde persistence
and declared-entity insertion resolve the zone from the authored longitude and
latitude and write geography PointZM4326 with zero z/m.

Maturation refuses a legacy place without coordinates before generation and no
longer authors or changes points. The operator backfill helpers remain. The five
prompt edits use the frozen order's exact wording. The retired coordinate-cost
probe and its two tests are deleted; its historical evidence remains.

Migration149 guards INSERTs with NULL coordinates and UPDATEs that remove an
existing point. It does not backfill, scan, or rewrite a row. Legacy missing-point
rows remain editable and can gain a point. Its header labels the October7 fleet
counts as historical; a current read-only survey and the coordinator's reviewed
backup/application procedure are still owed at landing. The four object comments
match the work order verbatim.

An independent source review found no concrete correctness issue in production,
migration, or prompts. Root reviewed all30 adapted consumer files. A second
test review identified unordered comment matching; the migration test now
compares each comment against its named function, trigger or column. This is source review, not execution evidence.

## Required Regression Coverage

New migration cases cover all four place types, unrelated legacy-row updates,
point addition/removal, unchanged legacy xmin through migration replay, enabled
triggers and exact comments. Writer cases use distinct story and authored zones.
Persistence covers new-point writes, existing-point preservation, and a no-point
blocker without insertion. Domain tests cover both dry/apply refusal and strict
derived grammar. Declaration cases cover missing/null place points and rejection
of points on non-place declarations. A real queued maturation job over a deliberately
legacy row must fail without changing the job or place.

Existing public-table fixture inserts and declaration/expansion consumers are
adapted with authored fixture points. Only tests whose subject is legacy
missing-point data may disable the insert trigger, narrowly on their disposable
clone. The private minimal shadow schemas in test_geo_resolver_live and
test_recruit_ally_migration_pg retain their historical contracts. No change to
`tests/pg_fixtures.py`, the schema setup script or owner databases is permitted.
The complete [changed-test list](changed-tests.json) accompanies this checkpoint.

## Reachability and Canonical Documents

The only production baseline member removed is
`nexus/agents/orrery/geo_authoring.py`, with the exact prescribed reason. No other
baseline exemption or production path is removed. Retiring the probe leaves
`scripts/entity_reference_parity.py` test-only, reached from
`tests/test_chunk_entity_references_pg.py`; its classification records that root.
The actual pytest ratchet remains pending. Static graph inspection passed after the single classification correction; final
tracked-file checking also runs in normal hooks.

The [canonical closure](canonical-source-closure.json) is AGENTS plus decisions
0007,0016,0017,0034,0049,0055. Reverification preserves their text and rulings and
updates only their stamps. Frontmatter execution remains pending. No deleted
handler currently requires an exception-baseline change; the actual checker is
still owed.

## Pending Execution and Landing

The serial proof slot is now assigned to777 UI acceptance after the earlier
WaveA gate passed. That gate contains none of this lane. Black and normal
source hooks passed or are run by the normal commit at nice15/load below24; all pytest,
PostgreSQL, mypy,
build and browser phases wait. Required proof includes the frozen focused files,
all changed consumers, migration comment lint, reachability/frontmatter,
no-new-diagnostic static comparisons, and the coordinator's final immutable-tree
full gate. Retain denied secret-store, zero owner-target and private-receipt guard
summaries for every pytest phase.

Run both ordered negative controls on fresh disposable clones: remove both
CREATE TRIGGER statements and their two dependent COMMENT ON TRIGGER
statements from migration149 before constructing the clone, so the NULL-insert
test fails (retaining comments for absent triggers would fail setup instead); remove the expansion point validator call so the
missing-entry test fails. Restore sources/triggers and retain exact evidence.
Never weaken guards or invent a production point to obtain a pass.

Before landing, inspect current fleet counts and apply149 only through the
coordinator's separately recorded backup/migration checks. Owner services stay
stopped. Gateway restart is owed at the next authorized startup; no UI source
change or state-surface regeneration belongs to this lane. The optional paid
retry probe is outside this order and has not been run.

Codex — GPT-6
