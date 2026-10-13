# Required Place Points: Source Checkpoint

Status: the source checkpoint below was authored by Codex on base 4ae8b8d2
without execution. The integrated wave-B tree carries this lane, the fixes
recorded under "Fixer Changes (2026-10-13)" and the proof recorded under
"Integrated-Tree Proof (2026-10-13)". The assembly moved the canonical
documents' `verified_commit` stamps to f073b371; the base and closure file below
still cite 4ae8b8d2, the lane's original base.

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

The Codex checkpoint recorded a source review with no command or output; it is
not execution evidence. A later independent Opus review (the coordinator's lane
findings) did find defects; the fixes are listed under "Fixer Changes
(2026-10-13)".

## Required Regression Coverage

New migration cases cover all four place types, unrelated legacy-row updates,
point addition/removal, unchanged legacy xmin through migration replay, enabled
triggers and exact comments. Writer cases use distinct story and authored zones.
Persistence covers new-point writes, existing-point preservation, and a no-point
blocker without insertion. Domain tests cover both dry/apply refusal and strict
derived grammar. Declaration cases cover missing/null place points and rejection
of points on non-place declarations. A queued maturation job over a deliberately
legacy row runs through `drain_maturation_jobs_sync`: the loader refuses it
before any provider call, and the runner records the failure on the job
(`failure_class` ValueError, the "which has no point" error, one attempt) while
the place keeps its NULL point.

Existing public-table fixture inserts and declaration/expansion consumers are
adapted with authored fixture points. Only tests whose subject is legacy
missing-point data may disable the insert trigger, narrowly on their disposable
clone. The private minimal shadow schemas in test_geo_resolver_live and
test_recruit_ally_migration_pg retain their historical contracts. No change to
`tests/pg_fixtures.py`, the schema setup script or owner databases is permitted.
The complete [changed-test list](changed-tests.json) accompanies this checkpoint.

## Reachability and Canonical Documents

This lane's only production baseline member removed is
`nexus/agents/orrery/geo_authoring.py`. The assembly merged the baseline's single
`reason` field into a combined multi-lane summary ("Combined #803 init/desktop,
#823 journal, #840 point policy and #811 maintenance-module closure; ...") that
does not carry the ordered 840-S2 sentence; the coordinator sanctioned the
combined wording, and 823-S1's fixer owns that file. No other 840-S2 baseline
exemption or production path is removed. Retiring the probe leaves
`scripts/entity_reference_parity.py` test-only, reached from
`tests/test_chunk_entity_references_pg.py`; its classification records that root.
The pytest ratchet ran on the integrated tree (see "Integrated-Tree Proof").

The [canonical closure](canonical-source-closure.json) is AGENTS plus decisions
0007,0016,0017,0034,0049,0055. Reverification preserves their text and rulings and
updates only their stamps. The front-matter test and the exception checker ran
on the integrated tree (see "Integrated-Tree Proof").

## Landing

Before landing, inspect current fleet counts and apply 149 only through the
coordinator's recorded backup and migration checks. Owner services stay stopped.
Gateway restart is owed at the next authorized startup; no UI source change or
state-surface regeneration belongs to this lane. The optional paid retry probe
is outside this order and has not been run.

Codex — GPT-6

## Fixer Changes (2026-10-13)

Branch `claude/waveb-fix-840-s2`, cut from integration head 7eb9a10c. The
coordinator committed the Gaia prompt trim before this fixer ran (3717a64b,
79332999; `prompts/storyteller_gaia.md` is 697 words and keeps the ordered
coordinates sentence and the pinned "riffs off it, never against it" phrase).
This fixer added:

- f4d424b8: `NewEntityDeclaration.coordinates` description shortened to "A place
  declaration carries its point; no other kind carries GIS data." (70
  characters). The ordered text (79 characters) exceeded
  `SKALD_WIRE_DESCRIPTION_MAX_CHARS = 70` (`tests/test_skald_wire.py:96`) in
  `test_wire_schema_size_and_description_budget`. The validator docstring keeps
  the ordered sentence with its quotes on their own lines (clears E501). The
  pinned Gaia request digest in
  `tests/test_lore/test_assembled_prompt_fingerprint.py` moves from
  `cac3d730f8b3e3081aa4f297a642694fb1f937ffd0639f4f906c70c14e11da6f` to
  `0003d4d83ad6d44a7658b580f68f30de01e23d12120051f987917af4b0916d3c` (a stale
  baseline made by this order's own prompt sentence and schema description).
  The writer digest stays
  `09b26dfed922d661ebbed44ac7f8e5621f5a21734d99d078c2718cb5b505cac6`:
  `SkaldWriterWire` has no `new_entities`, and the writer prompt carries
  neither the Gaia sentence nor the declaration schema.
- 1462f46b: coordinator ruling (b) for a re-declared legacy place. When a place
  declaration's name matches a pre-149 row without a point,
  `_fill_legacy_place_point` writes the declaration's point and the zone
  `resolve_zone_for_point` gives it (allowed by `trg_places_keep_point`); a row
  that already has a point keeps it; the enqueue path raises rather than queue
  a job for a place that still has no point. New PostgreSQL tests
  `test_redeclared_legacy_place_takes_the_authored_point` and
  `test_redeclared_pointed_place_keeps_its_point`.
  `test_pointless_place_target_is_not_matured` now runs the job through
  `drain_maturation_jobs_sync` on its own clone (`qa640_840s2_drain`) and
  asserts the recorded failure. The unused `Mapping` import is removed.
- ace4bac6: the migration-149 replay test clears the column comment before it
  deletes the stamp and pins the four comments verbatim from order item 1 (a
  second assertion still parses the migration file); it imports `migrate` from
  `nexus.maintenance`. The offline trait-compiler fake answers the
  point-to-zone query with `point_zone = 88`, distinct from `story_zone = 77`.
- 91f52e00: new mypy diagnostics on this lane's lines removed:
  `DomainTraitInput.coordinates` uses `Field(default=None, ...)` (same schema;
  mypy read the positional default as required), the new Domain refusal test
  passes every field as the file's other call does, and the GIS stub test types
  its payload and passes a `Coordinates` model.
- 9b755ba3: `tests/test_runtime/test_init_plan_pg.py:23` imports `migrate` from
  `nexus.maintenance` (the coordinator's one-line change), which
  `tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module`
  requires.

## Integrated-Tree Proof (2026-10-13)

`$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every command ran from the
worktree root with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`
unset. Each PostgreSQL run first read the one-minute load and waited in a
bounded loop (cap 20 minutes) while it was 24 or more; no run had to wait (each
tail shows the load read). Each tail names the commit it ran on; "dirty" counts
uncommitted files (the plant in a red run, the then-uncommitted mypy edits in
the last focused run). Commits after ace4bac6 change only the
`DomainTraitInput.coordinates` default spelling and tests; the files they touch
were rerun at those commits.

Import check: `PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'`
printed `/Users/pythagor/nexus/.claude/worktrees/fix-840-s2/nexus/__init__.py`.

### Red Run 1: Migration 149 Without Its Triggers

Plant (applied before the clones were made; restored with
`git checkout -- migrations/149_place_point_required.sql`, then
`git diff --quiet -- migrations/149_place_point_required.sql` printed
"restored: git diff --quiet clean"):

```diff
diff --git a/migrations/149_place_point_required.sql b/migrations/149_place_point_required.sql
index 34952363..ef7fcc16 100644
--- a/migrations/149_place_point_required.sql
+++ b/migrations/149_place_point_required.sql
@@ -39,18 +39,8 @@ END;
 $$;
 
 DROP TRIGGER IF EXISTS trg_places_require_point ON public.places;
-CREATE TRIGGER trg_places_require_point
-    BEFORE INSERT ON public.places
-    FOR EACH ROW WHEN (NEW.coordinates IS NULL)
-    EXECUTE FUNCTION public.places_refuse_missing_point();
 
 DROP TRIGGER IF EXISTS trg_places_keep_point ON public.places;
-CREATE TRIGGER trg_places_keep_point
-    BEFORE UPDATE OF coordinates ON public.places
-    FOR EACH ROW WHEN (OLD.coordinates IS NOT NULL AND NEW.coordinates IS NULL)
-    EXECUTE FUNCTION public.places_refuse_missing_point();
 
 COMMENT ON FUNCTION public.places_refuse_missing_point() IS 'Trigger function for trg_places_require_point and trg_places_keep_point: raises not_null_violation naming the place. Every place inserted since migration 149 carries a real-Earth point, whatever its type, and a point is never removed (#840, Decisions 840-Q5 and 840-Q6).';
-COMMENT ON TRIGGER trg_places_require_point ON public.places IS 'Refuses an INSERT of a places row whose coordinates is NULL, for every place type, virtual places and vehicles included.';
-COMMENT ON TRIGGER trg_places_keep_point ON public.places IS 'Refuses an UPDATE that sets a non-NULL coordinates to NULL. A row inserted before migration 149 without a point stays updatable and may gain a point.';
 COMMENT ON COLUMN public.places.coordinates IS 'Real-Earth point of the place (geography PointZM, SRID 4326, longitude as x; z and m are 0). Every row inserted since migration 149 carries one, authored by the structured output that introduced the place; a point is never removed. Rows inserted earlier may be NULL and are left as they are (#840).';
```

```
head: ace4bac6 dirty: 1
uptime before run: 12:35  up 5 days, 23:15, 5 users, load averages: 22.81 14.94 13.52 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_place_point_required_pg.py::test_insert_without_point_refused
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_840s2_guard_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_orrery/test_place_point_required_pg.py::test_insert_without_point_refused[fixed_location]
FAILED tests/test_orrery/test_place_point_required_pg.py::test_insert_without_point_refused[vehicle]
FAILED tests/test_orrery/test_place_point_required_pg.py::test_insert_without_point_refused[virtual]
FAILED tests/test_orrery/test_place_point_required_pg.py::test_insert_without_point_refused[other]
4 failed in 9.47s
exit: 1
```

Each of the four parametrized cases failed with
`Failed: DID NOT RAISE <class 'psycopg2.errors.NotNullViolation'>`.

### Red Run 2: Expansion Without `_new_place_point_issues`

Plant: delete the `issues.extend(_new_place_point_issues(...))` call at
`nexus/agents/orrery/retrograde_expansion.py:844-848`; restored with
`git checkout --`, then `git diff --quiet` on the path printed "restored: git diff
--quiet clean".

```
head: ace4bac6 dirty: 1
command: PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_orrery/test_retrograde_expansion.py::test_new_place_without_point_is_refused
E       Failed: DID NOT RAISE <class 'nexus.agents.orrery.retrograde_expansion.RetrogradeExpansionValidationError'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_retrograde_expansion.py::test_new_place_without_point_is_refused
1 failed, 5 warnings in 0.41s
exit: 1
```

### Red Run 3: Re-Declaration Without the Legacy Point Fill

Plant: delete the two lines in `_resolve_or_create_stub` that call
`_fill_legacy_place_point`; restored with `git checkout --` and proved with
`git diff --quiet`.

```
head: ace4bac6 dirty: 1
uptime before run: 12:35  up 5 days, 23:15, 5 users, load averages: 19.39 14.90 13.55 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_retrograde_maturation.py::test_redeclared_legacy_place_takes_the_authored_point
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_maturation799_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_orrery/test_retrograde_maturation.py::test_redeclared_legacy_place_takes_the_authored_point
1 failed in 2.53s
exit: 1
```

The row kept `lon`, `lat` and `zone` NULL where the test expects the authored
point (102.25, 12.5) and its zone.

### Focused PostgreSQL Proof Set

The order's focused command, split in two pieces under ten minutes.

```
head: ace4bac6 dirty: 0
uptime before run: 12:36  up 5 days, 23:16, 5 users, load averages: 19.19 15.43 13.81 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_place_point_required_pg.py tests/test_orrery/test_gis_stub_paths_live.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_retrograde_maturation.py tests/test_trait_compiler_integration.py tests/test_gis_scripts_live.py tests/test_orrery/test_gaia_registry_schema_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 23 targets: postgres, qa638_*, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_811_gaia_scene_*, qa640_840s2_drain_*, qa640_840s2_guard_* x6, qa640_840s2_persistence_*, qa640_maturation799_*, qa735_gis_scripts_* x3, qa735_gis_stubs_* x4, qa885_trait_compiler_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
93 passed, 1 skipped in 58.30s
exit: 0
```

```
head: ace4bac6 dirty: 0
uptime before run: 12:37  up 5 days, 23:17, 5 users, load averages: 23.64 18.05 14.95 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_entity_reference_parity_pg.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 20 targets: postgres, qa640_816_lifecycle_test_provider, qa640_836_parity_* x2, qa640_885_ren_replay_* x4, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55478 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55484 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55478 (psycopg2), save_04@local:55484 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
276 passed, 2 skipped, 2 warnings in 104.01s (0:01:44)
exit: 0
```

The skips are `test_live_openai_accepts_registry_gaia_strict_schema` (a paid
live gate behind `NEXUS_638_ENUM_E2E=1`) and `requires_corpus` tests. The
migration-gap test in `tests/test_orrery/test_migrate.py` passed: 149, 150 and
151 are all present on this tree.

### Changed Consumers

Every file `grep -rlE "INSERT INTO (public\.)?places" tests` lists plus every
test file this lane changed (`git diff --name-only c38df3b1 d59b2fca -- tests`
and this fixer's commits), less the files the focused set already ran and
`tests/pg_fixtures.py`: 36 files, in three pieces.

```
head: ace4bac6 dirty: 0
uptime before run: 12:40  up 5 days, 23:19, 5 users, load averages: 12.39 15.48 14.40 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_backstage_endpoints_pg.py tests/test_api/test_lore_adapter.py tests/test_api/test_reader_place_provenance_pg.py tests/test_api/test_reentry_wire_pg.py tests/test_api/test_return_recap_pg.py tests/test_bootstrap_episode_pg.py tests/test_character_name_reveals.py tests/test_commit_choice_presence_pg.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_character_dossier_tags_pg.py tests/test_lore/test_entity_phase_subtraction_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 64 targets: nexus_test_813_*, postgres, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_910_dossier_* x7, qa640_acceptance_* x38, qa640_uib_turn_*, qa832_recap_* x10, qa947_episode_*, qa950_place_* x2, qa_wt715_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_backstage_endpoints_pg.py::test_economics_matches_inspect_turn_for_a_test_turn
FAILED tests/test_lore/test_character_dossier_tags_pg.py::test_dossier_place_and_relationship_names
2 failed, 113 passed, 9 warnings in 202.36s (0:03:22)
exit: 1
```

Rerun of the two failures once:

```
head: ace4bac6 dirty: 0
uptime before run: 12:43  up 5 days, 23:23, 5 users, load averages: 17.65 15.40 14.57 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_backstage_endpoints_pg.py::test_economics_matches_inspect_turn_for_a_test_turn tests/test_lore/test_character_dossier_tags_pg.py::test_dossier_place_and_relationship_names
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_910_dossier_*, qa640_uib_turn_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_lore/test_character_dossier_tags_pg.py::test_dossier_place_and_relationship_names
1 failed, 1 passed, 9 warnings in 23.17s
exit: 1
```

`test_economics_matches_inspect_turn_for_a_test_turn` passed on rerun (a job
was leased mid-read the first time). `test_dossier_place_and_relationship_names`
fails deterministically with `psycopg2.errors.ForeignKeyViolation:
character_relationships.character2_id = 999999 names no characters row` from
`fn_relationship_entity_ids()` in migration 151 (836-S6a): the test deliberately
points a relationship at a missing character, which 151 now refuses. This lane
changed only the test's place insert; the failure belongs to the 836-S6a lane.

```
head: ace4bac6 dirty: 0
uptime before run: 12:44  up 5 days, 23:24, 5 users, load averages: 17.97 15.75 14.73 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_place_reference_validation.py tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_character_experiences_pg.py tests/test_orrery/test_character_identity_pg.py tests/test_orrery/test_claim_birth_coverage_pg.py tests/test_orrery/test_geo_resolver_live.py tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_orrery/test_place_point_contract.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_orrery/test_recruit_ally_migration_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 79 targets: nexus_test_pass2_* x7, postgres, qa640_* x18, qa640_geo_resolver_*, qa640_mig077_*, qa640_need_absence_* x7, qa640_roster798_* x11, qa640_settings_stamp_*, qa640_wizard_drain_* x3, qa649_*, qa679_*, qa_wt724_experience_* x26, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
194 passed, 9 warnings in 205.72s (0:03:25)
exit: 0
```

```
head: ace4bac6 dirty: 0
uptime before run: 12:47  up 5 days, 23:27, 5 users, load averages: 9.59 11.94 13.26 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_retrograde_expansion.py tests/test_orrery/test_retrograde_orchestrator.py tests/test_orrery/test_retrograde_projects_live.py tests/test_orrery/test_retrograde_retrieval_pg.py tests/test_orrery/test_weather_live.py tests/test_player_identity_consumers_pg.py tests/test_presence_roster_pg.py tests/test_skald_wire.py tests/test_trait_compiler.py tests/test_trait_input_derivation.py tests/test_travel_reachability_pg.py tests/test_wizard_opening_presence_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 46 targets: postgres, qa640_785_reach_* x3, qa640_projects799_*, qa640_retrieval_* x2, qa640_roster798_* x23, qa655_wizard_0743121dd3, qa655_wizard_23e3306ab7, qa655_wizard_31e9f2ced6, qa655_wizard_40471d937b, qa655_wizard_4cab0cbc03, qa655_wizard_617b6a4d97, qa735_weather_*, qa885_presence_baseline_*, qa_identity_surface_154ff14144, qa_identity_surface_59403930a8, qa_identity_surface_60087d5a05, qa_identity_surface_6dc3de787d, qa_identity_surface_983fcf10e2, qa_identity_surface_bead7165cc, qa_identity_surface_e18aebd807, qa_player_identity_ac620bdb33
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
299 passed, 1 skipped, 4 warnings in 146.54s (0:02:26)
exit: 0
```

After the mypy commit (dirty 3 is those edits, committed as 91f52e00):

```
head: ace4bac6 dirty: 3
uptime before run: 12:54  up 5 days, 23:33, 5 users, load averages: 7.12 9.45 11.66 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_trait_compiler_integration.py tests/test_orrery/test_gis_stub_paths_live.py tests/test_trait_input_derivation.py tests/test_trait_compiler.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa735_gis_stubs_* x4, qa885_trait_compiler_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
63 passed in 11.92s
exit: 0
```

At the final code commit:

```
head: 9b755ba3 dirty: 0
uptime before run: 13:09  up 5 days, 23:48, 5 users, load averages: 6.94 7.82 9.43 (waited 0s for load < 24)
command: env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_init_plan_pg.py tests/test_script_wrappers.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 7 targets: postgres, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
11 passed in 23.10s
exit: 0
```

### Migrated Clone: `\d+ places` and the Four Comments

`PYTHONPATH=$PWD nice -n 15 $PY <scratchpad>/fix-waveb-r2-840-S2/describe_places.py` (scratch script: `disposable_slot_database
("qa640_840s2_describe")`, then `psql -X -d <clone> -c '\d+ places'` and the
`obj_description`/`col_description` query; the clone is dropped on exit, and a
later `pg_database` query for `qa640_840s2%` returned no rows). Excerpt:

```
clone: qa640_840s2_describe_efb88e3ae4c6
 stamp
 151
 coordinates    | geography(PointZM,4326)  |           |          |                                                    | main     |             |              | Real-Earth point of the place (geography PointZM, SRID 4326, longitude as x; z and m are 0). Every row inserted since migration 149 carries one, authored by the structured output that introduced the place; a point is never removed. Rows inserted earlier may be NULL and are left as they are (#840).
Triggers:
    trg_places_entity_kind BEFORE INSERT OR UPDATE OF entity_id ON places FOR EACH ROW EXECUTE FUNCTION orrery_ensure_subtype_entity_kind('place')
    trg_places_forget_chunk_references AFTER DELETE ON places FOR EACH ROW EXECUTE FUNCTION chunk_entity_references_forget_subtype()
    trg_places_keep_point BEFORE UPDATE OF coordinates ON places FOR EACH ROW WHEN (old.coordinates IS NOT NULL AND new.coordinates IS NULL) EXECUTE FUNCTION places_refuse_missing_point()
    trg_places_require_point BEFORE INSERT ON places FOR EACH ROW WHEN (new.coordinates IS NULL) EXECUTE FUNCTION places_refuse_missing_point()
    trg_places_set_updated BEFORE UPDATE ON places FOR EACH ROW EXECUTE FUNCTION set_updated_at()
-[ RECORD 1 ]-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
object  | FUNCTION public.places_refuse_missing_point()
comment | Trigger function for trg_places_require_point and trg_places_keep_point: raises not_null_violation naming the place. Every place inserted since migration 149 carries a real-Earth point, whatever its type, and a point is never removed (#840, Decisions 840-Q5 and 840-Q6).
-[ RECORD 2 ]-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
object  | TRIGGER trg_places_keep_point ON public.places
comment | Refuses an UPDATE that sets a non-NULL coordinates to NULL. A row inserted before migration 149 without a point stays updatable and may gain a point.
-[ RECORD 3 ]-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
object  | TRIGGER trg_places_require_point ON public.places
comment | Refuses an INSERT of a places row whose coordinates is NULL, for every place type, virtual places and vehicles included.
-[ RECORD 4 ]-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
object  | COLUMN public.places.coordinates
comment | Real-Earth point of the place (geography PointZM, SRID 4326, longitude as x; z and m are 0). Every row inserted since migration 149 carries one, authored by the structured output that introduced the place; a point is never removed. Rows inserted earlier may be NULL and are left as they are (#840).
```

The four comments equal order item 1 verbatim (also pinned in
`tests/test_orrery/test_place_point_required_pg.py`).

### Read-Only Fleet Survey

```
command: for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do PGOPTIONS='-c default_transaction_read_only=on' psql -X -d $db -At -F ' | ' -c "SELECT current_database(), (SELECT max(version) FROM schema_migrations) AS stamp, count(*) FILTER (WHERE coordinates IS NULL) AS pointless, count(*) AS places, (SELECT count(*) FROM pg_trigger WHERE tgrelid='places'::regclass AND tgname IN ('trg_places_require_point','trg_places_keep_point')) AS guard_triggers, current_setting('transaction_read_only') AS read_only FROM places"; done
columns: database | stamp | places without a point | places | 149 guard triggers | read_only
NEXUS_template | 148 | 0 | 0 | 0 | on
save_01 | 148 | 27 | 77 | 0 | on
save_02 | 148 | 27 | 77 | 0 | on
save_03 | 148 | 3 | 5 | 0 | on
save_04 | 148 | 5 | 7 | 0 | on
save_05 | 148 | 0 | 0 | 0 | on
command: for db in save_01 save_02 save_03 save_04 save_05; do PGOPTIONS='-c default_transaction_read_only=on' psql -X -d $db -At -F ' | ' -c "SELECT current_database(), count(*) AS place_jobs, count(*) FILTER (WHERE p.coordinates IS NULL) AS place_jobs_without_point FROM orrery_maturation_jobs j JOIN places p ON p.id = j.entity_subtype_id WHERE j.entity_kind = 'place'"; done
save_01 | 0 | 0
save_02 | 0 | 0
save_03 | 0 | 0
save_04 | 0 | 0
save_05 | 0 | 0
```

No database is at 149 yet; the counts (27, 27, 3 and 5 places without a point)
match the order's 2026-10-07 survey, and no maturation job targets a place.

### Static Checks

```
head: 9b755ba3
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_skald_wire.py tests/test_lore/test_assembled_prompt_fingerprint.py tests/test_lore/test_two_pass_pipeline.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
259 passed, 2 skipped, 5 warnings in 25.17s
$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
exit: 0
$ PYTHONPATH=$PWD $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
exit: 0
$ $PY -m black --check $(cat changed_py.txt)
47 files would be left unchanged.
exit: 0
```

`scripts/check_migration_comments.py` and `test_reachability.py` /
`test_doc_front_matter.py` also passed at ace4bac6 with the same output.

Flake8 (`$PY -m flake8 --config .flake8` over the 47 Python files this lane
and its fixer added or modified, against the same files at `origin/main`
f073b371 exported with `git show` into scratch; compared by file, code and
message with line numbers removed): main 85 diagnostics, head 73; added 0,
removed 12 (E501 lines in test files rewritten by the lanes).

Mypy (`PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases <files>` on the same
47 files at head, and on the 45 that exist at `origin/main` inside a
`git archive origin/main nexus tests scripts pyproject.toml` export): main 232
errors, head 231. Added on head: three diagnostics in
`tests/test_api/test_backstage_endpoints_pg.py` at lines 16 (`import requests`,
missing stubs) and 986 (`Item | Container` indexing); `git blame` attributes
both lines to 7557f00c "Specify Backstage elapsed time and observation
regressions", another wave-B lane. No added diagnostic sits on an 840-S2 line.

### Offline Suites

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice
-n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`
(head 91f52e00; it ran 11 m 51 s):

```
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
2 failed, 3195 passed, 671 skipped, 8 warnings in 711.65s (0:11:51)
```

The wrapper failure named `tests/test_runtime/test_init_plan_pg.py:23`; 9b755ba3
fixes it (`tests/test_script_wrappers.py` passes in the final-commit run above).
`test_transition_rejects_missing_diegetic_timestamp` fails with "Unit test
attempted psycopg2.connect"; this lane touches no wizard code, and the wave-B
commits that change the wizard paths are d0e9d848 ("Store wizard transcripts in
each slot database") and 95a45ca1.

`tests/test_api` offline (head 9b755ba3): `2 failed, 547 passed, 330 skipped`;
both failures are `tests/test_api/test_wizard_confirmation.py::
test_final_transition_cannot_bypass_artifact_acceptance` (setting_confirmed,
character_confirmed) with the same "attempted psycopg2.connect" cause; the
file's last change is d0e9d848.

`tests/test_orrery` offline (head 9b755ba3): `9 failed, 1349 passed, 1189
skipped`: `test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy`
(the message now says "emitted by background branches") and eight
`test_worker.py` tests (`orrery.projects.milestone_magnitude must be >=
orrery.promote.magnitude_threshold`); both come from the settings validators,
which this lane does not touch (dec6f76c "Require typed settings in remaining
product readers" is the wave-B commit on that path).

### Coordinator's Steps

- The whole-tree PostgreSQL gate.
- The state-surface regeneration (this lane changes no UI file).
- Fleet application of migration 149 (`python scripts/migrate.py --all`, then
  `--slot 1 --write-locked-slot`, then `nexus doctor`).
- The optional paid retry probe (not run; no paid call was made).
