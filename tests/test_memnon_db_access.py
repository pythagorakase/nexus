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
                    line = getattr(node, "lineno")
                    found.append(f"{path.relative_to(root)}:{line}")
    assert found == []


def test_content_processor_sql_alias_and_embedding_error_reraise() -> None:
    """Keep narrative text parameters while constructing SQL and failing loudly."""
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse(
        (root / "nexus/agents/memnon/utils/content_processor.py").read_text()
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "sqlalchemy"
        and any(
            alias.name == "text" and alias.asname == "sql_text" for alias in node.names
        )
        for node in ast.walk(tree)
    )
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"store_narrative_chunk", "_generate_chunk_embeddings"}
    }
    for method in methods.values():
        assert "text" in [arg.arg for arg in method.args.args]
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            for node in ast.walk(method)
        )
    assert (
        sum(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sql_text"
            for method in methods.values()
            for node in ast.walk(method)
        )
        == 6
    )
    handlers = [
        node
        for node in ast.walk(methods["_generate_chunk_embeddings"])
        if isinstance(node, ast.ExceptHandler)
    ]
    assert len(handlers) == 1
    assert isinstance(handlers[0].body[-1], ast.Raise)
    assert handlers[0].body[-1].exc is None
