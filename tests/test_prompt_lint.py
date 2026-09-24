"""Keep model prose file-backed and the registry closed over its live readers.

The AST heuristic checks every string expression regardless of quoting,
including implicit/explicit concatenation and f-string literal parts. It flags
known model-addressed phrases and sentence-opening second-person imperatives.
Function documentation uses a narrower model-address heuristic so ordinary
"Return the parsed result" docstrings are not mistaken for instructions. Known
model phrases are checked in docstrings too. Field(description=...) remains
outside this mechanical slice. Exact (path, literal) allowlist entries document
human-facing diagnostics; no file or call-site blanket exemptions hide new prose.
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
from scripts.check_reachability import repository_files

ROOT = Path(__file__).resolve().parents[1]
MODEL_ADDRESS = re.compile(
    "\\b(?:you (?:are|must|should|will|may)|respond with|continue the narrative|maintain consistency|return only|ignore freely)\\b",
    re.IGNORECASE,
)
PROSE = re.compile(
    r"\b(?:you (?:are|must|should|will|may)|respond with|continue the narrative|"
    r"maintain consistency|return only|ignore freely)\b"
    r"|(?:^|[.!?]\s+|\n)\s*(?:please\s+)?(?:Generate|Use|Create (?:a|an|the|your)|Write|Keep|"
    r"Ensure|Include|Avoid|Describe|Choose|Preserve|Respect|Treat|Follow|Output|"
    r"Do not|Return (?:json|a|the)|Select (?:a|the|only))\s",
    re.IGNORECASE,
)


# Exact reviewed human-facing messages only; the reason explains their audience.
PROSE_ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "nexus/database.py",
        "Return only non-secret target fields for preflight and diagnostics.",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "nexus/agents/orrery/drift.py",
        "Return only edges whose Stage-1 derived rung changed.",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "nexus/agents/lore/utils/chunk_operations.py",
        "\n    Format a chunk with its metadata headers for Apex AI.\n\n    Uses the same format as narrative_view to maintain consistency.\n\n    Args:\n        chunk_data: Dictionary with chunk data and metadata\n        include_world_time: Whether to include world time in header\n\n    Returns:\n        Formatted chunk text with headers\n    ",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "scripts/api_openai.py",
        '\nNEXUS OpenAI API Library\n\nThis module provides reusable components for OpenAI API access across NEXUS scripts.\nIt centralizes common functionality to maintain consistency and avoid code duplication.\n\nFeatures:\n- Support for both standard and reasoning models (GPT-4/GPT-4o vs o1/o4)\n- Automatic handling of appropriate parameters based on model type\n- Token counting and management\n- Rate limiting protection\n- Error handling and retries\n\nThis file is designed to be imported by other scripts rather than used directly.\n\nCommon Arguments for Scripts Using This Library:\n--------------------------------------------\nLLM Provider Options:\n    --model MODEL           Model name to use (defaults to DEFAULT_MODEL)\n    --api-key KEY           API key (optional, tries environment variables by default)\n    --temperature FLOAT     Model temperature (0.0-1.0, default 0.1)\n    --max-tokens INT        Maximum tokens to generate in response (default: 4000)\n    --system-prompt TEXT    Optional system prompt to use\n    --effort               Reasoning effort for o-prefixed models: "low", "medium", or "high"\n                            (Only applicable for reasoning models like o1, o4)\n\nProcessing Options:\n    --batch-size INT        Number of items to process before prompting to continue (default: 10)\n    --dry-run               Don\'t actually save results to the database\n    --db-url URL            Database connection URL (optional, defaults to environment variables)\n',
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "scripts/test_narrative_turn.py",
        "\n        Continue the narrative from a given chunk\n\n        Args:\n            parent_chunk_id: The chunk to continue from\n            user_text: User's completion text\n\n        Returns:\n            Dict with incubator data and diagnostics\n        ",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "scripts/api_anthropic.py",
        "\nNEXUS Anthropic API Library\n\nThis module provides reusable components for Anthropic Claude API access\nacross NEXUS scripts.\nIt centralizes common functionality to maintain consistency and avoid code duplication.\n\nFeatures:\n- Support for Claude models (standard, Sonnet, Opus, Haiku, etc.)\n- Token counting and management\n- Rate limiting protection\n- Error handling and retries\n- Support for Claude's reasoning capabilities via system prompts\n\nThis file is designed to be imported by other scripts rather than used directly.\n\nCommon Arguments for Scripts Using This Library:\n--------------------------------------------\nLLM Provider Options:\n    --model MODEL           Model name to use (defaults to DEFAULT_MODEL)\n    --api-key KEY           API key (optional, tries environment variables by default)\n    --temperature FLOAT     Model temperature (0.0-1.0, default: API default)\n    --max-tokens INT        Maximum tokens to generate in response (default: 4000)\n    --system-prompt TEXT    Optional system prompt to use\n    --top-p FLOAT           Top-p sampling parameter (0.0-1.0, default None)\n    --top-k INT             Top-k sampling parameter (default None)\n    --timeout INT           Request timeout in seconds (default: 120)\n\nProcessing Options:\n    --batch-size INT        Number of items processed before confirmation (default: 10)\n    --dry-run               Don't actually save results to the database\n    --db-url URL            Database URL (optional, defaults to environment variables)\n",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "scripts/estimate_time_delta.py",
        "\n    Get all chunks with missing or zero time_delta values.\n\n    Args:\n        db: Database engine\n        primary_only: If True, return only chunks with world_layer='primary'\n    ",
    ): "Developer API documentation describing the function or module, not model instructions.",
    (
        "nexus/agents/lore/logon_utility.py",
        "Anthropic two-pass execution cannot use anthropic_storyteller_transport='native': the gaia wire cannot compile under Anthropic native enforcement (probe G2b, issue #566). Choose 'prompted' or 'tool_envelope' for the gaia.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/agents/lore/lore.py",
        "answer_question is deprecated. Use retrieve_context with directives instead.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/agents/memnon/test_idf_dictionary.py",
        "No database URL provided. Use --db-url or configure in settings.json",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/agents/orrery/catalog.py",
        "Write the rendered catalog to docs/orrery_packages.md",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep moving, blend into public flow",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Preserve the silence another day",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep a public role legible",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep the ledger plausible from a fixed post",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep tabs from a distance",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Follow the public pattern",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep the target in view without contact",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep administrative obligations moving",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep the obligation from slipping",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep the household running",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "{actor} doesn't quite reach out — but they place a sign where {target} will see it, the kind of signal that says *I am willing to talk if you are*, without committing to anything. If {target} reads the sign, the contact has begun. If they don't, it hasn't.",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Keep the edge from dulling",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/templates.py",
        "Choose the place and begin committing",
    ): "Orrery branch label or quoted in-world dialogue, not an instruction to the model.",
    (
        "nexus/agents/orrery/worker.py",
        "Select the registered TEST provider in settings for scheduler proofs",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/api/mock_openai.py",
        "[TEST MODE] Let's establish the world that will shape this story. Choose how you would like to begin.",
    ): "Deterministic TEST response shown to the player, not provider input.",
    (
        "nexus/api/mock_openai.py",
        "Use the prepared test setting.",
    ): "Deterministic TEST response shown to the player, not provider input.",
    (
        "nexus/api/mock_openai.py",
        "Use the suggested three traits.",
    ): "Deterministic TEST response shown to the player, not provider input.",
    (
        "nexus/api/mock_openai.py",
        "Choose a different combination.",
    ): "Deterministic TEST response shown to the player, not provider input.",
    (
        "nexus/api/narrative.py",
        "Slot is in wizard mode. Use /api/story/new/chat for wizard.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/api/storyteller.py",
        "Legacy story generation is retired. Use POST /api/narrative/continue with an explicit slot to create a durable generation session.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/api/storyteller.py",
        "Legacy story regeneration is retired. Use POST /api/narrative/regenerate with an explicit slot to create a durable generation session.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/api/wizard_chat.py",
        "Slot is not in wizard mode. Use /api/narrative/continue for narrative mode.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/cli.py",
        "Follow the log",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Write canonical Retrograde rows. Without this flag the command uses a read-only dry run.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Treat unresolved expansion refs as minimum viable entity stubs. Dry-run reports would-create rows; execute inserts them before canonical Retrograde rows.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Ensure and embed retrieval summaries for persisted Retrograde world events",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Write dedicated summaries and run their embedding lifecycle. Without this flag the command uses a read-only dry run.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Write ready entity_tags from --manifest. Without this flag the command uses a read-only dry run.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/cli.py",
        "Slot  is empty. Use 'nexus continue --slot ' to initialize.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "nexus/config/settings_models.py",
        "[runtime.services.mock_openai] port  does not match the test provider base_url port  (). Keep them in sync.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/config/settings_models.py",
        "[runtime.services.llama_server] port  does not match the local provider base_url port  (). Keep them in sync.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "nexus/runtime/supervisor.py",
        "Service '' is already running (pid ). Use 'nexus restart' or 'nexus down' first.",
    ): "Application configuration or routing diagnostic for the operator or API client.",
    (
        "scripts/apply_slot2_semantic_tags.py",
        "Write tags. Without this flag the script only reports a dry run.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "Create a new context package with this name",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "\nUse 'exit' to quit",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "Invalid entity type for auto chunk: . Use 'character' or 'faction'.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "Invalid episode field: . Use 'summary' or 'raw'.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "Invalid episode content type: . Use 'summary' or 'raw'.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/assemble_context.py",
        "Invalid entity type for auto episode: . Use 'character' or 'faction'.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/check_reachability.py",
        "Write the complete deterministic JSON graph",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/creative_character_expansion.py",
        "Generate creative character expansions for NEXUS database",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/creative_character_expansion.py",
        "Process specific chunks (chunk IDs comma-separated, or range using hyphen, or 'all'). Use 'auto' to automatically get chunks for the character's appearances.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/creative_character_expansion.py",
        "Use a manually curated context file (JSON) instead of querying the database.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/estimate_time_delta.py",
        "Write results to database",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/faction_relationship_analyst.py",
        "Generate faction relationship data using OpenAI o3",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/freestyle_api_query.py",
        "Invalid number of episode arguments. Use one slug for a single episode, or two for a range.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/generate_octen_embeddings.py",
        "Generate Octen embeddings for MEMNON",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "Choose option [1-2]: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "Choose option []: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "Choose option [1-3, q]: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "Invalid option. Please choose 1, 2, 3, or q.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "\nChoose a different location:",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/map_builder_legacy.py",
        "Choose option [1-4, q]: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/process_characters.py",
        "Choose option [1-2]: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/process_characters.py",
        "Choose option [1-3]: ",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/qa_shift/qa_shift.py",
        "Create a guarded run",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/query_narratives.py",
        "Output format (default: text)",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/query_narratives_vector.py",
        "Embedding utilities not found. Please ensure scripts/utils/embedding_utils.py exists.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/query_narratives_vector.py",
        "Use text search instead of vector search",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/regenerate_embeddings.py",
        "Generate embeddings for one chunk ID",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/replay_state.py",
        "write the full state document (JSON)",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/retrieval_query_bakeoff.py",
        "Keep MEMNON/LLM library logs visible during long bake-off runs",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/run_golden_queries.py",
        'Output mode: "file" to save to disk, "json" to print to stdout',
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/simple_update.py",
        "You may need to alter the constraint to add ON UPDATE CASCADE",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/summarize_narrative.py",
        "Generate comprehensive narrative summaries",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/summarize_narrative.py",
        "Do not attempt a fallback model if the primary fails",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/summarize_narrative.py",
        "Invalid number of episode arguments. Use one slug for a single episode, or two for a range.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/sync_secrets.py",
        "ERROR: unknown reference scheme for '': . Use 'op-item:...' or 'op-read:...'.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/token_counter.py",
        "\nNo files to process. Use 'python token_counter.py --help' for usage.",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
    (
        "scripts/update_raw_text.py",
        "Create a backup of the narrative_chunks table before updating (default: True)",
    ): "Operator-facing CLI help, input prompt, or diagnostic.",
}


def _python_sources() -> list[Path]:
    """Every maintained Python file in git's view of the checkout.

    Ignored files (downloaded model weights under nexus/models/) are not
    repository source; a scratch copy without ``.git`` scans everything on disk.
    """
    tracked = repository_files(ROOT)
    return sorted(
        path
        for directory in (ROOT / "nexus", ROOT / "scripts")
        for path in directory.rglob("*.py")
        if tracked is None or path.relative_to(ROOT).as_posix() in tracked
    )


def _literal_text(node: ast.AST) -> str | None:
    """Collect literal text across concatenations without evaluating Python."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value for part in node.values if isinstance(part, ast.Constant)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal_text(node.left), _literal_text(node.right)
        if left is not None or right is not None:
            return (left or "") + (right or "")
    return None


def _embedded_prose(source: str, path: str = "") -> list[int]:
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
        if _literal_text(node) is None:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.JoinedStr) or (
            isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Add)
        ):
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
        value = _literal_text(node)
        heuristic = MODEL_ADDRESS if node in docstrings else PROSE
        if not isinstance(value, str) or not heuristic.search(value):
            continue
        if (path, value) not in PROSE_ALLOWLIST:
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


def test_python_has_no_embedded_prompt_prose() -> None:
    violations = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in _python_sources()
        for line in _embedded_prose(path.read_text(), str(path.relative_to(ROOT)))
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
    script = """
from pathlib import Path
from nexus.prompts.registry import PromptId, load
path = Path("prompts/storyteller_core.md")
try:
    load(PromptId.STORYTELLER_CORE)
except FileNotFoundError as exc:
    assert str(path.parent.resolve()) in str(exc)
else:
    raise AssertionError("missing directory was accepted")
path.parent.mkdir()
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


@pytest.mark.asyncio
async def test_wizard_tools_use_registered_descriptions() -> None:
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
            definition = await tool.prepare_tool_def(None)
            assert definition.description == load(prompt_id)


@pytest.mark.parametrize(
    "source",
    [
        'prompt = "Continue the narrative from this point."',
        "prompt = 'Maintain consistency with the supplied context.'",
        'prompt = ("Respond " "with a single JSON object.")',
        'prompt = f"Respond with a scene about {subject}."',
        'prompt = "Respond " + "with a single JSON object."',
        'prompt = "You are the narrator."',
        '"""You are the narrator."""',
        'def f():\n    """Respond with a JSON scene."""',
        'prompt = "Return only the requested JSON."',
        'prompt = "Ignore freely, render subtly."',
        'prompt = "Preserve the established voice."',
    ],
)
def test_all_literal_forms_reject_model_instructions(source: str) -> None:
    """Quoting style cannot conceal a model instruction from the AST scan."""
    assert _embedded_prose(source) == ([2] if source.startswith("def ") else [1])


def test_allowlist_is_exact_and_has_no_stale_entries() -> None:
    """Each exception names a reviewed literal and cannot exempt adjacent prose."""
    for (path, value), reason in PROSE_ALLOWLIST.items():
        assert reason
        source = (ROOT / path).read_text()
        tree = ast.parse(source)
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        literals.update(
            "".join(
                part.value for part in node.values if isinstance(part, ast.Constant)
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
        )
        assert value in literals, (path, value)
        assert PROSE.search(value), (path, value)
        assert not _embedded_prose(f"message = {value!r}", path)
        assert _embedded_prose(
            f"message = {value!r}\nprompt = 'Respond with a scene.'", path
        ) == [2]


def test_review_injections_fail_the_gate_in_scratch_copy(tmp_path: Path) -> None:
    """Run the actual repository lint against all three review injections."""
    for source in _python_sources():
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    test_file = tmp_path / "tests/test_prompt_lint.py"
    test_file.parent.mkdir()
    shutil.copy2(Path(__file__), test_file)
    injections = (
        'prompt = "Continue the narrative from this point."\n',
        "prompt = 'Maintain consistency with the supplied context.'\n",
        'prompt = ("Respond " "with a single JSON object.")\n',
    )
    for source in injections:
        (tmp_path / "nexus/review_injection.py").write_text(source)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(test_file) + "::test_python_has_no_embedded_prompt_prose",
                "--rootdir=" + str(tmp_path),
                "-c",
                "/dev/null",
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(tmp_path)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "nexus/review_injection.py:1" in result.stdout
        assert "1 failed" in result.stdout
        print(f"Rejected {source.strip()}: 1 failed (expected)")


def test_api_import_does_not_read_prompt_files() -> None:
    """A fresh API process defers all prompt reads until runtime use."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import nexus.api.narrative; "
            "from nexus.prompts.registry import _template; "
            "assert _template.cache_info().misses == 0, _template.cache_info()",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
