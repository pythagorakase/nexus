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
