# 811 Runtime Module Move: Source Checkpoint

Status: implementation, caller adaptations and guard tests are authored. Runtime
proof, four negative controls, static comparisons and read-only command probes
are **pending**. No pytest, collection, PostgreSQL query, provider call, service
operation, build, push or PR was run for this source checkpoint. The coordinator
continues to own the serial heavy-proof slot.

Source base: `a8cc15c43bf33cf370cd07567604980152db1318`, the committed 823
journal/staging prerequisite. Its main merge base is
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The frozen 811-S3a order and
coordinator's staging/runtime-move refresh govern this slice. The order requires
four restoring controls after implementation; it does not require an initial
unchanged-product red run.

## Mechanical Move and Compatibility

The four implementations move whole: migration, setup and target-name boundaries
to `nexus/maintenance`, and narrative summary generation to `nexus/jobs`.
The [bounded diff](bounded-move.diff) compares each new file to its original at
the source base. A stdlib AST comparison found exact equality after only the
ordered import, bootstrap and `MIGRATIONS_DIR` adaptations; disposition comments
and Black do not change handler bodies. Logger names, command examples and main
blocks remain intact. The summary provider shim import remains as ordered.

The original paths are deliberate re-export wrappers. Their AST-derived export
counts are **23 / 27 / 2 / 12**, respectively; private exports are retained and
import-only names are excluded. Wrappers document that assigning a wrapper name
does not change an implementation binding. Commands retain their original
bootstrap and main blocks; no forwarding proxy or new console script is added.
No runtime path imports one of these four wrappers.

The [source inventory](source-inventory.json) records all 66 import-site edits and
all **44 actual test importers** at the prerequisite: the previously measured 42
plus the two 823 test modules. Runtime lazy imports remain lazy. Script module
objects in the benchmark and identity backfill now name the implementation,
preserving assignment/patch behavior. Mixed imports are split while unrelated
script imports remain. Operator-only named imports retain their compatibility
wrappers, command subprocess paths remain `scripts/...`, and the logging probe
keeps both the implementation and wrapper imports.

One recorded predecessor adaptation is essential: 823 made the IDF rebuild
script production reachable. Its two named imports of migration/target helpers
therefore also move to `nexus.maintenance`; leaving them on wrappers would keep
two wrappers in the production closure. Its ambiguous-commit handling and all
journal/maintenance/staging behavior remain unchanged.

The four DDL allowlist paths and the planted setup path now follow the moved
implementations, retaining 823's `_build_from_template` and `_restore_clone`
function names and all existing reasons/rules. The three prompt-lint paths move
with the summary module. Routing imports target implementations; the three
command wrappers join the existing command-import logging guard.

Exactly **18** surviving path-keyed exception entries are removed and their
existing contracts marked on the moved handler headers. 823 already removed the
two temporary-dump cleanup handlers counted in the frozen order's 20. No entry
is added, no marker includes a `noqa` suffix, and no swallowing behavior changes.

## Source Checks

Black ran at nice 15 with the shared interpreter, exact worktree `PYTHONPATH`,
cleared runtime/routing/libpq/PYTEST overrides and denied Keychain/provider access.
It formatted the mechanical changes. The permitted source reachability generator
produced [this result](source-reachability.txt), with every finding list empty.
It explicitly does not prove route reachability.

```sh
PYTHONPATH="$PWD" nice -n 15 "$PY" -S scripts/check_reachability.py \
  --write-baseline \
  --reason '#811 S3a: migrate, new_story_setup and database_targets move into nexus/maintenance and summarize_narrative into nexus/jobs; the scripts/ wrappers become operator paths'
```

The baseline delta is exactly five new production paths (the maintenance package
and four implementation modules), four removed script wrappers, and the reason;
the unreachable set is unchanged. No additional discovery exemption is added.
The new wrapper test uses literal `importlib.import_module` calls so its imports
remain visible to source analysis. [Operator explanations](wrapper-operator-chains.json)
show each wrapper's actual root: its own main for the three commands, and the
Natural Earth loader for `database_targets`.

Normal-hook results and the exact clean checkpoint head are recorded in the
coordinator handoff. These permitted source checks do not replace the pending
tests or flake8/mypy baseline comparisons.

The [canonical closure](canonical-source-closure.json) is AGENTS, turn-flow and
decisions 0010/0040. Seat precedence, scheduling and test-fixture behavior remain
the same; quoted rulings, statuses and document bodies stay intact. 0040's source
follows `new_story_setup` into its implementation path. The first three stamps
advance to the source merge base; 0040 already carries that stamp from 823 and
was reverified. Recompute after the final normal merge with current main.

## Pending Proof

Under the coordinator's serial admission, first prove the exact worktree import
path. Clear inherited runtime/routing/libpq/PYTEST/live flags; use `nice -n 15`,
load at most 24, private receipts, denied Keychain and paid-provider access.
Run the [source-derived focused selection](focused-selectors.json), split by
directory/file as needed, with `NEXUS_RUN_POSTGRES=1` and
`-p tests.dbname_audit`. Require final secret-store, receipt and owner-target audit
summaries. The paid summary importer remains gated with live flags unset; a
collection/skip is not a provider proof. No independent whole-suite/offline gate
is claimed; the coordinator owns combined integration coverage.

The four new guard subjects are explicit export identity, no runtime wrapper
imports, no tracked script/test wrapper-module binding, and all three real
`--help` commands from a foreign working directory. After green proof, plant and
restore each ordered violation separately: omit `_postgres_tools`; restore the
readiness wrapper import; restore the benchmark wrapper-module import; remove
the migration wrapper's main block. Capture the corresponding failure reason and
byte-identical restoration. Do not claim these controls have run yet.

Run document freshness, prompt/DDL ownership, reachability, migration-comment and
exception-baseline consumers. Compare flake8 for moved modules by diagnostic code
and source-line text against their then-current originals, and run sanctioned
`mypy --explicit-package-bases` on every changed Python file with a same-command
baseline comparison. Existing original diagnostics do not authorize new ones.

The two explicitly read-only owner command probes are still pending coordinator
scheduling: `scripts/migrate.py --status` (confirm its migrations directory) and
`scripts/rebuild_memory_idf.py --all --dry-run`, each under
`PGOPTIONS='-c default_transaction_read_only=on'` and exact worktree `PYTHONPATH`.
The foreign-directory QA-kit/operator import smoke is likewise pending. Neither
probe authorizes staging, sweeping or setup operations on owner slots.

## Predecessors and Landing

This branch preserves the committed 823 journal, validated maintenance targets,
identity lifecycle, current Natural Earth seed inventory, ir_eval schema copying,
asset-DDL refusal and all current command behavior. Later 809 fresh-NULL pin
changes must be ported into the moved setup implementation and its wrapper export
set; take the ordered deletion of `test_new_story_setup_config.py`. Do not restore
the old setup snapshot or remove new staging helpers while resolving conflicts.
Apply future changes from any still-edited `scripts` source to its implementation,
restore the wrapper, rescan importers and rerun the guards after each merge.

This slice adds no migration and performs no fleet work. Migrations 149/150/151
remain owned by their existing lanes. No `poetry install`, package-list change,
provider-shim relocation, UI rebuild or state-surface capture is included.
Owner services stay stopped; the next authorized startup must load the moved
code. The installed-main import smoke belongs to landing, after the paths exist
in the main checkout. Eventual publication says `Refs #811`; unrelated owner
questions remain outside scope.

Codex — GPT-6
