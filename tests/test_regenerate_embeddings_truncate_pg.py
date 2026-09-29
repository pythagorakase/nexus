"""Issue #812: regenerate_embeddings.py deletes no rows for a model that cannot load.

With the Hugging Face fallback gone, a missing or broken ``local_path`` makes
``ModelLoader.load_model`` fail. ``EmbeddingRegenerator`` used to run its
``--truncate-table`` branch (TRUNCATE, or DELETE of this model's rows) before
loading the model, and ``--chunk`` committed the DELETE of the chunk's stored
row before anything loaded, so a missing artifact wiped embeddings and then
exited. The model now loads first on both paths. These tests run the real
script against a disposable slot and a real config whose registry entry
points at a missing folder.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator, List, Tuple

import pytest
import tomlkit

from nexus.agents.memnon.utils.embedding_tables import (
    ensure_embedding_table,
    table_name_for_dimensions,
)
from nexus.database import database_url
from tests.pg_fixtures import connect, disposable_slot_database, seed_committed_chunk

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = "bge-large"
DIMENSIONS = 1024


@pytest.fixture()
def seeded_slot() -> Iterator[str]:
    """A disposable slot holding two stored bge-large embeddings."""

    with disposable_slot_database("qa640_regen_truncate") as dbname:
        chunk_ids = [
            seed_committed_chunk(dbname, raw_text=text, scene=scene)
            for scene, text in enumerate(("the bell", "the lintel"), start=1)
        ]
        vector = "[" + ",".join(["0.5"] * DIMENSIONS) + "]"
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            table = ensure_embedding_table(cur, DIMENSIONS)
            for chunk_id in chunk_ids:
                cur.execute(
                    f"INSERT INTO {table} (chunk_id, model, embedding) "
                    "VALUES (%s, %s, %s::vector)",
                    (chunk_id, MODEL, vector),
                )
        yield dbname


def _stored_chunk_ids(dbname: str) -> List[int]:
    """The chunk ids that hold a stored bge-large embedding, in id order."""

    table = table_name_for_dimensions(DIMENSIONS)
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT chunk_id FROM {table} WHERE model = %s ORDER BY chunk_id",
            (MODEL,),
        )
        return [int(row[0]) for row in cur.fetchall()]


def _config_with_missing_artifact(tmp_path: Path) -> Tuple[Path, Path, str]:
    """Write nexus.toml with bge-large's local_path at a missing folder.

    Returns:
        The config path, the missing folder, and bge-large's repository.
    """

    document: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    entry = document["memnon"]["models"][MODEL]
    missing = tmp_path / "not-installed"
    entry["local_path"] = str(missing)
    config = tmp_path / "regen-missing-artifact.toml"
    config.write_text(tomlkit.dumps(document))
    return config, missing, str(entry["remote_path"])


@pytest.mark.requires_postgres
def test_truncate_table_keeps_rows_when_the_model_artifact_is_missing(
    seeded_slot: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing local_path exits before --truncate-table deletes anything."""

    config, missing, _ = _config_with_missing_artifact(tmp_path)
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    # The script opens its log file in the working directory.
    monkeypatch.chdir(tmp_path)

    spec = importlib.util.spec_from_file_location(
        "regenerate_embeddings_probe",
        REPO_ROOT / "scripts" / "regenerate_embeddings.py",
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.SETTINGS["models"][MODEL]["local_path"] == str(missing)
    stored = _stored_chunk_ids(seeded_slot)
    assert len(stored) == 2

    with pytest.raises(SystemExit) as exited:
        script.EmbeddingRegenerator(
            model_name=MODEL,
            db_url=database_url(seeded_slot),
            truncate_table=True,
        )

    assert exited.value.code == 1
    assert _stored_chunk_ids(seeded_slot) == stored


@pytest.mark.requires_postgres
def test_chunk_keeps_its_row_when_the_model_artifact_is_missing(
    seeded_slot: str, tmp_path: Path
) -> None:
    """--chunk fails with the restore command before it deletes the chunk's row.

    The script runs as an operator runs it, in its own interpreter, with the
    Hugging Face Hub switched off so any download attempt fails loudly.
    """

    config, missing, repo = _config_with_missing_artifact(tmp_path)
    stored = _stored_chunk_ids(seeded_slot)
    assert len(stored) == 2

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "regenerate_embeddings.py"),
            "--model",
            MODEL,
            "--chunk",
            str(stored[0]),
            "--db-url",
            database_url(seeded_slot),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "NEXUS_RUNTIME_CONFIG": str(config),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        # The script opens its log file in the working directory.
        cwd=tmp_path,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert _stored_chunk_ids(seeded_slot) == stored, result.stderr
    assert (
        f"Error: Embedding model '{MODEL}' is not installed: local_path {missing} "
        f"does not exist. Restore it with `hf download {repo} --local-dir "
        f"{missing}`, then run `nexus models verify`."
    ) in result.stdout.splitlines(), (result.stdout + result.stderr)
