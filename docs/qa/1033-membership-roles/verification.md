# Issue 1033: Faction Membership Follows the Role

Branch `claude/1033-membership-roles`, cut from `origin/main` at `384634f9`.
No migration, no paid provider call, no gateway lane. No `save_NN` or
`NEXUS_template` was written; every PostgreSQL test ran on disposable
`qa640_`/`qa885_` clones under `-p tests.dbname_audit` (owner targets: none).

## What Was Wrong

On `origin/main`, the `/* orrery:faction_memberships */` query in
`nexus/agents/orrery/resolver.py` (line 665) built
`WorldState.faction_memberships` from every `faction_character_relationships`
row with no filter on `role`, and `substrate.faction_member`
(`nexus/agents/orrery/substrate.py:2106`, unchanged by this branch) answers
true for any membership it finds. The `faction_member_role` enum on
`NEXUS_template` is
`{leader,employee,member,target,informant,sympathizer,defector,exile,insider_threat}`,
so a character a faction hunts (`target`) or expelled (`exile`) counted as a
member in every package condition that uses `faction_member`. Latent: a
read-only count on 2026-09-30 found zero `faction_character_relationships`
rows on `save_02`, `save_03`, and `save_04`.

## What Changed

- `nexus.toml` `[orrery.resolver] membership_roles` (line 345), default
  `["leader", "employee", "member", "sympathizer"]`.
- `OrreryResolverSettings` in `nexus/config/settings_models.py` (line 1335),
  attached as `OrrerySettings.resolver`. The validator rejects an empty list,
  a label that is not a `FactionMemberRole` value, and a repeated label.
- `hydrate_world_state` takes `resolver_settings` and validates it through
  `coerce_resolver_settings` (typed model, the resolve phase's dumped
  mapping, or `None` for the typed `nexus.toml` settings). The membership query
  adds `AND fcr.role::text = ANY(:membership_roles)` with the list bound as a
  parameter (`resolver.py:705`). The resolve phase (`turn_cycle.py`), the dev
  endpoints, `explain_dry_run`, `analyze_coverage`, and
  `scripts/orrery_sample.py` pass the section through.
- `tests/pg_fixtures.py` `seed_faction_membership(dbname, *, character_id,
  faction_id, role)`, refusing owner databases (added to the refusal table in
  `tests/test_pg_disposable_target.py`).

## Replacement Comment for Migration 135 (For #819 Slice D, Migration 136)

This PR ships no migration. Migration 135 (`135_schema_docs_backfill.sql`,
line 96) comments `faction_member_role` with a final sentence that describes
the old conflation: "The Orrery membership loader counts every row as
membership whatever its role." Slice D of #819 (migration 136) should carry
this exact statement:

```sql
COMMENT ON TYPE public.faction_member_role IS
    'Position of a character in a faction, written by the offline faction relationship analyst (scripts/faction_relationship_analyst.py) and exposed as entity_relationships_v.relationship_type with scope faction_character. The Orrery membership loader counts a row as membership only when its role is listed in nexus.toml [orrery.resolver] membership_roles (default leader, employee, member, sympathizer).';
```

The replacement sentence alone:

> The Orrery membership loader counts a row as membership only when its role is listed in nexus.toml [orrery.resolver] membership_roles (default leader, employee, member, sympathizer).

## Tests

`tests/test_orrery/test_faction_membership_roles_pg.py` seeds one faction and
one character per `faction_member_role` label (read from the clone's live
enum) on a disposable clone, then:

- asserts the seeded labels equal the Python `FactionMemberRole` values that
  the settings validator checks against;
- hydrates with the shipped settings and asserts `faction_member` is true for
  exactly the configured roles, and that no other role's character carries the
  faction;
- narrows the list to `["leader"]` through `settings_with` and asserts only
  the leader is a member, both through the typed section and through the
  dumped mapping the resolve phase hands the resolver.

`tests/test_orrery/test_config.py` asserts the shipped default, that an
unknown label (`overlord`) in a copied `nexus.toml` fails `load_settings`, and
that an empty or repeated list fails validation.

Bite check: planting `AND (fcr.role::text = ANY(:membership_roles) OR TRUE)`
in the query fails both hydration tests
(`test_faction_member_is_true_for_exactly_the_configured_roles`,
`test_narrowed_membership_roles_change_hydrated_membership`; 2 failed,
1 passed); the plant was reverted.

## Settings Parity and Fingerprint

The #1021 parity walk (`tests/config/test_settings_parity.py`) and the
assembled-request fingerprint
(`tests/test_lore/test_assembled_prompt_fingerprint.py`) cover the legacy
façade roots (`Agent Settings.global`, `.LORE`, `.MEMNON`, `API Settings.apex`).
`load_settings_as_dict()` exposes Orrery only as the top-level `orrery` dump,
not under an alias block, so the new key adds no façade leaf and no fingerprint
input. Both pass unchanged.

## Proof

The order's proof section, verbatim:

> - `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit <the new test module> tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_project_contexts_live.py tests/test_orrery/test_recruit_ally_projects.py tests/test_pg_disposable_target.py` with gateway variables unset; `tests/test_config` and the settings parity tests offline (a new key must appear in the fingerprint the way #1021 pins it).
> - Offline `$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery` and `$PY -m pytest -q tests/test_api tests/test_orrery` (ten-minute shell limit: split by directory if needed); `tests/test_reachability.py`; Black, flake8, mypy on changed files.

`$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every command ran from the
worktree root with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset, and
`nexus.__file__` resolved under the worktree.

PostgreSQL gate, split into two runs:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_faction_membership_roles_pg.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_membership_roles_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
64 passed in 3.50s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_faction_project_contexts_live.py tests/test_orrery/test_recruit_ally_projects.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa885_faction_contexts_*, qa885_recruit_ally_projects_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
31 passed, 9 skipped in 3.51s
```

The nine skips are opt-in lanes, not PostgreSQL skips (`-rs`): eight in
`test_composition_sources_live.py` need `NEXUS_RUN_LIVE_LLM=1` (no paid calls
in this order) and one in `test_recruit_ally_projects.py:808` needs
`NEXUS_RUN_CORPUS=1`.

Settings, parity, fingerprint, and reachability, offline:

```
$ $PY -m pytest -q tests/test_config tests/config tests/test_orrery/test_config.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
279 passed, 5 warnings in 15.26s
```

Offline suite, split by directory:

```
$ $PY -m pytest -q tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1177 passed, 503 skipped, 7 warnings in 8.51s

$ $PY -m pytest -q tests/test_api -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
632 passed, 237 skipped, 7 warnings in 22.51s

$ PYTHONPATH=$PWD $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2608 passed, 391 skipped, 8 warnings in 367.13s (0:06:07)
```

The first run of the last command, without `PYTHONPATH`, failed
`tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[False]`
and `[True]` (2 failed, 2606 passed, 391 skipped). The test starts a
subprocess from a foreign directory; there the shared venv's editable install
resolves `nexus` to the main checkout (`/Users/pythagor/nexus/nexus/database.py`
in the traceback), whose `OrrerySettings` has no `resolver` field, while the
copied config is this worktree's `nexus.toml`:
`orrery.resolver Extra inputs are not permitted`. With `PYTHONPATH=$PWD` the
file passes (24 passed, 2 skipped) and so does the whole run above. It is a
worktree artifact, and the same mismatch is why the owner gateway must restart
after the pull.

Black, flake8, mypy on the changed Python files:

```
$ $PY -m black --check <11 changed .py files>
All done! ✨ 🍰 ✨
11 files would be left unchanged.
```

flake8 reports the same findings on the changed files as on `origin/main`
(E501 at pre-existing lines of `audit.py`, `resolver.py`,
`settings_models.py`, and F401 at `turn_cycle.py:507`; the sorted,
line-number-stripped lists are identical), none on lines this branch adds.
mypy over the seven changed modules reports 15 errors in 4 files at the head,
identical after stripping line numbers to the same files' errors from a
`git archive origin/main` export, so none are new. The repository's mypy run
cannot check the test modules on their own ("Source file found twice under
different module names"), a pre-existing configuration limit.

## Coordinator Note

This PR adds a `nexus.toml` key under `extra="forbid"` models. The owner
gateway imports the main checkout's code and reads the main checkout's
`nexus.toml`; restart it immediately after the pull so the running process
loads the model that knows `[orrery.resolver]`.
