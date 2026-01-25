"""
Database mapping functions for new story initialization.

This module converts detailed Pydantic schemas from structured output
into the format expected by the database tables.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

from nexus.api.new_story_schemas import (
    CharacterSheet,
    PlaceProfile,
    ZoneDefinition,
    LayerDefinition,
    SpecificLocation,
    SettingCard,
    StorySeed,
    TransitionData,
)
from nexus.api.db_pool import get_connection
from nexus.api.new_story_cache import clear_cache

logger = logging.getLogger("nexus.api.new_story_db_mapper")


class NewStoryDatabaseMapper:
    """
    Maps structured output schemas to database table formats.

    The database uses a hybrid approach where core fields are columns
    and detailed attributes are stored in extra_data JSONB.
    """

    def __init__(self, dbname: str = "save_01"):
        """
        Initialize the mapper.

        Args:
            dbname: Target database name (save_01 through save_05)
        """
        self.dbname = dbname

    def map_character_to_db(
        self,
        character: CharacterSheet,
        emotional_state: Optional[str] = None,
        current_activity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Map CharacterSheet to characters table format.

        Database columns:
        - name, summary, appearance, background, personality (text fields)
        - emotional_state, current_activity (from story seed context)
        - current_location (set after place is created)
        - extra_data (JSONB for everything else)

        Args:
            character: CharacterSheet from structured output
            emotional_state: Initial emotional state (from seed stakes/tension)
            current_activity: What character is doing (from seed immediate_goal)

        Returns:
            Dictionary ready for database insertion
        """
        # Core fields that map directly to columns
        db_record: Dict[str, Any] = {
            "name": character.name,
            "summary": character.summary,
            "appearance": character.appearance,
            "background": character.background,
            "personality": character.personality,
            "emotional_state": emotional_state,
            "current_activity": current_activity,
            # current_location will be set after place is created
        }

        # Build extra_data from Mind's Eye Theatre traits
        extra_data = self._build_character_extra_data(character)
        db_record["extra_data"] = json.dumps(extra_data)

        return db_record

    def map_place_to_db(
        self, place: PlaceProfile, zone_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Map PlaceProfile to places table format.

        Database columns:
        - name, type (enum), zone (FK), summary, inhabitants, history, current_status, secrets
        - extra_data (JSONB for additional attributes)

        Args:
            place: PlaceProfile from structured output
            zone_id: Optional zone ID if already created

        Returns:
            Dictionary ready for database insertion
        """
        # Core fields map directly to columns
        db_record: Dict[str, Any] = {
            "name": place.name,
            "type": place.place_type,  # Already matches database enum
            "zone": zone_id,  # Will be set after zone creation
            "summary": place.summary,
            "inhabitants": place.inhabitants or [],
            "history": place.history,
            "current_status": place.current_status,
            "secrets": place.secrets,
        }

        extra_payload = {}
        if place.extra_data:
            extra_payload = place.extra_data.model_dump(exclude_none=True)
            extra_payload = {
                key: value
                for key, value in extra_payload.items()
                if value not in (None, "", [])
            }
        db_record["extra_data"] = json.dumps(extra_payload) if extra_payload else None

        return db_record

    def map_layer_to_db(self, layer: LayerDefinition) -> Dict[str, Any]:
        """
        Map LayerDefinition to layers table format.

        Database columns match exactly: name, type, description

        Args:
            layer: LayerDefinition from structured output

        Returns:
            Dictionary ready for database insertion
        """
        return {
            "name": layer.name,
            "type": layer.type.value,  # Convert enum to string
            "description": layer.description,
        }

    def map_zone_to_db(self, zone: ZoneDefinition, layer_id: int) -> Dict[str, Any]:
        """
        Map ZoneDefinition to zones table format.

        Database columns:
        - name, summary, layer (FK)
        - boundary (PostGIS polygon, not set during creation)

        Args:
            zone: ZoneDefinition from structured output
            layer_id: ID of the parent layer

        Returns:
            Dictionary ready for database insertion
        """
        return {
            "name": zone.name,
            "summary": zone.summary,
            "layer": layer_id,
            # boundary will be NULL initially (can be set later with PostGIS)
        }

    def save_setting_to_globals(self, setting: SettingCard, cursor=None) -> None:
        """
        Save setting information to global_variables table.

        Args:
            setting: SettingCard to save
            cursor: Optional database cursor for transactional operations

        Raises:
            Exception: If database operation fails
        """
        setting_json = json.dumps(setting.model_dump())

        if cursor:
            # Use provided cursor (part of larger transaction)
            try:
                cursor.execute(
                    "UPDATE global_variables SET setting = %s::jsonb WHERE id = true",
                    (setting_json,),
                )
                logger.info(f"Saved setting to global_variables: {setting.world_name}")
            except Exception as e:
                logger.error(f"Failed to save setting {setting.world_name}: {e}")
                raise
        else:
            # Standalone operation - create own connection
            try:
                with get_connection(self.dbname) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE global_variables SET setting = %s::jsonb WHERE id = true",
                            (setting_json,),
                        )
                        logger.info(
                            f"Saved setting to global_variables: {setting.world_name}"
                        )
            except Exception as e:
                logger.error(f"Failed to save setting {setting.world_name}: {e}")
                raise

    def save_story_seed(self, seed: StorySeed, cursor=None) -> None:
        """
        Save chosen story seed to global_variables by merging into setting JSONB.

        The story_seed contains AI-to-AI secrets channel data that should persist.

        Args:
            seed: Selected StorySeed
            cursor: Optional database cursor for transactional operations

        Raises:
            Exception: If database operation fails
        """
        seed_data = seed.model_dump()

        if cursor:
            # Use provided cursor (part of larger transaction)
            try:
                # Read existing setting, merge story_seed, save back
                cursor.execute("SELECT setting FROM global_variables WHERE id = true")
                row = cursor.fetchone()
                setting = row[0] if row and row[0] else {}
                setting["story_seed"] = seed_data
                cursor.execute(
                    "UPDATE global_variables SET setting = %s::jsonb WHERE id = true",
                    (json.dumps(setting),),
                )
                logger.info(f"Saved story seed to setting: {seed.title}")
            except Exception as e:
                logger.error(f"Failed to save story seed {seed.title}: {e}")
                raise
        else:
            # Standalone operation - create own connection
            try:
                with get_connection(self.dbname) as conn:
                    with conn.cursor() as cur:
                        # Read existing setting, merge story_seed, save back
                        cur.execute("SELECT setting FROM global_variables WHERE id = true")
                        row = cur.fetchone()
                        setting = row[0] if row and row[0] else {}
                        setting["story_seed"] = seed_data
                        cur.execute(
                            "UPDATE global_variables SET setting = %s::jsonb WHERE id = true",
                            (json.dumps(setting),),
                        )
                        logger.info(f"Saved story seed to setting: {seed.title}")
            except Exception as e:
                logger.error(f"Failed to save story seed {seed.title}: {e}")
                raise

    def create_protagonist(
        self,
        character: CharacterSheet,
        cursor=None,
        emotional_state: Optional[str] = None,
        current_activity: Optional[str] = None,
    ) -> int:
        """
        Create the protagonist in the characters table.

        Args:
            character: CharacterSheet to insert
            cursor: Optional database cursor for transactional operations
            emotional_state: Initial emotional state (from seed stakes/tension)
            current_activity: What character is doing (from seed immediate_goal)

        Returns:
            The character ID

        Raises:
            Exception: If database operation fails (transaction will be rolled back)
        """
        db_record = self.map_character_to_db(
            character,
            emotional_state=emotional_state,
            current_activity=current_activity,
        )

        if cursor:
            # Use provided cursor (part of larger transaction)
            try:
                cursor.execute(
                    """
                    INSERT INTO characters (
                        name, summary, appearance, background, personality,
                        emotional_state, current_activity, extra_data
                    ) VALUES (
                        %(name)s, %(summary)s, %(appearance)s, %(background)s,
                        %(personality)s, %(emotional_state)s, %(current_activity)s,
                        %(extra_data)s::jsonb
                    )
                    RETURNING id
                """,
                    db_record,
                )

                character_id = cursor.fetchone()[0]

                # Update global_variables to point to this character
                cursor.execute(
                    "UPDATE global_variables SET user_character = %s WHERE id = true",
                    (character_id,),
                )

                logger.info(
                    f"Created protagonist: {character.name} (ID: {character_id})"
                )
                return character_id

            except Exception as e:
                logger.error(f"Failed to create protagonist {character.name}: {e}")
                raise
        else:
            # Standalone operation - create own connection
            with get_connection(self.dbname) as conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO characters (
                                name, summary, appearance, background, personality,
                                emotional_state, current_activity, extra_data
                            ) VALUES (
                                %(name)s, %(summary)s, %(appearance)s, %(background)s,
                                %(personality)s, %(emotional_state)s, %(current_activity)s,
                                %(extra_data)s::jsonb
                            )
                            RETURNING id
                        """,
                            db_record,
                        )

                        character_id = cur.fetchone()[0]

                        # Update global_variables to point to this character
                        cur.execute(
                            "UPDATE global_variables SET user_character = %s WHERE id = true",
                            (character_id,),
                        )

                    logger.info(
                        f"Created protagonist: {character.name} (ID: {character_id})"
                    )
                    return character_id

                except Exception as e:
                    logger.error(f"Failed to create protagonist {character.name}: {e}")
                    raise

    def create_location_hierarchy(
        self,
        layer: LayerDefinition,
        zone: ZoneDefinition,
        place: PlaceProfile,
        character_id: int,
        cursor=None,
    ) -> Dict[str, int]:
        """
        Create the complete location hierarchy: layer -> zone -> place.

        Args:
            layer: LayerDefinition to create
            zone: ZoneDefinition to create
            place: PlaceProfile to create
            character_id: Protagonist's ID to update location
            cursor: Optional database cursor for transactional operations

        Returns:
            Dictionary with layer_id, zone_id, and place_id

        Raises:
            ValueError: If coordinates are invalid or character doesn't exist
            Exception: If database operation fails (transaction will be rolled back)
        """
        # Validate coordinates before attempting database operations
        lat, lon = place.coordinates[0], place.coordinates[1]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(
                f"Invalid coordinates: ({lat}, {lon}). "
                f"Latitude must be -90 to 90, longitude must be -180 to 180."
            )

        def _execute_hierarchy(cur):
            """Internal helper to execute hierarchy creation with given cursor"""
            # Verify character exists
            cur.execute("SELECT id FROM characters WHERE id = %s", (character_id,))
            if not cur.fetchone():
                raise ValueError(f"Character ID {character_id} does not exist")

            # First create the layer
            layer_record = self.map_layer_to_db(layer)
            cur.execute(
                """
                INSERT INTO layers (name, type, description)
                VALUES (%(name)s, %(type)s, %(description)s)
                RETURNING id
            """,
                layer_record,
            )
            layer_id = cur.fetchone()[0]
            logger.debug(f"Created layer: {layer.name} (ID: {layer_id})")

            # Then create the zone with layer reference
            zone_record = self.map_zone_to_db(zone, layer_id)
            cur.execute(
                """
                INSERT INTO zones (name, summary, layer)
                VALUES (%(name)s, %(summary)s, %(layer)s)
                RETURNING id
            """,
                zone_record,
            )
            zone_id = cur.fetchone()[0]
            logger.debug(f"Created zone: {zone.name} (ID: {zone_id})")

            # Finally create the place with zone reference and coordinates
            place_record = self.map_place_to_db(place, zone_id)

            # Add coordinates to the record for named parameter binding
            place_record["lon"] = lon
            place_record["lat"] = lat

            cur.execute(
                """
                INSERT INTO places (
                    name, type, zone, summary, inhabitants,
                    history, current_status, secrets, extra_data,
                    coordinates
                ) VALUES (
                    %(name)s, %(type)s, %(zone)s, %(summary)s, %(inhabitants)s,
                    %(history)s, %(current_status)s, %(secrets)s, %(extra_data)s::jsonb,
                    ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s, 0, 0), 4326)::geography
                )
                RETURNING id
            """,
                place_record,
            )  # Note: PostGIS takes (lon, lat) not (lat, lon)
            place_id = cur.fetchone()[0]
            logger.debug(
                f"Created place: {place.name} (ID: {place_id}) at ({lat}, {lon})"
            )

            # Update character's current location
            cur.execute(
                """
                UPDATE characters
                SET current_location = %s
                WHERE id = %s
            """,
                (place_id, character_id),
            )

            # Generate a default circular boundary for the zone
            # Using a 50-mile radius (approximately 80km) centered on the place
            self._create_default_zone_boundary(cur, zone_id, place.coordinates)

            logger.info(
                f"Created location hierarchy: {layer.name} (ID: {layer_id}) "
                f"-> {zone.name} (ID: {zone_id}) "
                f"-> {place.name} (ID: {place_id})"
            )
            return {"layer_id": layer_id, "zone_id": zone_id, "place_id": place_id}

        if cursor:
            # Use provided cursor (part of larger transaction)
            try:
                return _execute_hierarchy(cursor)
            except Exception as e:
                logger.error(
                    f"Failed to create location hierarchy for {layer.name}: {e}. "
                    f"Transaction will be rolled back."
                )
                raise
        else:
            # Standalone operation - create own connection
            with get_connection(self.dbname) as conn:
                try:
                    with conn.cursor() as cur:
                        return _execute_hierarchy(cur)
                except Exception as e:
                    logger.error(
                        f"Failed to create location hierarchy for {layer.name}: {e}. "
                        f"Transaction rolled back."
                    )
                    raise

    def perform_transition(self, transition_data: TransitionData) -> Dict[str, int]:
        """
        Perform complete transition from setup to narrative mode.

        This is an atomic operation - either all steps succeed or all are rolled back.

        Steps:
        1. Validates transition data completeness
        2. Saves setting to global_variables
        3. Saves story seed to global_variables
        4. Creates protagonist character
        5. Creates complete location hierarchy (layer -> zone -> place)
        6. Sets base timestamp
        7. Clears the wizard cache (mode is derived from data presence)

        Args:
            transition_data: Complete transition data package

        Returns:
            Dictionary with created IDs

        Raises:
            ValueError: If transition data is incomplete
            Exception: If any step fails (all changes will be rolled back)
        """
        # Validate before attempting any database operations
        if not transition_data.validate_completeness():
            missing_fields = []
            if not transition_data.setting:
                missing_fields.append("setting")
            if not transition_data.character:
                missing_fields.append("character")
            if not transition_data.seed:
                missing_fields.append("seed")
            if not transition_data.layer:
                missing_fields.append("layer")
            if not transition_data.zone:
                missing_fields.append("zone")
            if not transition_data.location:
                missing_fields.append("location")

            raise ValueError(
                f"Transition data is incomplete. Missing: {', '.join(missing_fields)}"
            )

        logger.info(
            f"Starting atomic transition for {transition_data.character.name} in {transition_data.setting.world_name}"
        )

        # ATOMIC OPERATION: All database operations in ONE transaction
        with get_connection(self.dbname) as conn:
            try:
                with conn.cursor() as cur:
                    # Ensure global_variables row exists (may have been deleted by previous CASCADE)
                    cur.execute("""
                        INSERT INTO global_variables (id, new_story)
                        VALUES (true, true)
                        ON CONFLICT (id) DO NOTHING
                    """)

                    # Clean slate: DELETE all entity data and reset sequences
                    # NOTE: Can't use TRUNCATE because global_variables has FK to characters,
                    # and PostgreSQL blocks TRUNCATE on tables with inbound FK references.
                    # DELETE respects ON DELETE SET NULL and works with FK constraints.
                    cur.execute(
                        "UPDATE global_variables SET user_character = NULL WHERE id = true"
                    )

                    # Delete in reverse dependency order (children before parents)
                    cur.execute("""
                        DELETE FROM chunk_character_references;
                        DELETE FROM chunk_faction_references;
                        DELETE FROM place_chunk_references;
                        DELETE FROM character_aliases;
                        DELETE FROM character_psychology;
                        DELETE FROM character_relationships;
                        DELETE FROM faction_relationships;
                        DELETE FROM faction_character_relationships;
                        DELETE FROM items;
                        DELETE FROM factions;
                        DELETE FROM characters;
                        DELETE FROM places;
                        DELETE FROM zones;
                        DELETE FROM layers;
                    """)

                    # Reset identity sequences so protagonist gets ID=1
                    cur.execute("""
                        ALTER SEQUENCE characters_id_seq RESTART WITH 1;
                        ALTER SEQUENCE places_id_seq RESTART WITH 1;
                        ALTER SEQUENCE zones_id_seq RESTART WITH 1;
                        ALTER SEQUENCE layers_id_seq RESTART WITH 1;
                        ALTER SEQUENCE items_id_seq RESTART WITH 1;
                        ALTER SEQUENCE character_relationships_id_seq RESTART WITH 1;
                    """)
                    logger.info("Truncated entity tables for clean slate")

                    # Save setting (using shared cursor)
                    self.save_setting_to_globals(transition_data.setting, cursor=cur)
                    logger.debug("Saved setting to global_variables")

                    # Save story seed (using shared cursor)
                    self.save_story_seed(transition_data.seed, cursor=cur)
                    logger.debug("Saved story seed to global_variables")

                    # Derive character's initial state from seed context
                    # - current_activity: What they're trying to do (immediate goal)
                    # - emotional_state: How they feel given the stakes/tension
                    seed = transition_data.seed
                    initial_activity = seed.immediate_goal
                    initial_emotional_state = (
                        f"Facing {seed.tension_source.lower()}; {seed.stakes.lower()}"
                    )

                    # Create protagonist (using shared cursor)
                    character_id = self.create_protagonist(
                        transition_data.character,
                        cursor=cur,
                        emotional_state=initial_emotional_state,
                        current_activity=initial_activity,
                    )
                    logger.debug(f"Created protagonist with ID {character_id}")

                    # Create complete location hierarchy (using shared cursor)
                    location_ids = self.create_location_hierarchy(
                        transition_data.layer,
                        transition_data.zone,
                        transition_data.location,
                        character_id,
                        cursor=cur,
                    )
                    logger.debug(f"Created location hierarchy: {location_ids}")

                    # Set base timestamp (already a datetime from TransitionData)
                    cur.execute(
                        "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                        (transition_data.base_timestamp,),
                    )

                # Transaction commits automatically on successful context exit
                logger.info("Atomic transition complete")

                # Clear the wizard cache - this is what transitions to narrative mode
                # (mode is derived from data presence, not a flag)
                clear_cache(self.dbname)
                logger.debug("Cleared wizard cache, slot now in narrative mode")

                return {
                    "character_id": character_id,
                    "layer_id": location_ids["layer_id"],
                    "zone_id": location_ids["zone_id"],
                    "place_id": location_ids["place_id"],
                }

            except Exception as e:
                # Transaction rolls back automatically on exception
                logger.error(
                    f"Atomic transition failed for {transition_data.character.name}: {e}. "
                    f"All database changes rolled back (no partial data)."
                )
                raise

    def _build_character_extra_data(self, character: CharacterSheet) -> Dict[str, Any]:
        """
        Build extra_data JSONB from CharacterSheet traits.

        The Mind's Eye Theatre system uses 10 menu traits (exactly 3 selected)
        plus a required wildcard trait. All traits are stored in the extra_data
        JSONB column rather than as separate database columns.

        Args:
            character: CharacterSheet with trait selections

        Returns:
            Dictionary ready for JSONB storage
        """
        extra_data: Dict[str, Any] = {}

        # Collect selected traits (exactly 3 entries)
        for trait in character.get_trait_entries():
            extra_data[trait.name] = trait.description

        # Add required wildcard trait
        extra_data["wildcard"] = {
            "name": character.wildcard_name,
            "description": character.wildcard_description,
        }

        return extra_data

    def _create_default_zone_boundary(
        self, cursor: Any, zone_id: int, coordinates: Tuple[float, float]
    ) -> None:
        """
        Create a default circular boundary for a zone.

        Creates a 50-mile radius circle as a MultiPolygon centered on the place coordinates.

        Args:
            cursor: Database cursor
            zone_id: ID of the zone to update
            coordinates: (lat, lon) tuple for the center point
        """
        try:
            lat, lon = coordinates
            # Create a 50-mile (approximately 80.47 km) radius circle
            # PostGIS ST_Buffer with geography type handles the spherical calculations

            cursor.execute(
                """
                UPDATE zones
                SET boundary = ST_Multi(
                    ST_Buffer(
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        80467  -- 50 miles in meters
                    )::geometry
                )
                WHERE id = %s
            """,
                (lon, lat, zone_id),
            )  # Note: PostGIS takes (lon, lat)

            logger.info(
                f"Created default 50-mile radius boundary for zone {zone_id} centered at ({lat}, {lon})"
            )
        except Exception as e:
            # Log but don't fail - boundary is optional
            logger.warning(f"Could not create default boundary for zone {zone_id}: {e}")
