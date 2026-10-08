"""Global pytest configuration for integration test gating."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

import psycopg2
import pytest

if TYPE_CHECKING:
    from _pytest.terminal import TerminalReporter

# Apply before collection and propagate to test subprocesses.
if os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
    os.environ["NEXUS_TEST_PROVIDER_ONLY"] = "1"

# Tests read the checkout's nexus.toml or a temporary one named by
# NEXUS_RUNTIME_CONFIG. An owner's exported NEXUS_HOME would make the owner's
# config active instead and refuse every temporary one as a second active
# config (#820). Tests that exercise the home set it themselves.
if "NEXUS_HOME" in os.environ:
    del os.environ["NEXUS_HOME"]

# An owner's exported NEXUS_SLOT names one of their save slots. Left in place,
# a gateway lifespan recovers that slot and starts its scheduler, and any code
# that resolves the active slot reaches the owner's database. It is removed
# here, before collection, so module imports never see it; the fixtures below
# remove it again for the session and for every test. A test or fixture that
# needs an active slot sets NEXUS_SLOT itself, for its own scope, to a slot it
# routes to a disposable clone.
if "NEXUS_SLOT" in os.environ:
    del os.environ["NEXUS_SLOT"]

from nexus.config.loader import TEST_PROVIDER_DATABASE_ENV
from nexus.runtime.contract import FALLBACK_RECEIPTS_DIR, TEST_RECEIPTS_ENV
from nexus.runtime.home import RECEIPTS_DIR, repo_root
from nexus.telemetry import usage as usage_telemetry
from nexus.util.secret_manager import (
    InMemorySecretBackend,
    keychain_read_error,
    use_secret_backend,
)
from tests import dbname_audit, secret_store_guard

ReceiptSnapshot = Optional[list[tuple[str, int]]]


def _snapshot_receipts(directory: Path) -> ReceiptSnapshot:
    """Sorted relative paths and sizes of every file below ``directory``."""
    if not directory.exists():
        return None
    return sorted(
        (path.relative_to(directory).as_posix(), path.stat().st_size)
        for path in directory.rglob("*")
        if path.is_file()
    )


# Failure receipts (#806) are written when a configuration fails to load, and
# tests break configurations on purpose. The checkout's and the user's receipt
# directories are snapshotted before anything can write a receipt, and every
# receipt of this session and its child processes (which inherit the seam)
# goes to a private temporary root instead. pytest_sessionfinish fails the
# session if either real directory changed.
_RECEIPT_ROOTS = (repo_root() / RECEIPTS_DIR, Path.home() / FALLBACK_RECEIPTS_DIR)
_RECEIPT_SNAPSHOTS = {root: _snapshot_receipts(root) for root in _RECEIPT_ROOTS}
_RECEIPT_SEAM = tempfile.mkdtemp(prefix="nexus-test-receipts-")
os.environ[TEST_RECEIPTS_ENV] = _RECEIPT_SEAM
_changed_receipt_roots: list[Path] = []

# No test or child process reaches the owner's ``mock`` (issue #816): every
# process this session spawns inherits this TEST provider database, which is
# never created, so an unrouted read fails because the database does not
# exist. A test that needs the TEST provider requests
# ``routed_test_provider_database``.
TEST_PROVIDER_UNROUTED_DATABASE = "qa640_816_test_provider_unrouted"
os.environ[TEST_PROVIDER_DATABASE_ENV] = TEST_PROVIDER_UNROUTED_DATABASE

# Guard the real secret-store backends before collection, so test-module
# imports and session- or module-scoped fixtures are covered as well as test
# bodies. A conftest that cannot install the guard fails to load, and pytest
# stops before collecting anything.
secret_store_guard.install(setattr)

# Env-only credential mode for this process too, except in live sessions,
# whose guarded reads of nexus-api need the store path. Child processes get
# NEXUS_KEYRING_DISABLE=1 from the guard's spawn tripwires in every session.
if not secret_store_guard.LIVE_LLM_OPT_IN:
    os.environ["NEXUS_KEYRING_DISABLE"] = "1"


def _flag_enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def _apply_marker_skip(items: Iterable[pytest.Item], marker: str, reason: str) -> None:
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if marker in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session", autouse=True)
def _clear_inherited_slot_for_the_session() -> None:
    """Remove an inherited ``NEXUS_SLOT`` before any session-scoped fixture."""
    os.environ.pop("NEXUS_SLOT", None)


@pytest.fixture(autouse=True)
def _clear_inherited_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no active slot.

    A slot left by a module- or session-scoped path (or set by a test outside
    its monkeypatch) never reaches the next test; a routed test that needs an
    active slot sets it after this runs.
    """
    monkeypatch.delenv("NEXUS_SLOT", raising=False)


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


@pytest.fixture(scope="session", autouse=True)
def _register_disposable_keychain_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Make pytest's base temp dir the only home of disposable keychains."""
    secret_store_guard.set_disposable_root(tmp_path_factory.getbasetemp())


@pytest.fixture(scope="session", autouse=True)
def _register_private_runtime_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Let the private-runtime guard admit configs under ``--basetemp``."""
    from tests import scheduler_helpers

    scheduler_helpers.register_pytest_basetemp(tmp_path_factory.getbasetemp())


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


class UnreadableSecretBackend(InMemorySecretBackend):
    """A store whose every read fails as a locked login Keychain does.

    Writes still land, as they do when only the read path is refused. Each
    read raises the error ``MacOSKeychainBackend.read`` raises for a
    ``security`` exit 36 (``errSecAuthFailed``) whose stderr carries a
    sentinel, so a test can prove that no message repeats the CLI's stderr.
    """

    def read(self, account: str) -> str | None:
        """Raise the access error a locked Keychain gives for ``account``."""
        raise keychain_read_error(
            account,
            subprocess.CalledProcessError(
                36, ["security"], stderr="STDERR-SENTINEL-821"
            ),
        )


@pytest.fixture
def unreadable_secret_store(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[UnreadableSecretBackend]:
    """Route ``get_secret``/``set_secret`` to a store that refuses every read.

    It requests ``in_memory_secret_store`` so its own override is entered last
    and wins (``use_secret_backend`` nests). This is the store seam, the same
    one the in-memory fixture uses, not a stand-in for the code under test.
    """
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    backend = UnreadableSecretBackend()
    with use_secret_backend(backend):
        yield backend


@pytest.fixture
def routed_test_provider_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route this process and its children to a seeded disposable TEST database.

    The clone is seeded through migration 008's production path. List this
    fixture before ``mock_openai_server`` (or any fixture that spawns a TEST
    provider): fixtures run in parameter order, and a child inherits the
    environment at spawn.
    """
    from tests import pg_fixtures

    with pg_fixtures.disposable_test_provider_database() as dbname:
        pg_fixtures.route_test_provider_database(monkeypatch.setenv, dbname)
        yield dbname


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


def pytest_configure(config: pytest.Config) -> None:
    """Load the owner-connection audit when ``NEXUS_DBNAME_AUDIT=1`` is set.

    ``-p tests.dbname_audit`` registers the same module under the same name,
    so both spellings together audit once.
    """
    name = dbname_audit.__name__
    if dbname_audit.enabled_by_environment() and not config.pluginmanager.has_plugin(
        name
    ):
        config.pluginmanager.register(dbname_audit, name)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the session's temporary receipt root."""
    shutil.rmtree(_RECEIPT_SEAM, ignore_errors=True)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the session if a test wrote into a real receipt directory."""
    _changed_receipt_roots[:] = [
        root
        for root in _RECEIPT_ROOTS
        if _snapshot_receipts(root) != _RECEIPT_SNAPSHOTS[root]
    ]
    if _changed_receipt_roots:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_report_header(config: pytest.Config) -> str:
    """Show the secret-store guard state at the top of every run."""
    return secret_store_guard.describe()


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Repeat the guard state after the run; ``-q`` hides the report header."""
    terminalreporter.write_line(secret_store_guard.describe())
    if _changed_receipt_roots:
        changed = ", ".join(str(root) for root in _changed_receipt_roots)
        terminalreporter.write_line(f"receipt isolation: receipts changed ({changed})")
    else:
        terminalreporter.write_line(
            "receipt isolation: checkout and user receipts untouched"
        )


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

    if not _flag_enabled("NEXUS_RUN_CORPUS"):
        _apply_marker_skip(
            items,
            "requires_corpus",
            "Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.",
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
