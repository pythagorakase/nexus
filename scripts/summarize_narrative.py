#!/usr/bin/env python3
"""
NEXUS Narrative Summary Generator

This script generates comprehensive summaries of entire seasons or specific episodes
using the configured summary model, saving the results to the appropriate tables in
the PostgreSQL database.

Features:
- Multi-mode support: season summaries or episode summaries
- Episode range support: summarize multiple episodes in one run
- Database integration: saves structured JSONB to seasons and episodes tables
- Context-aware: includes padding chunks for better continuity
- Structured output: Uses each registry provider's native structured-output transport
  with Pydantic models for consistent results

Usage:
    # Summarize an entire season
    python summarize_narrative.py --season 3

    # Summarize a single episode
    python summarize_narrative.py --episode s03e01

    # Summarize a range of episodes
    python summarize_narrative.py --episode s03e01 s03e13

    # Manually specify chunk range (fallback option)
    python summarize_narrative.py --chunks 120 150

    # Options
    python summarize_narrative.py --season 3 --dry-run

The implementation is nexus.jobs.summarize_narrative; this module re-exports its names.
Assigning a name here does not change the implementation: patch
nexus.jobs.summarize_narrative instead.
"""

import os
import sys

# Add parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from nexus.jobs.summarize_narrative import (  # noqa: E402
    CONTEXT_CHUNK_AFTER,
    CONTEXT_CHUNK_BEFORE,
    DEFAULT_MODEL,
    DatabaseManager,
    EpisodeSlugParser,
    EpisodeSummary,
    FALLBACK_MODEL,
    SeasonSummary,
    SummaryGenerator,
    _resolve_default_summary_model,
    logger,
    main,
)

__all__ = [
    "CONTEXT_CHUNK_AFTER",
    "CONTEXT_CHUNK_BEFORE",
    "DEFAULT_MODEL",
    "DatabaseManager",
    "EpisodeSlugParser",
    "EpisodeSummary",
    "FALLBACK_MODEL",
    "SeasonSummary",
    "SummaryGenerator",
    "_resolve_default_summary_model",
    "logger",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
