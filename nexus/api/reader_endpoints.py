"""Read-only reading-surface endpoints, ported from the retired Express layer.

These routes power the reader (seasons/episodes/chunks/outline), the cast
pane (characters), and the map (places/zones/current-place). They were
previously implemented in ``ui/server/routes.ts`` + ``ui/server/storage.ts``
(Drizzle); this module re-homes them onto the FastAPI gateway so one origin
serves everything (issue #396).

Wire-format contract: the JSON shapes match what the Express/Drizzle layer
served (camelCase keys, ``currentLocation`` coerced to a string, ``metadata``
omitted when a chunk has none). The client code under ``ui/client/src`` is
the consumer contract — do not change shapes here without updating it.

Queries are written against the LIVE database schema (``psql -d save_NN -c
'\\d+ <table>'``), not the retired Drizzle typings, which had drifted
(e.g. ``characters.current_location`` is live bigint; the live ``factions``
table dropped most of the columns Drizzle still declared).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import require_slot_dbname

logger = logging.getLogger("nexus.api.reader_endpoints")

router = APIRouter(tags=["reader"])


def resolve_dbname(slot: Optional[int]) -> str:
    """Resolve a slot query param to a database name.

    Invalid slots are a client error (400); a missing slot with no
    NEXUS_SLOT environment fallback is a server misconfiguration (500).
    """
    try:
        return require_slot_dbname(slot=slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _fetch_all(dbname: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Run a read query against a slot database, returning dict rows."""
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


_CHUNK_SELECT = """
    SELECT
        nc.id,
        nc.raw_text,
        nc.storyteller_text,
        nc.choice_object,
        nc.choice_text,
        nc.created_at,
        cm.chunk_id,
        cm.season,
        cm.episode,
        cm.scene,
        cm.world_layer::text AS world_layer,
        cm.time_delta::text AS time_delta,
        cm.generation_date,
        cm.slug
"""


def _chunk_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map a chunk+metadata row to the legacy camelCase wire shape.

    The ``metadata`` key is omitted entirely when the chunk has no
    chunk_metadata row, matching JSON.stringify's treatment of undefined.
    """
    payload: Dict[str, Any] = {
        "id": row["id"],
        "rawText": row["raw_text"],
        "storytellerText": row["storyteller_text"],
        "choiceObject": row["choice_object"],
        "choiceText": row["choice_text"],
        "createdAt": row["created_at"],
    }
    if row["chunk_id"] is not None:
        payload["metadata"] = {
            "id": row["chunk_id"],
            "chunkId": row["chunk_id"],
            "season": row["season"],
            "episode": row["episode"],
            "scene": row["scene"],
            "worldLayer": row["world_layer"],
            "timeDelta": row["time_delta"],
            "generationDate": row["generation_date"],
            "slug": row["slug"],
        }
    return payload


@router.get("/status")
async def status() -> Dict[str, str]:
    """Liveness probe (legacy Express parity)."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Narrative reads
# ---------------------------------------------------------------------------


@router.get("/api/narrative/seasons")
async def get_seasons(slot: Optional[int] = None) -> List[Dict[str, Any]]:
    """All seasons, ordered by id."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(dbname, "SELECT id, summary FROM seasons ORDER BY id")
    return [{"id": row["id"], "summary": row["summary"]} for row in rows]


@router.get("/api/narrative/episodes/{season_id}")
async def get_episodes(
    season_id: int, slot: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Episodes for a season, ordered by episode number."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT season, episode, chunk_span::text AS chunk_span, summary
        FROM episodes
        WHERE season = %s
        ORDER BY episode
        """,
        (season_id,),
    )
    return [
        {
            "season": row["season"],
            "episode": row["episode"],
            "chunkSpan": row["chunk_span"],
            "summary": row["summary"],
        }
        for row in rows
    ]


@router.get("/api/narrative/latest-chunk")
async def get_latest_chunk(slot: Optional[int] = None) -> Dict[str, Any]:
    """The newest committed chunk (with metadata). 404 when none exist."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        _CHUNK_SELECT
        + """
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        ORDER BY nc.id DESC
        LIMIT 1
        """,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No chunks found")
    return _chunk_payload(rows[0])


@router.get("/api/narrative/outline")
async def get_outline(slot: Optional[int] = None) -> List[Dict[str, Any]]:
    """Story outline: metadata coordinates per committed chunk, story order.

    Powers the right-rail story tree without shipping chunk prose.
    """
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT cm.chunk_id, cm.season, cm.episode, cm.scene, cm.slug
        FROM chunk_metadata cm
        JOIN narrative_chunks nc ON nc.id = cm.chunk_id
        ORDER BY cm.chunk_id
        """,
    )
    return [
        {
            "id": row["chunk_id"],
            "season": row["season"],
            "episode": row["episode"],
            "scene": row["scene"],
            "slug": row["slug"],
        }
        for row in rows
    ]


@router.get("/api/narrative/chunks/{chunk_id}/adjacent")
async def get_adjacent_chunks(
    chunk_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Previous and next committed chunks around a chunk id."""
    dbname = resolve_dbname(slot)
    previous_rows = _fetch_all(
        dbname,
        _CHUNK_SELECT
        + """
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE nc.id < %s
        ORDER BY nc.id DESC
        LIMIT 1
        """,
        (chunk_id,),
    )
    next_rows = _fetch_all(
        dbname,
        _CHUNK_SELECT
        + """
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE nc.id > %s
        ORDER BY nc.id ASC
        LIMIT 1
        """,
        (chunk_id,),
    )
    return {
        "previous": _chunk_payload(previous_rows[0]) if previous_rows else None,
        "next": _chunk_payload(next_rows[0]) if next_rows else None,
    }


@router.get("/api/narrative/chunks/{chunk_id}/context")
async def get_chunk_context(
    chunk_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Character and place references for a chunk.

    Powers the reader's location header and the Session Ledger scene cast.
    """
    dbname = resolve_dbname(slot)
    character_rows = _fetch_all(
        dbname,
        """
        SELECT c.id, c.name, ccr.reference::text AS reference
        FROM chunk_character_references ccr
        JOIN characters c ON c.id = ccr.character_id
        WHERE ccr.chunk_id = %s
        ORDER BY (ccr.reference = 'present') DESC, c.id ASC
        """,
        (chunk_id,),
    )
    place_rows = _fetch_all(
        dbname,
        """
        SELECT p.id, p.name, pcr.reference_type::text AS reference_type
        FROM place_chunk_references pcr
        JOIN places p ON p.id = pcr.place_id
        WHERE pcr.chunk_id = %s
        ORDER BY (pcr.reference_type = 'setting') DESC, p.id ASC
        """,
        (chunk_id,),
    )
    return {
        "characters": [
            {"id": row["id"], "name": row["name"], "reference": row["reference"]}
            for row in character_rows
        ],
        "places": [
            {
                "id": row["id"],
                "name": row["name"],
                "referenceType": row["reference_type"],
            }
            for row in place_rows
        ],
    }


@router.get("/api/narrative/chunks/{season_id}/{episode_id}")
async def get_chunks_by_season_and_episode(
    season_id: int,
    episode_id: int,
    offset: int = 0,
    limit: int = 50,
    slot: Optional[int] = None,
) -> Dict[str, Any]:
    """Chunks for a season/episode with pagination."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        _CHUNK_SELECT
        + """
        FROM narrative_chunks nc
        LEFT JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE cm.season = %s AND cm.episode = %s
        ORDER BY nc.id
        LIMIT %s OFFSET %s
        """,
        (season_id, episode_id, limit, offset),
    )
    count_rows = _fetch_all(
        dbname,
        """
        SELECT count(*) AS count
        FROM narrative_chunks nc
        LEFT JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE cm.season = %s AND cm.episode = %s
        """,
        (season_id, episode_id),
    )
    return {
        "chunks": [_chunk_payload(row) for row in rows],
        "total": count_rows[0]["count"] if count_rows else 0,
    }


@router.get("/api/narrative/chunks/{chunk_id}")
async def get_chunk_by_id(chunk_id: int, slot: Optional[int] = None) -> Dict[str, Any]:
    """A single committed chunk by id (historical reading). 404 when absent.

    Inner join: only committed chunks with metadata are addressable for
    historical reading.
    """
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        _CHUNK_SELECT
        + """
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE nc.id = %s
        """,
        (chunk_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")
    return _chunk_payload(rows[0])


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------


@router.get("/api/characters")
async def get_characters(
    startId: Optional[int] = None,
    endId: Optional[int] = None,
    slot: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """All characters with resolved location name and display portrait.

    The current-location place name is resolved server-side and each
    character's display portrait (main first, then display order) is picked
    in the same query so the cast pane needs no second fetch per row.
    """
    dbname = resolve_dbname(slot)
    conditions = ["TRUE"]
    params: List[Any] = []
    if startId is not None:
        conditions.append("c.id >= %s")
        params.append(startId)
    if endId is not None:
        conditions.append("c.id <= %s")
        params.append(endId)
    rows = _fetch_all(
        dbname,
        f"""
        SELECT
            c.id,
            c.name,
            c.summary,
            c.appearance,
            c.background,
            c.personality,
            c.emotional_state,
            c.current_activity,
            c.current_location,
            c.extra_data,
            c.created_at,
            c.updated_at,
            p.name AS current_location_name,
            (
                SELECT ci.file_path
                FROM assets.character_images ci
                WHERE ci.character_id = c.id
                ORDER BY ci.is_main DESC, ci.display_order ASC
                LIMIT 1
            ) AS portrait_path
        FROM characters c
        LEFT JOIN places p ON p.id = c.current_location
        WHERE {' AND '.join(conditions)}
        ORDER BY c.id
        """,
        tuple(params),
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "appearance": row["appearance"],
            "background": row["background"],
            "personality": row["personality"],
            "emotionalState": row["emotional_state"],
            "currentActivity": row["current_activity"],
            # current_location is live bigint; the wire contract is a string
            # (legacy Drizzle typing) so the client compares against String(id).
            "currentLocation": (
                str(row["current_location"])
                if row["current_location"] is not None
                else None
            ),
            "extraData": row["extra_data"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "currentLocationName": row["current_location_name"],
            "portraitPath": row["portrait_path"],
        }
        for row in rows
    ]


@router.get("/api/characters/{character_id}/relationships")
async def get_character_relationships(
    character_id: int, slot: Optional[int] = None
) -> List[Dict[str, Any]]:
    """All relationship rows where the character appears on either side."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT character1_id, character2_id, relationship_type,
               emotional_valence, dynamic, recent_events, history,
               extra_data, created_at, updated_at
        FROM character_relationships
        WHERE character1_id = %s OR character2_id = %s
        """,
        (character_id, character_id),
    )
    return [
        {
            "character1Id": row["character1_id"],
            "character2Id": row["character2_id"],
            "relationshipType": row["relationship_type"],
            "emotionalValence": row["emotional_valence"],
            "dynamic": row["dynamic"],
            "recentEvents": row["recent_events"],
            "history": row["history"],
            "extraData": row["extra_data"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


@router.get("/api/characters/{character_id}/psychology")
async def get_character_psychology(
    character_id: int, slot: Optional[int] = None
) -> Dict[str, Any]:
    """Character psychology profile. 404 when absent."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT character_id, self_concept, behavior, cognitive_framework,
               temperament, relational_style, defense_mechanisms,
               character_arc, secrets, validation_evidence,
               created_at, updated_at
        FROM character_psychology
        WHERE character_id = %s
        LIMIT 1
        """,
        (character_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Character psychology not found")
    row = rows[0]
    return {
        "characterId": row["character_id"],
        "selfConcept": row["self_concept"],
        "behavior": row["behavior"],
        "cognitiveFramework": row["cognitive_framework"],
        "temperament": row["temperament"],
        "relationalStyle": row["relational_style"],
        "defenseMechanisms": row["defense_mechanisms"],
        "characterArc": row["character_arc"],
        "secrets": row["secrets"],
        "validationEvidence": row["validation_evidence"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Places, zones, factions
# ---------------------------------------------------------------------------


@router.get("/api/places")
async def get_places(slot: Optional[int] = None) -> List[Dict[str, Any]]:
    """All places, with coordinates extracted as GeoJSON from PostGIS."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT
            id,
            name,
            type::text AS type,
            zone,
            summary,
            inhabitants,
            history,
            current_status,
            secrets,
            extra_data,
            created_at,
            updated_at,
            ST_AsGeoJSON(coordinates)::json AS geometry
        FROM places
        ORDER BY id
        """,
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "zone": row["zone"],
            "summary": row["summary"],
            "inhabitants": row["inhabitants"],
            "history": row["history"],
            "currentStatus": row["current_status"],
            "secrets": row["secrets"],
            "extraData": row["extra_data"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "geometry": row["geometry"],
        }
        for row in rows
    ]


@router.get("/api/current-place")
async def get_current_place(slot: Optional[int] = None) -> Dict[str, Any]:
    """The narrative's current location (read-only).

    The 'setting' place reference on the most recent COMMITTED chunk that
    has one (committed = has a chunk_metadata row; without the join a
    draft/incubator chunk's setting would leak in). 404 when the story has
    no setting references yet.
    """
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT pcr.place_id, p.name, pcr.chunk_id
        FROM place_chunk_references pcr
        JOIN places p ON p.id = pcr.place_id
        JOIN chunk_metadata cm ON cm.chunk_id = pcr.chunk_id
        WHERE pcr.reference_type = 'setting'
        ORDER BY pcr.chunk_id DESC
        LIMIT 1
        """,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No current place recorded")
    row = rows[0]
    return {"placeId": row["place_id"], "name": row["name"], "chunkId": row["chunk_id"]}


@router.get("/api/zones")
async def get_zones(slot: Optional[int] = None) -> List[Dict[str, Any]]:
    """All zones, boundary served as GeoJSON (raw geometry is EWKB hex)."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT id, name, summary, ST_AsGeoJSON(boundary)::json AS boundary
        FROM zones
        ORDER BY id
        """,
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "boundary": row["boundary"],
        }
        for row in rows
    ]


@router.get("/api/factions")
async def get_factions(slot: Optional[int] = None) -> List[Dict[str, Any]]:
    """All factions (live schema: the Drizzle-era columns were dropped)."""
    dbname = resolve_dbname(slot)
    rows = _fetch_all(
        dbname,
        """
        SELECT id, name, summary, primary_location, extra_data,
               created_at, updated_at
        FROM factions
        ORDER BY id
        """,
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "primaryLocation": row["primary_location"],
            "extraData": row["extra_data"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]
