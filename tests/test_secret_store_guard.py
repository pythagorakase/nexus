"""Proof that the session guard denies the real platform secret store (#963).

Each probe first asserts that the guard is installed, so a broken guard fails
the test before any real backend method can run.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import keyring
import keyring.backend
import keyring.core
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from keyring.backends import macOS, null

from nexus.api import secrets_endpoints
from nexus.api.secrets_endpoints import SecretProvider, router
from nexus.util.secret_manager import (
    SERVICE_NAME,
    KeyringLibraryBackend,
    MacOSKeychainBackend,
    get_secret,
    set_secret,
)
from tests import secret_store_guard

PROBE_ACCOUNT = "guard-probe-963"
REPO_ROOT = Path(__file__).resolve().parents[1]
DISPOSABLE_SERVICE = "nexus-test-guard-probe"
REAL_BACKENDS = [MacOSKeychainBackend, KeyringLibraryBackend]

live_reads_allowed = pytest.mark.skipif(
    secret_store_guard.LIVE_LLM_OPT_IN,
    reason="NEXUS_RUN_LIVE_LLM=1 sessions may read service nexus-api.",
)


@pytest.fixture(autouse=True)
def _hostile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every variable a test might use to try to reopen the store.

    The guard's opt-ins were read before collection, so none of these edits
    may widen it.
    """
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    monkeypatch.setenv(secret_store_guard.SECRET_STORE_FLAG, "1")
    monkeypatch.setenv("NEXUS_RUN_LIVE_LLM", "1")
    assert secret_store_guard.installed()


def test_every_real_backend_operation_is_wrapped() -> None:
    for backend in REAL_BACKENDS:
        for operation in secret_store_guard.OPERATIONS:
            method = backend.__dict__[operation]
            assert getattr(method, secret_store_guard.GUARD_MARKER, False), (
                backend,
                operation,
            )


@pytest.mark.parametrize("backend_cls", REAL_BACKENDS)
@pytest.mark.parametrize("operation", ["write", "delete"])
def test_production_mutation_is_denied(
    backend_cls: type[MacOSKeychainBackend | KeyringLibraryBackend],
    operation: str,
) -> None:
    backend = backend_cls()
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@live_reads_allowed
@pytest.mark.parametrize("backend_cls", REAL_BACKENDS)
def test_production_read_is_denied(
    backend_cls: type[MacOSKeychainBackend | KeyringLibraryBackend],
) -> None:
    backend = backend_cls()
    assert not secret_store_guard.access_allowed(backend, "read")
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        backend.read(PROBE_ACCOUNT)


@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_owner_keyring_is_denied_under_any_service(operation: str) -> None:
    """The keyring default store is the owner's; no service makes it disposable."""
    backend = KeyringLibraryBackend(service=DISPOSABLE_SERVICE)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_login_keychain_search_list_is_denied_under_any_service(
    operation: str,
) -> None:
    """A non-production service still needs an explicit disposable keychain."""
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@pytest.mark.skipif(
    secret_store_guard.SECRET_STORE_OPT_IN,
    reason="NEXUS_RUN_SECRET_STORE=1 sessions may use disposable keychains.",
)
@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_disposable_keychain_needs_session_opt_in(
    operation: str,
    tmp_path: Path,
) -> None:
    backend = MacOSKeychainBackend(
        service=DISPOSABLE_SERVICE,
        keychain=tmp_path / "guard-probe.keychain-db",
    )
    assert secret_store_guard.is_disposable_keychain(backend.keychain)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


def test_every_keyring_backend_password_method_is_wrapped() -> None:
    """Including the macOS backend, which keyring defines only on demand."""
    classes = secret_store_guard.keyring_backend_classes()
    assert macOS.Keyring in classes and null.Keyring in classes
    for cls in classes:
        for name in secret_store_guard.KEYRING_FUNCTIONS:
            method = cls.__dict__.get(name)
            if method is not None:
                assert getattr(method, secret_store_guard.GUARD_MARKER, False), (
                    cls,
                    name,
                )


def test_keychain_outside_the_temp_root_is_never_disposable() -> None:
    login = Path.home() / "Library" / "Keychains" / "login.keychain-db"
    assert not secret_store_guard.is_disposable_keychain(login)
    assert not secret_store_guard.is_disposable_keychain(None)
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE, keychain=login)
    for operation in secret_store_guard.OPERATIONS:
        assert not secret_store_guard.access_allowed(backend, operation)


def test_only_pytest_basetemp_is_disposable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``TMPDIR`` pointing at home cannot make anything under home disposable."""
    assert secret_store_guard.is_disposable_keychain(tmp_path / "probe.keychain-db")
    monkeypatch.setattr(tempfile, "tempdir", str(Path.home()))
    assert tempfile.gettempdir() == str(Path.home())
    for outside in (
        Path.home() / "nexus-secret-it" / "probe.keychain-db",
        Path.home() / "Library" / "Keychains" / "login.keychain-db",
    ):
        assert not secret_store_guard.is_disposable_keychain(outside)
    monkeypatch.setattr(tempfile, "tempdir", None)
    sibling = Path(tempfile.gettempdir()) / "nexus-secret-it" / "probe.keychain-db"
    assert not secret_store_guard.is_disposable_keychain(sibling)


def test_library_is_never_disposable_even_under_the_disposable_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base temp dir above ``~/Library`` cannot expose the login keychain."""
    monkeypatch.setattr(secret_store_guard, "_disposable_root", Path.home().resolve())
    login = Path.home() / "Library" / "Keychains" / "login.keychain-db"
    assert not secret_store_guard.is_disposable_keychain(login)
    assert secret_store_guard.is_disposable_keychain(Path.home() / "x.keychain-db")


def test_nothing_is_disposable_before_the_root_is_registered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(secret_store_guard, "_disposable_root", None)
    assert not secret_store_guard.is_disposable_keychain(tmp_path / "x.keychain-db")


def test_keyword_call_reaches_the_guard() -> None:
    """Keyword arguments are forwarded, so the guard, not a TypeError, answers."""
    backend = MacOSKeychainBackend()
    with pytest.raises(pytest.fail.Exception, match=f"account '{PROBE_ACCOUNT}'"):
        backend.write(account=PROBE_ACCOUNT, key="never-stored")


def test_set_secret_without_injection_is_denied() -> None:
    with pytest.raises(pytest.fail.Exception, match="secret-store write"):
        set_secret(PROBE_ACCOUNT, "never-stored")


@live_reads_allowed
def test_get_secret_without_injection_is_denied() -> None:
    get_secret.cache_clear()
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        get_secret(PROBE_ACCOUNT)


@live_reads_allowed
def test_verify_endpoint_cannot_swallow_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verify route catches ``Exception``; the guard is a BaseException."""
    get_secret.cache_clear()
    provider = SecretProvider(provider=PROBE_ACCOUNT, account=PROBE_ACCOUNT)
    monkeypatch.setattr(secrets_endpoints, "get_secret_providers", lambda: [provider])
    app = FastAPI()
    app.include_router(router)
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        TestClient(app).post(f"/api/secrets/{PROBE_ACCOUNT}/verify")


def test_direct_security_cli_spawn_is_denied() -> None:
    """The #963 tests shelled out to ``security`` directly; that fails too."""
    with pytest.raises(pytest.fail.Exception, match="security CLI"):
        subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", "x"],
            capture_output=True,
            timeout=5.0,
        )


def test_shell_security_cli_spawn_is_denied() -> None:
    with pytest.raises(pytest.fail.Exception, match="security CLI"):
        subprocess.run(
            f"/usr/bin/security find-generic-password -s {SERVICE_NAME} -a x -w",
            shell=True,
            capture_output=True,
            timeout=5.0,
        )


def test_other_subprocesses_still_run() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "print('ok')"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30.0,
    )
    assert result.stdout == "ok\n"


@pytest.mark.parametrize("module", [keyring, keyring.core])
@pytest.mark.parametrize(
    "name,args",
    [
        ("get_password", (SERVICE_NAME, PROBE_ACCOUNT)),
        ("set_password", (SERVICE_NAME, PROBE_ACCOUNT, "never-stored")),
        ("delete_password", (SERVICE_NAME, PROBE_ACCOUNT)),
        ("get_credential", (SERVICE_NAME, PROBE_ACCOUNT)),
    ],
)
def test_direct_keyring_call_is_denied(
    module: object,
    name: str,
    args: tuple[str, ...],
) -> None:
    with pytest.raises(pytest.fail.Exception, match=f"keyring.{name}"):
        getattr(module, name)(*args)


@pytest.mark.skipif(
    secret_store_guard.SECRET_STORE_OPT_IN,
    reason="NEXUS_RUN_SECRET_STORE=1 sessions may set up disposable keychains.",
)
def test_disposable_keychain_setup_needs_session_opt_in(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="without opt-in"):
        with secret_store_guard.disposable_keychain_setup(tmp_path / "x.keychain"):
            pass


@pytest.fixture
def disposable_scope(tmp_path: Path) -> Iterator[Path]:
    """Open the scope ``disposable_keychain_setup`` would open.

    It enters the scope directly, without the session opt-in, so these tests
    can prove what an active disposable permission still refuses. Every probe
    below must be refused before anything is spawned.
    """
    keychain = tmp_path / "guard-probe.keychain-db"
    scope = secret_store_guard.keychain_setup_scope(keychain)
    with secret_store_guard._active_scope(scope):
        yield keychain


def _refused(argv: list[str], match: str) -> None:
    with pytest.raises(pytest.fail.Exception, match=match):
        subprocess.run(argv, capture_output=True, timeout=5.0)


def test_disposable_scope_refuses_a_mismatched_keychain(
    disposable_scope: Path,
    tmp_path: Path,
) -> None:
    other = str(tmp_path / "other.keychain-db")
    login = str(Path.home() / "Library" / "Keychains" / "login.keychain-db")
    for argv in (
        ["security", "delete-keychain", other],
        ["security", "show-keychain-info", login],
        ["security", "create-keychain", "-p", "pw", other],
        ["security", "delete-keychain", str(disposable_scope), other],
    ):
        _refused(argv, "exactly the disposable keychain")


def test_disposable_scope_refuses_a_missing_keychain(disposable_scope: Path) -> None:
    for argv in (
        ["security", "delete-keychain"],
        ["security", "show-keychain-info"],
        ["security", "unlock-keychain", "-p", "pw"],
    ):
        _refused(argv, "exactly the disposable keychain")


def test_disposable_scope_refuses_the_production_service(
    disposable_scope: Path,
) -> None:
    keychain = str(disposable_scope)
    for argv in (
        ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", "x"],
        ["security", "find-generic-password", f"-s{SERVICE_NAME}", "-a", "x", "-w"],
        [
            "security",
            "delete-generic-password",
            "-s",
            SERVICE_NAME,
            "-a",
            "x",
            keychain,
        ],
    ):
        _refused(argv, f"service '{SERVICE_NAME}'")


def test_disposable_scope_refuses_unneeded_subcommands(disposable_scope: Path) -> None:
    keychain = str(disposable_scope)
    for argv in (
        ["security", "dump-keychain", keychain],
        ["security", "set-keychain-settings", keychain],
        ["security", "default-keychain", "-s", keychain],
        ["security", "find-generic-password", "-s", "svc", "-a", "x", "-w", keychain],
    ):
        _refused(argv, "not permitted in this scope")
    _refused(
        ["security", "list-keychains", "-d", "user", "-s", keychain],
        "may only list the user search list",
    )


def test_disposable_backend_scope_binds_service_and_keychain(tmp_path: Path) -> None:
    keychain = tmp_path / "guard-probe.keychain-db"
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE, keychain=keychain)
    other = str(tmp_path / "other.keychain-db")
    with secret_store_guard._active_scope(
        secret_store_guard.backend_scope(backend, "delete")
    ):
        base = ["security", "delete-generic-password", "-a", "x"]
        _refused([*base, "-s", DISPOSABLE_SERVICE], "named keychain")
        _refused([*base, "-s", DISPOSABLE_SERVICE, other], "named keychain")
        _refused([*base, "-s", SERVICE_NAME, str(keychain)], f"'{SERVICE_NAME}'")
        _refused([*base, "-s", "nexus-test-other", str(keychain)], "targeted service")
        _refused(
            ["security", "add-generic-password", "-s", DISPOSABLE_SERVICE, "-a", "x"],
            "not permitted in this scope",
        )


def test_security_command_problem_accepts_exactly_the_needed_shapes(
    tmp_path: Path,
) -> None:
    """The integration fixture's and backends' own commands stay permitted."""
    keychain = tmp_path / "guard-probe.keychain-db"
    setup = secret_store_guard.keychain_setup_scope(keychain)
    for rest in (
        ["list-keychains", "-d", "user"],
        ["create-keychain", "-p", "pw", str(keychain)],
        ["unlock-keychain", "-p", "pw", str(keychain)],
        ["show-keychain-info", str(keychain)],
        ["delete-keychain", str(keychain)],
    ):
        assert (
            secret_store_guard.security_command_problem(["security", *rest], setup)
            is None
        )
    disposable = MacOSKeychainBackend(service=DISPOSABLE_SERVICE, keychain=keychain)
    production = MacOSKeychainBackend()
    for backend, operation, argv in (
        (disposable, "read", disposable._argv("find-generic-password", "a", "-w")),
        (disposable, "write", disposable._argv("delete-generic-password", "a")),
        (
            disposable,
            "write",
            disposable._argv("add-generic-password", "a", "-A", "-w", "k"),
        ),
        (disposable, "delete", disposable._argv("delete-generic-password", "a")),
        (production, "read", production._argv("find-generic-password", "a", "-w")),
    ):
        scope = secret_store_guard.backend_scope(backend, operation)
        assert secret_store_guard.security_command_problem(argv, scope) is None


def test_refusal_messages_never_repeat_secrets(tmp_path: Path) -> None:
    keychain = tmp_path / "guard-probe.keychain-db"
    other = str(tmp_path / "other.keychain-db")
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE, keychain=keychain)
    write_scope = secret_store_guard.backend_scope(backend, "write")
    add = ["security", "add-generic-password", "-s", DISPOSABLE_SERVICE, "-a", "x"]
    problem = secret_store_guard.security_command_problem(
        [*add, "-A", "-w", "sk-leak-probe", other], write_scope
    )
    assert problem is not None and "sk-leak-probe" not in problem
    setup = secret_store_guard.keychain_setup_scope(keychain)
    problem = secret_store_guard.security_command_problem(
        ["security", "create-keychain", "-p", "pw-leak-probe", other], setup
    )
    assert problem is not None and "pw-leak-probe" not in problem


def test_keyring_scope_binds_the_service() -> None:
    backend = KeyringLibraryBackend(service=DISPOSABLE_SERVICE)
    with secret_store_guard._active_scope(
        secret_store_guard.backend_scope(backend, "read")
    ):
        with pytest.raises(pytest.fail.Exception, match="inside a scope"):
            keyring.get_password(SERVICE_NAME, PROBE_ACCOUNT)
        with pytest.raises(pytest.fail.Exception, match="inside a scope"):
            keyring.get_keyring().get_password(SERVICE_NAME, PROBE_ACCOUNT)
        with pytest.raises(pytest.fail.Exception, match="inside a scope"):
            null.Keyring().get_password(service=SERVICE_NAME, username="x")
        # The scope's own service still reaches the backend.
        assert null.Keyring().get_password(DISPOSABLE_SERVICE, PROBE_ACCOUNT) is None


KEYRING_BACKEND_CALLS = [
    ("get_password", (SERVICE_NAME, PROBE_ACCOUNT)),
    ("set_password", (SERVICE_NAME, PROBE_ACCOUNT, "never-stored")),
    ("delete_password", (SERVICE_NAME, PROBE_ACCOUNT)),
    ("get_credential", (SERVICE_NAME, PROBE_ACCOUNT)),
]


@pytest.mark.parametrize("name,args", KEYRING_BACKEND_CALLS)
def test_resolved_keyring_backend_is_denied(name: str, args: tuple[str, ...]) -> None:
    """``keyring.get_keyring()`` is the owner's store; its methods are guarded."""
    with pytest.raises(pytest.fail.Exception, match=f"keyring backend .*{name}"):
        getattr(keyring.get_keyring(), name)(*args)


@pytest.mark.parametrize("name,args", KEYRING_BACKEND_CALLS)
@pytest.mark.parametrize(
    "backend",
    [macOS.Keyring, null.Keyring],
    ids=["macOS", "null"],
)
def test_directly_built_keyring_backend_is_denied(
    backend: type[keyring.backend.KeyringBackend],
    name: str,
    args: tuple[str, ...],
) -> None:
    with pytest.raises(pytest.fail.Exception, match=f"keyring backend .*{name}"):
        getattr(backend(), name)(*args)


def test_keyring_backend_defined_after_install_is_guarded() -> None:
    class LateKeyring(keyring.backend.KeyringBackend):
        priority = 0  # type: ignore[assignment]

        def get_password(self, service: str, username: str) -> str | None:
            raise AssertionError("the guard must refuse before the backend runs")

        def set_password(self, service: str, username: str, password: str) -> None:
            raise AssertionError("the guard must refuse before the backend runs")

    try:
        assert secret_store_guard.installed()
        for call in (
            lambda: LateKeyring().get_password(SERVICE_NAME, PROBE_ACCOUNT),
            lambda: LateKeyring().set_password(SERVICE_NAME, PROBE_ACCOUNT, "x"),
            lambda: LateKeyring().get_credential(SERVICE_NAME, PROBE_ACCOUNT),
        ):
            with pytest.raises(pytest.fail.Exception, match="LateKeyring"):
                call()
    finally:
        # keyring registers every concrete backend class; keep this one out of
        # later backend detection.
        keyring.backend.KeyringBackend._classes.discard(LateKeyring)


def test_path_like_popen_args_are_checked() -> None:
    """``Popen`` accepts a bare path-like program; it is checked like argv."""
    ran = subprocess.run(
        Path(sys.executable),
        input=b"print('ok')",
        capture_output=True,
        check=True,
        timeout=30.0,
    )
    assert ran.stdout == b"ok\n"
    with pytest.raises(pytest.fail.Exception, match="security CLI outside"):
        subprocess.run(Path("/usr/bin/security"), capture_output=True, timeout=5.0)


def test_os_system_security_is_denied() -> None:
    for command in (
        "security list-keychains",
        "/usr/bin/env security find-generic-password -s nexus-api -a x -w",
    ):
        with pytest.raises(pytest.fail.Exception, match="command string"):
            os.system(command)


@pytest.mark.skipif(not hasattr(os, "posix_spawn"), reason="No os.posix_spawn.")
@pytest.mark.parametrize("name", secret_store_guard.OS_POSIX_SPAWN_FUNCTIONS)
def test_os_posix_spawn_security_is_denied(name: str) -> None:
    path = "/usr/bin/security" if name == "posix_spawn" else "security"
    argv = ["security", "list-keychains", "-d", "user"]
    with pytest.raises(pytest.fail.Exception, match="security CLI outside"):
        getattr(os, name)(path, argv, dict(os.environ))


def _os_spawn_call(name: str, argv: list[str]) -> Callable[[], Any]:
    """Build one ``os.spawn*`` call running ``argv`` through ``name``."""
    searches_path = "p" in name[len("spawn") :]
    file = argv[0] if searches_path else "/usr/bin/security"
    env = dict(os.environ)
    function = getattr(os, name)
    takes_env = name.endswith("e")
    if name.startswith("spawnl"):
        rest = [*argv, env] if takes_env else argv
    else:
        rest = [argv, env] if takes_env else [argv]
    return lambda: function(os.P_WAIT, file, *rest)


@pytest.mark.parametrize("name", secret_store_guard.OS_SPAWN_FUNCTIONS)
def test_os_spawn_family_security_is_denied(name: str) -> None:
    call = _os_spawn_call(name, ["security", "list-keychains", "-d", "user"])
    with pytest.raises(pytest.fail.Exception, match="security CLI outside"):
        call()


CHILD_REPORT = (
    "import os, sys; "
    "open(sys.argv[1], 'w').write(str(os.environ.get('NEXUS_KEYRING_DISABLE')))"
)


@pytest.mark.parametrize(
    "spawn",
    [
        "popen-inherited",
        "popen-explicit-env",
        "os.system",
        "os.posix_spawn",
        "os.spawnv",
        "os.spawnve",
    ],
)
def test_every_child_starts_in_environment_only_mode(
    spawn: str,
    tmp_path: Path,
) -> None:
    """Children get NEXUS_KEYRING_DISABLE=1 even when this process lacks it.

    The autouse fixture removed it from this process, as a live session does.
    """
    if spawn == "os.posix_spawn" and not hasattr(os, "posix_spawn"):
        pytest.skip("No os.posix_spawn.")
    assert "NEXUS_KEYRING_DISABLE" not in os.environ
    report = tmp_path / "child-env.txt"
    argv = [sys.executable, "-c", CHILD_REPORT, str(report)]
    minimal = {"PATH": os.environ.get("PATH", "")}
    if spawn == "popen-inherited":
        subprocess.run(argv, check=True, timeout=30.0)
    elif spawn == "popen-explicit-env":
        subprocess.run(argv, env=minimal, check=True, timeout=30.0)
    elif spawn == "os.system":
        assert os.system(shlex.join(argv)) == 0
    elif spawn == "os.posix_spawn":
        pid = os.posix_spawn(sys.executable, argv, minimal)
        assert os.waitpid(pid, 0)[1] == 0
    elif spawn == "os.spawnv":
        assert os.spawnv(os.P_WAIT, sys.executable, argv) == 0
    else:
        assert os.spawnve(os.P_WAIT, sys.executable, argv, minimal) == 0
    assert report.read_text() == "1"
    assert "NEXUS_KEYRING_DISABLE" not in os.environ


@pytest.mark.parametrize(
    "env",
    [
        {"NEXUS_KEYRING_DISABLE": "0"},
        {"NEXUS_KEYRING_DISABLE": ""},
        {b"NEXUS_KEYRING_DISABLE": b"0"},
    ],
    ids=["zero", "empty", "bytes-key"],
)
def test_a_copied_env_cannot_lift_environment_only_mode(
    env: dict[Any, Any],
    tmp_path: Path,
) -> None:
    """An ``env`` that merely carries the flag (say, a shell copy) is overridden."""
    report = tmp_path / "child-env.txt"
    subprocess.run(
        [sys.executable, "-c", CHILD_REPORT, str(report)],
        env={"PATH": os.environ.get("PATH", ""), **env},
        check=True,
        timeout=30.0,
    )
    assert report.read_text() == "1"


def test_store_access_env_is_the_only_opt_out(tmp_path: Path) -> None:
    """A test that needs store access in a child must mark the env itself."""
    report = tmp_path / "child-env.txt"
    subprocess.run(
        [sys.executable, "-c", CHILD_REPORT, str(report)],
        env=secret_store_guard.store_access_env(
            {"PATH": os.environ.get("PATH", ""), "NEXUS_KEYRING_DISABLE": "0"}
        ),
        check=True,
        timeout=30.0,
    )
    assert report.read_text() == "0"


WAIT_FOR_GO = """
import pathlib, sys, time
pathlib.Path(sys.argv[1]).touch()
deadline = time.monotonic() + 30
while not pathlib.Path(sys.argv[2]).exists() and time.monotonic() < deadline:
    time.sleep(0.01)
"""


@pytest.mark.parametrize("spawn", ["os.system", "os.spawnv"])
def test_env_less_spawns_leave_this_process_environment_alone(
    spawn: str,
    tmp_path: Path,
) -> None:
    """Other threads never see ``os.environ`` edited while a child runs."""
    started, go = tmp_path / "started", tmp_path / "go"
    argv = [sys.executable, "-c", WAIT_FOR_GO, str(started), str(go)]
    if spawn == "os.system":
        child = threading.Thread(target=os.system, args=(shlex.join(argv),))
    else:
        child = threading.Thread(
            target=os.spawnv, args=(os.P_WAIT, sys.executable, argv)
        )
    child.start()
    try:
        deadline = time.monotonic() + 30
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        assert "NEXUS_KEYRING_DISABLE" not in os.environ
    finally:
        go.touch()
        child.join(timeout=30)


def test_check_spawn_hook_accepts_this_python() -> None:
    secret_store_guard.check_spawn_hook(
        secret_store_guard._unguarded(subprocess.Popen, "_execute_child")
    )


@pytest.mark.parametrize(
    "hook",
    [
        None,
        lambda self, argv: None,
        lambda self, args, executable, preexec_fn: None,
    ],
)
def test_check_spawn_hook_rejects_a_changed_hook(hook: object) -> None:
    with pytest.raises(RuntimeError, match="_execute_child"):
        secret_store_guard.check_spawn_hook(hook)


@pytest.mark.parametrize(
    "tamper",
    [
        "del subprocess.Popen._execute_child",
        "subprocess.Popen._execute_child = lambda self, argv: None",
    ],
)
def test_session_refuses_to_start_when_the_spawn_hook_changed(tamper: str) -> None:
    """A reshaped private hook stops a fresh session with exit status 4."""
    code = (
        f"import subprocess\n{tamper}\nimport sys, pytest\n"
        "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '--co', "
        "'tests/test_secret_store_guard.py']))"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in (secret_store_guard.SECRET_STORE_FLAG, "NEXUS_RUN_LIVE_LLM")
    }
    env["NEXUS_KEYRING_DISABLE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180.0,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 4, output
    assert "_execute_child" in output
