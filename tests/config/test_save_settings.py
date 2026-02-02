"""Tests for save_settings() TOML write functionality."""

import pytest
from pathlib import Path
from nexus.config import save_settings


@pytest.fixture
def sample_toml(tmp_path):
    """Create a sample TOML file with comments."""
    content = '''# Header comment
[global.model]
# Default model comment
default_model = "old-model"
possible_values = [
    "model-a",
    "model-b",
]
'''
    toml_path = tmp_path / "test.toml"
    toml_path.write_text(content)
    return toml_path


def test_preserves_comments(sample_toml):
    """Verify comments are preserved after save."""
    save_settings(
        {"global.model.default_model": "new-model"},
        path=sample_toml,
        validate=False,
    )
    content = sample_toml.read_text()
    assert "# Header comment" in content
    assert "# Default model comment" in content
    assert 'default_model = "new-model"' in content


def test_partial_update_leaves_other_fields(sample_toml):
    """Verify only specified fields are changed."""
    save_settings(
        {"global.model.default_model": "new-model"},
        path=sample_toml,
        validate=False,
    )
    import tomllib
    with open(sample_toml, "rb") as f:
        data = tomllib.load(f)
    assert data["global"]["model"]["default_model"] == "new-model"
    assert data["global"]["model"]["possible_values"] == ["model-a", "model-b"]


def test_creates_backup(sample_toml):
    """Verify backup file is created."""
    original_content = sample_toml.read_text()
    save_settings(
        {"global.model.default_model": "new-model"},
        path=sample_toml,
        backup=True,
        validate=False,
    )
    backup_path = sample_toml.with_suffix(".toml.bak")
    assert backup_path.exists()
    assert backup_path.read_text() == original_content


def test_file_not_found_raises(tmp_path):
    """Verify FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        save_settings(
            {"global.model.default_model": "new"},
            path=tmp_path / "nonexistent.toml",
        )


def test_preserves_multiline_arrays(tmp_path):
    """Verify multiline array format is preserved."""
    content = '''[global.model]
possible_values = [
    "model-a",
    "model-b",
]
'''
    toml_path = tmp_path / "test.toml"
    toml_path.write_text(content)

    save_settings(
        {"global.model.possible_values": ["model-a", "model-b", "model-c"]},
        path=toml_path,
        validate=False,
    )

    result = toml_path.read_text()
    # Check that array is still multiline (one element per line)
    assert '"model-a",' in result
    assert '"model-b",' in result
    assert '"model-c"' in result
    # Ensure it's not a single-line array
    lines_with_model_a = [l for l in result.split("\n") if "model-a" in l]
    assert len(lines_with_model_a) == 1, "Array should be multiline, not single-line"
