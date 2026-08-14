"""Helpers for keeping model-controlled values inert in structured logs."""


def quote_log_value(value: str) -> str:
    """Return a quoted value whose content cannot create a log field token."""

    return ascii(value).replace("=", r"\x3d")
