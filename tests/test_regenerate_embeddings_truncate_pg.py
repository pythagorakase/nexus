"""Issue #812: --truncate-table never deletes rows for a model that cannot load.

With the Hugging Face fallback gone, a missing or broken ``local_path`` makes
``ModelLoader.load_model`` fail. ``EmbeddingRegenerator`` used to run its
``--truncate-table`` branch (TRUNCATE, or DELETE of this model's rows) before
loading the model, so a missing artifact wiped the model's embeddings and then
exited. The model now loads first. This test runs the real script against a
disposable slot and a real config whose registry entry points at a missing
folder.
"""

from __future__ import annotations

import importlib.util
from contextlib import closing
from pathlib import Path
from typing import Iterator

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


def _stored_rows(dbname: str) -> int:
    table = table_name_for_dimensions(DIMENSIONS)
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE model = %s", (MODEL,))
        return int(cur.fetchone()[0])


@pytest.mark.requires_postgres
def test_truncate_table_keeps_rows_when_the_model_artifact_is_missing(
    seeded_slot: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing local_path exits before --truncate-table deletes anything."""

    document = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    missing = tmp_path / "not-installed"
    document["memnon"]["models"][MODEL]["local_path"] = str(missing)
    config = tmp_path / "regen-truncate.toml"
    config.write_text(tomlkit.dumps(document))
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
    assert _stored_rows(seeded_slot) == 2

    with pytest.raises(SystemExit) as exited:
        script.EmbeddingRegenerator(
            model_name=MODEL,
            db_url=database_url(seeded_slot),
            truncate_table=True,
        )

    assert exited.value.code == 1
    assert _stored_rows(seeded_slot) == 2
