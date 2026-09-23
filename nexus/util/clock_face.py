"""The UTC face of a story instant, shared by prompts and the reader."""

from datetime import datetime, timezone

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def clock_face(ts: datetime | str) -> str:
    """Render an aware story instant as ``D Mon YYYY · HH:MM`` in UTC.

    ISO strings are accepted at the serialized prompt boundary. Naive or
    malformed timestamps fail loudly instead of inheriting the host zone.
    """
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.utcoffset() is None:
        raise ValueError("Story timestamps must be timezone-aware")
    utc = ts.astimezone(timezone.utc)
    return (
        f"{utc.day} {_MONTHS[utc.month - 1]} {utc.year:04d}"
        f" · {utc.hour:02d}:{utc.minute:02d}"
    )
