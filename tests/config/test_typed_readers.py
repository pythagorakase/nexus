"""Typed settings readers reject absent required sections before database work."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import psycopg2
import pytest
from pydantic import ValidationError

from nexus.agents.orrery.experiences import experience_settings
from nexus.agents.orrery.retrograde_maturation import (
    drain_maturation_jobs_sync,
    enqueue_declared_entity_maturations,
)
from nexus.agents.orrery.worker import (
    drain_narration_outbox_sync,
    promote_pending_resolutions_sync,
)
from nexus.config import load_settings, load_settings_as_dict
from nexus.config.settings_models import Settings
from nexus.jobs.scheduler import SlotScheduler
from tests.config.test_settings_models import _nexus_toml_dict


@pytest.fixture(autouse=True)
def _forbid_reader_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep admission tests offline even inside a PostgreSQL-enabled session."""

    def fail_connect(*args: object, **kwargs: object) -> NoReturn:
        # This is a refusal tripwire, not a simulated database. pytest.fail's
        # BaseException outcome cannot satisfy the expected RuntimeError.
        pytest.fail("A settings reader attempted PostgreSQL before refusal")

    monkeypatch.setattr(psycopg2, "connect", fail_connect)


def test_no_product_module_reads_the_dict_facade() -> None:
    """Only the compatibility loader and its public export retain the facade."""
    root = Path(__file__).resolve().parents[2]
    allowed = {"nexus/config/__init__.py", "nexus/config/loader.py"}
    violations: set[str] = set()

    for path in sorted((root / "nexus").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=relative)):
            if isinstance(node, ast.ImportFrom):
                if any(alias.name == "load_settings_as_dict" for alias in node.names):
                    violations.add(f"{relative}:{node.lineno}")
            elif isinstance(node, ast.Name) and node.id == "load_settings_as_dict":
                violations.add(f"{relative}:{node.lineno}")
            elif (
                isinstance(node, ast.Attribute) and node.attr == "load_settings_as_dict"
            ):
                violations.add(f"{relative}:{node.lineno}")

    assert not violations, "Product dict facade readers:\n" + "\n".join(
        sorted(violations)
    )


@pytest.mark.parametrize(
    "missing_path",
    [
        pytest.param(("api", "constraints"), id="constraints-table"),
        pytest.param(
            ("api", "constraints", "max_choice_text_length"), id="choice-text-limit"
        ),
    ],
)
def test_api_constraints_are_required(missing_path: tuple[str, ...]) -> None:
    """An API table must specify its constraints and choice-text limit."""
    raw = _nexus_toml_dict()
    parent = raw
    for key in missing_path[:-1]:
        parent = parent[key]
    del parent[missing_path[-1]]

    with pytest.raises(ValidationError) as exc:
        Settings(**raw)

    assert any(
        error["loc"] == missing_path and error["type"] == "missing"
        for error in exc.value.errors()
    )


def test_require_section_helpers() -> None:
    """Section admission preserves identity and names the caller on refusal."""
    settings = load_settings()
    assert settings.require_orrery("x") is settings.orrery
    assert settings.require_runtime("x") is settings.runtime

    without_orrery = settings.model_copy(update={"orrery": None})
    with pytest.raises(RuntimeError) as exc:
        without_orrery.require_orrery("x")
    assert str(exc.value) == (
        "nexus.toml is missing the [orrery] section required for x"
    )

    without_runtime = settings.model_copy(update={"runtime": None})
    with pytest.raises(RuntimeError) as exc:
        without_runtime.require_runtime("x")
    assert str(exc.value) == (
        "nexus.toml is missing the [runtime] section required for x"
    )


@pytest.mark.parametrize(
    "reader",
    [
        pytest.param(
            lambda settings: promote_pending_resolutions_sync(settings=settings),
            id="promotion",
        ),
        pytest.param(
            lambda settings: drain_narration_outbox_sync(settings=settings),
            id="narration",
        ),
        pytest.param(
            lambda settings: drain_maturation_jobs_sync(settings=settings),
            id="maturation-drain",
        ),
        pytest.param(
            lambda settings: enqueue_declared_entity_maturations(
                None,
                declarations=[
                    {"kind": "character", "name": "Ash", "summary": "A runner."}
                ],
                chunk_id=1,
                raw_text="Ash",
                settings=settings,
            ),
            id="maturation-enqueue",
        ),
        pytest.param(experience_settings, id="experiences"),
        pytest.param(
            lambda settings: SlotScheduler(
                4, dbname="qa640_809_unused", settings=settings
            ),
            id="scheduler",
        ),
    ],
)
def test_readers_raise_without_orrery(
    monkeypatch: pytest.MonkeyPatch, reader: Callable[[Settings], object]
) -> None:
    """Missing Orrery fails before connections, defaults, or queue operations."""
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    settings = load_settings().model_copy(update={"orrery": None})

    with pytest.raises(RuntimeError, match=r"\[orrery\]"):
        reader(settings)


def test_scheduler_requires_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scheduler refuses absent runtime settings before starting work."""
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    settings = load_settings().model_copy(update={"runtime": None})

    with pytest.raises(RuntimeError, match=r"\[runtime\]"):
        SlotScheduler(4, dbname="qa640_809_unused", settings=settings)


def test_orrery_dump_equals_facade_section() -> None:
    """The one engine-boundary dump preserves the facade's exact Orrery value."""
    orrery = load_settings().orrery
    assert orrery is not None
    assert orrery.model_dump(by_alias=True) == load_settings_as_dict()["orrery"]
