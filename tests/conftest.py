"""Global pytest configuration for integration test gating."""

from __future__ import annotations

import os
from typing import Iterable

import psycopg2
import pytest


def _flag_enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def _apply_marker_skip(items: Iterable[pytest.Item], marker: str, reason: str) -> None:
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if marker in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(autouse=True)
def _forbid_unopted_postgres_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a default-path test attempts a live DB connection."""
    if _flag_enabled("NEXUS_RUN_POSTGRES"):
        return

    def fail_connect(*args: object, **kwargs: object) -> None:
        # pytest.fail raises a BaseException-derived outcome, so application
        # code that wraps optional DB reads in `except Exception` cannot
        # swallow the tripwire and quietly proceed.
        pytest.fail(
            "Unit test attempted psycopg2.connect; mark it requires_postgres "
            "and run with NEXUS_RUN_POSTGRES=1.",
            pytrace=False,
        )

    monkeypatch.setattr(psycopg2, "connect", fail_connect)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not _flag_enabled("NEXUS_RUN_POSTGRES"):
        _apply_marker_skip(
            items,
            "requires_postgres",
            "Set NEXUS_RUN_POSTGRES=1 to run PostgreSQL integration tests.",
        )

    if not _flag_enabled("NEXUS_RUN_LIVE_LLM"):
        _apply_marker_skip(
            items,
            "live_llm",
            "Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.",
        )
        _apply_marker_skip(
            items,
            "live",
            "Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.",
        )
