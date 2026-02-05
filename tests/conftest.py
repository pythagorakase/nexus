"""Global pytest configuration for integration test gating."""

from __future__ import annotations

import os
from typing import Iterable

import pytest


def _flag_enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def _apply_marker_skip(items: Iterable[pytest.Item], marker: str, reason: str) -> None:
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if marker in item.keywords:
            item.add_marker(skip_marker)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _flag_enabled("NEXUS_RUN_POSTGRES"):
        _apply_marker_skip(
            items,
            "requires_postgres",
            "Set NEXUS_RUN_POSTGRES=1 to run PostgreSQL integration tests.",
        )

    if not _flag_enabled("NEXUS_RUN_LOCAL_LLM"):
        _apply_marker_skip(
            items,
            "requires_local_llm",
            "Set NEXUS_RUN_LOCAL_LLM=1 to run local LM Studio tests.",
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
