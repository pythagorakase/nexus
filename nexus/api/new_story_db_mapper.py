"""
Database mapping functions for new story initialization.

This module converts detailed Pydantic schemas from structured output
into the format expected by the database tables.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List
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

    def map_character_to_db(self, character: CharacterSheet) -> Dict[str, Any]:
        """
        Map CharacterSheet to characters table format.

        Database columns:
        - name, summary, appearance, background, personality (text fields)
        - extra_data (JSONB for everything else)

        Args:
            character: CharacterSheet from structured output

        Returns:
            Dictionary ready for database insertion
        """
        # Core fields that map to columns
        db_record = {
            "name": character.name,
            "summary": self._generate_character_summary(character),
            "appearance": character.appearance,
            "background": character.backstory,
            "personality": character.personality,
            "emotional_state": "calm",  # Default starting state
            "current_activity": "Beginning their journey",  # Will be updated by story
            # current_location will be set after place is created
        }

        # Everything else goes in extra_data
        extra_data = {
            "age": character.age,
            "gender": character.gender,
            "species": character.species,
            "occupation": character.occupation,
            "faction": character.faction,
            "height": character.height,
            "build": character.build,
            "distinguishing_features": character.distinguishing_features,
            "motivations": character.motivations,
            "fears": character.fears,
            "skills": character.skills,
            "weaknesses": character.weaknesses,
            "special_abilities": character.special_abilities,
            "family": character.family,
            "possessions": character.possessions,
            "wealth_level": character.wealth_level,
            "allies": character.allies or [],
            "enemies": character.enemies or [],
            "growth_areas": character.growth_areas,
            "background_type": character.background.value,
        }

        db_record["extra_data"] = extra_data

        return db_record

    def map_place_to_db(self, place: PlaceProfile, zone_id: Optional[int] = None) -> Dict[str, Any]:
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
        # Map our category to database place_type enum
        type_mapping = {
            "settlement": "fixed_location",
            "wilderness": "fixed_location",
            "dungeon": "fixed_location",
            "building": "fixed_location",
            "district": "fixed_location",
            "landmark": "fixed_location",
            "road": "fixed_location",  # Could be 'other'
            "border": "other",
        }
        db_type = type_mapping.get(place.category.value, "other")

        # Build inhabitants list (if population is set, include it)
        inhabitants = []
        if place.population:
            inhabitants.append(f"Population: {place.population}")
        if place.ruler:
            inhabitants.append(f"Ruled by: {place.ruler}")
        if place.factions:
            inhabitants.extend([f"Faction: {f}" for f in place.factions])

        # Build secrets/plot hooks
        secrets_parts = []
        if place.dangers:
            secrets_parts.append(f"Dangers: {', '.join(place.dangers)}")
        if place.rumors:
            secrets_parts.append(f"Rumors: {'; '.join(place.rumors)}")
        secrets = " | ".join(secrets_parts) if secrets_parts else "No known secrets"

        # Core fields
        db_record = {
            "name": place.name,
            "type": db_type,
            "zone": zone_id,  # Will be set after zone creation
            "summary": place.description,
            "inhabitants": inhabitants,
            "history": place.atmosphere,  # Using atmosphere as history for now
            "current_status": self._generate_place_status(place),
            "secrets": secrets,
        }

        # Additional data in extra_data
        extra_data = {
            "category": place.category.value,
            "size": place.size,
            "region": place.region,
            "nearby_landmarks": place.nearby_landmarks,
            "notable_features": place.notable_features,
            "resources": place.resources,
            "culture": place.culture,
            "economy": place.economy,
            "trade_goods": place.trade_goods,
            "current_events": place.current_events,
        }

        db_record["extra_data"] = extra_data

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

    def save_setting_to_globals(self, setting: SettingCard) -> None:
        """
        Save setting information to global_variables table.

        Args:
            setting: SettingCard to save

        Raises:
            Exception: If database operation fails
        """
        try:
            with get_connection(self.dbname) as conn:
                with conn.cursor() as cur:
                    # Store setting as JSONB in global_variables
                    setting_json = setting.model_dump()

                    cur.execute("""
                        INSERT INTO global_variables (key, value)
                        VALUES ('setting', %s::jsonb)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value
                    """, (setting_json,))

                    logger.info(f"Saved setting to global_variables: {setting.world_name}")
        except Exception as e:
            logger.error(f"Failed to save setting {setting.world_name}: {e}")
            raise

    def save_story_seed(self, seed: StorySeed) -> None:
        """
        Save chosen story seed to global_variables.

        Args:
            seed: Selected StorySeed

        Raises:
            Exception: If database operation fails
        """
        try:
            with get_connection(self.dbname) as conn:
                with conn.cursor() as cur:
                    seed_json = seed.model_dump()

                    cur.execute("""
                        INSERT INTO global_variables (key, value)
                        VALUES ('story_seed', %s::jsonb)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value
                    """, (seed_json,))

                    logger.info(f"Saved story seed: {seed.title}")
        except Exception as e:
            logger.error(f"Failed to save story seed {seed.title}: {e}")
            raise

    def create_protagonist(self, character: CharacterSheet) -> int:
        """
        Create the protagonist in the characters table.

        Args:
            character: CharacterSheet to insert

        Returns:
            The character ID

        Raises:
            Exception: If database operation fails (transaction will be rolled back)
        """
        db_record = self.map_character_to_db(character)

        with get_connection(self.dbname) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO characters (
                            name, summary, appearance, background, personality,
                            emotional_state, current_activity, extra_data
                        ) VALUES (
                            %(name)s, %(summary)s, %(appearance)s, %(background)s,
                            %(personality)s, %(emotional_state)s, %(current_activity)s,
                            %(extra_data)s::jsonb
                        )
                        RETURNING id
                    """, db_record)

                    character_id = cur.fetchone()[0]

                    # Update global_variables to point to this character
                    cur.execute("""
                        INSERT INTO global_variables (key, value)
                        VALUES ('user_character', %s)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value
                    """, (character_id,))

                logger.info(f"Created protagonist: {character.name} (ID: {character_id})")
                return character_id

            except Exception as e:
                logger.error(f"Failed to create protagonist {character.name}: {e}")
                raise

    def create_location_hierarchy(
        self,
        layer: LayerDefinition,
        zone: ZoneDefinition,
        place: PlaceProfile,
        character_id: int
    ) -> Dict[str, int]:
        """
        Create the complete location hierarchy: layer -> zone -> place.

        Args:
            layer: LayerDefinition to create
            zone: ZoneDefinition to create
            place: PlaceProfile to create
            character_id: Protagonist's ID to update location

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

        with get_connection(self.dbname) as conn:
            try:
                with conn.cursor() as cur:
                    # Verify character exists
                    cur.execute("SELECT id FROM characters WHERE id = %s", (character_id,))
                    if not cur.fetchone():
                        raise ValueError(f"Character ID {character_id} does not exist")

                    # First create the layer
                    layer_record = self.map_layer_to_db(layer)
                    cur.execute("""
                        INSERT INTO layers (name, type, description)
                        VALUES (%(name)s, %(type)s, %(description)s)
                        RETURNING id
                    """, layer_record)
                    layer_id = cur.fetchone()[0]
                    logger.debug(f"Created layer: {layer.name} (ID: {layer_id})")

                    # Then create the zone with layer reference
                    zone_record = self.map_zone_to_db(zone, layer_id)
                    cur.execute("""
                        INSERT INTO zones (name, summary, layer)
                        VALUES (%(name)s, %(summary)s, %(layer)s)
                        RETURNING id
                    """, zone_record)
                    zone_id = cur.fetchone()[0]
                    logger.debug(f"Created zone: {zone.name} (ID: {zone_id})")

                    # Finally create the place with zone reference and coordinates
                    place_record = self.map_place_to_db(place, zone_id)
                    cur.execute("""
                        INSERT INTO places (
                            name, type, zone, summary, inhabitants,
                            history, current_status, secrets, extra_data,
                            coordinates
                        ) VALUES (
                            %(name)s, %(type)s, %(zone)s, %(summary)s, %(inhabitants)s,
                            %(history)s, %(current_status)s, %(secrets)s, %(extra_data)s::jsonb,
                            ST_SetSRID(ST_MakePoint(%s, %s, 0, 0), 4326)::geography
                        )
                        RETURNING id
                    """, (*place_record.values(), lon, lat))  # Note: PostGIS takes (lon, lat) not (lat, lon)
                    place_id = cur.fetchone()[0]
                    logger.debug(f"Created place: {place.name} (ID: {place_id}) at ({lat}, {lon})")

                    # Update character's current location
                    cur.execute("""
                        UPDATE characters
                        SET current_location = %s
                        WHERE id = %s
                    """, (place_id, character_id))

                    # Generate a default circular boundary for the zone
                    # Using a 50-mile radius (approximately 80km) centered on the place
                    self._create_default_zone_boundary(cur, zone_id, place.coordinates)

                # Commit happens automatically when context manager exits
                logger.info(
                    f"Created location hierarchy: {layer.name} (ID: {layer_id}) "
                    f"-> {zone.name} (ID: {zone_id}) "
                    f"-> {place.name} (ID: {place_id})"
                )
                return {
                    "layer_id": layer_id,
                    "zone_id": zone_id,
                    "place_id": place_id
                }

            except Exception as e:
                # Rollback happens automatically when context manager exits with exception
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
        7. Sets new_story = false to transition to narrative mode
        8. Clears the cache

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

        logger.info(f"Starting transition for {transition_data.character.name} in {transition_data.setting.world_name}")

        try:
            # Save setting
            self.save_setting_to_globals(transition_data.setting)
            logger.debug("Saved setting to global_variables")

            # Save story seed
            self.save_story_seed(transition_data.seed)
            logger.debug("Saved story seed to global_variables")

            # Create protagonist
            character_id = self.create_protagonist(transition_data.character)
            logger.debug(f"Created protagonist with ID {character_id}")

            # Create complete location hierarchy
            location_ids = self.create_location_hierarchy(
                transition_data.layer,
                transition_data.zone,
                transition_data.location,
                character_id
            )
            logger.debug(f"Created location hierarchy: {location_ids}")

            # Set base timestamp and transition flag in a single transaction
            with get_connection(self.dbname) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO global_variables (key, value)
                        VALUES ('base_timestamp', %s)
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value
                    """, (transition_data.base_timestamp.isoformat(),))

                    # Finally, set new_story = false to transition to narrative mode
                    cur.execute("""
                        UPDATE global_variables
                        SET value = 'false'
                        WHERE key = 'new_story'
                    """)

            logger.info("Transition complete: new_story set to false")

            # Clear the cache (safe to do after successful transition)
            from nexus.api.new_story_cache import clear_new_story_cache
            clear_new_story_cache(self.dbname)
            logger.debug("Cleared new story cache")

            return {
                "character_id": character_id,
                "layer_id": location_ids["layer_id"],
                "zone_id": location_ids["zone_id"],
                "place_id": location_ids["place_id"]
            }

        except Exception as e:
            logger.error(
                f"Transition failed for {transition_data.character.name}: {e}. "
                f"All database changes have been rolled back."
            )
            raise

    def _generate_character_summary(self, character: CharacterSheet) -> str:
        """Generate a brief character summary."""
        return (
            f"{character.name} is a {character.age} year old {character.gender} {character.species} "
            f"with a {character.background.value} background, currently working as {character.occupation}. "
            f"{character.motivations[0] if character.motivations else 'Seeking their destiny'}."
        )

    def _create_default_zone_boundary(self, cursor, zone_id: int, coordinates: tuple[float, float]) -> None:
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

            cursor.execute("""
                UPDATE zones
                SET boundary = ST_Multi(
                    ST_Buffer(
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        80467  -- 50 miles in meters
                    )::geometry
                )
                WHERE id = %s
            """, (lon, lat, zone_id))  # Note: PostGIS takes (lon, lat)

            logger.info(f"Created default 50-mile radius boundary for zone {zone_id} centered at ({lat}, {lon})")
        except Exception as e:
            # Log but don't fail - boundary is optional
            logger.warning(f"Could not create default boundary for zone {zone_id}: {e}")

    def _generate_place_status(self, place: PlaceProfile) -> str:
        """Generate current status description for a place."""
        status_parts = []

        if place.current_events:
            status_parts.append(f"Current events: {'; '.join(place.current_events)}")

        if place.economy:
            status_parts.append(f"Economy based on {place.economy}")

        if place.trade_goods:
            status_parts.append(f"Trading in {', '.join(place.trade_goods[:3])}")

        return " | ".join(status_parts) if status_parts else "Normal operations"