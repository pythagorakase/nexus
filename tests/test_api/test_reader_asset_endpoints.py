"""Tests for the gateway's ported read and asset endpoints (issue #396).

These exercise the real routers over HTTP through a TestClient against real
slot databases - no mocks. Read coverage runs against save_02 (mature
corpus, read-only); the asset upload round-trip runs against save_05 (the
disposable dev slot) with a self-cleaning character fixture.

Wire-format assertions mirror the legacy Express/Drizzle responses: the
client code under ui/client/src was written against those shapes and this
PR re-homed them without redesign.
"""

from __future__ import annotations

import io
from typing import Iterator, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.asset_endpoints import UPLOAD_ROOT, router as asset_router
from nexus.api.db_pool import get_connection
from nexus.api.reader_endpoints import router as reader_router

pytestmark = pytest.mark.requires_postgres

READ_SLOT = 2  # save_02: mature corpus, read-only verification
WRITE_SLOT = 5  # save_05: empty dev slot, fair game

# Minimal valid 1x1 PNG (89 bytes).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(reader_router)
    app.include_router(asset_router)
    return TestClient(app)


class TestNarrativeReads:
    def test_status(self, client: TestClient) -> None:
        assert client.get("/status").json() == {"status": "ok"}

    def test_seasons_shape(self, client: TestClient) -> None:
        seasons = client.get(f"/api/narrative/seasons?slot={READ_SLOT}").json()
        assert isinstance(seasons, list) and seasons
        assert set(seasons[0].keys()) == {"id", "summary"}

    def test_episodes_shape(self, client: TestClient) -> None:
        seasons = client.get(f"/api/narrative/seasons?slot={READ_SLOT}").json()
        episodes = client.get(
            f"/api/narrative/episodes/{seasons[0]['id']}?slot={READ_SLOT}"
        ).json()
        assert episodes
        assert set(episodes[0].keys()) == {"season", "episode", "chunkSpan", "summary"}

    def test_latest_chunk_shape(self, client: TestClient) -> None:
        chunk = client.get(f"/api/narrative/latest-chunk?slot={READ_SLOT}").json()
        assert set(chunk.keys()) == {
            "id",
            "rawText",
            "storytellerText",
            "choiceObject",
            "choiceText",
            "createdAt",
            "metadata",
        }
        meta = chunk["metadata"]
        assert meta["chunkId"] == chunk["id"]
        assert set(meta.keys()) == {
            "id",
            "chunkId",
            "season",
            "episode",
            "scene",
            "worldLayer",
            "timeDelta",
            "generationDate",
            "slug",
        }

    def test_outline_and_chunk_by_id(self, client: TestClient) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        assert outline
        assert set(outline[0].keys()) == {"id", "season", "episode", "scene", "slug"}
        chunk_id = outline[0]["id"]
        chunk = client.get(f"/api/narrative/chunks/{chunk_id}?slot={READ_SLOT}").json()
        assert chunk["id"] == chunk_id
        assert chunk["metadata"]["chunkId"] == chunk_id

    def test_chunk_404(self, client: TestClient) -> None:
        response = client.get(f"/api/narrative/chunks/999999999?slot={READ_SLOT}")
        assert response.status_code == 404

    def test_adjacent(self, client: TestClient) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        middle = outline[len(outline) // 2]["id"]
        result = client.get(
            f"/api/narrative/chunks/{middle}/adjacent?slot={READ_SLOT}"
        ).json()
        assert set(result.keys()) == {"previous", "next"}
        assert result["previous"]["id"] < middle
        assert result["next"]["id"] > middle

    def test_context_shape(self, client: TestClient) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        context = client.get(
            f"/api/narrative/chunks/{outline[-1]['id']}/context?slot={READ_SLOT}"
        ).json()
        assert set(context.keys()) == {"characters", "places"}
        for entry in context["characters"]:
            assert set(entry.keys()) == {"id", "name", "reference"}
        for entry in context["places"]:
            assert set(entry.keys()) == {"id", "name", "referenceType"}

    def test_chunks_by_season_episode(self, client: TestClient) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        row = outline[0]
        result = client.get(
            f"/api/narrative/chunks/{row['season']}/{row['episode']}"
            f"?limit=5&slot={READ_SLOT}"
        ).json()
        assert result["total"] >= 1
        assert len(result["chunks"]) >= 1
        assert result["chunks"][0]["metadata"]["season"] == row["season"]


class TestWorldReads:
    def test_characters_shape(self, client: TestClient) -> None:
        characters = client.get(f"/api/characters?slot={READ_SLOT}").json()
        assert characters
        entry = characters[0]
        assert set(entry.keys()) == {
            "id",
            "name",
            "summary",
            "appearance",
            "background",
            "personality",
            "emotionalState",
            "currentActivity",
            "currentLocation",
            "extraData",
            "createdAt",
            "updatedAt",
            "currentLocationName",
            "portraitPath",
        }
        # Wire contract: currentLocation is a string (legacy Drizzle typing)
        # even though the live column is bigint.
        for character in characters:
            location = character["currentLocation"]
            assert location is None or isinstance(location, str)

    def test_places_shape(self, client: TestClient) -> None:
        places = client.get(f"/api/places?slot={READ_SLOT}").json()
        assert places
        entry = places[0]
        assert set(entry.keys()) == {
            "id",
            "name",
            "type",
            "zone",
            "summary",
            "inhabitants",
            "history",
            "currentStatus",
            "secrets",
            "extraData",
            "createdAt",
            "updatedAt",
            "geometry",
        }
        located = [p for p in places if p["geometry"] is not None]
        assert located, "expected at least one place with coordinates"
        assert located[0]["geometry"]["type"] == "Point"

    def test_zones_shape(self, client: TestClient) -> None:
        zones = client.get(f"/api/zones?slot={READ_SLOT}").json()
        assert zones
        assert set(zones[0].keys()) == {"id", "name", "summary", "boundary"}

    def test_factions_live_schema(self, client: TestClient) -> None:
        factions = client.get(f"/api/factions?slot={READ_SLOT}").json()
        assert isinstance(factions, list)
        if factions:
            assert set(factions[0].keys()) == {
                "id",
                "name",
                "summary",
                "primaryLocation",
                "extraData",
                "createdAt",
                "updatedAt",
            }

    def test_current_place(self, client: TestClient) -> None:
        response = client.get(f"/api/current-place?slot={READ_SLOT}")
        assert response.status_code == 200
        assert set(response.json().keys()) == {"placeId", "name", "chunkId"}

    def test_relationships_and_psychology(self, client: TestClient) -> None:
        characters = client.get(f"/api/characters?slot={READ_SLOT}").json()
        character_id = characters[0]["id"]
        relationships = client.get(
            f"/api/characters/{character_id}/relationships?slot={READ_SLOT}"
        ).json()
        assert isinstance(relationships, list)
        if relationships:
            assert {"character1Id", "character2Id", "relationshipType"} <= set(
                relationships[0].keys()
            )
        psychology = client.get(
            f"/api/characters/{character_id}/psychology?slot={READ_SLOT}"
        )
        assert psychology.status_code in (200, 404)

    def test_invalid_slot_is_400(self, client: TestClient) -> None:
        assert client.get("/api/places?slot=9").status_code == 400


@pytest.fixture()
def temp_character() -> Iterator[Tuple[int, str]]:
    """A disposable character row in save_05 for asset round-trips."""
    dbname = f"save_{WRITE_SLOT:02d}"
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
            entity_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (%s, %s)
                RETURNING id
                """,
                (f"__test_upload_{entity_id}", entity_id),
            )
            character_id = cur.fetchone()[0]
    try:
        yield character_id, dbname
    finally:
        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM assets.character_images WHERE character_id = %s",
                    (character_id,),
                )
                cur.execute("DELETE FROM characters WHERE id = %s", (character_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))


class TestAssetRoundTrip:
    def test_portrait_upload_set_main_delete(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        character_id, _ = temp_character

        # Upload: first portrait becomes main automatically.
        response = client.post(
            f"/api/characters/{character_id}/images?slot={WRITE_SLOT}",
            files={"images": ("portrait one.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        image = body["images"][0]
        assert set(image.keys()) == {
            "id",
            "characterId",
            "filePath",
            "isMain",
            "displayOrder",
            "uploadedAt",
        }
        assert image["isMain"] == 1
        assert image["filePath"].startswith(f"character_portraits/{character_id}/")
        stored = UPLOAD_ROOT / image["filePath"]
        assert stored.is_file() and stored.read_bytes() == PNG_BYTES

        # Second upload is not main.
        second = client.post(
            f"/api/characters/{character_id}/images?slot={WRITE_SLOT}",
            files={"images": ("two.jpg", io.BytesIO(PNG_BYTES), "image/jpeg")},
        ).json()["images"][0]
        assert second["isMain"] == 0
        assert second["displayOrder"] == image["displayOrder"] + 1

        # Promote the second to main.
        response = client.put(
            f"/api/characters/{character_id}/images/{second['id']}/main"
            f"?slot={WRITE_SLOT}"
        )
        assert response.json() == {"success": True}
        listed = client.get(
            f"/api/characters/{character_id}/images?slot={WRITE_SLOT}"
        ).json()
        mains = {row["id"]: row["isMain"] for row in listed}
        assert mains[second["id"]] == 1 and mains[image["id"]] == 0

        # Delete both; files disappear with the rows.
        for row in listed:
            response = client.delete(
                f"/api/characters/{character_id}/images/{row['id']}"
                f"?slot={WRITE_SLOT}"
            )
            assert response.json() == {"success": True}
        assert not stored.exists()
        assert (
            client.get(
                f"/api/characters/{character_id}/images?slot={WRITE_SLOT}"
            ).json()
            == []
        )

    def test_invalid_type_rejected(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        character_id, _ = temp_character
        response = client.post(
            f"/api/characters/{character_id}/images?slot={WRITE_SLOT}",
            files={"images": ("nope.gif", io.BytesIO(b"GIF89a"), "image/gif")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.text

    def test_delete_handles_legacy_leading_slash_paths(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        """Legacy rows store file_path as "/character_portraits/...".

        pathlib treats a leading-slash right operand as absolute (Node's
        path.join did not), so delete must strip it or the public file is
        orphaned (Codex P2 on PR #400).
        """
        character_id, dbname = temp_character
        rel_dir = UPLOAD_ROOT / "character_portraits" / str(character_id)
        rel_dir.mkdir(parents=True, exist_ok=True)
        stored = rel_dir / "legacy.png"
        stored.write_bytes(PNG_BYTES)

        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO assets.character_images
                        (character_id, file_path, is_main, display_order)
                    VALUES (%s, %s, 0, 0)
                    RETURNING id
                    """,
                    (
                        character_id,
                        f"/character_portraits/{character_id}/legacy.png",
                    ),
                )
                image_id = cur.fetchone()["id"]

        response = client.delete(
            f"/api/characters/{character_id}/images/{image_id}?slot={WRITE_SLOT}"
        )
        assert response.json() == {"success": True}
        assert not stored.exists(), "legacy-path file must be unlinked"
