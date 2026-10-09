"""Explicit script exports preserve command compatibility after the #811 move."""

import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVED = {
    "scripts.migrate": "nexus.maintenance.migrate",
    "scripts.new_story_setup": "nexus.maintenance.new_story_setup",
    "scripts.database_targets": "nexus.maintenance.database_targets",
    "scripts.summarize_narrative": "nexus.jobs.summarize_narrative",
}
WRAPPER_PATHS = {name.replace(".", "/") + ".py" for name in MOVED}


def _defined_names(tree: ast.Module) -> set[str]:
    """Find definitions and assignments in module scope, including its blocks."""
    names: set[str] = set()

    def assignment_names(target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                assignment_names(item)
        elif isinstance(target, ast.Starred):
            assignment_names(target.value)

    def visit(statements: list[ast.stmt]) -> None:
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    assignment_names(target)
            elif isinstance(node, ast.AnnAssign):
                assignment_names(node.target)
            elif isinstance(node, (ast.If, ast.Try, ast.TryStar, ast.With)):
                visit(node.body)
                if isinstance(node, (ast.If, ast.Try, ast.TryStar)):
                    visit(node.orelse)
                if isinstance(node, (ast.Try, ast.TryStar)):
                    visit(node.finalbody)
                    for handler in node.handlers:
                        visit(handler.body)

    visit(tree.body)
    return {name for name in names if not name.startswith("__")}


@pytest.mark.parametrize(("wrapper_name", "module_name"), sorted(MOVED.items()))
def test_wrapper_reexports_every_defined_name(
    wrapper_name: str, module_name: str
) -> None:
    """Fails when a wrapper drops a private export or gains an imported-only name."""
    path = ROOT / (module_name.replace(".", "/") + ".py")
    expected = _defined_names(ast.parse(path.read_text()))
    # Literal imports keep the repository's source reachability check complete.
    modules = {
        "scripts.migrate": importlib.import_module("scripts.migrate"),
        "scripts.new_story_setup": importlib.import_module("scripts.new_story_setup"),
        "scripts.database_targets": importlib.import_module("scripts.database_targets"),
        "scripts.summarize_narrative": importlib.import_module(
            "scripts.summarize_narrative"
        ),
        "nexus.maintenance.migrate": importlib.import_module(
            "nexus.maintenance.migrate"
        ),
        "nexus.maintenance.new_story_setup": importlib.import_module(
            "nexus.maintenance.new_story_setup"
        ),
        "nexus.maintenance.database_targets": importlib.import_module(
            "nexus.maintenance.database_targets"
        ),
        "nexus.jobs.summarize_narrative": importlib.import_module(
            "nexus.jobs.summarize_narrative"
        ),
    }
    wrapper, module = modules[wrapper_name], modules[module_name]
    assert wrapper.__all__ == sorted(expected)
    for name in expected:
        assert getattr(wrapper, name) is getattr(module, name), name


def _moved_imports(tree: ast.Module, *, named_imports: bool) -> list[int]:
    """Locate forbidden module-object imports and, optionally, named imports."""
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in MOVED for alias in node.names):
                findings.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "scripts" and any(
                f"scripts.{alias.name}" in MOVED for alias in node.names
            ):
                findings.append(node.lineno)
            elif named_imports and node.module in MOVED:
                findings.append(node.lineno)
    return findings


def test_runtime_imports_no_moved_script_module() -> None:
    """Fails if any runtime path, including a lazy import, retains a wrapper."""
    findings = []
    for path in sorted((ROOT / "nexus").rglob("*.py")):
        findings.extend(
            f"{path.relative_to(ROOT)}:{line}"
            for line in _moved_imports(ast.parse(path.read_text()), named_imports=True)
        )
    assert findings == []


def test_no_tracked_file_binds_a_wrapper_module() -> None:
    """Fails if a script or test patches an independent wrapper module binding."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "scripts", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.split("\0")
    findings = []
    for relative in tracked:
        if not relative.endswith(".py") or relative in WRAPPER_PATHS:
            continue
        findings.extend(
            f"{relative}:{line}"
            for line in _moved_imports(
                ast.parse((ROOT / relative).read_text()), named_imports=False
            )
        )
    assert findings == []


@pytest.mark.parametrize(
    "script", ["migrate", "new_story_setup", "summarize_narrative"]
)
def test_wrappers_run_as_commands(tmp_path: Path, script: str) -> None:
    """Fails if a command wrapper loses its main block or its path bootstrap."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / f"{script}.py"), "--help"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()
