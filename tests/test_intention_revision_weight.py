"""Offline tests for the 782-S0 Gaia revision weight report."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

from nexus.agents.logon.apex_schema import OrreryReplacementStateDelta
from nexus.agents.logon.skald_wire import SkaldGaiaWire
from scripts.qa_shift import intention_revision_weight as report

SCRIPT_PATH = Path(report.__file__)
DEFAULT_COUNTS = [int(part) for part in report.DEFAULT_OPEN_COUNTS.split(",")]
REPORT_KEYS = {
    "model_id",
    "baseline",
    "verb_set",
    "probe_shape",
    "grammar",
    "grammar_delta",
    "rendered_context",
    "per_call_growth",
}
FORBIDDEN_IMPORTS = (
    "psycopg2",
    "asyncpg",
    "sqlalchemy",
    "nexus.agents.logon.gaia_registry_schema",
)


def _drop_property(node: Dict[str, Any], name: str) -> None:
    """Delete one property and its ``required`` entry from a schema object."""

    del node["properties"][name]
    if name in node.get("required", []):
        node["required"].remove(name)
        if not node["required"]:
            del node["required"]


def _strip_option_1(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove option 1's root field and probe definition."""

    stripped = copy.deepcopy(schema)
    _drop_property(stripped, "intention_revisions")
    del stripped["$defs"]["IntentionRevisionProbe"]
    return stripped


def _strip_option_2(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove option 2's delta field and probe definition."""

    stripped = copy.deepcopy(schema)
    _drop_property(
        stripped["$defs"]["OrreryReplacementStateDelta"], "intention_revision"
    )
    del stripped["$defs"]["IntentionRevisionDeltaProbe"]
    return stripped


STRIPPERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "option_1_new_field": _strip_option_1,
    "option_2_replace_path": _strip_option_2,
}
SCHEMAS: Dict[str, Callable[[Any], Dict[str, Any]]] = {
    "strict": report.strict_schema,
    "lenient": report.lenient_schema,
}


def test_baseline_is_the_static_gaia_wire() -> None:
    """The baseline is the production wire itself, not a copy."""

    assert report.WIRES["baseline"] is SkaldGaiaWire


@pytest.mark.parametrize("schema_kind", sorted(SCHEMAS))
@pytest.mark.parametrize("option", sorted(STRIPPERS))
def test_probe_wires_add_only_their_field(option: str, schema_kind: str) -> None:
    """Each probe wire equals the baseline once its one field is removed."""

    build = SCHEMAS[schema_kind]
    probe = build(report.WIRES[option])
    baseline = build(report.WIRES["baseline"])
    assert STRIPPERS[option](probe) == baseline


def test_listing_growth() -> None:
    """Option 1's listing grows with every open count; option 2 adds none."""

    settings = report.load_settings()
    count = report.estimator_for(
        settings.apex.gaia_model or settings.apex.model, settings=settings
    )
    option_1 = report.listing_tokens("option_1_new_field", DEFAULT_COUNTS, count)
    option_2 = report.listing_tokens("option_2_replace_path", DEFAULT_COUNTS, count)
    tokens = [option_1[str(n)] for n in DEFAULT_COUNTS]
    assert DEFAULT_COUNTS[0] == 0 and tokens[0] == 0
    assert all(later > earlier for earlier, later in zip(tokens, tokens[1:]))
    assert set(option_2.values()) == {0}


def test_production_wire_unchanged() -> None:
    """The probe fields never leak into the production models."""

    assert "intention_revisions" not in SkaldGaiaWire.model_fields
    assert "intention_revision" not in OrreryReplacementStateDelta.model_fields


def test_script_is_offline() -> None:
    """The script imports no database driver and no registry schema."""

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    offenders = {
        name
        for name in imported
        for forbidden in FORBIDDEN_IMPORTS
        if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert offenders == set()


def test_main_prints_one_json_document(capsys: pytest.CaptureFixture[str]) -> None:
    """``main`` prints exactly one JSON document carrying every report key."""

    assert report.main(["--open-counts", "0,2"]) == 0
    out = capsys.readouterr().out
    document = json.loads(out)
    assert set(document) >= REPORT_KEYS
    assert set(document["rendered_context"]["option_1_new_field"]["tokens"]) == {
        "0",
        "2",
    }
