"""The retired settings writer must fail before touching repository files."""

from pathlib import Path

import pytest

from nexus.config import save_settings


@pytest.mark.parametrize("validate,backup", [(True, True), (False, False)])
def test_save_settings_is_read_only(
    tmp_path: Path, validate: bool, backup: bool
) -> None:
    path = tmp_path / "nexus.toml"
    path.write_text("# repository defaults\n")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="read-only at runtime"):
        save_settings(
            {"ui.theme": "vector"}, path=path, validate=validate, backup=backup
        )
    assert path.read_bytes() == before
    assert not path.with_suffix(".toml.bak").exists()
