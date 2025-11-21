"""Tests for database conversion utilities"""

import pytest
from datetime import timedelta
from nexus.api.db_converters import (
    time_fields_to_interval,
    interval_to_time_fields,
    chronology_to_db_values,
)
from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    PlaceReference,
    PlaceReferenceType
)


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
