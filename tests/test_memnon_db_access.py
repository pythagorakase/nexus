"""Offline removal proof for constructor schema setup."""

import ast
from pathlib import Path


def test_setup_database_indexes_is_absent() -> None:
    """Reject the removed function, imports, calls and hybrid setup method."""
    root = Path(__file__).resolve().parents[1]
    found = []
    for directory in ["nexus", "scripts", "ir_eval"]:
        for path in sorted((root / directory).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                names = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        names.append(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        names.append(node.func.attr)
                if any(
                    name in {"setup_database_indexes", "_setup_hybrid_search"}
                    for name in names
                ):
                    found.append(f"{path.relative_to(root)}:{node.lineno}")
    assert found == []
