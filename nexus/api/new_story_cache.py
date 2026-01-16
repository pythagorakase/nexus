"""
Helpers for persisting new-story setup state in assets.new_story_creator.

The normalized schema stores wizard state in typed columns rather than JSONB blobs.
Phase completion is determined by:
- Setting complete: setting_genre IS NOT NULL
- Character complete: 4 traits selected in assets.traits (3 + wildcard with rationale)
- Seed complete: seed_type IS NOT NULL
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.new_story_cache")

# Valid trait enum values (must match PostgreSQL trait enum)
VALID_TRAITS = frozenset({
    'allies', 'contacts', 'patron', 'dependents', 'status',
    'reputation', 'resources', 'domain', 'enemies', 'obligations'
})


def _parse_pg_array(value: Any) -> List[str]:
    """Parse PostgreSQL array literal to Python list.

    psycopg2's RealDictCursor doesn't auto-convert array columns.
    PostgreSQL returns arrays as strings like '{foo,bar}'.

    Always returns a list (empty if null) for UI compatibility.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value  # Already a list
    if isinstance(value, str):
        # Parse PostgreSQL array format: {elem1,elem2,...}
        if value.startswith('{') and value.endswith('}'):
            inner = value[1:-1]
            if not inner:
                return []
            return inner.split(',')
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SettingData:
    """Setting phase data (normalized columns)."""
    genre: Optional[str] = None
    secondary_genres: List[str] = field(default_factory=list)  # Always array for UI
    world_name: Optional[str] = None
    time_period: Optional[str] = None
    tech_level: Optional[str] = None
    magic_exists: Optional[bool] = None
    magic_description: Optional[str] = None
    political_structure: Optional[str] = None
    major_conflict: Optional[str] = None
    tone: Optional[str] = None
    themes: List[str] = field(default_factory=list)  # Always array for UI
    cultural_notes: Optional[str] = None
    language_notes: Optional[str] = None
    geographic_scope: Optional[str] = None
    diegetic_artifact: Optional[str] = None


@dataclass
class SuggestedTrait:
    """A single LLM-suggested trait with rationale."""
    trait: str
    rationale: str


@dataclass
class CharacterData:
    """Character phase data.

    Concept data is in new_story_creator columns.
    Trait data is now in assets.traits table.
    """
    # Concept subphase (from new_story_creator)
    name: Optional[str] = None
    archetype: Optional[str] = None
    background: Optional[str] = None
    appearance: Optional[str] = None
    # Ephemeral suggestions (from assets.traits where is_selected=TRUE)
    suggested_traits: List[SuggestedTrait] = field(default_factory=list)
    # Trait selection status (derived from assets.traits)
    selected_trait_count: int = 0
    # Explicit confirmation flag (from new_story_creator.traits_confirmed)
    traits_confirmed: bool = False
    # Wildcard status (derived from assets.traits id=11)
    wildcard_name: Optional[str] = None  # from traits.name where id=11
    wildcard_rationale: Optional[str] = None  # from traits.rationale where id=11

    def has_concept(self) -> bool:
        """Check if concept subphase is complete."""
        return self.name is not None

    def has_traits(self) -> bool:
        """Check if trait selection subphase is complete (user confirmed with 3 selected)."""
        return self.traits_confirmed

    def has_wildcard(self) -> bool:
        """Check if wildcard subphase is complete (rationale is set)."""
        return self.wildcard_rationale is not None

    def is_complete(self) -> bool:
        """Check if all character subphases are complete."""
        return self.has_concept() and self.has_traits() and self.has_wildcard()


@dataclass
class SeedData:
    """Seed phase data (normalized columns)."""
    # StorySeed
    seed_type: Optional[str] = None
    title: Optional[str] = None
    situation: Optional[str] = None
    hook: Optional[str] = None
    immediate_goal: Optional[str] = None
    stakes: Optional[str] = None
    tension_source: Optional[str] = None
    starting_location: Optional[str] = None
    weather: Optional[str] = None
    key_npcs: Optional[List[str]] = None
    initial_mystery: Optional[str] = None
    potential_allies: Optional[List[str]] = None
    potential_obstacles: Optional[List[str]] = None
    secrets: Optional[str] = None
    # Layer
    layer_name: Optional[str] = None
    layer_type: Optional[str] = None
    layer_description: Optional[str] = None
    # Zone
    zone_name: Optional[str] = None
    zone_summary: Optional[str] = None
    zone_boundary_description: Optional[str] = None
    zone_approximate_area: Optional[str] = None
    # PlaceProfile (complex - kept as dict)
    initial_location: Optional[Dict[str, Any]] = None


@dataclass
class WizardCache:
    """Complete wizard cache state."""
    thread_id: Optional[str] = None
    target_slot: Optional[int] = None
    setting: SettingData = field(default_factory=SettingData)
    character: CharacterData = field(default_factory=CharacterData)
    seed: SeedData = field(default_factory=SeedData)
    base_timestamp: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def setting_complete(self) -> bool:
        """Check if setting phase is complete."""
        return self.setting.genre is not None

    def character_complete(self) -> bool:
        """Check if character phase is complete."""
        return self.character.is_complete()

    def seed_complete(self) -> bool:
        """Check if seed phase is complete."""
        return self.seed.seed_type is not None

    def current_phase(self) -> str:
        """Infer current phase from data presence."""
        if not self.setting_complete():
            return "setting"
        elif not self.character_complete():
            return "character"
        elif not self.seed_complete():
            return "seed"
        else:
            return "ready"

    # ═══════════════════════════════════════════════════════════════
    # BACKWARDS COMPATIBILITY HELPERS
    # ═══════════════════════════════════════════════════════════════
    # These reconstruct the old JSONB dict format for code that
    # still expects it (e.g., transition endpoint)

    def get_setting_dict(self) -> Optional[Dict[str, Any]]:
        """Reconstruct setting_draft dict from normalized columns."""
        if not self.setting_complete():
            return None
        return {
            "genre": self.setting.genre,
            "secondary_genres": self.setting.secondary_genres or [],
            "world_name": self.setting.world_name,
            "time_period": self.setting.time_period,
            "tech_level": self.setting.tech_level,
            "magic_exists": self.setting.magic_exists or False,
            "magic_description": self.setting.magic_description,
            "political_structure": self.setting.political_structure,
            "major_conflict": self.setting.major_conflict,
            "tone": self.setting.tone or "balanced",
            "themes": self.setting.themes or [],
            "cultural_notes": self.setting.cultural_notes,
            "language_notes": self.setting.language_notes,
            "geographic_scope": self.setting.geographic_scope or "regional",
            "diegetic_artifact": self.setting.diegetic_artifact,
        }

    def get_character_dict(self) -> Optional[Dict[str, Any]]:
        """Reconstruct character_draft dict from normalized columns + assets.traits."""
        if not self.character_complete():
            return None

        # Build trait data from suggested_traits (which are the selected ones)
        selected = [st.trait for st in self.character.suggested_traits]
        rationales = {st.trait: st.rationale for st in self.character.suggested_traits}

        return {
            "concept": {
                "name": self.character.name,
                "archetype": self.character.archetype,
                "background": self.character.background,
                "appearance": self.character.appearance,
                "suggested_traits": selected,
                "trait_rationales": rationales,
            },
            "trait_selection": {
                "selected_traits": selected,
                "trait_rationales": rationales,
            },
            "wildcard": {
                "wildcard_name": self.character.wildcard_name,
                "wildcard_description": self.character.wildcard_rationale,
            },
        }

    def get_seed_dict(self) -> Optional[Dict[str, Any]]:
        """Reconstruct selected_seed dict from normalized columns.

        Note: base_timestamp is included from cache-level storage since
        StorySeed schema expects it as part of seed data. Defaults to
        current UTC time if not set.
        """
        if not self.seed_complete():
            return None
        # Build base_timestamp dict for StoryTimestamp schema
        ts = self.base_timestamp or datetime.now(timezone.utc)
        base_timestamp_dict = {
            "year": ts.year,
            "month": ts.month,
            "day": ts.day,
            "hour": ts.hour,
            "minute": ts.minute,
        }
        return {
            "seed_type": self.seed.seed_type,
            "title": self.seed.title,
            "situation": self.seed.situation,
            "hook": self.seed.hook,
            "immediate_goal": self.seed.immediate_goal,
            "stakes": self.seed.stakes,
            "tension_source": self.seed.tension_source,
            "starting_location": self.seed.starting_location,
            "base_timestamp": base_timestamp_dict,
            "weather": self.seed.weather,
            "key_npcs": self.seed.key_npcs or [],
            "initial_mystery": self.seed.initial_mystery,
            "potential_allies": self.seed.potential_allies or [],
            "potential_obstacles": self.seed.potential_obstacles or [],
            "secrets": self.seed.secrets,
        }

    def get_layer_dict(self) -> Optional[Dict[str, Any]]:
        """Reconstruct layer_draft dict from normalized columns."""
        if not self.seed.layer_name:
            return None
        return {
            "name": self.seed.layer_name,
            "type": self.seed.layer_type,
            "description": self.seed.layer_description,
        }

    def get_zone_dict(self) -> Optional[Dict[str, Any]]:
        """Reconstruct zone_draft dict from normalized columns."""
        if not self.seed.zone_name:
            return None
        return {
            "name": self.seed.zone_name,
            "summary": self.seed.zone_summary,
            "boundary_description": self.seed.zone_boundary_description,
            "approximate_area": self.seed.zone_approximate_area,
        }

    def get_initial_location(self) -> Optional[Dict[str, Any]]:
        """Get initial_location JSONB (still stored as-is)."""
        return self.seed.initial_location


# ═══════════════════════════════════════════════════════════════════════════════
# READ FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def read_cache(dbname: Optional[str] = None) -> Optional[WizardCache]:
    """
    Read the current new-story setup cache.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)

    Returns:
        WizardCache containing all cached state, or None if no cache exists
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM assets.new_story_creator WHERE id = TRUE")
            row = cur.fetchone()
            if row is None:
                return None

            # Load trait data from assets.traits
            cur.execute(
                """
                SELECT id, name, rationale, is_selected
                FROM assets.traits
                ORDER BY id
                """
            )
            traits_rows = cur.fetchall()

            # Build trait info for CharacterData
            selected_traits = [
                SuggestedTrait(trait=r["name"], rationale=r["rationale"] or "")
                for r in traits_rows
                if r["is_selected"] and r["id"] <= 10
            ]
            selected_count = len(selected_traits)
            wildcard_row = next((r for r in traits_rows if r["id"] == 11), None)

            return _row_to_cache(
                dict(row),
                selected_traits,
                selected_count,
                row.get("traits_confirmed", False),
                wildcard_row,
            )


def read_cache_raw(dbname: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read the cache as a raw dictionary (for backwards compatibility).

    Args:
        dbname: Optional database name

    Returns:
        Dictionary containing cache data, or None if no cache exists
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM assets.new_story_creator WHERE id = TRUE")
            row = cur.fetchone()
            return dict(row) if row else None


def _row_to_cache(
    row: Dict[str, Any],
    selected_traits: Optional[List[SuggestedTrait]] = None,
    selected_trait_count: int = 0,
    traits_confirmed: bool = False,
    wildcard_row: Optional[Dict[str, Any]] = None,
) -> WizardCache:
    """Convert a database row to a WizardCache object."""
    return WizardCache(
        thread_id=row.get("thread_id"),
        target_slot=row.get("target_slot"),
        setting=SettingData(
            genre=row.get("setting_genre"),
            secondary_genres=_parse_pg_array(row.get("setting_secondary_genres")),
            world_name=row.get("setting_world_name"),
            time_period=row.get("setting_time_period"),
            tech_level=row.get("setting_tech_level"),
            magic_exists=row.get("setting_magic_exists"),
            magic_description=row.get("setting_magic_description"),
            political_structure=row.get("setting_political_structure"),
            major_conflict=row.get("setting_major_conflict"),
            tone=row.get("setting_tone"),
            themes=_parse_pg_array(row.get("setting_themes")),
            cultural_notes=row.get("setting_cultural_notes"),
            language_notes=row.get("setting_language_notes"),
            geographic_scope=row.get("setting_geographic_scope"),
            diegetic_artifact=row.get("setting_diegetic_artifact"),
        ),
        character=CharacterData(
            name=row.get("character_name"),
            archetype=row.get("character_archetype"),
            background=row.get("character_background"),
            appearance=row.get("character_appearance"),
            suggested_traits=selected_traits or [],
            selected_trait_count=selected_trait_count,
            traits_confirmed=traits_confirmed,
            wildcard_name=wildcard_row.get("name") if wildcard_row else None,
            wildcard_rationale=wildcard_row.get("rationale") if wildcard_row else None,
        ),
        seed=SeedData(
            seed_type=row.get("seed_type"),
            title=row.get("seed_title"),
            situation=row.get("seed_situation"),
            hook=row.get("seed_hook"),
            immediate_goal=row.get("seed_immediate_goal"),
            stakes=row.get("seed_stakes"),
            tension_source=row.get("seed_tension_source"),
            starting_location=row.get("seed_starting_location"),
            weather=row.get("seed_weather"),
            key_npcs=_parse_pg_array(row.get("seed_key_npcs")),
            initial_mystery=row.get("seed_initial_mystery"),
            potential_allies=_parse_pg_array(row.get("seed_potential_allies")),
            potential_obstacles=_parse_pg_array(row.get("seed_potential_obstacles")),
            secrets=row.get("seed_secrets"),
            layer_name=row.get("layer_name"),
            layer_type=row.get("layer_type"),
            layer_description=row.get("layer_description"),
            zone_name=row.get("zone_name"),
            zone_summary=row.get("zone_summary"),
            zone_boundary_description=row.get("zone_boundary_description"),
            zone_approximate_area=row.get("zone_approximate_area"),
            initial_location=row.get("initial_location"),
        ),
        base_timestamp=row.get("base_timestamp"),
        updated_at=row.get("updated_at"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WRITE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def write_setting(
    dbname: Optional[str],
    *,
    genre: str,
    world_name: str,
    time_period: str,
    tech_level: str,
    political_structure: str,
    major_conflict: str,
    themes: List[str],
    cultural_notes: str,
    diegetic_artifact: str,
    secondary_genres: Optional[List[str]] = None,
    magic_exists: bool = False,
    magic_description: Optional[str] = None,
    tone: str = "balanced",
    language_notes: Optional[str] = None,
    geographic_scope: str = "regional",
) -> None:
    """Write setting phase data to cache."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    setting_genre = %s,
                    setting_secondary_genres = %s,
                    setting_world_name = %s,
                    setting_time_period = %s,
                    setting_tech_level = %s,
                    setting_magic_exists = %s,
                    setting_magic_description = %s,
                    setting_political_structure = %s,
                    setting_major_conflict = %s,
                    setting_tone = %s,
                    setting_themes = %s,
                    setting_cultural_notes = %s,
                    setting_language_notes = %s,
                    setting_geographic_scope = %s,
                    setting_diegetic_artifact = %s,
                    updated_at = NOW()
                WHERE id = TRUE
                """,
                (
                    genre,
                    secondary_genres,
                    world_name,
                    time_period,
                    tech_level,
                    magic_exists,
                    magic_description,
                    political_structure,
                    major_conflict,
                    tone,
                    themes,
                    cultural_notes,
                    language_notes,
                    geographic_scope,
                    diegetic_artifact,
                ),
            )
    logger.info("Updated setting data in %s", dbname or os.environ.get("PGDATABASE"))


def write_character_concept(
    dbname: Optional[str],
    *,
    name: str,
    archetype: str,
    background: str,
    appearance: str,
) -> None:
    """Write character concept (subphase 1) to cache."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    character_name = %s,
                    character_archetype = %s,
                    character_background = %s,
                    character_appearance = %s,
                    updated_at = NOW()
                WHERE id = TRUE
                """,
                (name, archetype, background, appearance),
            )
    logger.info("Updated character concept in %s", dbname or os.environ.get("PGDATABASE"))


def toggle_trait(dbname: Optional[str], trait_name: str) -> bool:
    """Toggle a trait's is_selected state. Returns new state."""
    if trait_name not in VALID_TRAITS:
        raise ValueError(f"Invalid trait: {trait_name}. Must be one of {sorted(VALID_TRAITS)}")

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.traits
                SET is_selected = NOT is_selected
                WHERE name = %s
                RETURNING is_selected
                """,
                (trait_name,),
            )
            result = cur.fetchone()
            new_state = result[0] if result else False
    logger.info("Toggled trait %s to %s in %s", trait_name, new_state, dbname)
    return new_state


def confirm_trait_selection(dbname: Optional[str]) -> List[str]:
    """Confirm trait selection: validate exactly 3 optional traits selected, set confirmation flag.

    Returns list of selected trait names.
    Raises ValueError if not exactly 3 traits selected.
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            # Get selected optional traits (id 1-10, not wildcard)
            cur.execute(
                "SELECT name FROM assets.traits WHERE is_selected = TRUE AND id <= 10"
            )
            selected = [row[0] for row in cur.fetchall()]

            if len(selected) != 3:
                raise ValueError(
                    f"Must have exactly 3 traits selected. Currently: {len(selected)}"
                )

            # Clear rationales for non-selected traits
            cur.execute(
                "UPDATE assets.traits SET rationale = NULL WHERE is_selected = FALSE AND id <= 10"
            )

            # Set confirmation flag in cache
            cur.execute(
                "UPDATE assets.new_story_creator SET traits_confirmed = TRUE WHERE id = TRUE"
            )
    logger.info("Confirmed trait selection in %s: %s", dbname, selected)
    return selected


@dataclass
class TraitMenuItem:
    """A trait for the selection menu."""
    id: int
    name: str
    description: List[str]  # Bullet points
    is_selected: bool
    rationale: Optional[str]


def get_trait_menu(dbname: Optional[str]) -> List[TraitMenuItem]:
    """
    Get all 10 optional traits for the selection menu.

    Returns traits with their definitions, selection state, and rationales.
    Used for rendering the interactive trait selection UI.
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, is_selected, rationale
                FROM assets.traits
                WHERE id <= 10
                ORDER BY id
                """
            )
            rows = cur.fetchall()
            return [
                TraitMenuItem(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"] or [],
                    is_selected=row["is_selected"],
                    rationale=row["rationale"],
                )
                for row in rows
            ]


def get_selected_trait_count(dbname: Optional[str]) -> int:
    """Get count of selected optional traits (not including wildcard)."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM assets.traits WHERE is_selected = TRUE AND id <= 10"
            )
            return cur.fetchone()[0]


def write_character_wildcard(
    dbname: Optional[str],
    *,
    wildcard_name: str,
    wildcard_description: str,
) -> None:
    """Write character wildcard (subphase 3) to assets.traits row 11."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.traits SET
                    name = %s,
                    rationale = %s
                WHERE id = 11
                """,
                (wildcard_name, wildcard_description),
            )
    logger.info("Updated character wildcard in %s", dbname or os.environ.get("PGDATABASE"))


def write_suggested_traits(
    dbname: Optional[str],
    suggestions: List[Dict[str, str]],
) -> None:
    """
    Write LLM-suggested traits to assets.traits (select them and set rationales).

    Args:
        dbname: Database name
        suggestions: List of dicts with 'trait' and 'rationale' keys (max 3)
    """
    if len(suggestions) > 3:
        raise ValueError("Cannot store more than 3 suggested traits")

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            # First deselect all optional traits (not wildcard)
            cur.execute(
                "UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10"
            )

            # Select and set rationale for each suggested trait
            for suggestion in suggestions:
                cur.execute(
                    """
                    UPDATE assets.traits
                    SET is_selected = TRUE, rationale = %s
                    WHERE name = %s
                    """,
                    (suggestion["rationale"], suggestion["trait"]),
                )
    logger.info(
        "Wrote %d suggested traits to %s",
        len(suggestions),
        dbname or os.environ.get("PGDATABASE"),
    )


def clear_suggested_traits(dbname: Optional[str] = None) -> None:
    """Clear trait selections (deselect all optional traits, clear rationales)."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10"
            )
    logger.info("Cleared trait selections in %s", dbname or os.environ.get("PGDATABASE"))


def write_seed(
    dbname: Optional[str],
    *,
    # StorySeed
    seed_type: str,
    title: str,
    situation: str,
    hook: str,
    immediate_goal: str,
    stakes: str,
    tension_source: str,
    starting_location: str,
    secrets: str,
    weather: Optional[str] = None,
    key_npcs: Optional[List[str]] = None,
    initial_mystery: Optional[str] = None,
    potential_allies: Optional[List[str]] = None,
    potential_obstacles: Optional[List[str]] = None,
    # Layer
    layer_name: str,
    layer_type: str,
    layer_description: str,
    # Zone
    zone_name: str,
    zone_summary: str,
    zone_boundary_description: Optional[str] = None,
    zone_approximate_area: Optional[str] = None,
    # PlaceProfile
    initial_location: Optional[Dict[str, Any]] = None,
    # Timestamp
    base_timestamp: Optional[datetime] = None,
) -> None:
    """Write seed phase data to cache."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    seed_type = %s,
                    seed_title = %s,
                    seed_situation = %s,
                    seed_hook = %s,
                    seed_immediate_goal = %s,
                    seed_stakes = %s,
                    seed_tension_source = %s,
                    seed_starting_location = %s,
                    seed_weather = %s,
                    seed_key_npcs = %s,
                    seed_initial_mystery = %s,
                    seed_potential_allies = %s,
                    seed_potential_obstacles = %s,
                    seed_secrets = %s,
                    layer_name = %s,
                    layer_type = %s,
                    layer_description = %s,
                    zone_name = %s,
                    zone_summary = %s,
                    zone_boundary_description = %s,
                    zone_approximate_area = %s,
                    initial_location = %s,
                    base_timestamp = %s,
                    updated_at = NOW()
                WHERE id = TRUE
                """,
                (
                    seed_type,
                    title,
                    situation,
                    hook,
                    immediate_goal,
                    stakes,
                    tension_source,
                    starting_location,
                    weather,
                    key_npcs,
                    initial_mystery,
                    potential_allies,
                    potential_obstacles,
                    secrets,
                    layer_name,
                    layer_type,
                    layer_description,
                    zone_name,
                    zone_summary,
                    zone_boundary_description,
                    zone_approximate_area,
                    json.dumps(initial_location) if initial_location else None,
                    base_timestamp,
                ),
            )
    logger.info("Updated seed data in %s", dbname or os.environ.get("PGDATABASE"))


def init_cache(
    dbname: Optional[str],
    thread_id: str,
    target_slot: int,
) -> None:
    """
    Initialize cache with thread_id and target slot.
    Creates the singleton row if it doesn't exist.
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets.new_story_creator (id, thread_id, target_slot)
                VALUES (TRUE, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    target_slot = EXCLUDED.target_slot,
                    updated_at = NOW()
                """,
                (thread_id, target_slot),
            )
    logger.info("Initialized cache for slot %s in %s", target_slot, dbname or os.environ.get("PGDATABASE"))


def clear_cache(dbname: Optional[str] = None) -> None:
    """
    Clear the new-story setup cache.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
            # Reset traits: deselect optional traits, clear rationales, reset wildcard name
            cur.execute(
                "UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10"
            )
            cur.execute(
                "UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11"
            )
    logger.info("Cleared new_story_creator cache in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))


def clear_seed_phase(dbname: Optional[str] = None) -> None:
    """Clear seed phase columns to revert from ready to seed phase."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    seed_type = NULL,
                    seed_title = NULL,
                    seed_situation = NULL,
                    seed_hook = NULL,
                    seed_immediate_goal = NULL,
                    seed_stakes = NULL,
                    seed_tension_source = NULL,
                    seed_starting_location = NULL,
                    seed_weather = NULL,
                    seed_key_npcs = NULL,
                    seed_initial_mystery = NULL,
                    seed_potential_allies = NULL,
                    seed_potential_obstacles = NULL,
                    seed_secrets = NULL,
                    layer_name = NULL,
                    layer_type = NULL,
                    layer_description = NULL,
                    zone_name = NULL,
                    zone_summary = NULL,
                    zone_boundary_description = NULL,
                    zone_approximate_area = NULL,
                    initial_location = NULL,
                    base_timestamp = NULL,
                    updated_at = NOW()
                WHERE id = TRUE
                """
            )
    logger.info("Cleared seed phase in %s", dbname or os.environ.get("PGDATABASE"))


def clear_character_phase(dbname: Optional[str] = None) -> None:
    """Clear character and seed phase columns to revert to character phase."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            # Clear character concept columns
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    -- Character columns
                    character_name = NULL,
                    character_archetype = NULL,
                    character_background = NULL,
                    character_appearance = NULL,
                    -- Seed columns (also clear downstream)
                    seed_type = NULL,
                    seed_title = NULL,
                    seed_situation = NULL,
                    seed_hook = NULL,
                    seed_immediate_goal = NULL,
                    seed_stakes = NULL,
                    seed_tension_source = NULL,
                    seed_starting_location = NULL,
                    seed_weather = NULL,
                    seed_key_npcs = NULL,
                    seed_initial_mystery = NULL,
                    seed_potential_allies = NULL,
                    seed_potential_obstacles = NULL,
                    seed_secrets = NULL,
                    layer_name = NULL,
                    layer_type = NULL,
                    layer_description = NULL,
                    zone_name = NULL,
                    zone_summary = NULL,
                    zone_boundary_description = NULL,
                    zone_approximate_area = NULL,
                    initial_location = NULL,
                    base_timestamp = NULL,
                    updated_at = NOW()
                WHERE id = TRUE
                """
            )
            # Reset traits: deselect all (except wildcard), clear rationales, reset wildcard name
            cur.execute(
                """
                UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10;
                UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11;
                """
            )
    logger.info("Cleared character phase in %s", dbname or os.environ.get("PGDATABASE"))


def clear_setting_phase(dbname: Optional[str] = None) -> None:
    """Clear all phase columns to revert to setting phase."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.new_story_creator SET
                    -- Setting columns
                    setting_genre = NULL,
                    setting_secondary_genres = NULL,
                    setting_world_name = NULL,
                    setting_time_period = NULL,
                    setting_tech_level = NULL,
                    setting_magic_exists = NULL,
                    setting_magic_description = NULL,
                    setting_political_structure = NULL,
                    setting_major_conflict = NULL,
                    setting_tone = NULL,
                    setting_themes = NULL,
                    setting_cultural_notes = NULL,
                    setting_language_notes = NULL,
                    setting_geographic_scope = NULL,
                    setting_diegetic_artifact = NULL,
                    -- Character columns
                    character_name = NULL,
                    character_archetype = NULL,
                    character_background = NULL,
                    character_appearance = NULL,
                    -- Seed columns
                    seed_type = NULL,
                    seed_title = NULL,
                    seed_situation = NULL,
                    seed_hook = NULL,
                    seed_immediate_goal = NULL,
                    seed_stakes = NULL,
                    seed_tension_source = NULL,
                    seed_starting_location = NULL,
                    seed_weather = NULL,
                    seed_key_npcs = NULL,
                    seed_initial_mystery = NULL,
                    seed_potential_allies = NULL,
                    seed_potential_obstacles = NULL,
                    seed_secrets = NULL,
                    layer_name = NULL,
                    layer_type = NULL,
                    layer_description = NULL,
                    zone_name = NULL,
                    zone_summary = NULL,
                    zone_boundary_description = NULL,
                    zone_approximate_area = NULL,
                    initial_location = NULL,
                    base_timestamp = NULL,
                    updated_at = NOW()
                WHERE id = TRUE
                """
            )
            # Reset traits to defaults
            cur.execute(
                """
                UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10;
                UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11;
                """
            )
    logger.info("Cleared setting phase in %s", dbname or os.environ.get("PGDATABASE"))


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════════
# These functions maintain backwards compatibility during transition


def write_cache(
    thread_id: Optional[str] = None,
    setting_draft: Optional[Dict[str, Any]] = None,
    character_draft: Optional[Dict[str, Any]] = None,
    selected_seed: Optional[Dict[str, Any]] = None,
    layer_draft: Optional[Dict[str, Any]] = None,
    zone_draft: Optional[Dict[str, Any]] = None,
    initial_location: Optional[Dict[str, Any]] = None,
    base_timestamp: Optional[str] = None,
    target_slot: Optional[int] = None,
    dbname: Optional[str] = None,
) -> None:
    """
    Legacy write function - converts JSONB format to normalized columns.

    DEPRECATED: Use the typed write_* functions instead.
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            # Build the update dynamically based on what's provided
            updates = ["updated_at = NOW()"]
            params = []

            if thread_id is not None:
                updates.append("thread_id = %s")
                params.append(thread_id)

            if target_slot is not None:
                updates.append("target_slot = %s")
                params.append(target_slot)

            if setting_draft is not None:
                # Map old JSONB to new columns
                # Enum columns need explicit casting
                updates.extend([
                    "setting_genre = %s::genre",
                    "setting_secondary_genres = %s::genre[]",
                    "setting_world_name = %s",
                    "setting_time_period = %s",
                    "setting_tech_level = %s::tech_level",
                    "setting_magic_exists = %s",
                    "setting_magic_description = %s",
                    "setting_political_structure = %s",
                    "setting_major_conflict = %s",
                    "setting_tone = %s::tone",
                    "setting_themes = %s",
                    "setting_cultural_notes = %s",
                    "setting_language_notes = %s",
                    "setting_geographic_scope = %s::geographic_scope",
                    "setting_diegetic_artifact = %s",
                ])
                params.extend([
                    setting_draft.get("genre"),
                    setting_draft.get("secondary_genres"),
                    setting_draft.get("world_name"),
                    setting_draft.get("time_period"),
                    setting_draft.get("tech_level"),
                    setting_draft.get("magic_exists"),
                    setting_draft.get("magic_description"),
                    setting_draft.get("political_structure"),
                    setting_draft.get("major_conflict"),
                    setting_draft.get("tone"),
                    setting_draft.get("themes"),
                    setting_draft.get("cultural_notes"),
                    setting_draft.get("language_notes"),
                    setting_draft.get("geographic_scope"),
                    setting_draft.get("diegetic_artifact"),
                ])

            if character_draft is not None:
                # Character draft contains nested subphase data
                concept = character_draft.get("concept", {})
                traits = character_draft.get("trait_selection", {})
                wildcard = character_draft.get("wildcard", {})

                if concept:
                    updates.extend([
                        "character_name = %s",
                        "character_archetype = %s",
                        "character_background = %s",
                        "character_appearance = %s",
                    ])
                    params.extend([
                        concept.get("name"),
                        concept.get("archetype"),
                        concept.get("background"),
                        concept.get("appearance"),
                    ])

                # Traits are written to assets.traits table (using the existing cursor)
                if traits:
                    selected = traits.get("selected_traits", [])
                    rationales = traits.get("trait_rationales", {})
                    if len(selected) == 3:
                        # Clear previous selections, then set new ones
                        cur.execute(
                            "UPDATE assets.traits SET is_selected = FALSE, rationale = NULL WHERE id <= 10"
                        )
                        for trait_name in selected:
                            rationale = rationales.get(trait_name, "")
                            cur.execute(
                                """
                                UPDATE assets.traits
                                SET is_selected = TRUE, rationale = %s
                                WHERE name = %s
                                """,
                                (rationale, trait_name),
                            )
                        logger.info("Wrote 3 selected traits to assets.traits in %s", dbname)

                if wildcard:
                    write_character_wildcard(
                        dbname,
                        wildcard_name=wildcard.get("wildcard_name", "wildcard"),
                        wildcard_description=wildcard.get("wildcard_description", ""),
                    )

            if selected_seed is not None:
                updates.extend([
                    "seed_type = %s::seed_type",
                    "seed_title = %s",
                    "seed_situation = %s",
                    "seed_hook = %s",
                    "seed_immediate_goal = %s",
                    "seed_stakes = %s",
                    "seed_tension_source = %s",
                    "seed_starting_location = %s",
                    "seed_weather = %s",
                    "seed_key_npcs = %s",
                    "seed_initial_mystery = %s",
                    "seed_potential_allies = %s",
                    "seed_potential_obstacles = %s",
                    "seed_secrets = %s",
                ])
                params.extend([
                    selected_seed.get("seed_type"),
                    selected_seed.get("title"),
                    selected_seed.get("situation"),
                    selected_seed.get("hook"),
                    selected_seed.get("immediate_goal"),
                    selected_seed.get("stakes"),
                    selected_seed.get("tension_source"),
                    selected_seed.get("starting_location"),
                    selected_seed.get("weather"),
                    selected_seed.get("key_npcs"),
                    selected_seed.get("initial_mystery"),
                    selected_seed.get("potential_allies"),
                    selected_seed.get("potential_obstacles"),
                    selected_seed.get("secrets"),
                ])

            if layer_draft is not None:
                updates.extend([
                    "layer_name = %s",
                    "layer_type = %s::layer_type",
                    "layer_description = %s",
                ])
                params.extend([
                    layer_draft.get("name"),
                    layer_draft.get("type"),
                    layer_draft.get("description"),
                ])

            if zone_draft is not None:
                updates.extend([
                    "zone_name = %s",
                    "zone_summary = %s",
                    "zone_boundary_description = %s",
                    "zone_approximate_area = %s",
                ])
                params.extend([
                    zone_draft.get("name"),
                    zone_draft.get("summary"),
                    zone_draft.get("boundary_description"),
                    zone_draft.get("approximate_area"),
                ])

            if initial_location is not None:
                updates.append("initial_location = %s")
                params.append(json.dumps(initial_location))

            if base_timestamp is not None:
                updates.append("base_timestamp = %s")
                params.append(base_timestamp)

            # First ensure the row exists
            cur.execute(
                """
                INSERT INTO assets.new_story_creator (id)
                VALUES (TRUE)
                ON CONFLICT (id) DO NOTHING
                """
            )

            # Then update
            if updates:
                sql = f"UPDATE assets.new_story_creator SET {', '.join(updates)} WHERE id = TRUE"
                cur.execute(sql, params)

    logger.info("Updated new_story_creator cache in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))
