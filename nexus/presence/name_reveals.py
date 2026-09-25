"""Validate and atomically persist explicit same-person name revelations."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from nexus.agents.logon.apex_schema import (
    NewEntityDeclaration,
    ReferencedEntities,
    StateUpdates,
)
from nexus.agents.orrery.reconstruction import (
    log_state_delta_async,
    log_state_delta_sync,
)
from nexus.api.native_structured_output import WireContractViolation
from nexus.presence.roster import IdentityIndex, RosterEntry


class CharacterNameRevealConflict(WireContractViolation):
    """Reject an unsupported or conflicting identity ruling without retrying."""


@dataclass(frozen=True)
class NameReveal:
    """A validated rename of one existing identity, never a row merge."""

    target: RosterEntry
    new_name: str
    evidence: str


def project_name_reveals(
    declarations: Sequence[Mapping[str, Any]],
    index: IdentityIndex,
    *,
    narrative: str | None,
) -> tuple[IdentityIndex, list[NameReveal]]:
    """Return a read-only prospective catalog after validating explicit rulings."""
    from nexus.presence.identity import generated_aliases, resolve_character_declaration

    projected = copy(index)
    projected.by_id = dict(index.by_id)
    projected.by_name = {key: set(value) for key, value in index.by_name.items()}
    projected.labels = list(index.labels)
    projected.evidence = dict(index.evidence)
    reveals = []
    seen = set()
    for raw in declarations:
        if raw.get("same_as") is None:
            continue
        declaration = NewEntityDeclaration.model_validate(raw)
        ruling = declaration.same_as
        assert ruling is not None
        key = ("character", ruling.character_id)
        target = projected.by_id.get(key)
        if target is None or target.name != ruling.previous_name:
            raise CharacterNameRevealConflict(
                "Name reveal must name an existing character ID and its exact "
                f"current canonical name: {ruling.character_id}, "
                f"{ruling.previous_name!r}"
            )
        if key in seen:
            raise CharacterNameRevealConflict("Multiple name reveals target one person")
        if (
            not narrative
            or ruling.evidence not in narrative
            or declaration.name not in ruling.evidence
        ):
            raise CharacterNameRevealConflict(
                "Name reveal evidence must quote the finished narrative and include "
                "the revealed name; choices and private letters are not evidence"
            )
        if declaration.name == target.name:
            raise CharacterNameRevealConflict("Name reveal must change the name")
        resolution = resolve_character_declaration(
            {"kind": "character", "name": declaration.name}, projected
        )
        other_keys = {candidate.key for candidate in resolution.candidates} - {key}
        if other_keys or (
            resolution.existing_id is not None and resolution.existing_id != target.id
        ):
            raise CharacterNameRevealConflict(
                f"Revealed name {declaration.name!r} collides with another identity"
            )
        seen.add(key)
        reveals.append(NameReveal(target, declaration.name, ruling.evidence))
        projected.by_id[key] = target.model_copy(update={"name": declaration.name})
        projected.labels.append(("character", declaration.name, key))
        projected.by_name.setdefault(
            ("character", declaration.name.casefold()), set()
        ).add(key)
    revealed_ids = {reveal.target.id for reveal in reveals}
    for character_id, alias in generated_aliases(projected) if reveals else []:
        if character_id in revealed_ids:
            key = ("character", character_id)
            projected.labels.append(("character", alias, key))
            projected.by_name.setdefault(("character", alias.casefold()), set()).add(
                key
            )
    return projected, reveals


def ordinary_declarations(
    declarations: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Exclude name revelations from stub creation and backstory maturation."""
    return [
        declaration for declaration in declarations if not declaration.get("same_as")
    ]


def bind_staged_name_reveal_identities(
    data: Mapping[str, Any], index: IdentityIndex
) -> dict[str, Any]:
    """Validate and bind only staged identities affected by a name revelation.

    This read-only projection precedes both draft resolution and acceptance.
    Supplied IDs must agree with a unique old/new name or alias; ID-only
    references remain valid. Unrelated identities retain their existing rules.
    The returned draft is private to the accepting transaction, never a rewrite
    of the persisted incubator or any existing story record.
    """
    declarations = data.get("new_entities") or []
    result = dict(data)
    if not any(item.get("same_as") is not None for item in declarations):
        return result
    projected, reveals = project_name_reveals(
        declarations, index, narrative=data.get("storyteller_text")
    )
    revealed_ids = {reveal.target.id for reveal in reveals}

    def bind(reference: Any, id_field: str, name_field: str, path: str) -> None:
        identifier = getattr(reference, id_field)
        name = getattr(reference, name_field)
        keys = projected.matching_keys(name, "character") if name is not None else set()
        names_reveal = any(key[1] in revealed_ids for key in keys)
        if identifier not in revealed_ids and not names_reveal:
            return
        if name is None and identifier in revealed_ids:
            return
        if len(keys) != 1:
            raise CharacterNameRevealConflict(
                f"{path}: name-reveal reference has an unresolved or ambiguous name"
            )
        key = next(iter(keys))
        if key[1] not in revealed_ids or (
            identifier is not None and identifier != key[1]
        ):
            raise CharacterNameRevealConflict(
                f"{path}: supplied ID conflicts with the name-reveal identity"
            )
        setattr(reference, id_field, key[1])

    references = ReferencedEntities.model_validate(data["reference_updates"])
    states = StateUpdates.model_validate(data["entity_updates"])
    for collection in ("characters", "departures"):
        for ordinal, reference in enumerate(getattr(references, collection)):
            bind(
                reference,
                "character_id",
                "character_name",
                f"reference_updates.{collection}[{ordinal}]",
            )
    for ordinal, update in enumerate(states.characters):
        bind(
            update,
            "character_id",
            "character_name",
            f"entity_updates.characters[{ordinal}]",
        )
    for ordinal, relationship in enumerate(states.relationships):
        for endpoint in (1, 2):
            bind(
                relationship,
                f"character{endpoint}_id",
                f"character{endpoint}_name",
                f"entity_updates.relationships[{ordinal}].character{endpoint}",
            )
    result["reference_updates"] = references.model_dump(mode="json")
    result["entity_updates"] = states.model_dump(mode="json")
    return result


def apply_name_reveals(
    conn: Any,
    declarations: Sequence[Mapping[str, Any]],
    *,
    narrative: str,
    chunk_id: int,
    generation_session_id: str,
) -> None:
    """Rename under the identity lock inside the caller's acceptance transaction."""
    from nexus.presence.identity import read_identity_index, refresh_generated_aliases

    if not any(declaration.get("same_as") for declaration in declarations):
        return
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(current_database()), "
            "hashtext('character-identity'))"
        )
        _, reveals = project_name_reveals(
            declarations, read_identity_index(conn), narrative=narrative
        )
        for reveal in reveals:
            cur.execute(
                "UPDATE characters SET name = %s WHERE id = %s AND name = %s "
                "RETURNING entity_id",
                (reveal.new_name, reveal.target.id, reveal.target.name),
            )
            row = cur.fetchone()
            if row is None:
                raise CharacterNameRevealConflict("Name changed during acceptance")
            entity_id = row[0]
            cur.execute(
                "INSERT INTO character_aliases (character_id, alias, provenance) "
                "VALUES (%s, %s, 'authored') ON CONFLICT (character_id, alias) "
                "DO UPDATE SET provenance = 'authored'",
                (reveal.target.id, reveal.target.name),
            )
            cur.execute(
                "INSERT INTO character_identity_rulings "
                "(source_chunk_id, character_id, entity_id, decision, previous_name, "
                "new_name, evidence, generation_session_id) "
                "VALUES (%s, %s, %s, 'same_as', %s, %s, %s, %s)",
                (
                    chunk_id,
                    reveal.target.id,
                    entity_id,
                    reveal.target.name,
                    reveal.new_name,
                    reveal.evidence,
                    generation_session_id,
                ),
            )
            log_state_delta_sync(
                cur,
                source_chunk_id=chunk_id,
                writer="skald_state_update",
                entity_id=entity_id,
                field="characters.name",
                old_value=reveal.target.name,
                new_value=reveal.new_name,
            )
        refresh_generated_aliases(cur)


async def apply_name_reveals_async(
    conn: Any,
    declarations: Sequence[Mapping[str, Any]],
    *,
    narrative: str,
    chunk_id: int,
    generation_session_id: str,
) -> None:
    """Apply the identical rename and audit contract through async acceptance."""
    from nexus.presence.identity import (
        read_identity_index_async,
        refresh_generated_aliases_async,
    )

    if not any(declaration.get("same_as") for declaration in declarations):
        return
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtext(current_database()), "
        "hashtext('character-identity'))"
    )
    _, reveals = project_name_reveals(
        declarations, await read_identity_index_async(conn), narrative=narrative
    )
    for reveal in reveals:
        entity_id = await conn.fetchval(
            "UPDATE characters SET name = $1 WHERE id = $2 AND name = $3 "
            "RETURNING entity_id",
            reveal.new_name,
            reveal.target.id,
            reveal.target.name,
        )
        if entity_id is None:
            raise CharacterNameRevealConflict("Name changed during acceptance")
        await conn.execute(
            "INSERT INTO character_aliases (character_id, alias, provenance) "
            "VALUES ($1, $2, 'authored') ON CONFLICT (character_id, alias) "
            "DO UPDATE SET provenance = 'authored'",
            reveal.target.id,
            reveal.target.name,
        )
        await conn.execute(
            "INSERT INTO character_identity_rulings "
            "(source_chunk_id, character_id, entity_id, decision, previous_name, "
            "new_name, evidence, generation_session_id) "
            "VALUES ($1, $2, $3, 'same_as', $4, $5, $6, $7)",
            chunk_id,
            reveal.target.id,
            entity_id,
            reveal.target.name,
            reveal.new_name,
            reveal.evidence,
            generation_session_id,
        )
        await log_state_delta_async(
            conn,
            source_chunk_id=chunk_id,
            writer="skald_state_update",
            entity_id=entity_id,
            field="characters.name",
            old_value=reveal.target.name,
            new_value=reveal.new_name,
        )
    await refresh_generated_aliases_async(conn)
