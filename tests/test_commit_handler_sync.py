"""Unit tests for synchronous narrative commit helpers."""

from nexus.agents.logon.apex_schema import CharacterReference, ReferenceType
from nexus.api.commit_handler_sync import resolve_character_references_sync


class MissingLookupCursor:
    """Cursor stand-in whose name lookups find no rows."""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return None


class MissingLookupConnection:
    """Connection stand-in for sync resolver tests."""

    def cursor(self):
        return MissingLookupCursor()


def test_sync_unresolved_character_reference_is_skipped(caplog):
    """Unresolved group labels should not block chunk commit."""
    refs = resolve_character_references_sync(
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
