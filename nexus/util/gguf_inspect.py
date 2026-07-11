"""Lightweight GGUF metadata inspection without loading model tensors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gguf import GGUFReader, LlamaFileType


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


def _field_value(reader: GGUFReader, key: str) -> Any:
    """Return one decoded metadata value, or None when the field is absent."""
    field = reader.get_field(key)
    if field is None:
        return None
    value = field.contents()
    return value.item() if hasattr(value, "item") else value


def _quantization_name(file_type: int | None) -> str | None:
    """Convert llama.cpp's general.file_type enum into a display quant."""
    if file_type is None:
        return None
    try:
        name = LlamaFileType(file_type).name
    except ValueError:
        return str(file_type)
    return name.removeprefix("MOSTLY_")


def inspect_gguf(path: str) -> GgufInfo:
    """Inspect GGUF header metadata without reading model tensor contents.

    Invalid or unreadable files return ``valid=False`` with a user-facing
    reason. The four-byte magic is checked before constructing ``GGUFReader``.
    The reader memory-maps the file and parses metadata/tensor descriptors; it
    does not load tensor contents into memory.
    """
    candidate = Path(path).expanduser()
    try:
        with candidate.open("rb") as handle:
            magic = handle.read(4)
    except OSError as exc:
        return GgufInfo(reason=f"Cannot read GGUF file: {exc}")
    if magic != b"GGUF":
        return GgufInfo(reason="Invalid GGUF file: expected GGUF magic header")

    try:
        reader = GGUFReader(candidate, "r")
        architecture_value = _field_value(reader, "general.architecture")
        architecture = (
            str(architecture_value) if architecture_value is not None else None
        )
        file_type_value = _field_value(reader, "general.file_type")
        file_type = int(file_type_value) if file_type_value is not None else None
        context_value = (
            _field_value(reader, f"{architecture}.context_length")
            if architecture
            else None
        )
        parameter_value = _field_value(reader, "general.parameter_count")
        name_value = _field_value(reader, "general.name")
        return GgufInfo(
            architecture=architecture,
            name=str(name_value) if name_value is not None else None,
            parameter_count=(
                int(parameter_value) if parameter_value is not None else None
            ),
            quantization=_quantization_name(file_type),
            file_type=file_type,
            context_length=int(context_value) if context_value is not None else None,
            valid=True,
        )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        return GgufInfo(reason=f"Invalid or unreadable GGUF metadata: {exc}")
