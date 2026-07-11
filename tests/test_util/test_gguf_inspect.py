"""Tests for lightweight GGUF header inspection."""

from pathlib import Path

import pytest

from nexus.util.gguf_inspect import inspect_gguf


def test_inspect_real_gguf_when_installed() -> None:
    """A locally installed Hermes GGUF exposes architecture and quantization."""
    root = Path.home() / ".lmstudio/models/lmstudio-community"
    candidates = list(root.glob("Hermes*/**/*.gguf"))
    if not candidates:
        pytest.skip("No locally installed Hermes GGUF is available")

    info = inspect_gguf(str(candidates[0]))

    assert info.valid is True
    assert info.architecture
    assert info.quantization


def test_inspect_rejects_wrong_magic(tmp_path: Path) -> None:
    """A normal file is rejected before the GGUF parser is constructed."""
    invalid = tmp_path / "not-a-model.gguf"
    invalid.write_bytes(b"NOPE ordinary content")

    info = inspect_gguf(str(invalid))

    assert info.valid is False
    assert info.reason is not None
    assert "magic" in info.reason.lower()


def test_inspect_skips_large_arrays_and_reads_fields(tmp_path: Path) -> None:
    """Fields after a large string array are still read (arrays are skipped)."""
    gguf = pytest.importorskip("gguf")

    target = tmp_path / "synthetic.gguf"
    writer = gguf.GGUFWriter(str(target), "llama")
    # A large tokenizer-style string array BEFORE the fields we want forces
    # the parser to seek past it rather than materialize it.
    writer.add_array("tokenizer.ggml.tokens", [f"tok{i}" for i in range(50_000)])
    writer.add_uint32("llama.context_length", 4096)
    writer.add_string("general.name", "Synthetic Test Model")
    writer.add_uint32("general.file_type", int(gguf.LlamaFileType.MOSTLY_Q4_K_M))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    info = inspect_gguf(str(target))

    assert info.valid is True
    assert info.architecture == "llama"
    assert info.name == "Synthetic Test Model"
    assert info.context_length == 4096
    assert info.quantization == "Q4_K_M"


def test_inspect_rejects_unsupported_version(tmp_path: Path) -> None:
    """A GGUF magic with a bogus version is rejected loudly, not parsed."""
    import struct

    bogus = tmp_path / "bogus.gguf"
    bogus.write_bytes(b"GGUF" + struct.pack("<I", 999) + b"\x00" * 16)

    info = inspect_gguf(str(bogus))

    assert info.valid is False
    assert "version" in (info.reason or "").lower()


def test_inspect_rejects_truncated_header(tmp_path: Path) -> None:
    """A file that ends mid-header reports truncation instead of raising."""
    import struct

    stub = tmp_path / "truncated.gguf"
    stub.write_bytes(b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0))

    info = inspect_gguf(str(stub))

    assert info.valid is False
    assert "truncated" in (info.reason or "").lower()


def _minimal_gguf(kvs: "list[tuple[str, int, bytes]]") -> bytes:
    """Hand-craft a minimal GGUF v3 header: full control over KV ordering."""
    import struct

    out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0)
    out += struct.pack("<Q", len(kvs))
    for key, value_type, payload in kvs:
        encoded = key.encode()
        out += struct.pack("<Q", len(encoded)) + encoded
        out += struct.pack("<I", value_type) + payload
    return out


def test_inspect_reads_context_length_written_before_architecture(
    tmp_path: Path,
) -> None:
    """KV ordering is not guaranteed; ctx-before-arch must still resolve."""
    import struct

    arch = b"llama"
    target = tmp_path / "ctx-first.gguf"
    target.write_bytes(
        _minimal_gguf(
            [
                ("llama.context_length", 4, struct.pack("<I", 8192)),
                (
                    "general.architecture",
                    8,
                    struct.pack("<Q", len(arch)) + arch,
                ),
            ]
        )
    )

    info = inspect_gguf(str(target))

    assert info.valid is True
    assert info.architecture == "llama"
    assert info.context_length == 8192


def test_inspect_skips_nested_arrays_without_rejecting(tmp_path: Path) -> None:
    """A legal nested-array KV is skipped, not treated as corruption."""
    import struct

    arch = b"llama"
    # array of 2 arrays, each holding 3 uint32 values
    inner = struct.pack("<I", 4) + struct.pack("<Q", 3) + struct.pack("<3I", 1, 2, 3)
    nested_payload = struct.pack("<I", 9) + struct.pack("<Q", 2) + inner + inner
    target = tmp_path / "nested.gguf"
    target.write_bytes(
        _minimal_gguf(
            [
                ("exotic.nested", 9, nested_payload),
                (
                    "general.architecture",
                    8,
                    struct.pack("<Q", len(arch)) + arch,
                ),
                ("llama.context_length", 4, struct.pack("<I", 2048)),
            ]
        )
    )

    info = inspect_gguf(str(target))

    assert info.valid is True
    assert info.architecture == "llama"
    assert info.context_length == 2048
