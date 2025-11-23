import pytest

from nexus.api.slot_utils import slot_dbname, all_slots


def test_slot_dbname_valid():
    assert slot_dbname(1) == "save_01"
    assert slot_dbname(5) == "save_05"


def test_slot_dbname_invalid():
    with pytest.raises(ValueError):
        slot_dbname(0)
    with pytest.raises(ValueError):
        slot_dbname(6)


def test_all_slots():
    assert all_slots() == [1, 2, 3, 4, 5]
