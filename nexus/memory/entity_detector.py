"""High-specificity entity detector using database lookups.

This module provides entity detection with extremely high specificity by matching
only against known entities from the database. No regex patterns, no guessing,
just exact matches against characters (including aliases), places, and factions.
"""

import logging
import re
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EntityMatch:
    """Results from entity detection."""

    characters: List[Dict[str, Any]]  # List of matched character records
    places: List[Dict[str, Any]]  # List of matched place records
    factions: List[Dict[str, Any]]  # List of matched faction records

    @property
    def detected(self) -> bool:
        """Check if any entities were detected."""
        return bool(self.characters or self.places or self.factions)

    @property
    def all_entities(self) -> List[Dict[str, Any]]:
        """Get all detected entities in a single list."""
        all_entities = []
        for char in self.characters:
            all_entities.append({"type": "character", **char})
        for place in self.places:
            all_entities.append({"type": "place", **place})
        for faction in self.factions:
            all_entities.append({"type": "faction", **faction})
        return all_entities


class HighSpecificityEntityDetector:
    """Detect known entities with extremely high specificity using database lookups.

    This detector ONLY matches entities that exist in the database:
    - Characters (including all their aliases)
    - Places
    - Factions

    No regex patterns, no common word matching, no false positives.
    """

    def __init__(self, db_connection=None):
        """Initialize the entity detector.

        Args:
            db_connection: Database connection or session object
        """
        self.db = db_connection

        # These will be populated from database
        self.character_lookup = {}  # lowercase name/alias -> character record
        self.place_lookup = {}  # lowercase name -> place record
        self.faction_lookup = {}  # lowercase name -> faction record

        # Load entities from database
        if self.db:
            self._load_entities()

    def _load_entities(self) -> None:
        """Load all entities from database for matching."""
        try:
            # Load characters and their aliases
            self._load_characters()

            # Load places
            self._load_places()

            # Load factions
            self._load_factions()

            logger.info(
                "Loaded entities for high-specificity detection: "
                "%d characters/aliases, %d places, %d factions",
                len(self.character_lookup),
                len(self.place_lookup),
                len(self.faction_lookup)
            )

        except Exception as e:
            logger.error("Failed to load entities from database: %s", e)
            # Continue with empty lookups - detector will simply find nothing

    def _load_characters(self) -> None:
        """Load characters and their aliases from database."""
        try:
            # First load all characters
            result = self.db.execute(
                "SELECT id, name, summary FROM characters WHERE name IS NOT NULL"
            )
            characters = {}
            for row in result:
                char_record = {
                    "id": row.id,
                    "name": row.name,
                    "summary": row.summary[:100] if row.summary else None
                }
                characters[row.id] = char_record
                # Add primary name to lookup (case-insensitive)
                self.character_lookup[row.name.lower()] = char_record

            # Now load all aliases
            result = self.db.execute(
                "SELECT character_id, alias FROM character_aliases"
            )
            for row in result:
                if row.character_id in characters:
                    # Add alias to lookup (case-insensitive)
                    self.character_lookup[row.alias.lower()] = characters[row.character_id]

            logger.debug("Loaded %d characters with aliases", len(characters))

        except Exception as e:
            logger.error("Failed to load characters: %s", e)

    def _load_places(self) -> None:
        """Load places from database."""
        try:
            result = self.db.execute(
                "SELECT id, name, type, zone FROM places WHERE name IS NOT NULL"
            )
            for row in result:
                place_record = {
                    "id": row.id,
                    "name": row.name,
                    "type": row.type,
                    "zone": row.zone
                }
                # Add to lookup (case-insensitive)
                self.place_lookup[row.name.lower()] = place_record

                # Also add version with "the" prefix if not already present
                if not row.name.lower().startswith("the "):
                    self.place_lookup[f"the {row.name.lower()}"] = place_record

            logger.debug("Loaded %d places", len(self.place_lookup))

        except Exception as e:
            logger.error("Failed to load places: %s", e)

    def _load_factions(self) -> None:
        """Load factions from database."""
        try:
            result = self.db.execute(
                "SELECT id, name, ideology FROM factions WHERE name IS NOT NULL"
            )
            for row in result:
                faction_record = {
                    "id": row.id,
                    "name": row.name,
                    "ideology": row.ideology
                }
                # Add to lookup (case-insensitive)
                self.faction_lookup[row.name.lower()] = faction_record

            logger.debug("Loaded %d factions", len(self.faction_lookup))

        except Exception as e:
            logger.error("Failed to load factions: %s", e)

    def detect_entities(self, text: str) -> EntityMatch:
        """Detect known entities in the given text with high specificity.

        This method uses word boundary matching to find exact entity names
        in the text. It will NOT match partial words or common words.

        Args:
            text: The text to search for entities

        Returns:
            EntityMatch containing all detected entities
        """
        if not text:
            return EntityMatch(characters=[], places=[], factions=[])

        # Normalize text for matching (but preserve original for display)
        text_lower = text.lower()

        # Track what we've found (using sets to avoid duplicates)
        found_characters = {}
        found_places = {}
        found_factions = {}

        # Check each character name/alias
        for name_or_alias, char_record in self.character_lookup.items():
            # Use word boundaries for exact matching
            # This prevents matching "alex" in "alexander" or "complex"
            pattern = r'\b' + re.escape(name_or_alias) + r'\b'
            if re.search(pattern, text_lower):
                found_characters[char_record["id"]] = char_record
                logger.debug("Detected character: %s (id=%d)", char_record["name"], char_record["id"])

        # Check each place name
        for place_name, place_record in self.place_lookup.items():
            pattern = r'\b' + re.escape(place_name) + r'\b'
            if re.search(pattern, text_lower):
                found_places[place_record["id"]] = place_record
                logger.debug("Detected place: %s (id=%d)", place_record["name"], place_record["id"])

        # Check each faction name
        for faction_name, faction_record in self.faction_lookup.items():
            pattern = r'\b' + re.escape(faction_name) + r'\b'
            if re.search(pattern, text_lower):
                found_factions[faction_record["id"]] = faction_record
                logger.debug("Detected faction: %s (id=%d)", faction_record["name"], faction_record["id"])

        result = EntityMatch(
            characters=list(found_characters.values()),
            places=list(found_places.values()),
            factions=list(found_factions.values())
        )

        if result.detected:
            logger.info(
                "High-specificity detection found: %d characters, %d places, %d factions",
                len(result.characters),
                len(result.places),
                len(result.factions)
            )

        return result

    def to_divergence_format(self, entity_match: EntityMatch) -> Dict[str, Any]:
        """Convert EntityMatch to the format expected by divergence system.

        Args:
            entity_match: The entity match results

        Returns:
            Dictionary compatible with DivergenceResult format
        """
        gaps = {}
        unmatched_entities = set()

        for char in entity_match.characters:
            key = f"character_{char['id']}"
            gaps[key] = f"Character '{char['name']}' mentioned"
            unmatched_entities.add(key)

        for place in entity_match.places:
            key = f"place_{place['id']}"
            gaps[key] = f"Location '{place['name']}' referenced"
            unmatched_entities.add(key)

        for faction in entity_match.factions:
            key = f"faction_{faction['id']}"
            gaps[key] = f"Faction '{faction['name']}' mentioned"
            unmatched_entities.add(key)

        return {
            "detected": entity_match.detected,
            "confidence": 1.0 if entity_match.detected else 0.0,  # High confidence in our matches
            "gaps": gaps,
            "unmatched_entities": unmatched_entities,
            "references_seen": {"user_input"} if entity_match.detected else set()
        }