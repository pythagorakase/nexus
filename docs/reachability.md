# Python reachability gate

`scripts/check_reachability.py` reads Python ASTs and configuration without importing
NEXUS, collecting pytest, connecting to PostgreSQL, or starting providers. It reports
possible module import paths from exact executable/discovery symbols. This implements
the reachability foundation from #808; it does not authorize deleting a reported orphan.

Run the same stdlib-only gate used by CI:

```sh
python -S scripts/check_reachability.py --report /tmp/nexus-reachability.json
python -S scripts/check_reachability.py --explain nexus/api/storyteller.py
python -S scripts/check_reachability.py --explain scripts/api_openai.py --kind operator
```

The JSON report includes every root and its authority, import edges with source line and
scope, reachability by role, test-only modules, existing orphans, unknown dynamic import
sites, dependency violations, and an explicit `route_reachability.status = not_proven`.
`--explain` returns one shortest import chain for the selected role. Counts by role overlap.

## Root inventory

`config/reachability.toml` declares the maintained Python scope: `nexus`, `scripts`,
`ir_eval`, Python migrations, and top-level Python files. Python test helpers are scanned
as graph nodes separately, within the configured pytest test paths. Archived tests are
excluded according to `pytest.ini`. Rust, TypeScript, shell, and skill-local scripts are
outside this gate.

- **Production:** exact CLI symbols from `[project.scripts]` in `pyproject.toml`, and exact
  ASGI symbols in the configured Python/uvicorn runtime service commands in `nexus.toml`.
  Unknown Python service command forms fail instead of silently acquiring a broad root.
- **Operators:** the explicit `path:symbol` inventory in `config/reachability.toml`, each
  with a concrete supported workflow as its reason. A file named `scripts/*.py` or a
  function called `main` alone supplies no operator authority.
- **Migrations:** the exact loader symbol and each managed migration's `run` symbol.
  Script-only exclusions must match the loader's literal `SCRIPT_ONLY_MIGRATIONS` list;
  the manual 008 seed executable is registered separately as an operator.
- **Tests:** initialization of matching test modules, explicitly configured test files,
  and their conftests (including ancestors up to the repository/configuration root).
  These discovery-only `<module>` roots include import-only setup and imported tests;
  they cannot be used as broad operator or production roots. Named test functions/class
  methods, conftest fixtures/hooks, and literal `pytest_plugins` declarations add explicit
  symbol evidence. Plugin declarations may be assigned or annotated in any collected
  module. This follows the configured AST discovery model, without running collection.

The checker verifies that each entry symbol exists in the parsed module. Importing a
package does not establish every child module as reachable. Explicit import aliases and
search paths account for the existing LORE/IR/script `sys.path` conventions; these change
import resolution, not root authority.

## Ratchet and baseline maintenance

`config/reachability_baseline.json` records existing unreachable modules and established
production paths. The initial inventory deliberately leaves legacy modules unclassified;
their presence in the baseline is neither maintenance approval nor a deletion decision.

The gate fails for a newly unreachable maintained module or an established production
module that loses its production path, even when tests still import it. Deleting a module
does not count as loss of its production path. Separate baseline maintenance findings
require adding newly established production paths and removing resolved orphan exemptions
and deleted production paths. This prevents a new path from going unrecorded and prevents
an old orphan exemption from hiding a later regression after the module becomes reachable.

When a change intentionally adds a production path, adopts an orphan, or deletes a module,
review the graph and update the checked-in inventory with the reason in the same change:

```sh
python -S scripts/check_reachability.py --write-baseline \
  --reason 'Describe the specific reviewed additions, adoption, or retirement.'
```

Review both baseline lists in the diff. Resolve unexpected lost paths/new orphans before
refreshing; `--write-baseline` is an explicit inventory replacement, not evidence that a
removal is safe. A reachability failure can call for restoring an import, registering a
supported executable, or removing genuinely retired code after its separate decision.

## Dynamic imports and retired names

Ordinary and relative imports, package initialization, deferred imports, and literal
`importlib.import_module`/`__import__` names produce edges. Literal relative `import_module`
names resolve against a literal package or the source module's `__package__`. Computed
package/name expressions and file-location loaders remain visible as dynamic sites.

An explicit dynamic edge names the exact source scope (`path:function`, including nested
symbols, or `path:<module>` for initialization), target Python file, and reason. Each
declaration must identify exactly one computed call. `expression` selects a Python call
using its normalized AST spelling; optional one-based `line` and zero-based `column`
disambiguate identical calls. A scope-only declaration is accepted only when that scope
contains exactly one dynamic site. Stale or ambiguous selectors fail, and other calls in
the same scope remain unregistered. Multiple target edges may describe one selected call.

For example, `expression = "import_module(module_name)"` pins the Retrograde event-source
test's declaration without depending on changing line numbers. Declarations supply
potential dependencies without turning either endpoint into a root. The migration
loader uses the same selection rules (`loader_expression`, optionally `loader_line` and
`loader_column`); its selected call is backed by the managed migration inventory.

Dependency direction is checked independently: application modules cannot import tests.
Optional tombstones can prohibit an exact path, Python symbol, literal within one Python
file, or key within one TOML file. Every entry requires its explicit retirement decision.
There are initially no tombstones: unresolved architectural choices are not retired names.

## Evidence limits

This is a conservative module import graph, not a call graph. Imports inside unused
functions, conditional branches, and type-checking blocks remain possible edges; source
scope is retained to explain them. AST symbol presence does not prove runtime callability.
Arbitrary alias rebinding, reflection, generated imports, and external pytest plugin
behavior are not fully modeled. External or unresolved top-level import names are exposed
in the report; missing internal module names and unregistered recognized dynamic loaders
fail the gate.

In particular, a reachable ASGI module does not prove router mounting or HTTP exposure.
For example, an API package's deferred import can make `storyteller.py` potentially
reachable without proving that its legacy routes are served. Route retirement requires
its own mounted-route and consumer evidence. No providers or live services should be
started merely to refresh this static report.

The ordinary pytest gate includes `tests/test_reachability.py`; CI also runs the standalone
checker without installing application dependencies and uploads its JSON evidence.
