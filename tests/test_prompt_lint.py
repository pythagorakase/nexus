"""Keep model prose file-backed and the registry closed over its live readers.

The prose heuristic inspects triple-quoted string expressions (including
f-strings), excluding actual Python docstrings and Field(description=...). It
flags sentences addressed to a model: "You are", second-person directions,
"Please", "Generate", "Return JSON/a/the", and "Do not". SQL, data formatting,
and developer docstrings are not prompt prose. No per-file exemptions apply.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from nexus.prompts.registry import PLACEHOLDER, PROMPTS, PromptId, load

ROOT = Path(__file__).resolve().parents[1]
PROSE = re.compile(
    r"\b(?:you are|your\s|you must|please\s|generate\s|return (?:json|a\s|the\s)|do not\s)",
    re.IGNORECASE,
)


def _python_sources() -> list[Path]:
    return sorted(
        path
        for directory in (ROOT / "nexus", ROOT / "scripts")
        for path in directory.rglob("*.py")
    )


def _embedded_prose(source: str) -> list[int]:
    tree = ast.parse(source)
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.JoinedStr)) or node in docstrings:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.JoinedStr):
            continue
        if isinstance(parent, ast.keyword) and parent.arg == "description":
            call = parents.get(parent)
            if isinstance(call, ast.Call) and (
                isinstance(call.func, ast.Name)
                and call.func.id == "Field"
                or isinstance(call.func, ast.Attribute)
                and call.func.attr == "Field"
            ):
                continue
        value = (
            node.value
            if isinstance(node, ast.Constant)
            else "".join(
                part.value for part in node.values if isinstance(part, ast.Constant)
            )
        )
        if not isinstance(value, str) or not PROSE.search(value):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if '"""' in segment or "'''" in segment:
            violations.append(node.lineno)
    return violations


def test_registry_paths_and_placeholders_are_complete() -> None:
    """Every document has exactly one registered identity and an exact contract."""
    paths = [spec.path for spec in PROMPTS.values()]
    assert len(paths) == len(set(paths))
    assert set(paths) == {
        str(path.relative_to(ROOT / "prompts"))
        for path in (ROOT / "prompts").rglob("*.md")
    }
    assert set(PROMPTS) == set(PromptId)
    for prompt_id, spec in PROMPTS.items():
        path = ROOT / "prompts" / spec.path
        assert path.resolve().is_relative_to(ROOT / "prompts")
        text = path.read_text(encoding="utf-8")
        assert text.strip(), prompt_id
        assert set(PLACEHOLDER.findall(text)) == spec.placeholders, prompt_id
        assert spec.seats, prompt_id
        assert load(prompt_id, **{key: f"<{key}>" for key in spec.placeholders})


def test_every_prompt_has_a_reader_outside_tests() -> None:
    """A document mentioned only by the registry itself is dead and fails."""
    readers = set()
    for path in _python_sources():
        if path == ROOT / "nexus/prompts/registry.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "load"
            ):
                if node.args and isinstance(node.args[0], ast.Attribute):
                    argument = node.args[0]
                    if (
                        isinstance(argument.value, ast.Name)
                        and argument.value.id == "PromptId"
                    ):
                        readers.add(argument.attr)
    assert readers == {prompt_id.name for prompt_id in PROMPTS}


def test_python_has_no_embedded_triple_quoted_prompt_prose() -> None:
    violations = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in _python_sources()
        for line in _embedded_prose(path.read_text())
    ]
    assert not violations, "Move prompt prose to the registry: " + ", ".join(violations)


def test_only_registry_constructs_prompt_paths() -> None:
    violations = []
    for path in _python_sources():
        if path == ROOT / "nexus/prompts/registry.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and node.value == "prompts":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, violations


def test_prose_heuristic_distinguishes_instructions_from_documentation() -> None:
    assert _embedded_prose('prompt = """You are a narrator.\nReturn JSON."""') == [1]
    assert _embedded_prose('prompt = f"""Please generate a scene.\n{context}"""') == [1]
    assert not _embedded_prose(
        'def f():\n    """Return the parsed result."""\n    pass'
    )
    assert not _embedded_prose('sql = """SELECT id\nFROM narrative_chunks"""')
    assert not _embedded_prose('field = Field(description="""Generate a scene.""")')


def test_missing_and_unknown_substitutions_fail_loudly() -> None:
    with pytest.raises(ValueError, match="missing placeholders.*MAX_LETTER_TOKENS"):
        load(PromptId.STORYTELLER_GAIA)
    with pytest.raises(ValueError, match="unknown placeholders.*EXTRA"):
        load(PromptId.STORYTELLER_GAIA, MAX_LETTER_TOKENS=300, EXTRA="unused")
    assert "{{EXTRA}}" in load(PromptId.STORYTELLER_GAIA, MAX_LETTER_TOKENS="{{EXTRA}}")


def test_real_file_failure_and_process_cache(tmp_path: Path) -> None:
    """Exercise real file IO in an isolated registry installation, without mocks."""
    package = tmp_path / "nexus/prompts"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    shutil.copy2(ROOT / "nexus/prompts/registry.py", package / "registry.py")
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    script = """
from pathlib import Path
from nexus.prompts.registry import PromptId, load
path = Path("prompts/storyteller_core.md")
try:
    load(PromptId.STORYTELLER_CORE)
except FileNotFoundError:
    pass
else:
    raise AssertionError("missing file was accepted")
path.write_text("Unchanged first read.\\n")
assert load(PromptId.STORYTELLER_CORE) == "Unchanged first read.\\n"
path.write_text("Changed on disk.")
assert load(PromptId.STORYTELLER_CORE) == "Unchanged first read.\\n"
path = Path("prompts/storyteller_gaia.md")
path.write_text("Missing its declared marker.")
try:
    load(PromptId.STORYTELLER_GAIA, MAX_LETTER_TOKENS=300)
except ValueError as exc:
    assert "placeholder contract differs" in str(exc)
else:
    raise AssertionError("missing template marker was accepted")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_wizard_tools_use_registered_descriptions() -> None:
    from nexus.api import wizard_agent

    for name in (
        "_setting_agent",
        "_setting_accept_agent",
        "_concept_agent",
        "_concept_accept_agent",
        "_traits_agent",
        "_wildcard_agent",
        "_wildcard_accept_agent",
        "_seed_agent",
        "_seed_accept_agent",
    ):
        for tool_name, tool in getattr(
            wizard_agent, name
        )._function_toolset.tools.items():
            prompt_id = PromptId["WIZARD_TOOL_" + tool_name.upper()]
            assert tool.description == load(prompt_id)
