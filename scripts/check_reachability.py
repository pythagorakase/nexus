#!/usr/bin/env python3
"""Report and ratchet static Python import reachability without importing NEXUS."""

from __future__ import annotations

import argparse
import ast
import configparser
import fnmatch
import importlib.util
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = "config/reachability.toml"


@dataclass(frozen=True)
class EntryPoint:
    """One exact executable or discovery symbol, with its source of authority."""

    path: str
    symbol: str
    kind: str
    reason: str


@dataclass(frozen=True)
class ImportEdge:
    """A possible import dependency, not a claim that a call/route executes."""

    source: str
    target: str
    line: int
    kind: str
    scope: str = "<module>"


def _module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _symbols(tree: ast.AST, prefix: str = "") -> set[str]:
    found: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = prefix + node.name
            found.add(name)
            found.update(_symbols(node, name + "."))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found.update(
                prefix + target.id for target in targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found.update(
                prefix + (item.asname or item.name.split(".")[0]) for item in node.names
            )
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            found.update(_symbols(node, prefix))
            for child in getattr(node, "handlers", []):
                found.update(_symbols(child, prefix))
            for branch in (getattr(node, "orelse", []), getattr(node, "finalbody", [])):
                found.update(_symbols(ast.Module(body=branch, type_ignores=[]), prefix))
    return found


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    return ""


def _reachable(roots: Iterable[str], adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(roots)
    while queue:
        path = queue.popleft()
        if path not in seen:
            seen.add(path)
            queue.extend(sorted(adjacency[path] - seen))
    return seen


def analyze_repository(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic graph from source text and declared discovery rules."""
    if config.get("version") != 1:
        raise ValueError("Unsupported reachability config version")
    for section in (
        "operators",
        "import_aliases",
        "import_search_paths",
        "dynamic_edges",
        "forbidden_dependencies",
    ):
        if any(
            not declaration.get("reason", "").strip()
            for declaration in config.get(section, [])
        ):
            raise ValueError(f"Every {section} declaration needs a reason")
    maintained = {
        path.relative_to(root).as_posix()
        for pattern in config["maintained"]
        for path in root.glob(pattern)
        if path.is_file()
    }
    pytest_config = configparser.ConfigParser()
    pytest_config.read(root / config["pytest"]["config"])
    pytest_section = pytest_config["pytest"]
    testpaths = pytest_section.get("testpaths", "tests").split()
    patterns = pytest_section.get("python_files", "test_*.py *_test.py").split()
    ignored = pytest_section.get("norecursedirs", "").split()
    class_patterns = pytest_section.get("python_classes", "Test*").split()
    function_patterns = pytest_section.get("python_functions", "test_*").split()
    test_files = {
        path.relative_to(root).as_posix()
        for testpath in testpaths
        for path in (root / testpath).rglob("*.py")
        if not any(
            fnmatch.fnmatch(part, pattern)
            for part in path.relative_to(root).parts
            for pattern in ignored
        )
    }
    paths = sorted(maintained | test_files)
    trees = {
        path: ast.parse((root / path).read_text(encoding="utf-8-sig"), filename=path)
        for path in paths
    }
    modules = {_module_name(path): path for path in paths}
    if len(modules) != len(paths):
        raise ValueError("Ambiguous module names in maintained/test source inventory")
    symbols = {path: _symbols(tree) for path, tree in trees.items()}
    roots: list[EntryPoint] = []
    edges: set[ImportEdge] = set()
    dynamic_calls: list[dict[str, Any]] = []
    unresolved_internal: list[dict[str, Any]] = []
    external_names: set[str] = set()

    def entry(
        target: str, kind: str, reason: str, *, module_target: bool = False
    ) -> None:
        path, separator, symbol = target.partition(":")
        if module_target:
            path = modules.get(path, path)
        if (
            not separator
            or not symbol
            or path not in symbols
            or symbol not in symbols[path]
        ):
            raise ValueError(f"Missing exact {kind} entry point {target!r}: {reason}")
        roots.append(EntryPoint(path, symbol, kind, reason))

    project = tomllib.loads((root / config["production"]["project_config"]).read_text())
    for name, target in project["project"]["scripts"].items():
        entry(target, "production", f"project.scripts.{name}", module_target=True)
    runtime = tomllib.loads((root / config["production"]["runtime_config"]).read_text())
    asgi: list[dict[str, str]] = []
    external_services: list[str] = []
    for name, service in runtime["runtime"]["services"].items():
        command = service["command"]
        if command[:3] == ["{python}", "-m", "uvicorn"]:
            target = command[3]
            entry(
                target,
                "production",
                f"runtime.services.{name}.command",
                module_target=True,
            )
            asgi.append({"service": name, "entrypoint": target})
        elif command[0] == "{python}":
            raise ValueError(f"Unregistered Python service command: {name}")
        else:
            external_services.append(name)
    for declaration in config.get("operators", []):
        entry(declaration["target"], "operator", declaration["reason"])

    migration = config["migrations"]
    entry(migration["loader"], "migration", migration["reason"])
    loader_path = migration["loader"].split(":")[0]
    excluded = None
    for node in trees[loader_path].body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SCRIPT_ONLY_MIGRATIONS"
            for target in node.targets
        ):
            excluded = set(ast.literal_eval(node.value))
    if excluded != set(migration["script_only_versions"]):
        raise ValueError("Migration root exclusions differ from SCRIPT_ONLY_MIGRATIONS")
    for path in sorted(maintained):
        if (
            fnmatch.fnmatch(path, migration["pattern"])
            and Path(path).name[:3] not in excluded
        ):
            entry(f"{path}:{migration['symbol']}", "migration", migration["reason"])

    for path in sorted(test_files):
        is_conftest = Path(path).name == "conftest.py"
        if not is_conftest and not any(
            fnmatch.fnmatch(Path(path).name, pattern) for pattern in patterns
        ):
            continue
        for node in trees[path].body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [
                    _dotted(item.func if isinstance(item, ast.Call) else item)
                    for item in node.decorator_list
                ]
                if any(
                    fnmatch.fnmatch(node.name, pattern) for pattern in function_patterns
                ) or (
                    is_conftest
                    and (
                        node.name.startswith("pytest_")
                        or any(
                            item.rsplit(".", 1)[-1] == "fixture" for item in decorators
                        )
                    )
                ):
                    entry(
                        f"{path}:{node.name}",
                        "test",
                        "pytest.ini discovery; no collection/import executed",
                    )
            elif isinstance(node, ast.ClassDef) and any(
                fnmatch.fnmatch(node.name, pattern) for pattern in class_patterns
            ):
                for method in node.body:
                    if isinstance(
                        method, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) and any(
                        fnmatch.fnmatch(method.name, pattern)
                        for pattern in function_patterns
                    ):
                        entry(
                            f"{path}:{node.name}.{method.name}",
                            "test",
                            "pytest.ini class discovery; no collection/import executed",
                        )
            elif (
                is_conftest
                and isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "pytest_plugins"
                    for target in node.targets
                )
            ):
                entry(f"{path}:pytest_plugins", "test", "pytest plugin declaration")
                plugins = ast.literal_eval(node.value)
                for name in [plugins] if isinstance(plugins, str) else plugins:
                    if name in modules:
                        edges.add(
                            ImportEdge(
                                path, modules[name], node.lineno, "pytest_plugin"
                            )
                        )

    local_prefixes = {
        _module_name(path).split(".")[0] for path in maintained | test_files
    }
    aliases = config.get("import_aliases", [])

    def resolve(name: str, source: str) -> str | None:
        for alias in aliases:
            if fnmatch.fnmatch(source, alias["source"]) and (
                name == alias["prefix"] or name.startswith(alias["prefix"] + ".")
            ):
                name = alias["target"] + name[len(alias["prefix"]) :]
        direct = modules.get(name)
        if direct:
            return direct
        candidates = {
            modules[prefix.replace("/", ".") + "." + name]
            for declaration in config.get("import_search_paths", [])
            if fnmatch.fnmatch(source, declaration["source"])
            for prefix in declaration["paths"]
            if prefix.replace("/", ".") + "." + name in modules
        }
        if len(candidates) > 1:
            raise ValueError(f"Ambiguous declared import search for {source}: {name}")
        return next(iter(candidates), None)

    class ImportVisitor(ast.NodeVisitor):
        def __init__(self, source: str) -> None:
            self.source = source
            self.scope: list[str] = []
            self.function_depth = 0
            self.call_aliases: dict[str, str] = {}

        def record(
            self,
            name: str,
            node: ast.AST,
            kind: str = "import",
            *,
            required: bool = True,
        ) -> None:
            target = resolve(name, self.source)
            if target:
                edges.add(
                    ImportEdge(
                        self.source,
                        target,
                        node.lineno,
                        "deferred_" + kind if self.function_depth else kind,
                        ".".join(self.scope) or "<module>",
                    )
                )
            elif any(module.startswith(name + ".") for module in modules):
                # Namespace packages have no file node, but importing them still
                # executes any regular package ancestors.
                parts = name.split(".")[:-1]
                while parts:
                    ancestor = modules.get(".".join(parts))
                    if ancestor and Path(ancestor).name == "__init__.py":
                        edges.add(
                            ImportEdge(
                                self.source,
                                ancestor,
                                node.lineno,
                                (
                                    "deferred_namespace_package_initialization"
                                    if self.function_depth
                                    else "namespace_package_initialization"
                                ),
                                ".".join(self.scope) or "<module>",
                            )
                        )
                    parts.pop()
            elif required:
                if name.split(".")[0] in local_prefixes:
                    unresolved_internal.append(
                        {"source": self.source, "line": node.lineno, "name": name}
                    )
                else:
                    external_names.add(name.split(".")[0])

        def visit_Import(self, node: ast.Import) -> None:
            for imported in node.names:
                self.call_aliases[imported.asname or imported.name.split(".")[0]] = (
                    imported.name if imported.asname else imported.name.split(".")[0]
                )
                self.record(imported.name, node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level:
                package = _module_name(self.source)
                if Path(self.source).name != "__init__.py":
                    package = package.rpartition(".")[0]
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                name = ".".join(item for item in (base, node.module) if item)
            else:
                name = node.module or ""
            self.record(name, node, required=bool(node.module))
            for imported in node.names:
                self.call_aliases[imported.asname or imported.name] = (
                    name + "." + imported.name
                )
                self.record(name + "." + imported.name, node, required=False)

        def visit_FunctionDef(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> None:
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            if node.returns is not None:
                self.visit(node.returns)
            aliases_before = dict(self.call_aliases)
            self.scope.append(node.name)
            self.function_depth += 1
            for statement in node.body:
                self.visit(statement)
            self.function_depth -= 1
            self.scope.pop()
            self.call_aliases = aliases_before

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            for expression in [*node.decorator_list, *node.bases, *node.keywords]:
                self.visit(expression)
            aliases_before = dict(self.call_aliases)
            self.scope.append(node.name)
            for statement in node.body:
                self.visit(statement)
            self.scope.pop()
            self.call_aliases = aliases_before

        def visit_Call(self, node: ast.Call) -> None:
            name = _dotted(node.func)
            first, separator, suffix = name.partition(".")
            name = self.call_aliases.get(first, first) + (
                separator + suffix if separator else ""
            )
            if name in {"importlib.import_module", "import_module", "__import__"}:
                imported_name = self.literal_dynamic_name(node, name)
                if imported_name is not None:
                    self.record(imported_name, node, "literal_dynamic_import")
                else:
                    dynamic_calls.append(
                        {
                            "source": self.source,
                            "line": node.lineno,
                            "scope": ".".join(self.scope) or "<module>",
                            "call": name,
                        }
                    )
            elif name.endswith("spec_from_file_location"):
                dynamic_calls.append(
                    {
                        "source": self.source,
                        "line": node.lineno,
                        "scope": ".".join(self.scope) or "<module>",
                        "call": name,
                    }
                )
            self.generic_visit(node)

        def literal_dynamic_name(self, node: ast.Call, call: str) -> str | None:
            """Resolve import_module literals without evaluating package expressions."""
            keywords = {item.arg: item.value for item in node.keywords}
            name_node = node.args[0] if node.args else keywords.get("name")
            if not (
                isinstance(name_node, ast.Constant)
                and isinstance(name_node.value, str)
                and name_node.value
            ):
                return None
            imported_name = name_node.value
            if call == "__import__":
                level = node.args[4] if len(node.args) > 4 else keywords.get("level")
                if level is not None and not (
                    isinstance(level, ast.Constant) and level.value == 0
                ):
                    return None
                return imported_name if not imported_name.startswith(".") else None
            if not imported_name.startswith("."):
                return imported_name
            package_node = (
                node.args[1] if len(node.args) > 1 else keywords.get("package")
            )
            if isinstance(package_node, ast.Constant) and isinstance(
                package_node.value, str
            ):
                package = package_node.value
            elif (
                isinstance(package_node, ast.Name) and package_node.id == "__package__"
            ):
                package = _module_name(self.source)
                if Path(self.source).name != "__init__.py":
                    package = package.rpartition(".")[0]
            else:
                return None
            try:
                return importlib.util.resolve_name(imported_name, package)
            except (ImportError, ValueError):
                return None

    for source, tree in trees.items():
        ImportVisitor(source).visit(tree)
        package = _module_name(source).split(".")[:-1]
        while package:
            target = modules.get(".".join(package))
            if target and Path(target).name == "__init__.py":
                edges.add(ImportEdge(source, target, 0, "package_initialization"))
            package.pop()
    for declaration in config.get("dynamic_edges", []):
        source, _, symbol = declaration["source"].partition(":")
        target = declaration["target"]
        if (
            source not in symbols
            or (symbol != "<module>" and symbol not in symbols[source])
            or target not in trees
        ):
            raise ValueError(f"Invalid declared dynamic edge: {declaration}")
        edges.add(ImportEdge(source, target, 0, "declared_dynamic_import", symbol))

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
    by_kind = {
        kind: _reachable((item.path for item in roots if item.kind == kind), adjacency)
        for kind in ("production", "operator", "migration", "test")
    }
    all_reachable = set().union(*by_kind.values())
    forbidden = [
        asdict(edge)
        for edge in edges
        for rule in config.get("forbidden_dependencies", [])
        if fnmatch.fnmatch(edge.source, rule["source"])
        and fnmatch.fnmatch(edge.target, rule["target"])
    ]
    tombstones: list[str] = []
    for retired in config.get("tombstones", []):
        if not retired.get("decision"):
            raise ValueError("Every tombstone needs its explicit retirement decision")
        kind, target = retired["kind"], retired["target"]
        path, _, symbol = target.partition(":")
        if kind == "path":
            present = (root / path).exists()
        elif kind == "symbol":
            present = symbol in symbols.get(path, set())
        elif kind == "toml_key":
            value = (
                tomllib.loads((root / path).read_text())
                if (root / path).exists()
                else {}
            )
            for key in symbol.split("."):
                if not isinstance(value, dict) or key not in value:
                    value = None
                    break
                value = value[key]
            present = value is not None
        elif kind == "python_literal":
            present = any(
                isinstance(node, ast.Constant) and node.value == symbol
                for node in ast.walk(
                    trees.get(path, ast.Module(body=[], type_ignores=[]))
                )
            )
        else:
            raise ValueError(f"Unknown tombstone kind: {kind}")
        if present:
            tombstones.append(target)
    for site in dynamic_calls:
        source_symbol = f"{site['source']}:{site['scope']}"
        site["registered_discovery_root"] = source_symbol == migration["loader"] or any(
            declaration["source"] == source_symbol
            for declaration in config.get("dynamic_edges", [])
        )
    return {
        "schema_version": 1,
        "declared_import_search_paths": config.get("import_search_paths", []),
        "declared_dynamic_edges": config.get("dynamic_edges", []),
        "maintained_modules": sorted(maintained),
        "roots": [
            asdict(item)
            for item in sorted(
                roots, key=lambda item: (item.kind, item.path, item.symbol)
            )
        ],
        "edges": [
            asdict(item)
            for item in sorted(
                edges,
                key=lambda item: (
                    item.source,
                    item.target,
                    item.line,
                    item.kind,
                    item.scope,
                ),
            )
        ],
        "reachable_by_kind": {
            kind: sorted(paths & maintained) for kind, paths in by_kind.items()
        },
        "test_only": sorted(
            (
                by_kind["test"]
                - by_kind["production"]
                - by_kind["operator"]
                - by_kind["migration"]
            )
            & maintained
        ),
        "unreachable": sorted(maintained - all_reachable),
        "unresolved_internal_imports": sorted(
            unresolved_internal,
            key=lambda item: (item["source"], item["line"], item["name"]),
        ),
        "external_or_unresolved_top_level_names": sorted(external_names),
        "dynamic_import_sites": sorted(
            dynamic_calls, key=lambda item: (item["source"], item["line"])
        ),
        "forbidden_dependencies": sorted(
            forbidden, key=lambda item: (item["source"], item["target"], item["line"])
        ),
        "tombstone_violations": sorted(tombstones),
        "route_reachability": {
            "status": "not_proven",
            "asgi_entrypoints": asgi,
            "external_services": sorted(external_services),
            "reason": (
                "Import reachability does not prove router mounting, HTTP exposure, "
                "or function execution. Deferred and conditional imports are "
                "possible dependencies only."
            ),
        },
    }


def baseline_findings(
    report: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, list[str]]:
    """Ratchet isolation and require the baseline to retain newly established paths."""
    if baseline.get("schema_version") != 1:
        raise ValueError("Unsupported reachability baseline version")
    current = set(report["maintained_modules"])
    unreachable = set(report["unreachable"])
    production = set(report["reachable_by_kind"]["production"])
    prior_unreachable = set(baseline["unreachable"])
    prior_production = set(baseline["production_reachable"])
    return {
        "newly_unreachable": sorted(unreachable - prior_unreachable),
        "lost_production_reachability": sorted(
            (prior_production & current) - production
        ),
        "baseline_add_production_paths": sorted(production - prior_production),
        "baseline_remove_orphan_exemptions": sorted(prior_unreachable - unreachable),
        "baseline_remove_deleted_production_paths": sorted(prior_production - current),
    }


def explain_reachability(
    report: dict[str, Any], path: str, kind: str
) -> dict[str, Any]:
    """Return one shortest root-to-module chain with import scope evidence."""
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in report["edges"]:
        adjacency[edge["source"]].append(edge)
    queue: deque[tuple[str, dict[str, Any], list[dict[str, Any]]]] = deque(
        (entry["path"], entry, []) for entry in report["roots"] if entry["kind"] == kind
    )
    seen: set[str] = set()
    while queue:
        current, entry, chain = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        if current == path:
            return {
                "path": path,
                "kind": kind,
                "reachable": True,
                "root": entry,
                "imports": chain,
            }
        queue.extend(
            (edge["target"], entry, chain + [edge]) for edge in adjacency[current]
        )
    return {"path": path, "kind": kind, "reachable": False}


def main(argv: list[str] | None = None) -> int:
    """Print a summary, optionally save evidence, and enforce the static gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument(
        "--report", type=Path, help="Write the complete deterministic JSON graph"
    )
    parser.add_argument(
        "--explain", help="Show a shortest import chain to this repository path"
    )
    parser.add_argument(
        "--kind",
        choices=["production", "operator", "migration", "test"],
        default="production",
    )
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument(
        "--reason", help="Reviewable justification required to replace the baseline"
    )
    args = parser.parse_args(argv)
    config = tomllib.loads((args.root / args.config).read_text())
    report = analyze_repository(args.root, config)
    baseline_path = args.root / config["baseline"]
    if args.write_baseline:
        if not args.reason:
            parser.error("--write-baseline requires --reason")
        baseline_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reason": args.reason,
                    "unreachable": report["unreachable"],
                    "production_reachable": report["reachable_by_kind"]["production"],
                },
                indent=2,
            )
            + "\n"
        )
    baseline = json.loads(baseline_path.read_text())
    findings = baseline_findings(report, baseline)
    report["findings"] = findings
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    unregistered_dynamic = [
        site
        for site in report["dynamic_import_sites"]
        if not site["registered_discovery_root"]
    ]
    summary = {
        "maintained": len(report["maintained_modules"]),
        "reachable_by_kind": {
            kind: len(paths) for kind, paths in report["reachable_by_kind"].items()
        },
        "test_only": len(report["test_only"]),
        "existing_unreachable": len(report["unreachable"]),
        **findings,
        "forbidden_dependencies": report["forbidden_dependencies"],
        "tombstone_violations": report["tombstone_violations"],
        "unresolved_internal_imports": report["unresolved_internal_imports"],
        "unregistered_dynamic_import_sites": unregistered_dynamic,
        "route_reachability": "not_proven",
    }
    if args.explain:
        summary["explanation"] = explain_reachability(report, args.explain, args.kind)
    print(json.dumps(summary, indent=2))
    return int(
        any(findings.values())
        or bool(
            report["forbidden_dependencies"]
            or report["tombstone_violations"]
            or report["unresolved_internal_imports"]
            or unregistered_dynamic
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
