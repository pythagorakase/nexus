"""Failure receipts: an append-only, sanitized record of configuration failures.

Issue #806 (decisions 806-Q1, Q2, Q5, Q12). Three surfaces record a receipt
when they fail and then re-raise the original exception unchanged:
``config.load_settings``, ``config.preferences`` and ``runtime.home``.

A receipt is an allowlisted envelope: the exception's type and module, its
traceback as (file, line, function) frames, and a small ``details`` record
per known exception type. It never records an exception message (except the
whitespace-collapsed ``RuntimeHomeError`` text, which names only locator
paths), a source line, local variables, an input value or a configuration
value, so prompts and secrets cannot reach the file.

Receipts are written to ``<home>/.nexus/receipts`` when the runtime home can
be located and to ``~/.nexus/receipts`` (the fallback root) when it cannot.
Each day's receipts are appended to ``failures-<UTC date>.jsonl``; nothing
prunes or rewrites them. ``nexus receipts`` reads both roots and groups
repeats by fingerprint.

The writer runs when no configuration loads, so nothing here reads
``nexus.toml``: the caps below are schema constants. ``nexus.runtime.home``
imports this module, so it is imported inside functions here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import errno as errno_module
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib
import traceback
from typing import Annotated, Literal, Mapping, Optional, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from nexus.runtime.contract import FALLBACK_RECEIPTS_DIR, TEST_RECEIPTS_ENV

# Schema constants, not nexus.toml tunables: the writer runs when no
# configuration loads.
MAX_FRAMES = 64
MAX_VALIDATION_ERRORS = 20
MAX_MESSAGE_CHARS = 512

SCHEMA_VERSION: Literal[1] = 1

Surface = Literal["config.load_settings", "config.preferences", "runtime.home"]

# A loc part or error type is kept only when it is plainly an identifier.
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_TOML_POSITION = re.compile(r"\(at line (\d+), column (\d+)\)$")
_REDACTED = "?"


class ReceiptReadError(ValueError):
    """A receipt file holds a line that is not a valid failure receipt."""


class _Record(BaseModel):
    """Base for every receipt model: closed and immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReceiptFrame(_Record):
    """One traceback frame: where, never what."""

    file: str
    line: int
    function: str


class ValidationErrorEntry(_Record):
    """One pydantic error, reduced to its location and error type."""

    loc: list[Union[int, str]]
    type: str


class ValidationDetails(_Record):
    """A pydantic ``ValidationError``: the model and its first errors."""

    kind: Literal["validation"]
    model: str
    error_count: int
    errors: list[ValidationErrorEntry]


class TomlDetails(_Record):
    """A ``tomllib.TOMLDecodeError``: the position only."""

    kind: Literal["toml"]
    line: Optional[int]
    column: Optional[int]


class RuntimeHomeDetails(_Record):
    """A ``RuntimeHomeError``: its collapsed message (locator paths only)."""

    kind: Literal["runtime_home"]
    message: str


class OsDetails(_Record):
    """An ``OSError``: the error number only."""

    kind: Literal["os"]
    errno: Optional[int]


ReceiptDetails = Annotated[
    Union[ValidationDetails, TomlDetails, RuntimeHomeDetails, OsDetails],
    Field(discriminator="kind"),
]


class FailureReceipt(_Record):
    """One recorded failure of a configuration or runtime-home surface."""

    schema_version: Literal[1]
    recorded_at: AwareDatetime
    surface: Surface
    pid: int
    config_path: Optional[str]
    exception_type: str
    exception_module: str
    frames: list[ReceiptFrame]
    frames_dropped: int
    details: Optional[ReceiptDetails]
    fingerprint: str

    @field_validator("recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        """Receipts are stamped in UTC so day files never straddle zones."""
        if value.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("recorded_at must be UTC")
        return value


class FailureGroup(_Record):
    """Every receipt that shares one fingerprint, compacted."""

    fingerprint: str
    count: int
    first_seen: AwareDatetime
    last_seen: AwareDatetime
    roots: list[str]
    first: FailureReceipt


def _seam_dir(subdirectory: str) -> Optional[Path]:
    """The test seam's subdirectory, or None when the seam is unset."""
    raw = os.environ.get(TEST_RECEIPTS_ENV)
    if raw is None or raw == "":
        return None
    root = Path(raw)
    if not root.is_absolute():
        raise ValueError(f"{TEST_RECEIPTS_ENV} must be an absolute path, got {raw!r}")
    return root / subdirectory


def home_receipts_dir() -> Path:
    """The active runtime home's receipt directory.

    The locator runs first, so a ``RuntimeHomeError`` propagates (after its
    own receipt is recorded in the fallback root) whether or not the test
    seam is set: the seam replaces directories, never routing.
    """
    from nexus.runtime.home import RECEIPTS_DIR, anchor_path, locate_runtime_home

    location = locate_runtime_home()
    seam = _seam_dir("home")
    if seam is not None:
        return seam
    return anchor_path(location.root, RECEIPTS_DIR)


def fallback_receipts_dir() -> Path:
    """The per-user receipt directory used when no home can be located."""
    seam = _seam_dir("fallback")
    if seam is not None:
        return seam
    return Path.home() / FALLBACK_RECEIPTS_DIR


def _frame_file(filename: str, root: Path) -> str:
    """A frame's file: POSIX and checkout-relative when under the checkout."""
    path = Path(filename)
    if not path.is_absolute():
        return filename
    resolved = Path(os.path.realpath(path))
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return path.as_posix()


def _frames(exc: BaseException) -> tuple[list[ReceiptFrame], int]:
    """The innermost ``MAX_FRAMES`` frames (innermost last) and the count cut."""
    from nexus.runtime.home import repo_root

    root = repo_root()
    frames = [
        ReceiptFrame(
            file=_frame_file(frame.f_code.co_filename, root),
            line=lineno,
            function=frame.f_code.co_name,
        )
        for frame, lineno in traceback.walk_tb(exc.__traceback__)
    ]
    dropped = max(0, len(frames) - MAX_FRAMES)
    return frames[dropped:], dropped


def _safe_token(value: str) -> str:
    """Keep an identifier-shaped string; replace anything else with ``?``."""
    return value if _SAFE_TOKEN.fullmatch(value) else _REDACTED


def _validation_details(exc: ValidationError) -> ValidationDetails:
    """Locations and error types of the first errors; never messages or input."""
    entries = []
    for error in exc.errors(include_url=False, include_context=False)[
        :MAX_VALIDATION_ERRORS
    ]:
        error_type = str(error["type"])
        parts: list[Union[int, str]] = [
            part if isinstance(part, int) else _safe_token(str(part))
            for part in error["loc"]
        ]
        if error_type == "extra_forbidden" and parts:
            # The unknown key is user-typed text.
            parts[-1] = _REDACTED
        entries.append(ValidationErrorEntry(loc=parts, type=_safe_token(error_type)))
    return ValidationDetails(
        kind="validation",
        model=_safe_token(str(exc.title)),
        error_count=exc.error_count(),
        errors=entries,
    )


def _toml_details(exc: tomllib.TOMLDecodeError) -> TomlDetails:
    """The decode position, from attributes when present, else the message."""
    line = getattr(exc, "lineno", None)
    column = getattr(exc, "colno", None)
    if isinstance(line, int) and isinstance(column, int):
        return TomlDetails(kind="toml", line=line, column=column)
    match = _TOML_POSITION.search(str(exc))
    if match is None:
        return TomlDetails(kind="toml", line=None, column=None)
    return TomlDetails(kind="toml", line=int(match[1]), column=int(match[2]))


def _details(exc: BaseException) -> Optional[ReceiptDetails]:
    """The allowlisted details of a known exception type, else None."""
    from nexus.runtime.home import RuntimeHomeError

    if isinstance(exc, ValidationError):
        return _validation_details(exc)
    if isinstance(exc, tomllib.TOMLDecodeError):
        return _toml_details(exc)
    if isinstance(exc, RuntimeHomeError):
        message = " ".join(str(exc).split())[:MAX_MESSAGE_CHARS]
        return RuntimeHomeDetails(kind="runtime_home", message=message)
    if isinstance(exc, OSError):
        return OsDetails(kind="os", errno=exc.errno)
    return None


def _fingerprint(
    surface: str, module: str, name: str, frames: list[ReceiptFrame]
) -> str:
    """SHA-256 over the surface, the exception class and the frame triples."""
    payload = json.dumps(
        [surface, module, name, [[f.file, f.line, f.function] for f in frames]],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_receipt(
    surface: Surface, exc: BaseException, *, config_path: Optional[str] = None
) -> FailureReceipt:
    """Build the sanitized receipt of ``exc`` without writing it."""
    frames, dropped = _frames(exc)
    exception_type = type(exc).__qualname__
    exception_module = type(exc).__module__
    return FailureReceipt(
        schema_version=SCHEMA_VERSION,
        recorded_at=datetime.now(timezone.utc),
        surface=surface,
        pid=os.getpid(),
        config_path=config_path,
        exception_type=exception_type,
        exception_module=exception_module,
        frames=frames,
        frames_dropped=dropped,
        details=_details(exc),
        fingerprint=_fingerprint(surface, exception_module, exception_type, frames),
    )


def _append(directory: Path, receipt: FailureReceipt) -> None:
    """Append one receipt line to its UTC day file (the usage-ledger append)."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"failures-{receipt.recorded_at.date().isoformat()}.jsonl"
    line = (
        json.dumps(receipt.model_dump(mode="json"), separators=(",", ":")) + "\n"
    ).encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        written = os.write(fd, line)
        if written != len(line):
            raise OSError(
                errno_module.EIO,
                f"Short receipt append to {path}: wrote {written} of "
                f"{len(line)} bytes",
            )
    finally:
        os.close(fd)


def _receipt_dir(surface: Surface) -> Path:
    """Where a receipt of ``surface`` goes (decision 806-Q12)."""
    from nexus.runtime.home import RuntimeHomeError

    if surface == "runtime.home":
        return fallback_receipts_dir()
    try:
        return home_receipts_dir()
    # Decision 806-Q12 sends a receipt whose root cannot be located to the
    # fallback root; the RuntimeHomeError recorded its own receipt there.
    except (
        RuntimeHomeError
    ):  # nexus-exception-disposition: safe-continuation; reason=Q12; safety=receipted
        return fallback_receipts_dir()


def record_failure(
    surface: Surface, exc: BaseException, *, config_path: Optional[str] = None
) -> None:
    """Append a sanitized receipt of ``exc``; never raises.

    The caller re-raises ``exc`` unchanged. A receipt that cannot be built or
    written is reported on stderr by surface and exception type name only.
    """
    try:
        receipt = build_receipt(surface, exc, config_path=config_path)
        _append(_receipt_dir(surface), receipt)
    # A failed receipt write must not mask the error being recorded; the
    # caller re-raises the original exception unchanged.
    except (
        Exception
    ):  # nexus-exception-disposition: safe-continuation; reason=no mask; safety=caller
        write_error = sys.exc_info()[1]
        print(
            f"receipt not written for {surface}: {type(write_error).__name__}",
            file=sys.stderr,
        )


def _read_receipts(
    roots: Mapping[str, Path],
) -> list[tuple[str, FailureReceipt]]:
    """Every receipt under ``roots`` in read order, labelled by root."""
    receipts: list[tuple[str, FailureReceipt]] = []
    for label, directory in roots.items():
        for path in sorted(directory.glob("failures-*.jsonl")):
            # Binary mode: undecodable bytes fail validation (json_invalid), so
            # they are reported by path and line like any other invalid line.
            with path.open("rb") as stream:
                for number, line in enumerate(stream, start=1):
                    try:
                        receipt = FailureReceipt.model_validate_json(line)
                    except ValidationError as exc:
                        raise ReceiptReadError(
                            f"{path}:{number}: not a failure receipt "
                            f"({exc.error_count()} validation errors)"
                        ) from exc
                    receipts.append((label, receipt))
    return receipts


def read_failure_groups(roots: Mapping[str, Path]) -> list[FailureGroup]:
    """Group every receipt under ``roots`` by fingerprint; read-only.

    ``roots`` maps a label (``home``, ``fallback``) to a directory; a missing
    directory holds no receipts. Groups are ordered by ``last_seen``
    descending, then fingerprint.

    Raises:
        ReceiptReadError: a line is not a valid receipt; names ``path:line``.
    """
    grouped: dict[str, list[tuple[str, FailureReceipt]]] = {}
    for label, receipt in _read_receipts(roots):
        grouped.setdefault(receipt.fingerprint, []).append((label, receipt))
    groups = []
    for fingerprint, members in grouped.items():
        times = [receipt.recorded_at for _, receipt in members]
        # min() keeps the first of equal values, so ties keep read order.
        first = min((receipt for _, receipt in members), key=lambda r: r.recorded_at)
        groups.append(
            FailureGroup(
                fingerprint=fingerprint,
                count=len(members),
                first_seen=min(times),
                last_seen=max(times),
                roots=sorted({label for label, _ in members}),
                first=first,
            )
        )
    groups.sort(key=lambda group: group.fingerprint)
    groups.sort(key=lambda group: group.last_seen, reverse=True)
    return groups
