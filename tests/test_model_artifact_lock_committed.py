"""Issue #812: the committed model artifact lock matches nexus.toml.

``nexus models verify`` compares the local artifacts with
``config/model_artifacts.lock.json``; this test only reads the committed lock
and the committed configuration (no hashing, no model folders needed), so it
fails when a production model changes in nexus.toml without a fresh
``nexus models lock``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Dict

from nexus.agents.memnon.utils.artifact_manifest import (
    EMBEDDER_ROLE,
    RERANKER_ROLE,
    REVISION_SOURCE_GIT,
    REVISION_SOURCE_HUGGINGFACE,
    read_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _committed() -> Dict[str, Any]:
    """The committed nexus.toml, read as plain TOML."""

    return tomllib.loads((REPO_ROOT / "nexus.toml").read_text(encoding="utf-8"))


def test_committed_lock_names_the_production_models() -> None:
    """The lock parses and records the active embedder and the reranker."""

    memnon = _committed()["memnon"]
    lock_file = Path(memnon["artifacts"]["lock_file"])
    manifest = read_manifest(
        lock_file if lock_file.is_absolute() else REPO_ROOT / lock_file
    )
    by_role: Dict[str, Dict[str, Any]] = {}
    for entry in manifest["artifacts"]:
        assert entry["role"] not in by_role, f"duplicate {entry['role']} entry"
        by_role[entry["role"]] = entry
    assert set(by_role) == {EMBEDDER_ROLE, RERANKER_ROLE}

    (active,) = [
        (name, model) for name, model in memnon["models"].items() if model["is_active"]
    ]
    embedder = by_role[EMBEDDER_ROLE]
    assert embedder["name"] == active[0]
    assert embedder["repo_id"] == active[1]["remote_path"]
    assert embedder["dimensions"] == active[1]["dimensions"]

    reranking = memnon["retrieval"]["cross_encoder_reranking"]
    reranker = by_role[RERANKER_ROLE]
    assert reranker["name"] == reranking["name"]
    assert reranker["repo_id"] == reranking["remote_path"]
    assert all(entry["files"] for entry in by_role.values())

    # Restore commands pin --revision from the lock, so every artifact that
    # restores from a repository records its revision and where it was read.
    for entry in by_role.values():
        if entry["repo_id"]:
            assert entry["revision"], f"{entry['role']} records no revision"
            assert entry["revision_source"] in {
                REVISION_SOURCE_GIT,
                REVISION_SOURCE_HUGGINGFACE,
            }
