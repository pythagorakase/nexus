"""Explicit database-name boundaries for offline evaluation tools.

The implementation is nexus.maintenance.database_targets; this module
re-exports its names.
Assigning a name here does not change the implementation: patch
nexus.maintenance.database_targets instead.
"""

from nexus.maintenance.database_targets import (
    evaluation_dbname,
    metrics_dbname,
)

__all__ = [
    "evaluation_dbname",
    "metrics_dbname",
]
