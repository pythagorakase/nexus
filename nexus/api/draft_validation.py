"""Read-only deterministic validation shared by staging and acceptance."""

from typing import Any, Mapping

from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    NewEntityDeclaration,
    ReferencedEntities,
    StateUpdates,
)
from nexus.agents.orrery.declaration_validation import (
    collect_new_entity_declaration_vocabulary_issues,
)
from nexus.agents.orrery.tag_writer import _row_value, validate_tag_bestowal
from nexus.api.commit_handler_sync import (
    _require_state_update_id_sync,
    resolve_character_references_sync,
    resolve_faction_references_sync,
    resolve_place_references_sync,
    resolve_state_update_ids_sync,
)
from nexus.api.db_converters import chronology_to_db_values
from nexus.api.lore_adapter import validate_incubator_data
from nexus.config import load_settings


def validate_commit_draft_sync(conn: Any, data: Mapping[str, Any]) -> None:
    """Parse draft structures and resolve existing identities without writing.

    Same-turn declarations may resolve only after their stubs are created during
    acceptance. Validate those declarations now and repeat full resolution after
    creation. Explicit numeric identities always refer to existing entities.
    """
    validate_incubator_data(dict(data))
    parent = data["parent_chunk_id"]
    season, episode = 1, 1
    if parent:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT season, episode FROM chunk_metadata WHERE chunk_id = %s",
                (parent,),
            )
            metadata = cur.fetchone()
        if metadata is None:
            raise ValueError(f"No metadata found for parent chunk {parent}")
        season = _row_value(metadata, "season", 0)
        episode = _row_value(metadata, "episode", 1)
    chronology_to_db_values(
        ChronologyUpdate.model_validate(data["metadata_updates"].get("chronology", {})),
        current_season=season,
        current_episode=episode,
    )
    declarations = [
        NewEntityDeclaration.model_validate(item)
        for item in data.get("new_entities") or []
    ]
    with conn.cursor() as cur:
        issues = collect_new_entity_declaration_vocabulary_issues(cur, declarations)
    if issues:
        raise ValueError("Invalid staged declarations: " + "; ".join(issues))
    pending = {
        table: frozenset(item.name for item in declarations if item.kind == kind)
        for table, kind in (
            ("characters", "character"),
            ("places", "place"),
            ("factions", "faction"),
        )
    }
    if declarations:
        settings = load_settings().orrery
        if settings is None or not settings.retrograde.maturation.enabled:
            pending = {table: frozenset() for table in pending}
    refs = ReferencedEntities.model_validate(data["reference_updates"])
    for table, kind, references, resolver in (
        ("characters", "character", refs.characters, resolve_character_references_sync),
        ("places", "place", refs.places, resolve_place_references_sync),
        ("factions", "faction", refs.factions, resolve_faction_references_sync),
    ):
        existing = []
        for ref in references:
            identifier = getattr(ref, f"{kind}_id")
            name = getattr(ref, f"{kind}_name")
            resolved_id = _require_state_update_id_sync(
                conn,
                kind=kind,
                table=table,
                current_id=identifier,
                name=name,
                pending_names=pending[table],
            )
            if resolved_id is not None:
                existing.append(ref)
        resolver(existing, conn)
    states = StateUpdates.model_validate(data["entity_updates"])
    resolve_state_update_ids_sync(conn, states, pending_entities=pending)
    with conn.cursor() as cur:
        for kind, updates in (
            ("character", states.characters),
            ("place", states.locations),
            ("faction", states.factions),
        ):
            for update in updates:
                issues = validate_tag_bestowal(
                    cur, entity_kind=kind, bestowal=update.orrery_tags
                )
                if issues:
                    raise ValueError("Invalid staged state tags: " + "; ".join(issues))
    for character in states.characters:
        if character.current_location is not None:
            _require_state_update_id_sync(
                conn,
                kind="character location",
                table="places",
                current_id=character.current_location,
                name=None,
            )
