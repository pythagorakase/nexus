"""Authorial-directive markers for Retrograde-created narrative chunks.

These constants live in a dependency-free leaf module so retrieval code
(MEMNON's recent-chunks surface) can import them without pulling the full
Retrograde persistence import chain.
"""

from __future__ import annotations

RETROGRADE_PROLOGUE_MARKER = "orrery:retrograde_prologue_anchor"
RETROGRADE_SUMMARY_MARKER = "orrery:retrograde_event_summary"
RETROGRADE_EVENT_MARKER_PREFIX = "orrery:retrograde_event:"


def retrograde_event_marker(event_ref: str) -> str:
    """Build the per-event idempotency marker for a Retrograde summary chunk."""

    if not event_ref or not event_ref.strip():
        raise ValueError("event_ref is required to build a Retrograde event marker")
    return f"{RETROGRADE_EVENT_MARKER_PREFIX}{event_ref}"
