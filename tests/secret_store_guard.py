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
  Any argv element whose basename is ``security``, or that holds it as a
  word, counts as a mention, so an unrelated argument such as
  ``/etc/security`` also fails the test. That noise is deliberate: an
  allowlist of wrapper commands would fail open for every wrapper it missed.
  The ``keyring`` password functions, and the password methods of every
  ``keyring`` backend class (including classes defined after install, such as
  the lazily loaded macOS backend), likewise need a scope for their service.
  These tripwires catch test code that bypasses the backends, as the tests
  behind #963 did with their own ``security delete-generic-password`` helpers.
* The same spawn tripwires put ``NEXUS_KEYRING_DISABLE=1`` into every child's
  environment, whatever the opt-in flags and whatever the caller's ``env``
  says. A child inherits none of the in-process patches, so env-only
  credential mode is its protection. The only opt-out is an ``env`` built
  with :func:`store_access_env`, with the reason in a comment at the call.

The opt-in flags are read once, when this module is first imported by the
root conftest. Editing the environment mid-session (for example unsetting
``NEXUS_KEYRING_DISABLE`` or setting ``NEXUS_RUN_SECRET_STORE``) cannot lift
the guard.

Disposable keychains live only under pytest's base temp directory, which
the root conftest registers with :func:`set_disposable_root` at session start.

Not covered: ``os.exec*`` and ``os.fork`` followed by an exec, ``pty.spawn``,
multiprocessing's internal ``fork_exec``, a copy or link of ``security``
under another name, a child process that runs ``security`` itself (env-only
mode does not stop a direct CLI call), and calls into the Security framework
through ``ctypes``, including ``keyring.backends.macOS.api``. The guard covers
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
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import keyring
import keyring.backend
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
KEYRING_FUNCTIONS = (
    "get_password",
    "set_password",
    "delete_password",
    "get_credential",
)
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
_ENV_ONLY_KEYS = (ENV_ONLY_FLAG, os.fsencode(ENV_ONLY_FLAG))

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
_disposable_root: Path | None = None


@dataclass(frozen=True)
class Scope:
    """What the current thread may do with the real store right now."""

    subcommands: frozenset[str] = frozenset()
    service: str | None = None
    keychain: str | None = None
    keyring_service: str | None = None


def set_disposable_root(root: Path) -> None:
    """Record pytest's base temp directory as the only disposable location.

    pytest owns that directory and deletes old copies of it, unlike the
    system temp root, which ``TMPDIR`` can point anywhere (even at home).
    """
    global _disposable_root
    _disposable_root = root.resolve()


def is_disposable_keychain(keychain: Path | None) -> bool:
    """Return whether ``keychain`` is an explicit file under pytest's temp dir.

    ``None`` means the user's keychain search list, which is the owner's
    login Keychain, so it is never disposable. Before the root conftest
    registers pytest's base temp directory nothing is disposable, and nothing
    under ``~/Library`` ever is.
    """
    if keychain is None or _disposable_root is None:
        return False
    resolved = keychain.resolve()
    if resolved.is_relative_to((Path.home() / "Library").resolve()):
        return False
    return resolved.is_relative_to(_disposable_root)


def access_allowed(backend: RealBackend, operation: str) -> bool:
    """Return whether this session may run one real secret-store operation.

    Service ``nexus-api`` holds the owner's credentials: only a live-inference
    session (``NEXUS_RUN_LIVE_LLM=1``) may read it, and no test session may
    write or delete it. Any other real access needs
    ``NEXUS_RUN_SECRET_STORE=1`` and a store proven disposable, which means a
    Keychain backend bound to a keychain file under pytest's temp dir. The
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

    Only an opted-in session may use it, only for a keychain file under
    pytest's temp dir, and only for commands that name exactly that file
    (plus the read-only ``list-keychains -d user``).
    """
    if not SECRET_STORE_OPT_IN:
        _deny("Test attempted disposable keychain setup without opt-in.")
    if not is_disposable_keychain(keychain):
        _deny(f"Keychain {keychain} is not under pytest's temp dir.")
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


class StoreAccessEnv(dict[str, str]):
    """A child environment a test deliberately exempts from env-only mode."""


def store_access_env(env: Mapping[str, str]) -> StoreAccessEnv:
    """Mark ``env`` as a child environment that keeps secret-store access.

    The spawn tripwires otherwise force ``NEXUS_KEYRING_DISABLE=1`` into every
    child, overriding any value ``env`` holds, so a copy of an environment
    that happens to carry ``NEXUS_KEYRING_DISABLE=0`` cannot hand a child the
    owner's store by accident. The child is unguarded: say why at the call.
    """
    return StoreAccessEnv(env)


def _child_env(env: Mapping[Any, Any] | None) -> Mapping[Any, Any]:
    """Return the environment a child gets: env-only mode unless exempted."""
    if isinstance(env, StoreAccessEnv):
        return env
    source = os.environ if env is None else env
    forced = {key: value for key, value in source.items() if key not in _ENV_ONLY_KEYS}
    forced[ENV_ONLY_FLAG] = "1"
    return forced


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
    """Wrap ``os.system``: refuse ``security``, force env-only in the shell.

    ``os.system`` cannot take an environment, so the shell exports the flag
    itself rather than this process editing ``os.environ`` under other
    threads.
    """

    @functools.wraps(original)
    def guarded(command: Any) -> Any:
        _check_spawn(None, command, shell=True)
        return original(f"export {ENV_ONLY_FLAG}=1\n{os.fsdecode(command)}")

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


def _guard_os_spawn(
    name: str, original: Callable[..., Any], with_env: Callable[..., Any]
) -> Callable[..., Any]:
    """Wrap one ``os.spawn*`` function: scope-check, force env-only.

    ``with_env`` is the function's ``e`` form, which an env-less call goes
    through with an explicit environment instead of the inherited one.
    """
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
        if list_form:
            return with_env(mode, file, *argv, _child_env(env))
        return with_env(mode, file, argv, _child_env(env))

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _keyring_service(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    """Return the service a ``keyring`` call names (``None`` if it names none)."""
    if args:
        return args[0]
    for key in ("service_name", "service", "system"):
        if key in kwargs:
            return kwargs[key]
    return None


def _check_keyring(label: str, service: Any) -> None:
    """Fail the test unless a ``keyring`` call is inside a scope for ``service``."""
    scope = _current_scope()
    if scope is None or scope.keyring_service is None:
        _deny(f"Test attempted {label} outside a permitted secret-store call.")
    if service != scope.keyring_service:
        _deny(
            f"Test attempted {label} for service {service!r} inside a scope for "
            f"{scope.keyring_service!r}."
        )


def _guard_keyring(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one ``keyring`` password function so an out-of-scope call fails."""

    @functools.wraps(original)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        _check_keyring(f"keyring.{name}", _keyring_service(args, kwargs))
        return original(*args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_keyring_method(
    name: str, original: Callable[..., Any]
) -> Callable[..., Any]:
    """Wrap one password method of a ``keyring`` backend class."""

    @functools.wraps(original)
    def guarded(self: Any, *args: Any, **kwargs: Any) -> Any:
        _check_keyring(
            f"keyring backend {type(self).__name__}.{name}",
            _keyring_service(args, kwargs),
        )
        return original(self, *args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def keyring_backend_classes() -> list[type[Any]]:
    """Return ``KeyringBackend`` and every subclass defined so far."""
    found: list[type[Any]] = []
    pending: list[type[Any]] = [keyring.backend.KeyringBackend]
    while pending:
        cls = pending.pop()
        if cls not in found:
            found.append(cls)
            pending.extend(cls.__subclasses__())
    return found


def _unguarded_keyring_methods(cls: type[Any]) -> Iterator[tuple[str, Any]]:
    """Yield the password methods ``cls`` itself defines that lack a guard."""
    for name in KEYRING_FUNCTIONS:
        method = cls.__dict__.get(name)
        if callable(method) and not getattr(method, GUARD_MARKER, False):
            yield name, method


def _guard_keyring_class(
    cls: type[Any], setattr_fn: Callable[[Any, str, Any], object]
) -> None:
    """Guard every password method ``cls`` itself defines."""
    for name, method in list(_unguarded_keyring_methods(cls)):
        setattr_fn(cls, name, _guard_keyring_method(name, method))


def _guard_keyring_meta(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``KeyringBackendMeta.__init__`` so later backend classes are guarded.

    ``keyring`` loads its platform backends (macOS included) lazily, on the
    first ``get_keyring``, so most backend classes do not exist at install.
    """

    @functools.wraps(original)
    def guarded(cls: type[Any], *args: Any, **kwargs: Any) -> None:
        original(cls, *args, **kwargs)
        _guard_keyring_class(cls, setattr)

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
        (os, name): _guard_os_spawn(
            name,
            _unguarded(os, name),
            _unguarded(os, name if name.endswith("e") else f"{name}e"),
        )
        for name in OS_SPAWN_FUNCTIONS
    },
    **{
        (module, name): _guard_keyring(name, _unguarded(module, name))
        for module in (keyring, keyring.core)
        for name in KEYRING_FUNCTIONS
    },
    (keyring.backend.KeyringBackendMeta, "__init__"): _guard_keyring_meta(
        _unguarded(keyring.backend.KeyringBackendMeta, "__init__")
    ),
}


def install(setattr_fn: Callable[[Any, str, Any], object]) -> None:
    """Route every real store entry point through the guard.

    ``setattr_fn`` is the builtin ``setattr`` for the pre-collection install
    or ``monkeypatch.setattr`` for the per-test re-application.
    """
    for (owner, name), guarded in _GUARDED.items():
        setattr_fn(owner, name, guarded)
    for cls in keyring_backend_classes():
        _guard_keyring_class(cls, setattr_fn)


def installed() -> bool:
    """Return whether every real store entry point is currently guarded."""
    return all(
        getattr(owner, name) is guarded for (owner, name), guarded in _GUARDED.items()
    ) and not any(
        next(_unguarded_keyring_methods(cls), None) for cls in keyring_backend_classes()
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
