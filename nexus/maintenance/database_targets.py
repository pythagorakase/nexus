"""Explicit database-name boundaries for offline evaluation tools."""

import argparse
import re


def evaluation_dbname(value: str) -> str:
    """Accept only named disposable or reference databases, never live slots."""
    if not re.fullmatch(r"(?:qa640|ref)_[a-z0-9_]+", value):
        raise argparse.ArgumentTypeError("Database must match qa640_* or ref_*")
    return value


def metrics_dbname(value: str) -> str:
    """Also allow save_NN for strictly read-only corpus measurement."""
    if re.fullmatch(r"save_[0-9]{2}", value):
        return value
    return evaluation_dbname(value)
