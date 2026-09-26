"""Session guard that keeps pytest away from the owner's secret store (#963).

``tests/conftest.py`` installs this guard at import, before collection, and
re-applies it around every test. It has two layers:

* Every ``read``/``write``/``delete`` on the real platform backends
  (``MacOSKeychainBackend`` and ``KeyringLibraryBackend``) passes through
  :func:`access_allowed` first. A denied operation fails the test before any
  ``security`` subprocess or ``keyring`` call can run.
* Tripwires at the lowest level fail any ``security`` CLI spawn and any
  direct ``keyring`` password call unless it happens inside an allowed backend
  operation or :func:`disposable_keychain_setup`. They catch test code that
  bypasses the backends, as the tests behind #963 did with their own
  ``security delete-generic-password`` helpers.

The opt-in flags are read once, when this module is first imported by the
root conftest. Editing the environment mid-session (for example unsetting
``NEXUS_KEYRING_DISABLE`` or setting ``NEXUS_RUN_SECRET_STORE``) cannot lift
the guard.
"""

from __future__ import annotations

import contextlib
import functools
import os
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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

RealBackend = MacOSKeychainBackend | KeyringLibraryBackend
REAL_BACKENDS: tuple[type[RealBackend], ...] = (
    MacOSKeychainBackend,
    KeyringLibraryBackend,
)
OPERATIONS = ("read", "write", "delete")
KEYRING_FUNCTIONS = ("get_password", "set_password", "delete_password")
GUARD_MARKER = "__nexus_secret_store_guard__"

_permission = threading.local()


def is_disposable_keychain(keychain: Path | None) -> bool:
    """Return whether ``keychain`` is an explicit file under the temp root.

    ``None`` means the user's keychain search list, which is the owner's
    login Keychain, so it is never disposable.
    """
    if keychain is None:
        return False
    temp_root = Path(tempfile.gettempdir()).resolve()
    return keychain.resolve().is_relative_to(temp_root)


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


def _deny(message: str) -> None:
    # pytest.fail raises a BaseException-derived outcome, so application code
    # that wraps credential access in `except Exception` (the verify endpoint
    # does) cannot swallow the tripwire and quietly proceed.
    pytest.fail(
        f"{message} Use the in_memory_secret_store fixture; platform-store "
        f"integration needs {SECRET_STORE_FLAG}=1 and a disposable store.",
        pytrace=False,
    )


@contextlib.contextmanager
def _permitted() -> Iterator[None]:
    """Open the low-level tripwires for the current thread only."""
    previous = getattr(_permission, "active", False)
    _permission.active = True
    try:
        yield
    finally:
        _permission.active = previous


def _require_permission(action: str) -> None:
    if not getattr(_permission, "active", False):
        _deny(f"Test attempted {action} outside a permitted secret-store call.")


@contextlib.contextmanager
def disposable_keychain_setup(keychain: Path) -> Iterator[None]:
    """Permit ``security`` commands that create or remove a disposable keychain.

    Only an opted-in session may use it, and only for a keychain file under
    the temp root.
    """
    if not SECRET_STORE_OPT_IN:
        _deny("Test attempted disposable keychain setup without opt-in.")
    if not is_disposable_keychain(keychain):
        _deny(f"Keychain {keychain} is not under the temp root.")
    with _permitted():
        yield


def _guard_backend(operation: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one real backend method so a denied call fails the test first."""

    @functools.wraps(original)
    def guarded(self: RealBackend, account: str, *args: str) -> Any:
        if not access_allowed(self, operation):
            _deny(
                f"Test attempted a real secret-store {operation} "
                f"({type(self).__name__}, service {self.service!r}, account "
                f"{account!r})."
            )
        with _permitted():
            return original(self, account, *args)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _program_name(args: Any, executable: Any) -> str:
    """Return the basename of the program a ``Popen`` call would start."""
    program = executable
    if program is None:
        if isinstance(args, (str, bytes)):
            words = os.fsdecode(args).split()
            program = words[0] if words else ""
        elif isinstance(args, os.PathLike):
            program = args
        else:
            program = list(args)[0] if args else ""
    return Path(os.fsdecode(program)).name


def _guard_spawn(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``Popen._execute_child`` so an unpermitted ``security`` spawn fails."""

    @functools.wraps(original)
    def guarded(
        self: subprocess.Popen[Any], args: Any, executable: Any, *rest: Any
    ) -> Any:
        if _program_name(args, executable) == "security":
            _require_permission("to run the macOS security CLI")
        return original(self, args, executable, *rest)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _guard_keyring(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap one ``keyring`` password function so a direct call fails."""

    @functools.wraps(original)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        _require_permission(f"keyring.{name}")
        return original(*args, **kwargs)

    setattr(guarded, GUARD_MARKER, True)
    return guarded


def _unguarded(owner: Any, name: str) -> Callable[..., Any]:
    """Return the original attribute, even if a guard is already installed."""
    attribute = getattr(owner, "__dict__", {}).get(name, getattr(owner, name))
    while getattr(attribute, GUARD_MARKER, False):
        attribute = getattr(attribute, "__wrapped__")
    return attribute


_GUARDED: dict[tuple[Any, str], Callable[..., Any]] = {
    **{
        (backend, operation): _guard_backend(operation, _unguarded(backend, operation))
        for backend in REAL_BACKENDS
        for operation in OPERATIONS
    },
    (subprocess.Popen, "_execute_child"): _guard_spawn(
        _unguarded(subprocess.Popen, "_execute_child")
    ),
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
