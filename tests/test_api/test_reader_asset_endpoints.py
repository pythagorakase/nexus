"""Tests for the gateway's ported read and asset endpoints (issue #396).

These exercise the real routers over HTTP through a TestClient against real
slot databases - no mocks. Read coverage runs against a disposable template
clone (``read_slot``) routed under ``READ_SLOT``, seeded once per module with
a played story through the accepted-turn factory (``seed_played_story``: a
zone, two located places, the protagonist and an off-screen cast, and turns
whose references name a setting place), a faction, a relationship on the
first character, and the episode and season summary rows in the summary
writer's shape. The asset upload round-trip runs against a second disposable
template clone (``asset_slot``) routed under ``ROUTED_SLOT``: the character is
inserted through the real pool after ``seed_story_clock`` anchors its need
clock, image rows are written through HTTP, and uploaded files land in a
per-test directory instead of the checkout's ``ui/client/public``. The clone
is dropped after the module, so no owner slot or portrait is written.

Wire-format assertions mirror the legacy Express/Drizzle responses: the
client code under ui/client/src was written against those shapes and this
PR re-homed them without redesign.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Iterator, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import asset_endpoints
from nexus.api.asset_endpoints import router as asset_router
from nexus.api.db_pool import get_connection
from nexus.api.reader_endpoints import router as reader_router
from psycopg2.extras import Json

from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_faction,
    seed_played_story,
    seed_relationship,
    seed_story_clock,
)

pytestmark = pytest.mark.requires_postgres

READ_SLOT = 2  # routed to read_slot's seeded clone for read coverage
ROUTED_SLOT = 4  # routed to asset_slot's disposable clone for writes
WORLD_TIME = datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)

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


# The seeded read story: turns played, and the off-screen cast they mention.
READ_TURNS = 4
READ_CAST = ("Mara Quill", "Oren Vale")
READ_FACTION = "Fixture Harbor Guild"


@pytest.fixture(scope="module")
def read_slot() -> Iterator[str]:
    """A template clone holding a small played story, owned by this module.

    The story is played through ``seed_played_story`` (every turn accepted
    by the production commit), so chunks, metadata, world time, and chunk
    references take their production shapes. The episode and season summary
    rows are written with the summary drain's own statements
    (``nexus.jobs.summaries.drain_summary``), since this module reads them
    rather than generating them.
    """

    with disposable_slot_database("qa640_reader_reads") as dbname:
        seed_played_story(dbname, turns=READ_TURNS, cast=READ_CAST)
        seed_faction(dbname, name=READ_FACTION)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM characters ORDER BY id LIMIT 2")
            (first,), (second,) = cur.fetchall()
        seed_relationship(
            dbname,
            subject_character_id=first,
            object_character_id=second,
            relationship_type="ally",
        )
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO seasons (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            )
            cur.execute(
                """INSERT INTO episodes (season, episode, summary, chunk_span)
                SELECT 1, 1, %s, int8range(min(chunk_id), max(chunk_id)+1, '[)')
                FROM chunk_metadata WHERE season=1 AND episode=1""",
                (Json({"summary": "The plaza empties as evening falls."}),),
            )
            assert cur.rowcount == 1
            cur.execute(
                "UPDATE seasons SET summary=%s WHERE id=1 AND summary IS NULL",
                (Json({"summary": "A first evening in Fixture Plaza."}),),
            )
            assert cur.rowcount == 1
        yield dbname


@pytest.fixture()
def routed_read_slot(read_slot: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Route ``READ_SLOT``, and only it, to the module's seeded read clone."""

    route_slot_to_disposable(monkeypatch.setattr, slot=READ_SLOT, dbname=read_slot)
    return read_slot


class TestNarrativeReads:
    def test_status(self, client: TestClient) -> None:
        assert client.get("/status").json() == {"status": "ok"}

    def test_seasons_shape(self, client: TestClient, routed_read_slot: str) -> None:
        seasons = client.get(f"/api/narrative/seasons?slot={READ_SLOT}").json()
        assert isinstance(seasons, list) and seasons
        assert set(seasons[0].keys()) == {"id", "summary"}

    def test_episodes_shape(self, client: TestClient, routed_read_slot: str) -> None:
        seasons = client.get(f"/api/narrative/seasons?slot={READ_SLOT}").json()
        episodes = client.get(
            f"/api/narrative/episodes/{seasons[0]['id']}?slot={READ_SLOT}"
        ).json()
        assert episodes
        assert set(episodes[0].keys()) == {"season", "episode", "chunkSpan", "summary"}

    def test_latest_chunk_shape(
        self, client: TestClient, routed_read_slot: str
    ) -> None:
        chunk = client.get(f"/api/narrative/latest-chunk?slot={READ_SLOT}").json()
        assert set(chunk.keys()) == {
            "id",
            "rawText",
            "storytellerText",
            "choiceObject",
            "choiceText",
            "createdAt",
            "hasInlineSceneMarkup",
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
            "worldTime",
            "worldTimeFace",
            "timeDelta",
            "generationDate",
            "slug",
        }

    def test_outline_and_chunk_by_id(
        self, client: TestClient, routed_read_slot: str
    ) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        assert outline
        assert set(outline[0].keys()) == {"id", "season", "episode", "scene", "slug"}
        chunk_id = outline[0]["id"]
        chunk = client.get(f"/api/narrative/chunks/{chunk_id}?slot={READ_SLOT}").json()
        assert chunk["id"] == chunk_id
        assert chunk["metadata"]["chunkId"] == chunk_id

    def test_chunk_404(self, client: TestClient, routed_read_slot: str) -> None:
        response = client.get(f"/api/narrative/chunks/999999999?slot={READ_SLOT}")
        assert response.status_code == 404

    def test_adjacent(self, client: TestClient, routed_read_slot: str) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        middle = outline[len(outline) // 2]["id"]
        result = client.get(
            f"/api/narrative/chunks/{middle}/adjacent?slot={READ_SLOT}"
        ).json()
        assert set(result.keys()) == {"previous", "next"}
        assert result["previous"]["id"] < middle
        assert result["next"]["id"] > middle

    def test_context_shape(self, client: TestClient, routed_read_slot: str) -> None:
        outline = client.get(f"/api/narrative/outline?slot={READ_SLOT}").json()
        context = client.get(
            f"/api/narrative/chunks/{outline[-1]['id']}/context?slot={READ_SLOT}"
        ).json()
        assert set(context.keys()) == {"characters", "places"}
        for entry in context["characters"]:
            assert set(entry.keys()) == {"id", "name", "reference"}
        for entry in context["places"]:
            assert set(entry.keys()) == {"id", "name", "referenceType"}
        with get_connection(routed_read_slot) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.name FROM place_chunk_references r "
                "JOIN places p ON p.id = r.place_id "
                "WHERE r.chunk_id = %s AND r.reference_type = 'setting' ORDER BY p.id",
                (outline[-1]["id"],),
            )
            expected_settings = cur.fetchall()
        assert expected_settings, "the seeded turns reference a setting place"
        assert [
            (place["id"], place["name"])
            for place in context["places"]
            if place["referenceType"] == "setting"
        ] == expected_settings

    def test_chunks_by_season_episode(
        self, client: TestClient, routed_read_slot: str
    ) -> None:
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
    def test_characters_shape(self, client: TestClient, routed_read_slot: str) -> None:
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

    def test_places_shape(self, client: TestClient, routed_read_slot: str) -> None:
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
            "extraData",
            "createdAt",
            "updatedAt",
            "geometry",
        }
        located = [p for p in places if p["geometry"] is not None]
        assert located, "expected at least one place with coordinates"
        assert located[0]["geometry"]["type"] == "Point"

    def test_zones_shape(self, client: TestClient, routed_read_slot: str) -> None:
        zones = client.get(f"/api/zones?slot={READ_SLOT}").json()
        assert zones
        assert set(zones[0].keys()) == {"id", "name", "summary", "boundary"}

    def test_factions_live_schema(
        self, client: TestClient, routed_read_slot: str
    ) -> None:
        factions = client.get(f"/api/factions?slot={READ_SLOT}").json()
        assert isinstance(factions, list)
        # The seeded faction makes the shape check below non-vacuous.
        assert [faction["name"] for faction in factions] == [READ_FACTION]
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

    def test_current_place(self, client: TestClient, routed_read_slot: str) -> None:
        response = client.get(f"/api/current-place?slot={READ_SLOT}")
        assert response.status_code == 200
        places = response.json()
        assert isinstance(places, list) and places
        assert all(set(place) == {"placeId", "name", "chunkId"} for place in places)
        assert [place["placeId"] for place in places] == sorted(
            place["placeId"] for place in places
        )

    def test_relationships_and_psychology(
        self, client: TestClient, routed_read_slot: str
    ) -> None:
        characters = client.get(f"/api/characters?slot={READ_SLOT}").json()
        character_id = characters[0]["id"]
        relationships = client.get(
            f"/api/characters/{character_id}/relationships?slot={READ_SLOT}"
        ).json()
        assert isinstance(relationships, list)
        # The seeded relationship makes the shape check below non-vacuous.
        assert [
            (row["character1Id"], row["relationshipType"]) for row in relationships
        ] == [(character_id, "ally")]
        if relationships:
            assert {"character1Id", "character2Id", "relationshipType"} <= set(
                relationships[0].keys()
            )
        # Hidden psychology is retired from the ordinary reader (issue #769):
        # the path is unrouted, not a lookup that found no row.
        psychology = client.get(
            f"/api/characters/{character_id}/psychology?slot={READ_SLOT}"
        )
        assert psychology.status_code == 404
        assert psychology.json() == {"detail": "Not Found"}

    def test_invalid_slot_is_400(self, client: TestClient) -> None:
        assert client.get("/api/places?slot=9").status_code == 400


@pytest.fixture(scope="module")
def asset_slot() -> Iterator[str]:
    """A template clone with a story clock, owned by this module."""

    with disposable_slot_database("qa640_reader_assets") as dbname:
        seed_story_clock(dbname, world_time=WORLD_TIME)
        yield dbname


@pytest.fixture()
def upload_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Serve uploads from a per-test directory, never the checkout's public."""

    root = tmp_path / "public"
    monkeypatch.setattr(asset_endpoints, "UPLOAD_ROOT", root)
    return root


@pytest.fixture()
def temp_character(
    asset_slot: str, upload_root: Path, monkeypatch: pytest.MonkeyPatch
) -> Tuple[int, str]:
    """A character in the routed clone, inserted through the real pool."""

    route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=asset_slot)
    with get_connection(asset_slot) as conn:
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
    return character_id, asset_slot


class TestAssetRoundTrip:
    def test_portrait_upload_set_main_delete(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        character_id, _ = temp_character

        # Upload: first portrait becomes main automatically.
        response = client.post(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}",
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
        stored = asset_endpoints.UPLOAD_ROOT / image["filePath"]
        assert stored.is_file() and stored.read_bytes() == PNG_BYTES

        # Second upload is not main.
        second = client.post(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}",
            files={"images": ("two.jpg", io.BytesIO(PNG_BYTES), "image/jpeg")},
        ).json()["images"][0]
        assert second["isMain"] == 0
        assert second["displayOrder"] == image["displayOrder"] + 1

        # Promote the second to main.
        response = client.put(
            f"/api/characters/{character_id}/images/{second['id']}/main"
            f"?slot={ROUTED_SLOT}"
        )
        assert response.json() == {"success": True}
        listed = client.get(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}"
        ).json()
        mains = {row["id"]: row["isMain"] for row in listed}
        assert mains[second["id"]] == 1 and mains[image["id"]] == 0

        # Delete both; files disappear with the rows.
        for row in listed:
            response = client.delete(
                f"/api/characters/{character_id}/images/{row['id']}"
                f"?slot={ROUTED_SLOT}"
            )
            assert response.json() == {"success": True}
        assert not stored.exists()
        assert (
            client.get(
                f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}"
            ).json()
            == []
        )

    def test_invalid_type_rejected(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        character_id, _ = temp_character
        response = client.post(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}",
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
        rel_dir = (
            asset_endpoints.UPLOAD_ROOT / "character_portraits" / str(character_id)
        )
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
            f"/api/characters/{character_id}/images/{image_id}?slot={ROUTED_SLOT}"
        )
        assert response.json() == {"success": True}
        assert not stored.exists(), "legacy-path file must be unlinked"

    def test_cross_owner_image_ids_are_404(
        self, client: TestClient, temp_character: Tuple[int, str]
    ) -> None:
        """set-main and delete must not mutate another owner's image rows.

        A foreign image_id is a 404 and the owner's own main flag is left
        untouched (Claude review on PR #400: cross-owner IDOR).
        """
        character_id, _ = temp_character
        own = client.post(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}",
            files={"images": ("mine.png", io.BytesIO(PNG_BYTES), "image/png")},
        ).json()["images"][0]
        assert own["isMain"] == 1

        foreign_id = own["id"] + 999_999  # guaranteed not this character's
        response = client.put(
            f"/api/characters/{character_id}/images/{foreign_id}/main"
            f"?slot={ROUTED_SLOT}"
        )
        assert response.status_code == 404
        response = client.delete(
            f"/api/characters/{character_id}/images/{foreign_id}?slot={ROUTED_SLOT}"
        )
        assert response.status_code == 404

        listed = client.get(
            f"/api/characters/{character_id}/images?slot={ROUTED_SLOT}"
        ).json()
        assert [row["id"] for row in listed] == [own["id"]]
        assert listed[0]["isMain"] == 1, "failed set-main must not clear the flag"

        # Cleanup through the API (also exercises the happy delete path).
        assert client.delete(
            f"/api/characters/{character_id}/images/{own['id']}?slot={ROUTED_SLOT}"
        ).json() == {"success": True}
