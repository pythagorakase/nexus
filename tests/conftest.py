"""Global pytest configuration for integration test gating."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Iterable

import psycopg2
import pytest

# Apply before collection and propagate to test subprocesses.
if os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
    os.environ["NEXUS_TEST_PROVIDER_ONLY"] = "1"

from nexus.telemetry import usage as usage_telemetry
from nexus.util.secret_manager import InMemorySecretBackend, use_secret_backend
from tests import secret_store_guard

# Guard the real secret-store backends before collection, so test-module
# imports and session- or module-scoped fixtures are covered as well as test
# bodies. A conftest that cannot install the guard fails to load, and pytest
# stops before collecting anything.
secret_store_guard.install(setattr)


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


@pytest.fixture(autouse=True)
def _forbid_unopted_secret_store_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test reaches a real platform secret store.

    Every Keychain and keyring operation is wrapped by
    ``tests/secret_store_guard.py``; a denied call fails through ``pytest.fail``
    before any ``security`` subprocess or ``keyring`` call runs. The guard is
    re-applied per test so a test that replaced a backend method still runs
    guarded. Only ``NEXUS_RUN_SECRET_STORE=1`` (disposable keychain files) and
    ``NEXUS_RUN_LIVE_LLM=1`` (reads of ``nexus-api``) widen it, and only when
    set before the session starts.
    """
    secret_store_guard.install(monkeypatch.setattr)


@pytest.fixture
def in_memory_secret_store(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemorySecretBackend]:
    """Route ``get_secret``/``set_secret`` to a private in-memory store.

    ``NEXUS_KEYRING_DISABLE`` is removed so the store path, not the env-only
    path, is exercised. With this backend injected and the session guard in
    place, removing it cannot reach the owner's store. Leaving the block
    restores the previous backend and clears the read cache.
    """
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    backend = InMemorySecretBackend()
    with use_secret_backend(backend):
        yield backend


@pytest.fixture(autouse=True)
def _isolate_provider_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep every fabricated provider response out of runtime telemetry."""

    config = usage_telemetry._RecorderConfig(
        enabled=True,
        usage_dir=tmp_path / "usage",
        daily_allowance={"openai": 2_500_000},
    )
    monkeypatch.setattr(usage_telemetry, "_config", config)


def pytest_report_header(config: pytest.Config) -> str:
    """Show the secret-store guard state at the top of every run."""
    return secret_store_guard.describe()


def pytest_collection_finish(session: pytest.Session) -> None:
    """Refuse to run any test if collection removed the secret-store guard."""
    if not secret_store_guard.installed():
        pytest.exit(
            "Secret-store guard is missing after collection; refusing to run "
            "tests that could reach the owner's credential store.",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not secret_store_guard.SECRET_STORE_OPT_IN:
        _apply_marker_skip(
            items,
            "requires_secret_store",
            "Set NEXUS_RUN_SECRET_STORE=1 to run disposable platform "
            "secret-store integration tests.",
        )

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
