"""The observer hold defaults to the configured poll interval."""

import pytest
from pydantic import ValidationError

from nexus.config.settings_models import DeferredWorkSettings


def test_unlock_hold_follows_poll_default() -> None:
    """An omitted hold derives from the supplied interval, not a fixed duration."""
    assert DeferredWorkSettings(poll_interval_seconds=2).unlock_hold_seconds == 2
    assert DeferredWorkSettings(unlock_hold_seconds=9).unlock_hold_seconds == 9


@pytest.mark.parametrize("hold", [0, -1])
def test_unlock_hold_must_be_positive(hold: float) -> None:
    """Configuration cannot silently disable the hold."""
    with pytest.raises(ValidationError):
        DeferredWorkSettings(unlock_hold_seconds=hold)
