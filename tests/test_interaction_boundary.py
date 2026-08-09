"""Static trust-boundary guards for interaction authorization."""

from __future__ import annotations

import ast
from pathlib import Path


def test_wire_and_adapter_layers_cannot_reach_interaction_grants() -> None:
    """Keep model-facing modules outside the interaction grant import graph."""
    nexus_root = Path(__file__).resolve().parents[1] / "nexus"
    candidates = set((nexus_root / "api").rglob("*.py"))
    candidates.update(nexus_root.rglob("*wire*.py"))
    candidates.update(nexus_root.rglob("*adapter*.py"))
    candidates.update(nexus_root.rglob("*schemas.py"))
    violations: list[str] = []
    for path in sorted(candidates):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "nexus.interactions"
            ):
                violations.append(f"{path}: imports {node.module}")
            elif isinstance(node, ast.Import) and any(
                alias.name.startswith("nexus.interactions") for alias in node.names
            ):
                violations.append(f"{path}: imports nexus.interactions")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "grant"
            ):
                violations.append(f"{path}: calls a grant API")
    assert violations == []
