"""Static reachability regressions; fixture modules must never be imported."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
import tomllib

import pytest

from scripts.check_reachability import (
    REPO_ROOT,
    analyze_repository,
    baseline_findings,
    classification_findings,
    explain_reachability,
)

CLASSIFICATION_LISTS = (
    "unclassified_paths",
    "classified_paths_not_in_repository",
    "class_graph_mismatches",
)


def _write(root: Path, path: str, source: str) -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source)


@pytest.fixture()
def static_repo(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Build an executable-looking corpus whose imports would fail immediately."""
    sources = {
        "pyproject.toml": '[project.scripts]\ndemo = "pkg.cli:main"\n',
        "nexus.toml": (
            "[runtime.services.gateway]\n"
            'command = ["{python}", "-m", "uvicorn", "pkg.api:app"]\n'
        ),
        "pytest.ini": "[pytest]\ntestpaths = tests\nnorecursedirs = archive\n",
        "pkg/__init__.py": 'raise RuntimeError("APPLICATION MUST NOT BE IMPORTED")\n',
        "pkg/cli.py": "def main():\n    from . import helper\n",
        "pkg/api.py": "app = object()\n",
        "pkg/helper.py": "value = 1\n",
        "scripts/migrate.py": (
            'SCRIPT_ONLY_MIGRATIONS = ["008"]\ndef load(path):\n    pass\n'
        ),
        "tests/test_example.py": "def test_example():\n    import pkg.helper\n",
    }
    for path, source in sources.items():
        _write(tmp_path, path, source)
    config = {
        "version": 1,
        "maintained": ["pkg/**/*.py", "scripts/**/*.py", "migrations/*.py"],
        "baseline": "baseline.json",
        "production": {
            "project_config": "pyproject.toml",
            "runtime_config": "nexus.toml",
        },
        "pytest": {"config": "pytest.ini"},
        "migrations": {
            "loader": "scripts/migrate.py:load",
            "pattern": "migrations/[0-9][0-9][0-9]_*.py",
            "symbol": "run",
            "script_only_versions": ["008"],
            "reason": "Registered migration loader",
        },
    }
    return tmp_path, config


def _baseline(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "unreachable": report["unreachable"],
        "production_reachable": report["reachable_by_kind"]["production"],
    }


def test_static_graph_follows_relative_namespace_and_literal_dynamic_imports(
    static_repo,
) -> None:
    """Potential deferred imports are followed without executing package code."""
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        """import importlib as loader

def main():
    from . import helper
    from pkg.namespace import leaf
    loader.import_module("pkg.dynamic")
""",
    )
    _write(root, "pkg/namespace/leaf.py", "value = 2\n")
    _write(root, "pkg/dynamic.py", "raise RuntimeError('NEVER IMPORT')\n")
    report = analyze_repository(root, config)
    assert {
        "pkg/__init__.py",
        "pkg/helper.py",
        "pkg/namespace/leaf.py",
        "pkg/dynamic.py",
    } <= set(report["reachable_by_kind"]["production"])
    assert report["unresolved_internal_imports"] == []
    assert any(
        edge["kind"] == "deferred_literal_dynamic_import" and edge["scope"] == "main"
        for edge in report["edges"]
    )
    assert report["route_reachability"]["status"] == "not_proven"
    assert report["route_reachability"]["asgi_entrypoints"] == [
        {"service": "gateway", "entrypoint": "pkg.api:app"}
    ]


def test_only_explicit_roots_are_executable_authority(static_repo) -> None:
    """A script having main() alone does not make it a supported operator."""
    root, config = static_repo
    _write(root, "scripts/unowned.py", "def main():\n    pass\n")
    report = analyze_repository(root, config)
    assert "scripts/unowned.py" in report["unreachable"]
    config["operators"] = [
        {"target": "scripts/unowned.py:main", "reason": "Explicit operator contract"}
    ]
    assert "scripts/unowned.py" not in analyze_repository(root, config)["unreachable"]
    config["operators"][0]["target"] = "scripts/unowned.py"
    with pytest.raises(ValueError, match="Missing exact operator entry"):
        analyze_repository(root, config)
    config["operators"][0]["target"] = "scripts/unowned.py:missing"
    with pytest.raises(ValueError, match="Missing exact operator entry"):
        analyze_repository(root, config)


def test_ratchet_catches_new_orphans_and_production_loss_hidden_by_tests(
    static_repo,
) -> None:
    """Test reachability cannot conceal loss of an established production path."""
    root, config = static_repo
    baseline = _baseline(analyze_repository(root, config))
    _write(root, "pkg/cli.py", "def main():\n    pass\n")
    _write(root, "pkg/new_orphan.py", "value = 1\n")
    report = analyze_repository(root, config)
    assert "pkg/helper.py" in report["test_only"]
    assert baseline_findings(report, baseline) == {
        "newly_unreachable": ["pkg/new_orphan.py"],
        "lost_production_reachability": ["pkg/helper.py"],
        "baseline_add_production_paths": [],
        "baseline_remove_orphan_exemptions": [],
        "baseline_remove_deleted_production_paths": [],
    }
    (root / "pkg/helper.py").unlink()
    assert (
        baseline_findings(analyze_repository(root, config), baseline)[
            "lost_production_reachability"
        ]
        == []
    )


def test_ratchet_records_new_production_paths_before_tests_can_hide_a_loss(
    static_repo,
) -> None:
    """Adding production code must tighten the baseline before a later removal."""
    root, config = static_repo
    baseline = _baseline(analyze_repository(root, config))
    _write(root, "pkg/new.py", "value = 1\n")
    _write(root, "pkg/cli.py", "def main():\n    from . import helper, new\n")
    _write(root, "tests/test_new.py", "def test_new():\n    import pkg.new\n")
    report = analyze_repository(root, config)
    findings = baseline_findings(report, baseline)
    assert findings["baseline_add_production_paths"] == ["pkg/new.py"]
    assert findings["newly_unreachable"] == []
    baseline = _baseline(report)
    assert not any(baseline_findings(report, baseline).values())
    _write(root, "pkg/cli.py", "def main():\n    from . import helper\n")
    report = analyze_repository(root, config)
    assert "pkg/new.py" in report["test_only"]
    assert baseline_findings(report, baseline)["lost_production_reachability"] == [
        "pkg/new.py"
    ]


def test_ratchet_prunes_resolved_orphans_and_deleted_paths(static_repo) -> None:
    """A once-exempt orphan cannot regain its exemption after becoming reachable."""
    root, config = static_repo
    _write(root, "scripts/old.py", "def main():\n    pass\n")
    baseline = _baseline(analyze_repository(root, config))
    config["operators"] = [
        {"target": "scripts/old.py:main", "reason": "Adopted explicit operator"}
    ]
    report = analyze_repository(root, config)
    assert baseline_findings(report, baseline)["baseline_remove_orphan_exemptions"] == [
        "scripts/old.py"
    ]
    baseline = _baseline(report)
    config["operators"] = []
    report = analyze_repository(root, config)
    assert baseline_findings(report, baseline)["newly_unreachable"] == [
        "scripts/old.py"
    ]
    (root / "pkg/helper.py").unlink()
    report = analyze_repository(root, config)
    assert baseline_findings(report, baseline)[
        "baseline_remove_deleted_production_paths"
    ] == ["pkg/helper.py"]


@pytest.mark.parametrize(
    "expression",
    [
        "loader.import_module('.helper', 'pkg')",
        "loader.import_module('.helper', package='pkg')",
        "loader.import_module(name='.helper', package=__package__)",
        "loader.import_module('..helper', package='pkg.nested')",
    ],
)
def test_literal_relative_dynamic_imports_resolve_statically(
    static_repo, expression
) -> None:
    """Literal relative imports retain the same production edge as ordinary imports."""
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        f"import importlib as loader\ndef main():\n    {expression}\n",
    )
    report = analyze_repository(root, config)
    assert "pkg/helper.py" in report["reachable_by_kind"]["production"]
    assert report["dynamic_import_sites"] == []
    assert report["unresolved_internal_imports"] == []
    assert "" not in report["external_or_unresolved_top_level_names"]


def test_unknown_relative_package_is_visible_and_module_scope_can_be_registered(
    static_repo,
) -> None:
    """A computed relative package must not silently turn into a blank external name."""
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        "import importlib\nimportlib.import_module('.helper', package=chosen)\n"
        "def main():\n    pass\n",
    )
    report = analyze_repository(root, config)
    assert "pkg/helper.py" not in report["reachable_by_kind"]["production"]
    site = report["dynamic_import_sites"][0]
    assert site["scope"] == "<module>"
    assert site["registered_discovery_root"] is False
    assert "" not in report["external_or_unresolved_top_level_names"]
    config["dynamic_edges"] = [
        {
            "source": "pkg/cli.py:<module>",
            "target": "pkg/helper.py",
            "reason": "Explicit module initialization loader contract",
        }
    ]
    report = analyze_repository(root, config)
    assert report["dynamic_import_sites"][0]["registered_discovery_root"] is True
    assert "pkg/helper.py" in report["reachable_by_kind"]["production"]


def test_migration_roots_match_loader_exclusions_and_exact_run_symbol(
    static_repo,
) -> None:
    """Managed migrations are explicit dynamic roots; manual seeds are excluded."""
    root, config = static_repo
    _write(
        root,
        "migrations/001_managed.py",
        "def run(conn):\n    import pkg.migration_helper\n",
    )
    _write(root, "migrations/008_seed.py", "def main():\n    pass\n")
    _write(root, "pkg/migration_helper.py", "value = 1\n")
    report = analyze_repository(root, config)
    assert "pkg/migration_helper.py" in report["reachable_by_kind"]["migration"]
    assert "migrations/008_seed.py" in report["unreachable"]
    config["migrations"]["script_only_versions"] = []
    with pytest.raises(ValueError, match="Migration root exclusions differ"):
        analyze_repository(root, config)
    config["migrations"]["script_only_versions"] = ["008"]
    _write(root, "migrations/002_broken.py", "def upgrade(conn):\n    pass\n")
    with pytest.raises(ValueError, match="Missing exact migration entry point"):
        analyze_repository(root, config)


def test_pytest_discovery_has_exact_roots_and_does_not_claim_other_scripts(
    static_repo,
) -> None:
    """The testpaths boundary, conftest fixtures, and class methods are distinct."""
    root, config = static_repo
    _write(
        root,
        "tests/conftest.py",
        "import pytest\n@pytest.fixture\ndef shared():\n"
        "    import pkg.fixture_helper\n",
    )
    _write(
        root,
        "tests/test_class.py",
        "class TestExample:\n    def test_case(self):\n"
        "        import pkg.class_helper\n",
    )
    _write(
        root,
        "tests/archive/test_old.py",
        "import pkg.ignored\ndef test_old():\n    pass\n",
    )
    for name in ("fixture_helper", "class_helper", "ignored"):
        _write(root, f"pkg/{name}.py", "value = 1\n")
    _write(root, "scripts/test_unused.py", "def test_old():\n    pass\n")
    report = analyze_repository(root, config)
    assert {"pkg/fixture_helper.py", "pkg/class_helper.py"} <= set(report["test_only"])
    assert {"pkg/ignored.py", "scripts/test_unused.py"} <= set(report["unreachable"])
    roots = {
        (item["path"], item["symbol"])
        for item in report["roots"]
        if item["kind"] == "test"
    }
    assert ("tests/conftest.py", "shared") in roots
    assert ("tests/test_class.py", "TestExample.test_case") in roots


def test_declared_dynamic_edge_and_search_paths_are_explicit(static_repo) -> None:
    """Unknown dynamic imports stay visible until a concrete edge is registered."""
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        "import importlib\ndef main():\n    importlib.import_module(chosen)\n"
        "    import local_helper\n",
    )
    _write(root, "pkg/local_helper.py", "value = 1\n")
    _write(root, "pkg/plugin.py", "value = 1\n")
    config["import_search_paths"] = [
        {
            "source": "pkg/cli.py",
            "paths": ["pkg"],
            "reason": "Explicit executable directory",
        }
    ]
    report = analyze_repository(root, config)
    assert report["dynamic_import_sites"][0]["registered_discovery_root"] is False
    assert "pkg/local_helper.py" in report["reachable_by_kind"]["production"]
    assert "pkg/plugin.py" in report["unreachable"]
    config["dynamic_edges"] = [
        {
            "source": "pkg/cli.py:main",
            "target": "pkg/plugin.py",
            "reason": "Registered plugin contract",
        }
    ]
    report = analyze_repository(root, config)
    assert report["dynamic_import_sites"][0]["registered_discovery_root"] is True
    assert "pkg/plugin.py" in report["reachable_by_kind"]["production"]


def test_collection_initialization_roots_do_not_require_test_functions(
    static_repo,
) -> None:
    """Pytest imports matching modules and conftests, but not arbitrary helpers."""
    root, config = static_repo
    for path, helper in (
        ("conftest.py", "root_setup"),
        ("tests/conftest.py", "setup"),
        ("tests/test_import_only.py", "collected"),
        ("tests/support.py", "uncollected"),
        ("tests/archive/conftest.py", "archived"),
    ):
        _write(root, path, f"import pkg.{helper}\n")
        _write(root, f"pkg/{helper}.py", "raise RuntimeError('do not import')\n")
    report = analyze_repository(root, config)
    assert {"pkg/root_setup.py", "pkg/setup.py", "pkg/collected.py"} <= set(
        report["test_only"]
    )
    assert {"pkg/uncollected.py", "pkg/archived.py"} <= set(report["unreachable"])
    roots = {
        (entry["path"], entry["symbol"])
        for entry in report["roots"]
        if entry["kind"] == "test"
    }
    assert {
        ("conftest.py", "<module>"),
        ("tests/conftest.py", "<module>"),
        ("tests/test_import_only.py", "<module>"),
    } <= roots
    assert ("tests/support.py", "<module>") not in roots
    config["operators"] = [
        {"target": "conftest.py:<module>", "reason": "Invalid broad operator root"}
    ]
    with pytest.raises(ValueError, match="Missing exact operator entry"):
        analyze_repository(root, config)


def test_nested_testpaths_load_ancestor_conftests_only(static_repo) -> None:
    root, config = static_repo
    _write(
        root,
        "pytest.ini",
        "[pytest]\ntestpaths = tests/nested\nnorecursedirs = archive\n",
    )
    for path, helper in (
        ("conftest.py", "root_setup"),
        ("tests/conftest.py", "ancestor_setup"),
        ("tests/nested/conftest.py", "nested_setup"),
        ("tests/nested/test_empty.py", "collected"),
        ("tests/test_outside.py", "outside"),
        ("standalone.py", "standalone_helper"),
    ):
        _write(root, path, f"import pkg.{helper}\n")
        _write(root, f"pkg/{helper}.py", "value = 1\n")
    config["maintained"].append("*.py")
    report = analyze_repository(root, config)
    assert {
        "pkg/root_setup.py",
        "pkg/ancestor_setup.py",
        "pkg/nested_setup.py",
        "pkg/collected.py",
    } <= set(report["test_only"])
    assert {"pkg/outside.py", "pkg/standalone_helper.py", "standalone.py"} <= set(
        report["unreachable"]
    )


@pytest.mark.parametrize(
    "location", ["tests/conftest.py", "tests/test_plugin_owner.py"]
)
@pytest.mark.parametrize(
    "declaration",
    [
        'pytest_plugins = ("tests.plugin",)',
        'pytest_plugins: tuple[str, ...] = ("tests.plugin",)',
    ],
)
def test_plugin_declarations_in_all_collected_modules(
    static_repo, location, declaration
) -> None:
    root, config = static_repo
    _write(root, location, declaration + "\n")
    _write(root, "tests/plugin.py", "import pkg.plugin_helper\n")
    _write(root, "pkg/plugin_helper.py", "raise RuntimeError('must not execute')\n")
    report = analyze_repository(root, config)
    assert "pkg/plugin_helper.py" in report["test_only"]
    assert any(
        edge["source"] == location
        and edge["target"] == "tests/plugin.py"
        and edge["kind"] == "pytest_plugin"
        for edge in report["edges"]
    )


def test_explicit_test_file_is_collected_without_filename_pattern(static_repo) -> None:
    root, config = static_repo
    _write(root, "pytest.ini", "[pytest]\ntestpaths = tests/checks.py\n")
    _write(root, "tests/checks.py", "import pkg.explicit_helper\n")
    _write(root, "pkg/explicit_helper.py", "value = 1\n")
    report = analyze_repository(root, config)
    assert "pkg/explicit_helper.py" in report["test_only"]
    assert any(
        entry["path"] == "tests/checks.py" and entry["symbol"] == "<module>"
        for entry in report["roots"]
    )


def test_annotation_without_plugin_value_has_no_plugin_edge(static_repo) -> None:
    root, config = static_repo
    _write(root, "tests/conftest.py", "pytest_plugins: tuple[str, ...]\n")
    report = analyze_repository(root, config)
    assert not any(edge["kind"] == "pytest_plugin" for edge in report["edges"])
    assert not any(entry["symbol"] == "pytest_plugins" for entry in report["roots"])


@pytest.mark.parametrize("value", ["None", "''", "[]", "()"])
def test_empty_plugin_declarations_have_no_plugin_edges(static_repo, value) -> None:
    root, config = static_repo
    _write(root, "tests/conftest.py", f"pytest_plugins = {value}\n")
    report = analyze_repository(root, config)
    assert not any(edge["kind"] == "pytest_plugin" for edge in report["edges"])


def test_comma_separated_plugin_literal_loads_each_plugin(static_repo) -> None:
    root, config = static_repo
    _write(root, "tests/conftest.py", 'pytest_plugins: str = "tests.one,tests.two"\n')
    for name in ("one", "two"):
        _write(root, f"tests/{name}.py", f"import pkg.{name}\n")
        _write(root, f"pkg/{name}.py", "value = 1\n")
    assert {"pkg/one.py", "pkg/two.py"} <= set(
        analyze_repository(root, config)["test_only"]
    )


def test_dynamic_registration_does_not_hide_a_second_call_in_the_same_scope(
    static_repo,
) -> None:
    """A newly used baseline orphan still requires its own dynamic-site declaration."""
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        "import importlib\ndef main():\n    importlib.import_module(first)\n",
    )
    for helper in ("first_plugin", "second_plugin"):
        _write(root, f"pkg/{helper}.py", "value = 1\n")
    config["dynamic_edges"] = [
        {
            "source": "pkg/cli.py:main",
            "target": "pkg/first_plugin.py",
            "expression": "importlib.import_module(first)",
            "reason": "First plugin contract",
        }
    ]
    baseline = _baseline(analyze_repository(root, config))
    _write(
        root,
        "pkg/cli.py",
        "import importlib\ndef main():\n"
        "    importlib.import_module(first)\n    importlib.import_module(second)\n",
    )
    report = analyze_repository(root, config)
    assert not any(baseline_findings(report, baseline).values())
    assert [
        (site["expression"], site["registered_discovery_root"])
        for site in report["dynamic_import_sites"]
    ] == [
        ("importlib.import_module(first)", True),
        ("importlib.import_module(second)", False),
    ]
    config["dynamic_edges"][0].pop("expression")
    with pytest.raises(ValueError, match="exactly one call site.*matched 2"):
        analyze_repository(root, config)
    config["dynamic_edges"][0]["expression"] = "importlib.import_module(first)"
    config["dynamic_edges"].append(
        {
            "source": "pkg/cli.py:main",
            "target": "pkg/second_plugin.py",
            "expression": "importlib.import_module(second)",
            "reason": "Second plugin contract",
        }
    )
    report = analyze_repository(root, config)
    assert all(
        site["registered_discovery_root"] for site in report["dynamic_import_sites"]
    )
    assert baseline_findings(report, baseline)["baseline_remove_orphan_exemptions"] == [
        "pkg/second_plugin.py"
    ]


def test_identical_same_line_dynamic_calls_need_distinct_coordinates(
    static_repo,
) -> None:
    root, config = static_repo
    _write(
        root,
        "pkg/cli.py",
        "import importlib\ndef main():\n"
        "    importlib.import_module(chosen); importlib.import_module(chosen)\n",
    )
    sites = analyze_repository(root, config)["dynamic_import_sites"]
    declaration = {
        "source": "pkg/cli.py:main",
        "target": "pkg/helper.py",
        "expression": "importlib.import_module(chosen)",
        "reason": "Explicit plugin contract",
    }
    config["dynamic_edges"] = [declaration]
    with pytest.raises(ValueError, match="exactly one call site.*matched 2"):
        analyze_repository(root, config)
    declaration.update(line=sites[0]["line"], column=sites[0]["column"])
    report = analyze_repository(root, config)
    assert [
        site["registered_discovery_root"] for site in report["dynamic_import_sites"]
    ] == [True, False]
    declaration["expression"] = "importlib.import_module(stale_name)"
    with pytest.raises(ValueError, match="exactly one call site.*matched 0"):
        analyze_repository(root, config)


def test_migration_loader_registration_covers_only_one_dynamic_call(
    static_repo,
) -> None:
    root, config = static_repo
    _write(
        root,
        "scripts/migrate.py",
        'SCRIPT_ONLY_MIGRATIONS = ["008"]\n'
        "import importlib\ndef load(path):\n"
        "    importlib.import_module(first)\n    importlib.import_module(second)\n",
    )
    with pytest.raises(ValueError, match="exactly one call site.*matched 2"):
        analyze_repository(root, config)
    config["migrations"]["loader_expression"] = "importlib.import_module(first)"
    report = analyze_repository(root, config)
    assert [
        site["registered_discovery_root"] for site in report["dynamic_import_sites"]
    ] == [True, False]


@pytest.mark.parametrize(
    "kind,target",
    [
        ("path", "pkg/helper.py"),
        ("symbol", "pkg/helper.py:value"),
        ("python_literal", "pkg/helper.py:retired-name"),
        ("toml_key", "nexus.toml:runtime.services.gateway.command"),
    ],
)
def test_tombstones_are_narrow_and_require_a_decision(
    static_repo, kind, target
) -> None:
    """Only explicitly selected paths/symbols/scoped values are forbidden."""
    root, config = static_repo
    _write(root, "pkg/helper.py", 'value = "retired-name"\n')
    config["tombstones"] = [
        {
            "kind": kind,
            "target": target,
            "decision": "Explicit fixture-owner retirement",
        }
    ]
    assert analyze_repository(root, config)["tombstone_violations"] == [target]
    config["tombstones"][0].pop("decision")
    with pytest.raises(ValueError, match="explicit retirement decision"):
        analyze_repository(root, config)


def test_dependency_direction_is_separate_from_reachability(static_repo) -> None:
    root, config = static_repo
    _write(root, "pkg/cli.py", "import tests.support\ndef main():\n    pass\n")
    _write(root, "tests/support.py", "value = 1\n")
    config["forbidden_dependencies"] = [
        {
            "source": "pkg/*",
            "target": "tests/*",
            "reason": "Application must not depend on tests",
        }
    ]
    report = analyze_repository(root, config)
    assert [
        (edge["source"], edge["target"]) for edge in report["forbidden_dependencies"]
    ] == [("pkg/cli.py", "tests/support.py")]


def test_ignored_files_are_not_source_in_a_git_checkout(static_repo) -> None:
    """Git's ignore rules, not disk contents, decide what the gate scans (#892)."""
    root, config = static_repo
    _write(root, ".gitignore", "/pkg/models/\n")
    _write(root, "pkg/models/weights/modeling.py", "import pkg.helper\n")
    _write(root, "pkg/untracked.py", "import pkg.helper\n")
    _write(root, "tests/test_ignored.py", "def test_x():\n    import pkg.helper\n")
    _write(root, "tests/conftest.py", "import pkg.helper\n")
    without_git = analyze_repository(root, config)
    assert "pkg/models/weights/modeling.py" in without_git["maintained_modules"]
    assert any(edge["source"] == "tests/conftest.py" for edge in without_git["edges"])

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "pkg/cli.py", "tests/test_example.py"],
        check=True,
    )
    _write(root, ".git/info/exclude", "/tests/test_ignored.py\n/tests/conftest.py\n")
    report = analyze_repository(root, config)
    assert "pkg/models/weights/modeling.py" not in report["maintained_modules"]
    assert "pkg/untracked.py" in report["maintained_modules"]
    assert "pkg/cli.py" in report["maintained_modules"]
    ignored_sources = {"tests/test_ignored.py", "tests/conftest.py"}
    assert all(edge["source"] not in ignored_sources for edge in report["edges"])
    assert any(edge["source"] == "tests/test_example.py" for edge in report["edges"])


def _classify(
    config: dict[str, Any],
    classes: dict[str, str],
    held: tuple[str, ...] = (),
) -> None:
    """Install a sorted [classification] table on a fixture config."""
    config["classification"] = {
        "scope": ["scripts"],
        "held_classes": list(held),
        "paths": [
            {"path": path, "class": cls, "reason": f"Fixture reason for {path}."}
            for path, cls in sorted(classes.items())
        ],
    }


def _classification(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    return classification_findings(root, config, analyze_repository(root, config))


def test_classification_requires_one_entry_per_scoped_path(static_repo) -> None:
    """Every scoped file, Python or not, needs exactly one well-formed entry."""
    root, config = static_repo
    _write(root, "scripts/data.json", "{}\n")
    _write(root, "scripts/run.sh", "#!/bin/sh\n")
    full = {
        "scripts/data.json": "dead",
        "scripts/migrate.py": "operator",
        "scripts/run.sh": "operator",
    }
    _classify(config, full)
    findings = _classification(root, config)
    assert {key: findings[key] for key in CLASSIFICATION_LISTS} == {
        key: [] for key in CLASSIFICATION_LISTS
    }
    assert findings["classification_counts"] == {"dead": 1, "operator": 2}

    _classify(config, {k: v for k, v in full.items() if k != "scripts/run.sh"})
    assert _classification(root, config)["unclassified_paths"] == ["scripts/run.sh"]

    _classify(config, {**full, "scripts/gone.py": "dead"})
    findings = _classification(root, config)
    assert findings["classified_paths_not_in_repository"] == ["scripts/gone.py"]
    assert findings["unclassified_paths"] == []
    assert findings["classification_counts"] == {"dead": 2, "operator": 2}

    # The duplicate is also out of order, so the message names the duplicate
    # only when the duplicate check runs before the sorted check.
    _classify(config, full)
    paths = config["classification"]["paths"]
    config["classification"]["paths"] = [paths[0], paths[1], dict(paths[0]), paths[2]]
    with pytest.raises(ValueError, match="more than one"):
        _classification(root, config)

    _classify(config, {**full, "scripts/run.sh": "fixture"})
    with pytest.raises(ValueError, match="'fixture'"):
        _classification(root, config)

    _classify(config, full)
    config["classification"]["paths"][1]["reason"] = "   "
    with pytest.raises(ValueError, match="non-blank reason"):
        _classification(root, config)

    _classify(config, full, held=("runtime",))
    with pytest.raises(ValueError, match="equals a graph class"):
        _classification(root, config)

    _classify(config, full)
    paths = config["classification"]["paths"]
    config["classification"]["paths"] = [paths[1], paths[0], paths[2]]
    with pytest.raises(ValueError, match="sorted"):
        _classification(root, config)

    del config["classification"]
    with pytest.raises(ValueError, match=r"Missing \[classification\]"):
        _classification(root, config)


def _graph_repo(root: Path, config: dict[str, Any]) -> None:
    """Give each graph class one fixture path under scripts/.

    ``scripts/shared.py`` is production- and operator-reachable, and
    ``scripts/tool_helper.py`` is operator- and test-reachable, so the
    parametrized cases pin both precedences.
    """
    _write(
        root,
        "pkg/cli.py",
        "def main():\n    from . import helper\n"
        "    import scripts.shared\n    import scripts.migrate\n",
    )
    _write(root, "scripts/shared.py", "value = 1\n")
    _write(
        root,
        "scripts/tool.py",
        "import scripts.shared\nimport scripts.tool_helper\n" "def main():\n    pass\n",
    )
    _write(root, "scripts/tool_helper.py", "value = 1\n")
    _write(
        root,
        "tests/test_example.py",
        "def test_example():\n    import pkg.helper\n    import scripts.tested\n"
        "    import scripts.tool_helper\n",
    )
    _write(root, "scripts/tested.py", "value = 1\n")
    _write(root, "scripts/orphan.py", "value = 1\n")
    config["operators"] = [
        {"target": "scripts/tool.py:main", "reason": "Declared fixture operator"}
    ]


GRAPH_FIXTURE_CLASSES = {
    "scripts/migrate.py": "runtime",
    "scripts/orphan.py": "documented",
    "scripts/shared.py": "runtime",
    "scripts/tested.py": "test-only",
    "scripts/tool.py": "operator",
    "scripts/tool_helper.py": "operator",
}


@pytest.mark.parametrize(
    "fixture,overrides,expected",
    [
        ("graph", {}, []),
        ("graph", {"scripts/orphan.py": "dead"}, []),
        ("graph", {"scripts/shared.py": "operator"}, ["runtime"]),
        ("graph", {"scripts/migrate.py": "operator"}, ["runtime"]),
        ("graph", {"scripts/tool.py": "dead"}, ["operator"]),
        ("graph", {"scripts/tool_helper.py": "test-only"}, ["operator"]),
        ("graph", {"scripts/tested.py": "operator"}, ["test-only"]),
        ("graph", {"scripts/orphan.py": "runtime"}, ["documented|dead"]),
        ("base", {"scripts/migrate.py": "dead"}, ["operator"]),
        ("base", {"scripts/migrate.py": "operator"}, []),
        ("base-tested", {"scripts/migrate.py": "test-only"}, ["operator"]),
        ("base-tested", {"scripts/migrate.py": "operator"}, []),
    ],
)
def test_classification_graph_classes_follow_reachability(
    static_repo, fixture, overrides, expected
) -> None:
    """Production beats operator and migration, which beat test, which beats none.

    ``graph`` is the ``_graph_repo`` fixture. ``base`` is the unmodified base
    fixture, where only the migration kind reaches the loader. ``base-tested``
    adds a test import of the loader, so migration and test roots reach it and
    no production or operator root does.
    """
    root, config = static_repo
    if fixture == "graph":
        _graph_repo(root, config)
        classes = {**GRAPH_FIXTURE_CLASSES, **overrides}
    else:
        if fixture == "base-tested":
            _write(
                root,
                "tests/test_example.py",
                "def test_example():\n    import pkg.helper\n"
                "    import scripts.migrate\n",
            )
        classes = dict(overrides)
    _classify(config, classes)
    findings = _classification(root, config)
    assert findings["unclassified_paths"] == []
    assert findings["class_graph_mismatches"] == [
        {"path": path, "class": classes[path], "expected": want}
        for path, want in zip(overrides, expected)
    ]


def test_held_classes_override_the_graph(static_repo) -> None:
    """A held class records a pending decision and skips the graph check."""
    root, config = static_repo
    _graph_repo(root, config)
    classes = {**GRAPH_FIXTURE_CLASSES, "scripts/shared.py": "pending-ruling:811-Q4"}
    _classify(config, classes, held=("pending-ruling:811-Q4",))
    findings = _classification(root, config)
    assert findings["class_graph_mismatches"] == []
    assert findings["classification_counts"]["pending-ruling:811-Q4"] == 1
    _classify(config, classes)
    with pytest.raises(ValueError, match="pending-ruling:811-Q4"):
        _classification(root, config)


def test_classification_view_follows_git_ignore_rules(static_repo) -> None:
    """An ignored file needs no entry in a git checkout, but does without .git."""
    root, config = static_repo
    _write(root, ".gitignore", "/scripts/logs/\n")
    _write(root, "scripts/logs/run.log", "noise\n")
    _classify(config, {"scripts/migrate.py": "operator"})
    assert _classification(root, config)["unclassified_paths"] == [
        "scripts/logs/run.log"
    ]
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    findings = _classification(root, config)
    assert {key: findings[key] for key in CLASSIFICATION_LISTS} == {
        key: [] for key in CLASSIFICATION_LISTS
    }
    _classify(
        config,
        {"scripts/logs/run.log": "dead", "scripts/migrate.py": "operator"},
    )
    assert _classification(root, config)["classified_paths_not_in_repository"] == [
        "scripts/logs/run.log"
    ]


def _repository_config() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "config/reachability.toml").read_text())


def test_repository_reachability_ratchet() -> None:
    """The ordinary pytest gate enforces the checked-in repository baseline."""
    config = _repository_config()
    report = analyze_repository(REPO_ROOT, config)
    baseline = json.loads((REPO_ROOT / config["baseline"]).read_text())
    assert not any(baseline_findings(report, baseline).values())
    assert report["unresolved_internal_imports"] == []
    assert report["forbidden_dependencies"] == []
    assert report["tombstone_violations"] == []
    assert all(
        site["registered_discovery_root"] for site in report["dynamic_import_sites"]
    )
    findings = classification_findings(REPO_ROOT, config, report)
    assert {key: findings[key] for key in CLASSIFICATION_LISTS} == {
        key: [] for key in CLASSIFICATION_LISTS
    }


# The 811-S1 rules 1-8, in order; the first match wins. Each is (class, fnmatch
# patterns, non-Python files only). Rules 5 and 8 cover whole families, so the
# decision test checks every path that falls to them, not one member each.
RULES_811_S1: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    (
        "pending-ruling:811-Q4",
        ("scripts/api_openai.py", "scripts/api_anthropic.py"),
        False,
    ),
    ("openrouter-shim", ("scripts/api_openrouter.py",), False),
    (
        "pending-ruling:811-Q1",
        (
            "scripts/apply_slot2_semantic_tags.py",
            "scripts/seed_slot2_routine_anchors.py",
            "scripts/backfill_routine_anchors.py",
        ),
        False,
    ),
    (
        "test-only",
        (
            "scripts/install_pgvector.sh",
            "ir_eval/README.md",
            "ir_eval/golden_queries_backup.json",
        ),
        False,
    ),
    (
        "pending-ruling:811-Q5",
        (
            "ir_eval/ir_eval.py",
            "ir_eval/ir_eval_debug.py",
            "ir_eval/ir_eval_sqlite.py",
            "ir_eval/db.py",
            "ir_eval/pg_db.py",
            "ir_eval/import_golden_queries.py",
            "ir_eval/migrate_sqlite_to_postgres.py",
            "ir_eval/test_*.py",
            "ir_eval/scripts/*",
            "ir_eval/golden_queries.json",
            "ir_eval/golden_queries.json.bak",
            "ir_eval/qrels.json",
            "ir_eval/pg_schema.sql",
            "ir_eval/*.md",
            "scripts/run_golden_queries.py",
            "scripts/README_golden_queries.md",
        ),
        False,
    ),
    ("operator", ("scripts/qa_shift/*", "scripts/scratchpad_audit/*"), True),
    (
        "dead",
        (
            "scripts/edi",
            "scripts/token_count",
            "scripts/register_production_conditions.sh",
        ),
        False,
    ),
    (
        "pending-ruling:811-Q3",
        (
            "scripts/*.json",
            "scripts/*.md",
            "scripts/*.txt",
            "scripts/*.sql",
            "scripts/*.bak",
            "scripts/*.new",
            "ir_eval/ir_eval.db",
            "ir_eval/ir_eval.db.bak",
            "ir_eval/results/*",
            "ir_eval/query_classifier_*",
        ),
        True,
    ),
)
PATTERN_HELD_CLASSES = ("pending-ruling:811-Q5", "pending-ruling:811-Q3")


def _first_811_rule_class(path: str) -> str | None:
    """Return the class of the first 811-S1 rule that matches ``path``."""
    for rule_class, patterns, non_python_only in RULES_811_S1:
        if non_python_only and path.endswith(".py"):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            return rule_class
    return None


def test_repository_classification_applies_811_decisions() -> None:
    """Paths decided on #811 keep the class those decisions gave them."""
    classification = _repository_config()["classification"]
    by_class: dict[str, set[str]] = {}
    for entry in classification["paths"]:
        by_class.setdefault(entry["class"], set()).add(entry["path"])
    assert by_class["pending-ruling:811-Q4"] == {
        "scripts/api_anthropic.py",
        "scripts/api_openai.py",
    }
    assert by_class["openrouter-shim"] == {"scripts/api_openrouter.py"}
    assert by_class["pending-ruling:811-Q1"] == {
        "scripts/apply_slot2_semantic_tags.py",
        "scripts/backfill_routine_anchors.py",
        "scripts/seed_slot2_routine_anchors.py",
    }
    assert "ir_eval/ir_eval.py" in by_class["pending-ruling:811-Q5"]
    assert "ir_eval/ir_eval.db" in by_class["pending-ruling:811-Q3"]
    pattern_classes: dict[str, set[str]] = {}
    for path in {entry["path"] for entry in classification["paths"]}:
        rule_class = _first_811_rule_class(path)
        if rule_class in PATTERN_HELD_CLASSES:
            pattern_classes.setdefault(rule_class, set()).add(path)
    for held in PATTERN_HELD_CLASSES:
        assert by_class[held] == pattern_classes[held]
    graph_classes = {"runtime", "operator", "test-only", "documented", "dead"}
    assert set(by_class) - graph_classes <= set(classification["held_classes"])


def test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app(
    tmp_path,
) -> None:
    """A fresh Python process runs the real CLI without any site packages."""
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(REPO_ROOT / "scripts/check_reachability.py"),
            "--report",
            str(report_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    for key in CLASSIFICATION_LISTS:
        assert summary[key] == []
    assert sum(summary["classification_counts"].values()) == len(
        _repository_config()["classification"]["paths"]
    )
    report = json.loads(report_path.read_text())
    assert report["classification"]["classification_counts"] == (
        summary["classification_counts"]
    )
    assert report["route_reachability"]["status"] == "not_proven"
    assert any(
        item["path"] == "nexus/cli.py" and item["symbol"] == "main"
        for item in report["roots"]
    )


def test_namespace_import_initializes_package_ancestor_and_explains_chain(
    static_repo,
) -> None:
    """A namespace import executes its package without importing child modules."""
    root, config = static_repo
    _write(
        root,
        "scripts/operator.py",
        "import independent.namespace\ndef main():\n    pass\n",
    )
    _write(root, "independent/__init__.py", "raise RuntimeError('do not execute')\n")
    _write(root, "independent/namespace/leaf.py", "value = 1\n")
    config["maintained"].append("independent/**/*.py")
    config["operators"] = [
        {"target": "scripts/operator.py:main", "reason": "Explicit fixture operator"}
    ]
    report = analyze_repository(root, config)
    assert "independent/__init__.py" in report["reachable_by_kind"]["operator"]
    assert "independent/namespace/leaf.py" in report["unreachable"]
    explanation = explain_reachability(report, "independent/__init__.py", "operator")
    assert explanation["root"]["symbol"] == "main"
    assert explanation["imports"][0]["kind"] == "namespace_package_initialization"
    assert (
        explain_reachability(report, "independent/__init__.py", "production")[
            "reachable"
        ]
        is False
    )
