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


INGEST_NAMES = {
    "ContentProcessor",
    "content_processor",
    "process_all_narrative_files",
    "process_chunked_file",
    "store_narrative_chunk",
    "_generate_chunk_embeddings",
}


def test_memnon_file_ingest_is_absent() -> None:
    """Reject any return of MEMNON's retired file ingest."""
    root = Path(__file__).resolve().parents[1]
    found = []
    if (root / "nexus/agents/memnon/utils/content_processor.py").exists():
        found.append("nexus/agents/memnon/utils/content_processor.py exists")
    for directory in ["nexus", "scripts", "ir_eval"]:
        for path in sorted((root / directory).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                names = []
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    names.append(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names.extend(alias.name for alias in node.names)
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names.extend(node.module.split("."))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    names.append(node.func.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                if any(name in INGEST_NAMES for name in names):
                    line = getattr(node, "lineno")
                    found.append(f"{path.relative_to(root)}:{line}")
    memnon = root / "nexus/agents/memnon/memnon.py"
    for node in ast.walk(ast.parse(memnon.read_text(), filename=str(memnon))):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("process files")
        ):
            found.append(f"memnon.py:{node.lineno}")
    assert found == []
