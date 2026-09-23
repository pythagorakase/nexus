"""Pure formatting contract, independent of database and host timezone."""

from datetime import datetime

import pytest

from nexus.util.clock_face import clock_face


@pytest.mark.parametrize(
    "instant",
    ["2189-10-17T15:12:00-04:00", "2189-10-17T19:12:00+00:00"],
)
def test_clock_face_uses_utc(instant: str) -> None:
    """The seed's hour survives both driver representations."""
    assert clock_face(instant) == "17 Oct 2189 · 19:12"
    assert clock_face(datetime.fromisoformat(instant)) == "17 Oct 2189 · 19:12"


def test_clock_face_rolls_over_date() -> None:
    """UTC conversion must move the date as well as the hour."""
    assert clock_face("2189-12-31T22:12:00-04:00") == "1 Jan 2190 · 02:12"


@pytest.mark.parametrize("instant", ["invalid", "2189-10-17T19:12:00"])
def test_clock_face_rejects_invalid_or_naive_time(instant: str) -> None:
    """Invalid story clocks fail at the server, without host-zone guesses."""
    with pytest.raises(ValueError):
        clock_face(instant)
