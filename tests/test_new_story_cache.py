"""Tests for the normalized new-story setup cache."""

from nexus.api.new_story_cache import (
    CharacterData,
    SuggestedTrait,
    WizardCache,
    _row_to_cache,
)
import nexus.api.new_story_cache as cache_module


def test_character_dict_preserves_wildcard_orrery_tags() -> None:
    """Cached protagonist tags must survive through transition assembly."""

    bestowal = {
        "applied_tags": ["elf", "oath_bound"],
        "new_tag_proposals": [
            {
                "tag": "moon_touched",
                "category": "state",
                "scope": "durable",
                "evidence": "The wildcard says moonlight altered her blood.",
            }
        ],
        "tags_to_clear": [],
    }
    cache = WizardCache(
        character=CharacterData(
            name="Selene",
            archetype="moon-haunted exile",
            background="A runaway heir with an altered bloodline.",
            appearance="Silver-eyed and marked by lunar sigils.",
            suggested_traits=[
                SuggestedTrait("allies", "A hidden circle shelters her."),
                SuggestedTrait("contacts", "Smugglers pass her messages."),
                SuggestedTrait("obligations", "An oath binds her to return."),
            ],
            selected_trait_count=3,
            traits_confirmed=True,
            wildcard_name="Moon-Touched Blood",
            wildcard_rationale="Her blood answers old lunar rites.",
            orrery_tags=bestowal,
        )
    )

    character = cache.get_character_dict()

    assert character is not None
    assert character["wildcard"]["orrery_tags"] == bestowal


def test_row_to_cache_reads_character_orrery_tags() -> None:
    """The normalized row mapper hydrates the wildcard tag payload."""

    bestowal = {
        "applied_tags": ["ritualist"],
        "new_tag_proposals": [],
        "tags_to_clear": [],
    }

    cache = _row_to_cache(
        {
            "character_name": "Mira",
            "character_archetype": "ritual scholar",
            "character_background": "Raised in a sealed archive.",
            "character_appearance": "Ink-stained hands and observant eyes.",
            "character_orrery_tags": bestowal,
        },
        selected_traits=[
            SuggestedTrait("contacts", "Archivists trade favors."),
            SuggestedTrait("resources", "She owns rare grimoires."),
            SuggestedTrait("enemies", "A rival academy hunts her."),
        ],
        selected_trait_count=3,
        traits_confirmed=True,
        wildcard_row={
            "id": 11,
            "name": "Living Gloss",
            "rationale": "A curse annotates reality.",
        },
    )

    assert cache.character.orrery_tags == bestowal
    assert cache.get_character_dict()["wildcard"]["orrery_tags"] == bestowal


def test_write_cache_marks_three_selected_traits_confirmed(monkeypatch) -> None:
    """Structured trait submissions should advance slot-state phase detection."""

    class FakeCursor:
        def __init__(self) -> None:
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def cursor(self):
            return self.cursor_obj

    fake_conn = FakeConnection()
    monkeypatch.setattr(cache_module, "get_connection", lambda _dbname: fake_conn)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "trait_selection": {
                "selected_traits": ["contacts", "enemies", "obligations"],
                "trait_rationales": {
                    "contacts": "Route-keepers still talk to her.",
                    "enemies": "Powerful people want her silenced.",
                    "obligations": "A dying archivist gave her one last charge.",
                },
            }
        },
    )

    assert any(
        "traits_confirmed = TRUE" in sql for sql, _params in fake_conn.cursor_obj.calls
    )


def test_write_cache_creates_row_before_wildcard_tags(monkeypatch) -> None:
    """First legacy cache writes must not drop wildcard Orrery tag payloads."""

    class FakeCursor:
        def __init__(self) -> None:
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def cursor(self):
            return self.cursor_obj

    fake_conn = FakeConnection()
    monkeypatch.setattr(cache_module, "get_connection", lambda _dbname: fake_conn)

    cache_module.write_cache(
        dbname="save_05",
        character_draft={
            "wildcard": {
                "wildcard_name": "Debts That Know Her Name",
                "wildcard_description": "Favors find her even underground.",
                "orrery_tags": {
                    "applied_tags": ["obligation_magnet"],
                    "new_tag_proposals": [],
                    "tags_to_clear": [],
                },
            }
        },
    )

    calls = [sql for sql, _params in fake_conn.cursor_obj.calls]
    row_insert_index = next(
        index
        for index, sql in enumerate(calls)
        if "INSERT INTO assets.new_story_creator" in sql
    )
    tag_update_index = next(
        index
        for index, sql in enumerate(calls)
        if "character_orrery_tags = %s::jsonb" in sql
    )

    assert row_insert_index < tag_update_index
