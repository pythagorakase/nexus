"""Session guard that keeps pytest away from the owner's secret store (#963).

``tests/conftest.py`` installs this guard at import, before collection, and
re-applies it around every test. It has three layers:

* Every ``read``/``write``/``delete`` on the real platform backends
  (``MacOSKeychainBackend`` and ``KeyringLibraryBackend``) passes through
  :func:`access_allowed` first. A denied operation fails the test before any
  ``security`` subprocess or ``keyring`` call can run.
* An allowed backend operation, or :func:`disposable_keychain_setup`, opens a
  :class:`Scope` for the current thread. The spawn tripwires wrap
  ``subprocess.Popen._execute_child``, ``os.system``, ``os.posix_spawn``,
  ``os.posix_spawnp`` and the ``os.spawn*`` family. A ``security`` CLI spawn
  passes only as an argv list whose subcommand, service (never ``nexus-api``
  unless the scope is a live-session read of it) and keychain path exactly
  match the open scope. Command strings that mention ``security`` always fail.
  The ``keyring`` password functions likewise need a scope for their service.
  These tripwires catch test code that bypasses the backends, as the tests
  behind #963 did with their own ``security delete-generic-password`` helpers.
* The same spawn tripwires put ``NEXUS_KEYRING_DISABLE=1`` into every child's
  environment, whatever the opt-in flags. A child inherits none of the
  in-process patches, so env-only credential mode is its protection. A test
  that genuinely needs a child with store access must pass an explicit
  ``env`` that sets ``NEXUS_KEYRING_DISABLE`` itself and say why; only an
  explicit value is honored.

The opt-in flags are read once, when this module is first imported by the
root conftest. Editing the environment mid-session (for example unsetting
``NEXUS_KEYRING_DISABLE`` or setting ``NEXUS_RUN_SECRET_STORE``) cannot lift
the guard.

Not covered: ``os.exec*`` and ``os.fork`` followed by an exec, ``pty.spawn``,
and multiprocessing's internal ``fork_exec``. The guard covers
credential-store access only. It is not a protected-path write guard, and
there is no launcher preflight outside pytest.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import os
import shlex
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import keyring
import keyring.core
import pytest

from nexus.util.secret_manager import (
    SERVICE_NAME,
    KeyringLibraryBackend,
    MacOSKeychainBackend,
)

SECRET_STORE_FLAG = "NEXUS_RUN_SECRET_STORE"
SECRET_STORE_OPT_IN = os.environ.get(SECRET_STORE_FLAG) == "1"
LIVE_LLM_OPT_IN = os.environ.get("NEXUS_RUN_LIVE_LLM") == "1"
ENV_ONLY_FLAG = "NEXUS_KEYRING_DISABLE"

RealBackend = MacOSKeychainBackend | KeyringLibraryBackend
REAL_BACKENDS: tuple[type[RealBackend], ...] = (
    MacOSKeychainBackend,
    KeyringLibraryBackend,
)
OPERATIONS = ("read", "write", "delete")
KEYRING_FUNCTIONS = ("get_password", "set_password", "delete_password")
OS_SPAWN_FUNCTIONS = tuple(
    name
    for name in (
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
    )
    if hasattr(os, name)
)
OS_POSIX_SPAWN_FUNCTIONS = tuple(
    name for name in ("posix_spawn", "posix_spawnp") if hasattr(os, name)
)
GUARD_MARKER = "__nexus_secret_store_guard__"

# ``security`` subcommands each backend operation issues, and the ones the
# disposable-keychain integration fixture needs. Nothing else may run.
_ITEM_SUBCOMMANDS = {
    "read": frozenset({"find-generic-password"}),
    "write": frozenset({"delete-generic-password", "add-generic-password"}),
    "delete": frozenset({"delete-generic-password"}),
}
_SETUP_SUBCOMMANDS = frozenset(
    {
        "list-keychains",
        "create-keychain",
        "unlock-keychain",
        "show-keychain-info",
        "delete-keychain",
    }
)

_permission = threading.local()


@dataclass(frozen=True)
class Scope:
    """What the current thread may do with the real store right now."""

    subcommands: frozenset[str] = frozenset()
    service: str | None = None
    keychain: str | None = None
    keyring_service: str | None = None


def is_disposable_keychain(keychain: Path | None) -> bool:
    """Return whether ``keychain`` is an explicit file under the temp root.

    ``None`` means the user's keychain search list, which is the owner's
    login Keychain, so it is never disposable. Nothing under
    ``~/Library`` is disposable either, even when ``TMPDIR`` points at one of
    its ancestors.
    """
    if keychain is None:
        return False
    resolved = keychain.resolve()
    if resolved.is_relative_to((Path.home() / "Library").resolve()):
        return False
    return resolved.is_relative_to(Path(tempfile.gettempdir()).resolve())


def access_allowed(backend: RealBackend, operation: str) -> bool:
    """Return whether this session may run one real secret-store operation.

    Service ``nexus-api`` holds the owner's credentials: only a live-inference
    session (``NEXUS_RUN_LIVE_LLM=1``) may read it, and no test session may
    write or delete it. Any other real access needs
    ``NEXUS_RUN_SECRET_STORE=1`` and a store proven disposable, which means a
    Keychain backend bound to a keychain file under the temp root. The
    ``keyring`` library's default store is the owner's login store, so it has
    no disposable form.
    """
    if backend.service == SERVICE_NAME:
        return LIVE_LLM_OPT_IN and operation == "read"
    return (
        SECRET_STORE_OPT_IN
        and isinstance(backend, MacOSKeychainBackend)
        and is_disposable_keychain(backend.keychain)
    )


def backend_scope(backend: RealBackend, operation: str) -> Scope:
    """Return the scope an allowed backend operation opens."""
    if isinstance(backend, MacOSKeychainBackend):
        keychain = None if backend.keychain is None else os.fspath(backend.keychain)
        return Scope(
            subcommands=_ITEM_SUBCOMMANDS[operation],
            service=backend.service,
            keychain=keychain,
        )
    return Scope(keyring_service=backend.service)


def keychain_setup_scope(keychain: Path) -> Scope:
    """Return the scope for creating and removing one disposable keychain."""
    return Scope(subcommands=_SETUP_SUBCOMMANDS, keychain=os.fspath(keychain))


def _deny(message: str) -> NoReturn:
    # pytest.fail raises a BaseException-derived outcome, so application code
    # that wraps credential access in `except Exception` (the verify endpoint
    # does) cannot swallow the tripwire and quietly proceed.
    pytest.fail(
        f"{message} Use the in_memory_secret_store fixture; platform-store "
        f"integration needs {SECRET_STORE_FLAG}=1 and a disposable store.",
        pytrace=False,
    )


@contextlib.contextmanager
def _active_scope(scope: Scope) -> Iterator[None]:
    """Open ``scope`` for the current thread only."""
    previous = getattr(_permission, "scope", None)
    _permission.scope = scope
    try:
        yield
    finally:
        _permission.scope = previous


def _current_scope() -> Scope | None:
    return getattr(_permission, "scope", None)


@contextlib.contextmanager
def disposable_keychain_setup(keychain: Path) -> Iterator[None]:
    """Permit the ``security`` commands that manage one disposable keychain.

    Only an opted-in session may use it, only for a keychain file under the
    temp root, and only for commands that name exactly that file (plus the
    read-only ``list-keychains -d user``).
    """
    if not SECRET_STORE_OPT_IN:
        _deny("Test attempted disposable keychain setup without opt-in.")
    if not is_disposable_keychain(keychain):
        _deny(f"Keychain {keychain} is not under the temp root.")
    with _active_scope(keychain_setup_scope(keychain)):
        yield


def _names_production_service(tokens: list[str]) -> bool:
    for index, token in enumerate(tokens):
        if token == f"-s{SERVICE_NAME}":
            return True
        if token == "-s" and tokens[index + 1 : index + 2] == [SERVICE_NAME]:
            return True
    return False


def _item_problem(subcommand: str, rest: list[str], scope: Scope) -> str | None:
    """Check a ``*-generic-password`` command against a backend scope."""
    value_options = {"-a", "-s"}
    flag_options: set[str] = set()
    if subcommand == "add-generic-password":
        value_options.add("-w")
        flag_options.add("-A")
    elif subcommand == "find-generic-password":
        flag_options.add("-w")
    values: dict[str, str] = {}
    positionals: list[str] = []
    tokens = iter(rest)
    for token in tokens:
        if token in value_options:
            value = next(tokens, None)
            if value is None:
                return f"security {subcommand} {token} has no value."
            values[token] = value
        elif token in flag_options:
            continue
        elif token.startswith("-"):
            return f"security {subcommand} option {token} is not permitted."
        else:
            positionals.append(token)
    if values.get("-s") != scope.service:
        return (
            f"security {subcommand} targeted service {values.get('-s')!r}, "
            f"not {scope.service!r}."
        )
    expected = [] if scope.keychain is None else [scope.keychain]
    if positionals != expected:
        return (
            f"security {subcommand} named keychain {positionals!r}, not "
            f"{expected!r}."
        )
    return None


def _setup_problem(
    subcommand: str, rest: list[str], keychain: str | None
) -> str | None:
    """Check a keychain-management command against the disposable keychain."""
    if subcommand == "list-keychains":
        # Only the read-only listing; "-s" would replace the search list.
        if rest == ["-d", "user"]:
            return None
        return "security list-keychains may only list the user search list."
    if keychain is None:
        return f"security {subcommand} has no disposable keychain bound."
    if subcommand in ("create-keychain", "unlock-keychain"):
        matches = len(rest) == 3 and rest[0] == "-p" and rest[2] == keychain
    else:
        matches = rest == [keychain]
    if matches:
        return None
    return (
        f"security {subcommand} must name exactly the disposable keychain {keychain}."
    )


def security_command_problem(argv: list[str], scope: Scope | None) -> str | None:
    """Return why ``argv`` (``security`` and its arguments) may not run.

    ``None`` means the command matches ``scope`` exactly. Messages never
    repeat option values, so a key or keychain password cannot leak.
    """
    if scope is None:
        return (
            "Test attempted to run the macOS security CLI outside a permitted "
            "secret-store call."
        )
    subcommand, rest = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    if _names_production_service(rest) and scope.service != SERVICE_NAME:
        return f"security {subcommand} targeted service {SERVICE_NAME!r}."
    if subcommand not in scope.subcommands:
        return f"security {subcommand or '(none)'} is not permitted in this scope."
    if subcommand in _SETUP_SUBCOMMANDS:
        return _setup_problem(subcommand, rest, scope.keychain)
    return _item_problem(subcommand, rest, scope)


def _words(value: Any) -> list[str]:
    text = os.fsdecode(value)
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _names_security(token: Any) -> bool:
    return Path(os.fsdecode(token)).name == "security"


def _check_spawn(program: Any, args: Any, *, shell: bool = False) -> None:
    """Fail the test unless a spawn leaves ``security`` alone or is in scope."""
    if shell or isinstance(args, (str, bytes)):
        words = (
            _words(args)
            if isinstance(args, (str, bytes))
            else [word for arg in args for word in _words(arg)]
        )
        if any(_names_security(word) for word in words) or (
            program is not None and _names_security(program)
        ):
            _deny(
                "Test attempted to run the macOS security CLI through a command "
                "string; only an argv list bound to a permitted scope may."
            )
        return
    if isinstance(args, os.PathLike):
        args = [args]
    argv = [os.fsdecode(arg) for arg in (list(args) if args is not None else [])]
    mentions = (program is not None and _names_security(program)) or any(
        _names_security(word)
        for arg in argv
        for word in ([arg] + (_words(arg) if any(c.isspace() for c in arg) else []))
    )
    if not mentions:
        return
    if not argv or not _names_security(argv[0]):
        _deny(
            "Test attempted to run the macOS security CLI through a wrapper "
            "command; only an argv list bound to a permitted scope may."
        )
    problem = security_command_problem(argv, _current_scope())
    if problem is not None:
        _deny(problem)


def _child_env(env: Mapping[Any, Any] | None) -> Mapping[Any, Any]:
    """Return ``env`` with env-only credential mode unless it sets it itself."""
    if env is None:
        return {**os.environ, ENV_ONLY_FLAG: "1"}
    if ENV_ONLY_FLAG in env or os.fsencode(ENV_ONLY_FLAG) in env:
        return env
    return {**env, ENV_ONLY_FLAG: "1"}


@contextlib.contextmanager
def _inherited_env_only() -> Iterator[None]:
    """Force env-only mode for spawns that inherit ``os.environ``."""
    previous = os.environ.get(ENV_ONLY_FLAG)
    os.environ[ENV_ONLY_FLAG] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_ONLY_FLAG, None)
        else:
            os.environ[ENV_ONLY_FLAG] = previous


def _guard_backend(operation: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one real backend method so a denied call fails the test first."""

    @functools.wraps(original)
    def guarded(self: RealBackend, *args: Any, **kwargs: Any) -> Any:
        if not access_allowed(self, operation):
            account = kwargs.get("account", args[0] if args else None)
            _deny(
                f"Test attempted a real secret-store {operation} "
                f"({type(self).__name__}, service {self.service!r}, account "
                f"{account!r})."
            )
        with _active_scope(backend_scope(self, operation)):
            return original(self, *args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def check_spawn_hook(execute_child: Any) -> None:
    """Fail loudly unless ``Popen._execute_child`` still has the known shape.

    It is private CPython API. If a Python upgrade renames or reshapes it, the
    spawn tripwire would silently stop seeing ``security`` calls, so the root
    conftest fails to load instead and pytest exits with status 4.
    """
    if not callable(execute_child):
        raise RuntimeError(
            "subprocess.Popen._execute_child is missing; the secret-store "
            "spawn guard cannot be installed."
        )
    parameters = list(inspect.signature(execute_child).parameters)
    if parameters[:3] != ["self", "args", "executable"] or not {
        "env",
        "shell",
    } <= set(parameters):
        raise RuntimeError(
            "subprocess.Popen._execute_child has an unexpected signature "
            f"{parameters}; the secret-store spawn guard cannot be installed."
        )


def _guard_popen(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``Popen._execute_child``: scope-check ``security``, force env-only."""
    signature = inspect.signature(original)

    @functools.wraps(original)
    def guarded(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> Any:
        bound = signature.bind(self, *args, **kwargs)
        arguments = bound.arguments
        _check_spawn(
            arguments["executable"],
            arguments["args"],
            shell=bool(arguments["shell"]),
        )
        arguments["env"] = _child_env(arguments["env"])
        return original(*bound.args, **bound.kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_system(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``os.system``: refuse ``security``, force env-only inheritance."""

    @functools.wraps(original)
    def guarded(command: Any) -> Any:
        _check_spawn(None, command, shell=True)
        with _inherited_env_only():
            return original(command)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_posix_spawn(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``os.posix_spawn(p)``: scope-check ``security``, force env-only."""

    @functools.wraps(original)
    def guarded(path: Any, argv: Any, env: Any, *args: Any, **kwargs: Any) -> Any:
        _check_spawn(path, argv)
        return original(path, argv, _child_env(env), *args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_os_spawn(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one ``os.spawn*`` function: scope-check, force env-only."""
    list_form = name.startswith("spawnl")
    takes_env = name.endswith("e")

    @functools.wraps(original)
    def guarded(mode: int, file: Any, *rest: Any) -> Any:
        if list_form:
            argv = list(rest[:-1]) if takes_env else list(rest)
            env = rest[-1] if takes_env else None
        else:
            argv = list(rest[0])
            env = rest[1] if takes_env else None
        _check_spawn(file, argv)
        if not takes_env:
            with _inherited_env_only():
                return original(mode, file, *rest)
        if list_form:
            return original(mode, file, *argv, _child_env(env))
        return original(mode, file, argv, _child_env(env))

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_keyring(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one ``keyring`` password function so an out-of-scope call fails."""

    @functools.wraps(original)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        scope = _current_scope()
        service = args[0] if args else kwargs.get("service_name")
        if scope is None or scope.keyring_service is None:
            _deny(
                f"Test attempted keyring.{name} outside a permitted secret-store call."
            )
        elif service != scope.keyring_service:
            _deny(
                f"Test attempted keyring.{name} for service {service!r} inside a "
                f"scope for {scope.keyring_service!r}."
            )
        return original(*args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _unguarded(owner: Any, name: str) -> Any:
    """Return the original attribute (``None`` if missing), unwrapping guards."""
    attribute = getattr(owner, "__dict__", {}).get(name, getattr(owner, name, None))
    while getattr(attribute, GUARD_MARKER, False):
        attribute = getattr(attribute, "__wrapped__")
    return attribute


check_spawn_hook(_unguarded(subprocess.Popen, "_execute_child"))

_GUARDED: dict[tuple[Any, str], Callable[..., Any]] = {
    **{
        (backend, operation): _guard_backend(operation, _unguarded(backend, operation))
        for backend in REAL_BACKENDS
        for operation in OPERATIONS
    },
    (subprocess.Popen, "_execute_child"): _guard_popen(
        _unguarded(subprocess.Popen, "_execute_child")
    ),
    (os, "system"): _guard_system(_unguarded(os, "system")),
    **{
        (os, name): _guard_posix_spawn(_unguarded(os, name))
        for name in OS_POSIX_SPAWN_FUNCTIONS
    },
    **{
        (os, name): _guard_os_spawn(name, _unguarded(os, name))
        for name in OS_SPAWN_FUNCTIONS
    },
    **{
        (module, name): _guard_keyring(name, _unguarded(module, name))
        for module in (keyring, keyring.core)
        for name in KEYRING_FUNCTIONS
    },
}


def install(setattr_fn: Callable[[Any, str, Any], object]) -> None:
    """Route every real store entry point through the guard.

    ``setattr_fn`` is the builtin ``setattr`` for the pre-collection install
    or ``monkeypatch.setattr`` for the per-test re-application.
    """
    for (owner, name), guarded in _GUARDED.items():
        setattr_fn(owner, name, guarded)


def installed() -> bool:
    """Return whether every real store entry point is currently guarded."""
    return all(
        getattr(owner, name) is guarded for (owner, name), guarded in _GUARDED.items()
    )


def describe() -> str:
    """Summarize the guard state for the pytest report header."""
    state = "active" if installed() else "MISSING"
    production = "read-only (live LLM)" if LIVE_LLM_OPT_IN else "denied"
    disposable = "allowed" if SECRET_STORE_OPT_IN else "denied"
    return (
        f"secret-store guard: {state}; {SERVICE_NAME}: {production}; "
        f"disposable keychain: {disposable}"
    )
