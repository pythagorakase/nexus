"""Tests for database conversion utilities"""

import pytest
from datetime import timedelta
from nexus.api.db_converters import (
    create_new_faction,
    time_fields_to_interval,
    interval_to_time_fields,
    chronology_to_db_values,
    resolve_character_references,
    resolve_faction_references,
    resolve_place_references,
)
from nexus.agents.logon.apex_schema import (
    CharacterReference,
    ChronologyUpdate,
    FactionReference,
    NewFaction,
    PlaceReference,
    PlaceReferenceType,
    ReferenceType,
)


class MissingLookupConnection:
    """Async connection stand-in whose name lookups find no rows."""

    async def fetchval(self, *_args, **_kwargs):
        return None


class RecordingAsyncFactionConnection:
    """Async connection stand-in for new-faction insert tests."""

    def __init__(self):
        self.statements = []
        self.params = []

    async def execute(self, sql, *args):
        self.statements.append(" ".join(sql.split()))
        self.params.append(args)

    async def fetchval(self, sql, *args):
        self.statements.append(" ".join(sql.split()))
        self.params.append(args)
        if "SELECT COALESCE(MAX(id), 0) + 1 FROM factions" in sql:
            return 88
        if "INSERT INTO factions" in sql:
            return 88
        return None


class TestTimeConversion:
    """Test time conversion functions"""

    def test_time_fields_to_interval_minutes_only(self):
        """Test conversion of minutes-only time"""
        interval = time_fields_to_interval(minutes=15)
        assert interval == timedelta(minutes=15)

    def test_time_fields_to_interval_hours_and_minutes(self):
        """Test conversion of hours and minutes"""
        interval = time_fields_to_interval(minutes=30, hours=2)
        assert interval == timedelta(hours=2, minutes=30)

    def test_time_fields_to_interval_all_fields(self):
        """Test conversion with days, hours, minutes"""
        interval = time_fields_to_interval(minutes=45, hours=3, days=2)
        assert interval == timedelta(days=2, hours=3, minutes=45)

    def test_time_fields_to_interval_all_none(self):
        """Test that all None fields return None"""
        interval = time_fields_to_interval(None, None, None)
        assert interval is None

    def test_interval_to_time_fields_simple(self):
        """Test reverse conversion with simple time"""
        interval = timedelta(minutes=45)
        minutes, hours, days = interval_to_time_fields(interval)
        assert minutes == 45
        assert hours == 0
        assert days == 0

    def test_interval_to_time_fields_complex(self):
        """Test reverse conversion with complex time"""
        interval = timedelta(days=2, hours=3, minutes=45)
        minutes, hours, days = interval_to_time_fields(interval)
        assert minutes == 45
        assert hours == 3
        assert days == 2

    def test_interval_roundtrip(self):
        """Test that conversion is reversible"""
        original = timedelta(days=1, hours=5, minutes=30)
        minutes, hours, days = interval_to_time_fields(original)
        reconstructed = time_fields_to_interval(minutes, hours, days)
        assert original == reconstructed


class TestChronologyConversion:
    """Test episode/season conversion logic"""

    def test_chronology_continue(self):
        """Test episode continuation"""
        chronology = ChronologyUpdate(
            episode_transition="continue",
            time_delta_minutes=5
        )
        result = chronology_to_db_values(
            chronology,
            current_season=3,
            current_episode=7
        )
        assert result["season"] == 3
        assert result["episode"] == 7
        assert result["time_delta"] == timedelta(minutes=5)

    def test_chronology_new_episode(self):
        """Test new episode transition"""
        chronology = ChronologyUpdate(
            episode_transition="new_episode",
            time_delta_hours=2
        )
        result = chronology_to_db_values(
            chronology,
            current_season=3,
            current_episode=7
        )
        assert result["season"] == 3
        assert result["episode"] == 8
        assert result["time_delta"] == timedelta(hours=2)

    def test_chronology_new_season(self):
        """Test new season transition"""
        chronology = ChronologyUpdate(
            episode_transition="new_season",
            time_delta_days=1
        )
        result = chronology_to_db_values(
            chronology,
            current_season=3,
            current_episode=7
        )
        assert result["season"] == 4
        assert result["episode"] == 1  # Seasons start at episode 1
        assert result["time_delta"] == timedelta(days=1)

    def test_chronology_no_time(self):
        """Test transition with no time passage"""
        chronology = ChronologyUpdate(
            episode_transition="continue"
            # No time fields provided
        )
        result = chronology_to_db_values(
            chronology,
            current_season=2,
            current_episode=5
        )
        assert result["season"] == 2
        assert result["episode"] == 5
        assert result["time_delta"] is None


class TestPlaceReference:
    """Test place reference handling"""

    def test_place_reference_validation(self):
        """Test PlaceReference validation"""
        # Valid with place_id
        ref = PlaceReference(
            place_id=1,
            reference_type=PlaceReferenceType.SETTING
        )
        assert ref.place_id == 1

        # Valid with place_name
        ref = PlaceReference(
            place_name="The Great Library",
            reference_type=PlaceReferenceType.MENTIONED
        )
        assert ref.place_name == "The Great Library"

        # Invalid - no reference provided
        with pytest.raises(ValueError, match="Must provide either"):
            PlaceReference(
                reference_type=PlaceReferenceType.SETTING
            )


class TestReferenceResolution:
    """Test reference resolver tolerance for non-canonical extraction metadata."""

    @pytest.mark.asyncio
    async def test_unresolved_character_reference_is_skipped(self, caplog):
        """Group labels should not block committing an otherwise valid chunk."""
        refs = await resolve_character_references(
            [
                CharacterReference(
                    character_name="Rectification officers",
                    reference_type=ReferenceType.PRESENT,
                )
            ],
            MissingLookupConnection(),
        )

        assert refs == []
        assert "Skipping unresolved character reference" in caplog.text

    @pytest.mark.asyncio
    async def test_unresolved_place_reference_is_skipped(self, caplog):
        refs = await resolve_place_references(
            [
                PlaceReference(
                    place_name="Unresolved Threshold",
                    reference_type=PlaceReferenceType.MENTIONED,
                )
            ],
            MissingLookupConnection(),
        )

        assert refs == []
        assert "Skipping unresolved place reference" in caplog.text

    @pytest.mark.asyncio
    async def test_unresolved_faction_reference_is_skipped(self, caplog):
        refs = await resolve_faction_references(
            [
                FactionReference(
                    faction_name="Unresolved Office",
                    reference_type=ReferenceType.MENTIONED,
                )
            ],
            MissingLookupConnection(),
        )

        assert refs == []
        assert "Skipping unresolved faction reference" in caplog.text

    @pytest.mark.asyncio
    async def test_create_new_faction_omits_obsolete_columns(self):
        """Async faction creation should not write retired semantic columns."""

        conn = RecordingAsyncFactionConnection()

        faction_id = await create_new_faction(
            conn,
            NewFaction(
                name="Project Palimpsest",
                summary="A covert continuity office.",
                extra_data={"leader": "unknown"},
            ),
        )

        insert_sql = next(sql for sql in conn.statements if sql.startswith("INSERT"))

        assert faction_id == 88
        assert "ideology" not in insert_sql
        assert "history" not in insert_sql
        assert "current_activity" not in insert_sql
        assert "hidden_agenda" not in insert_sql
        assert "territory" not in insert_sql
        assert "power_level" not in insert_sql
        assert "resources" not in insert_sql
        assert "id, name, summary, primary_location, extra_data" in insert_sql


class TestTimeFieldValidation:
    """Test ChronologyUpdate time field validation"""

    def test_valid_time_fields(self):
        """Test valid time field combinations"""
        # Just minutes
        chronology = ChronologyUpdate(
            time_delta_minutes=30
        )
        assert chronology.time_delta_minutes == 30

        # Hours and days
        chronology = ChronologyUpdate(
            time_delta_hours=2,
            time_delta_days=1
        )
        assert chronology.time_delta_hours == 2
        assert chronology.time_delta_days == 1

    def test_time_field_constraints(self):
        """Test time field value constraints"""
        # Minutes must be < 60
        with pytest.raises(ValueError):
            ChronologyUpdate(time_delta_minutes=60)

        # Hours must be < 24
        with pytest.raises(ValueError):
            ChronologyUpdate(time_delta_hours=24)

        # Days can be large
        chronology = ChronologyUpdate(time_delta_days=365)
        assert chronology.time_delta_days == 365

        # Negative values not allowed
        with pytest.raises(ValueError):
            ChronologyUpdate(time_delta_minutes=-5)
