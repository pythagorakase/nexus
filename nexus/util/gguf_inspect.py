"""Lightweight GGUF metadata inspection without loading model tensors.

This module parses the GGUF key-value header directly with bounded reads —
it never memory-maps the file and never materializes large metadata arrays
(a tokenizer vocabulary can be tens of megabytes; ``gguf.GGUFReader`` eagerly
decodes it, costing ~3.5s per large model and stalling the gateway under the
GIL — issue #471). Array payloads are seeked past, and parsing stops early
once every field ``GgufInfo`` needs has been read.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from gguf import LlamaFileType

# GGUF value types (spec: ggml/docs/gguf.md).
_UINT8, _INT8, _UINT16, _INT16 = 0, 1, 2, 3
_UINT32, _INT32, _FLOAT32, _BOOL = 4, 5, 6, 7
_STRING, _ARRAY, _UINT64, _INT64, _FLOAT64 = 8, 9, 10, 11, 12

_SCALAR_FORMATS: dict[int, str] = {
    _UINT8: "<B",
    _INT8: "<b",
    _UINT16: "<H",
    _INT16: "<h",
    _UINT32: "<I",
    _INT32: "<i",
    _FLOAT32: "<f",
    _BOOL: "<?",
    _UINT64: "<Q",
    _INT64: "<q",
    _FLOAT64: "<d",
}
_SCALAR_SIZES: dict[int, int] = {
    _UINT8: 1,
    _INT8: 1,
    _UINT16: 2,
    _INT16: 2,
    _UINT32: 4,
    _INT32: 4,
    _FLOAT32: 4,
    _BOOL: 1,
    _UINT64: 8,
    _INT64: 8,
    _FLOAT64: 8,
}

# Loud sanity bounds: a header field exceeding these is corrupt, not big.
_MAX_KEY_BYTES = 65_536
_MAX_STRING_BYTES = 1 << 30
_MAX_ARRAY_COUNT = 1 << 34


@dataclass(frozen=True)
class GgufInfo:
    """Metadata needed to verify and label a local GGUF file."""

    architecture: str | None = None
    name: str | None = None
    parameter_count: int | None = None
    quantization: str | None = None
    file_type: int | None = None
    context_length: int | None = None
    valid: bool = False
    reason: str | None = None


class _HeaderError(ValueError):
    """Raised for structurally invalid or unsupported GGUF headers."""


def _read_exact(handle: BinaryIO, count: int) -> bytes:
    data = handle.read(count)
    if len(data) != count:
        raise _HeaderError("truncated header")
    return data


def _read_u32(handle: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(handle, 4))[0]


def _read_u64(handle: BinaryIO) -> int:
    return struct.unpack("<Q", _read_exact(handle, 8))[0]


def _read_string(handle: BinaryIO, limit: int) -> str:
    length = _read_u64(handle)
    if length > limit:
        raise _HeaderError(f"string length {length} exceeds sanity bound")
    return _read_exact(handle, length).decode("utf-8", errors="replace")


def _read_scalar(handle: BinaryIO, value_type: int) -> Any:
    fmt = _SCALAR_FORMATS.get(value_type)
    if fmt is None:
        raise _HeaderError(f"unknown GGUF value type {value_type}")
    return struct.unpack(fmt, _read_exact(handle, _SCALAR_SIZES[value_type]))[0]


def _skip_string(handle: BinaryIO) -> None:
    length = _read_u64(handle)
    if length > _MAX_STRING_BYTES:
        raise _HeaderError(f"string length {length} exceeds sanity bound")
    handle.seek(length, 1)


def _skip_array(handle: BinaryIO) -> None:
    """Seek past an array value without materializing its elements."""
    element_type = _read_u32(handle)
    count = _read_u64(handle)
    if count > _MAX_ARRAY_COUNT:
        raise _HeaderError(f"array count {count} exceeds sanity bound")
    if element_type == _ARRAY:
        # No GGUF writer emits nested arrays; treat as corrupt rather than
        # recurse into an unbounded structure.
        raise _HeaderError("nested GGUF arrays are unsupported")
    if element_type == _STRING:
        for _ in range(count):
            _skip_string(handle)
        return
    size = _SCALAR_SIZES.get(element_type)
    if size is None:
        raise _HeaderError(f"unknown GGUF array element type {element_type}")
    handle.seek(count * size, 1)


def _quantization_name(file_type: int | None) -> str | None:
    """Convert llama.cpp's general.file_type enum into a display quant."""
    if file_type is None:
        return None
    try:
        name = LlamaFileType(file_type).name
    except ValueError:
        return str(file_type)
    return name.removeprefix("MOSTLY_")


def _parse_header_fields(handle: BinaryIO) -> dict[str, Any]:
    """Read the KV section, skipping arrays, stopping early once satisfied."""
    version = _read_u32(handle)
    if version not in (2, 3):
        if struct.unpack(">I", struct.pack("<I", version))[0] in (1, 2, 3):
            raise _HeaderError("big-endian GGUF files are unsupported")
        raise _HeaderError(f"unsupported GGUF version {version}")
    _read_u64(handle)  # tensor_count — unused here
    kv_count = _read_u64(handle)

    wanted_general = {
        "general.architecture",
        "general.name",
        "general.file_type",
        "general.parameter_count",
    }
    fields: dict[str, Any] = {}
    context_key: str | None = None
    for _ in range(kv_count):
        key = _read_string(handle, _MAX_KEY_BYTES)
        value_type = _read_u32(handle)
        wanted = key in wanted_general or (
            context_key is not None and key == context_key
        )
        if wanted and value_type == _STRING:
            fields[key] = _read_string(handle, _MAX_STRING_BYTES)
        elif wanted and value_type != _ARRAY:
            fields[key] = _read_scalar(handle, value_type)
        elif value_type == _STRING:
            _skip_string(handle)
        elif value_type == _ARRAY:
            _skip_array(handle)
        else:
            size = _SCALAR_SIZES.get(value_type)
            if size is None:
                raise _HeaderError(f"unknown GGUF value type {value_type}")
            handle.seek(size, 1)
        if key == "general.architecture" and key in fields:
            context_key = f"{fields[key]}.context_length"
        # Early exit: every wanted key present (context key only knowable
        # after the architecture has been read).
        if (
            wanted_general <= fields.keys()
            and context_key is not None
            and context_key in fields
        ):
            break
    return fields


def inspect_gguf(path: str) -> GgufInfo:
    """Inspect GGUF header metadata with bounded reads.

    Invalid or unreadable files return ``valid=False`` with a user-facing
    reason. The four-byte magic is checked first; the KV section is then
    parsed with small sequential reads, seeking past array payloads
    (tokenizer vocabularies and the like), so a multi-gigabyte model costs
    milliseconds to identify rather than seconds.
    """
    candidate = Path(path).expanduser()
    try:
        handle = candidate.open("rb")
    except OSError as exc:
        return GgufInfo(reason=f"Cannot read GGUF file: {exc}")
    with handle:
        try:
            magic = handle.read(4)
        except OSError as exc:
            return GgufInfo(reason=f"Cannot read GGUF file: {exc}")
        if magic != b"GGUF":
            return GgufInfo(reason="Invalid GGUF file: expected GGUF magic header")
        try:
            fields = _parse_header_fields(handle)
        except (_HeaderError, OSError, struct.error) as exc:
            return GgufInfo(reason=f"Invalid or unreadable GGUF metadata: {exc}")

    architecture = fields.get("general.architecture")
    file_type_value = fields.get("general.file_type")
    file_type = int(file_type_value) if file_type_value is not None else None
    context_value = (
        fields.get(f"{architecture}.context_length") if architecture else None
    )
    parameter_value = fields.get("general.parameter_count")
    name_value = fields.get("general.name")
    return GgufInfo(
        architecture=str(architecture) if architecture is not None else None,
        name=str(name_value) if name_value is not None else None,
        parameter_count=int(parameter_value) if parameter_value is not None else None,
        quantization=_quantization_name(file_type),
        file_type=file_type,
        context_length=int(context_value) if context_value is not None else None,
        valid=True,
    )
