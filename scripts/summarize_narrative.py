#!/usr/bin/env python3
"""
NEXUS Narrative Summary Generator

This script generates comprehensive summaries of entire seasons or specific episodes
using GPT-5.1 by default (with GPT-4.1 as a long-context fallback), saving the results
to the appropriate tables in the PostgreSQL database.

Features:
- Multi-mode support: season summaries or episode summaries
- Episode range support: summarize multiple episodes in one run
- Database integration: saves summaries as structured JSONB to seasons and episodes tables
- Context-aware: includes padding chunks for better continuity
- Structured output: Uses OpenAI's structured output mode with Pydantic models for consistent results

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
    python summarize_narrative.py --season 3 --model gpt-4.1 --dry-run
"""

import os
import sys
import re
import json
import time
import argparse
import logging
from typing import Dict, List, Any, Tuple, Optional, Union, Set
from pydantic import BaseModel, Field

# Add parent directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import API OpenAI utilities
from scripts.api_openai import (
    OpenAIProvider, LLMResponse, setup_abort_handler, 
    is_abort_requested, reset_abort_flag, get_token_count
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("summarize_narrative.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.summarize_narrative")

# Constants
DEFAULT_MODEL = "gpt-5.1"
FALLBACK_MODEL = "gpt-4.1"
DEFAULT_TEMPERATURE = 0.2
MAX_TOKENS_SEASON = 4000
MAX_TOKENS_EPISODE = 2500
CONTEXT_CHUNK_BEFORE = 1  # Number of chunks to include before target for context
CONTEXT_CHUNK_AFTER = 1   # Number of chunks to include after target for context

# Database connection using SQLAlchemy
import sqlalchemy as sa
from sqlalchemy import create_engine, MetaData, Table, Column, text
from sqlalchemy.dialects.postgresql import TSRANGE, JSONB

class EpisodeSlugParser:
    """Parse and validate episode slugs like 's01e05'."""
    
    @staticmethod
    def parse(slug: str) -> Tuple[int, int]:
        """
        Parse an episode slug string into season and episode numbers.
        
        Args:
            slug: Episode slug string like 's01e05'
            
        Returns:
            Tuple of (season_number, episode_number)
            
        Raises:
            ValueError: If the slug format is invalid
        """
        pattern = r'^s(\d{1,2})e(\d{1,2})$'
        match = re.match(pattern, slug.lower())
        
        if not match:
            raise ValueError(f"Invalid episode slug format: {slug}. Expected format: s01e05")
            
        season = int(match.group(1))
        episode = int(match.group(2))
        
        return season, episode
    
    @staticmethod
    def format(season: int, episode: int) -> str:
        """
        Format season and episode numbers into a slug.
        
        Args:
            season: Season number
            episode: Episode number
            
        Returns:
            Formatted slug like 's01e05'
        """
        return f"s{season:02d}e{episode:02d}"
    
    @staticmethod
    def validate_range(start_slug: str, end_slug: str) -> bool:
        """
        Validate that end_slug comes after start_slug.
        
        Args:
            start_slug: Starting episode slug
            end_slug: Ending episode slug
            
        Returns:
            True if valid range, False otherwise
        """
        start_season, start_episode = EpisodeSlugParser.parse(start_slug)
        end_season, end_episode = EpisodeSlugParser.parse(end_slug)
        
        if start_season > end_season:
            return False
        
        if start_season == end_season and start_episode > end_episode:
            return False
            
        return True
    
    @staticmethod
    def range_spans_season(start_slug: str, end_slug: str) -> Optional[int]:
        """
        Check if the range spans a complete season.
        
        Args:
            start_slug: Starting episode slug
            end_slug: Ending episode slug
            
        Returns:
            Season number if range spans a complete season, None otherwise
        """
        start_season, start_episode = EpisodeSlugParser.parse(start_slug)
        end_season, end_episode = EpisodeSlugParser.parse(end_slug)
        
        # Must be in same season
        if start_season != end_season:
            return None
            
        # Check if it's a full season by querying the database
        # This will be implemented in the DatabaseManager class
        return None

class SeasonSummary(BaseModel):
    """Structured output model for season summaries."""
    overview: str = Field(
        description="A concise description of the season's overarching narrative and primary conflicts."
    )
    character_evolution: Dict[str, Dict[str, str]] = Field(
        description="Documentation of how major characters evolved throughout the season, including starting state, key moments, ending state, and relationship dynamics."
    )
    narrative_arcs: List[Dict[str, str]] = Field(
        description="Major story arcs that spanned multiple episodes, including origin, progression, resolution/status, and significance."
    )
    world_development: Dict[str, List[str]] = Field(
        description="Major additions to the story world, including settings, factions/groups, rules/systems, and historical context."
    )
    continuity_anchors: Dict[str, List[str]] = Field(
        description="Key elements that future narrative must maintain consistency with, including established facts, unresolved questions, and promises/setups."
    )

class EpisodeSummary(BaseModel):
    """Structured output model for episode summaries."""
    overview: str = Field(
        description="A brief factual summary of what happened in this episode, focusing on major developments."
    )
    timeline: List[str] = Field(
        description="A detailed, chronological record of events in sequential order, each prefixed with 'THEN:'."
    )
    characters: Dict[str, str] = Field(
        description="Key characters and their emotional/physical/relationship status at the end of this episode."
    )
    plot_threads: Dict[str, List[str]] = Field(
        description="Ongoing storylines and their current status, categorized as active, resolved, or introduced."
    )
    continuity_elements: Dict[str, List[str]] = Field(
        description="Important objects, locations, or world states that should be tracked."
    )

class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize the database manager.
        
        Args:
            db_url: Optional database URL. If not provided, will use environment variables.
        """
        self.db_url = db_url or self._get_db_url()
        self.engine = create_engine(self.db_url)
        self.metadata = MetaData()
        self._init_tables()
        
    def _get_db_url(self) -> str:
        """Get database URL from environment variables."""
        DB_USER = os.environ.get("DB_USER", "pythagor")
        DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
        DB_HOST = os.environ.get("DB_HOST", "localhost")
        DB_PORT = os.environ.get("DB_PORT", "5432")
        DB_NAME = os.environ.get("DB_NAME", "NEXUS")
        
        # Build connection string (with password if provided)
        if DB_PASSWORD:
            connection_string = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        else:
            connection_string = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            
        return connection_string
    
    def _init_tables(self):
        """Initialize table definitions."""
        # Define table mappings
        self.narrative_chunks = Table(
            'narrative_chunks', self.metadata,
            Column('id', sa.BigInteger, primary_key=True),
            Column('raw_text', sa.Text, nullable=False),
            Column('created_at', sa.DateTime(timezone=True)),
            schema='public'
        )
        
        self.chunk_metadata = Table(
            'chunk_metadata', self.metadata,
            Column('id', sa.BigInteger, primary_key=True),
            Column('chunk_id', sa.BigInteger, sa.ForeignKey('public.narrative_chunks.id')),
            Column('season', sa.Integer),
            Column('episode', sa.Integer),
            Column('scene', sa.Integer),
            Column('slug', sa.String(10)),
            schema='public'
        )
        
        self.seasons = Table(
            'seasons', self.metadata,
            Column('id', sa.BigInteger, primary_key=True),
            # Change TEXT to JSONB for structured storage
            Column('summary', JSONB),
            schema='public'
        )
        
        self.episodes = Table(
            'episodes', self.metadata,
            Column('season', sa.BigInteger, primary_key=True),
            Column('episode', sa.BigInteger, primary_key=True),
            Column('chunk_span', TSRANGE),
            # Change TEXT to JSONB for structured storage
            Column('summary', JSONB),
            schema='public'
        )
    
    def get_season_chunks(self, season: int) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific season.
        
        Args:
            season: The season number
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        with self.engine.connect() as conn:
            # Query chunks and metadata for the season
            query = text("""
            SELECT 
                nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
            FROM 
                public.narrative_chunks nc
            JOIN 
                public.chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE 
                cm.season = :season
            ORDER BY 
                cm.episode ASC, cm.scene ASC
            """)
            
            result = conn.execute(query, {"season": season})
            chunks = []
            
            for row in result:
                chunk = {
                    "id": row.id,
                    "text": row.raw_text,
                    "season": row.season,
                    "episode": row.episode,
                    "scene": row.scene,
                    "slug": row.slug
                }
                chunks.append(chunk)
            
            return chunks
    
    def get_episode_chunks(
        self, 
        season: int, 
        episode: int,
        include_context: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific episode.
        
        Args:
            season: The season number
            episode: The episode number
            include_context: Whether to include context chunks before and after
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        with self.engine.connect() as conn:
            # Base query for the specific episode
            base_query = text("""
            SELECT 
                nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
            FROM 
                public.narrative_chunks nc
            JOIN 
                public.chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE 
                cm.season = :season AND cm.episode = :episode
            ORDER BY 
                cm.scene ASC
            """)
            
            result = conn.execute(base_query, {"season": season, "episode": episode})
            chunks = []
            
            # Track the min/max chunk IDs to debug any potential issues
            actual_chunk_ids = []
            
            for row in result:
                chunk = {
                    "id": row.id,
                    "text": row.raw_text,
                    "season": row.season,
                    "episode": row.episode,
                    "scene": row.scene,
                    "slug": row.slug,
                    "is_context": False  # Mark as non-context chunk explicitly
                }
                chunks.append(chunk)
                actual_chunk_ids.append(row.id)
            
            # Log the actual chunk IDs for this episode
            if actual_chunk_ids:
                logger.info(f"Actual chunk IDs for S{season:02d}E{episode:02d}: {min(actual_chunk_ids)}-{max(actual_chunk_ids)}")
            
            # If no chunks found or no context needed, return as is
            if not chunks or not include_context:
                return chunks
            
            # Add context chunks before
            if CONTEXT_CHUNK_BEFORE > 0:
                # Get ID of first chunk to find preceding chunks
                first_chunk_id = chunks[0]["id"]
                context_before_query = text("""
                SELECT 
                    nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
                FROM 
                    public.narrative_chunks nc
                JOIN 
                    public.chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    nc.id < :first_chunk_id
                ORDER BY 
                    nc.id DESC
                LIMIT :limit
                """)
                
                before_result = conn.execute(context_before_query, {
                    "first_chunk_id": first_chunk_id,
                    "limit": CONTEXT_CHUNK_BEFORE
                })
                
                context_before = []
                for row in before_result:
                    # Verify this is actually a context chunk (different episode or season)
                    is_context = row.season != season or row.episode != episode
                    
                    chunk = {
                        "id": row.id,
                        "text": row.raw_text,
                        "season": row.season,
                        "episode": row.episode,
                        "scene": row.scene,
                        "slug": row.slug,
                        "is_context": True  # Mark as context chunk
                    }
                    context_before.append(chunk)
                    
                    # Log if we found context chunks that actually belong to this episode
                    if not is_context:
                        logger.warning(f"Context chunk {row.id} belongs to S{season:02d}E{episode:02d} but is being treated as context")
                
                # Reverse to get chronological order
                chunks = context_before[::-1] + chunks
            
            # Add context chunks after
            if CONTEXT_CHUNK_AFTER > 0:
                # Get ID of last chunk to find following chunks
                last_chunk_id = chunks[-1]["id"]
                context_after_query = text("""
                SELECT 
                    nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
                FROM 
                    public.narrative_chunks nc
                JOIN 
                    public.chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    nc.id > :last_chunk_id
                ORDER BY 
                    nc.id ASC
                LIMIT :limit
                """)
                
                after_result = conn.execute(context_after_query, {
                    "last_chunk_id": last_chunk_id,
                    "limit": CONTEXT_CHUNK_AFTER
                })
                
                context_after = []
                for row in after_result:
                    # Verify this is actually a context chunk (different episode or season)
                    is_context = row.season != season or row.episode != episode
                    
                    chunk = {
                        "id": row.id,
                        "text": row.raw_text,
                        "season": row.season,
                        "episode": row.episode,
                        "scene": row.scene,
                        "slug": row.slug,
                        "is_context": True  # Mark as context chunk
                    }
                    context_after.append(chunk)
                    
                    # Log if we found context chunks that actually belong to this episode
                    if not is_context:
                        logger.warning(f"Context chunk {row.id} belongs to S{season:02d}E{episode:02d} but is being treated as context")
                
                chunks = chunks + context_after
            
            return chunks
    
    def get_episode_range_chunks(
        self, 
        start_season: int, 
        start_episode: int,
        end_season: int,
        end_episode: int,
        include_context: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a range of episodes.
        
        Args:
            start_season: The starting season number
            start_episode: The starting episode number
            end_season: The ending season number
            end_episode: The ending episode number
            include_context: Whether to include context chunks before and after
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        with self.engine.connect() as conn:
            # Query for the episode range
            range_query = text("""
            SELECT 
                nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
            FROM 
                public.narrative_chunks nc
            JOIN 
                public.chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE 
                (cm.season > :start_season OR (cm.season = :start_season AND cm.episode >= :start_episode))
                AND
                (cm.season < :end_season OR (cm.season = :end_season AND cm.episode <= :end_episode))
            ORDER BY 
                cm.season ASC, cm.episode ASC, cm.scene ASC
            """)
            
            result = conn.execute(range_query, {
                "start_season": start_season,
                "start_episode": start_episode,
                "end_season": end_season,
                "end_episode": end_episode
            })
            
            chunks = []
            for row in result:
                chunk = {
                    "id": row.id,
                    "text": row.raw_text,
                    "season": row.season,
                    "episode": row.episode,
                    "scene": row.scene,
                    "slug": row.slug
                }
                chunks.append(chunk)
            
            # If no chunks found or no context needed, return as is
            if not chunks or not include_context:
                return chunks
            
            # Add context chunks before
            if CONTEXT_CHUNK_BEFORE > 0:
                # Get ID of first chunk to find preceding chunks
                first_chunk_id = chunks[0]["id"]
                context_before_query = text("""
                SELECT 
                    nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
                FROM 
                    public.narrative_chunks nc
                JOIN 
                    public.chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    nc.id < :first_chunk_id
                ORDER BY 
                    nc.id DESC
                LIMIT :limit
                """)
                
                before_result = conn.execute(context_before_query, {
                    "first_chunk_id": first_chunk_id,
                    "limit": CONTEXT_CHUNK_BEFORE
                })
                
                context_before = []
                for row in before_result:
                    chunk = {
                        "id": row.id,
                        "text": row.raw_text,
                        "season": row.season,
                        "episode": row.episode,
                        "scene": row.scene,
                        "slug": row.slug,
                        "is_context": True
                    }
                    context_before.append(chunk)
                
                # Reverse to get chronological order
                chunks = context_before[::-1] + chunks
            
            # Add context chunks after
            if CONTEXT_CHUNK_AFTER > 0:
                # Get ID of last chunk to find following chunks
                last_chunk_id = chunks[-1]["id"]
                context_after_query = text("""
                SELECT 
                    nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
                FROM 
                    public.narrative_chunks nc
                JOIN 
                    public.chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    nc.id > :last_chunk_id
                ORDER BY 
                    nc.id ASC
                LIMIT :limit
                """)
                
                after_result = conn.execute(context_after_query, {
                    "last_chunk_id": last_chunk_id,
                    "limit": CONTEXT_CHUNK_AFTER
                })
                
                context_after = []
                for row in after_result:
                    chunk = {
                        "id": row.id,
                        "text": row.raw_text,
                        "season": row.season,
                        "episode": row.episode,
                        "scene": row.scene,
                        "slug": row.slug,
                        "is_context": True
                    }
                    context_after.append(chunk)
                
                chunks = chunks + context_after
            
            return chunks
    
    def get_chunks_by_id_range(self, start_id: int, end_id: int) -> List[Dict[str, Any]]:
        """
        Get chunks by ID range (manual fallback).
        
        Args:
            start_id: Starting chunk ID
            end_id: Ending chunk ID
            
        Returns:
            List of chunk dictionaries with text and metadata
        """
        with self.engine.connect() as conn:
            query = text("""
            SELECT 
                nc.id, nc.raw_text, cm.season, cm.episode, cm.scene, cm.slug
            FROM 
                public.narrative_chunks nc
            LEFT JOIN 
                public.chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE 
                nc.id >= :start_id AND nc.id <= :end_id
            ORDER BY 
                nc.id ASC
            """)
            
            result = conn.execute(query, {"start_id": start_id, "end_id": end_id})
            
            chunks = []
            for row in result:
                chunk = {
                    "id": row.id,
                    "text": row.raw_text,
                    "season": row.season if row.season is not None else None,
                    "episode": row.episode if row.episode is not None else None,
                    "scene": row.scene if row.scene is not None else None,
                    "slug": row.slug if row.slug is not None else None
                }
                chunks.append(chunk)
                
            return chunks
            
    def get_previous_season_summaries(self, season: int) -> List[Dict[str, Any]]:
        """
        Get all summaries from previous seasons.
        
        Args:
            season: The current season number
            
        Returns:
            List of dictionaries with season number and summary text
        """
        summaries = []
        try:
            with self.engine.connect() as conn:
                query = text("""
                SELECT id, summary 
                FROM public.seasons 
                WHERE id < :season AND summary IS NOT NULL
                ORDER BY id ASC
                """)
                
                result = conn.execute(query, {"season": season})
                
                for row in result:
                    summaries.append({
                        "season": row.id,
                        "summary": row.summary
                    })
                    
            return summaries
        except Exception as e:
            logger.error(f"Error retrieving previous season summaries: {e}")
            return []
            
    def get_previous_episode_summaries(self, season: int, episode: int) -> List[Dict[str, Any]]:
        """
        Get summaries from previous episodes in the same season.
        
        Args:
            season: The season number
            episode: The current episode number
            
        Returns:
            List of dictionaries with episode info and summary text
        """
        summaries = []
        try:
            with self.engine.connect() as conn:
                # Get previous episodes from this season
                query = text("""
                SELECT season, episode, summary 
                FROM public.episodes 
                WHERE season = :season AND episode < :episode AND summary IS NOT NULL
                ORDER BY episode ASC
                """)
                
                result = conn.execute(query, {"season": season, "episode": episode})
                
                for row in result:
                    summaries.append({
                        "season": row.season,
                        "episode": row.episode,
                        "slug": EpisodeSlugParser.format(row.season, row.episode),
                        "summary": row.summary
                    })
                    
            return summaries
        except Exception as e:
            logger.error(f"Error retrieving previous episode summaries: {e}")
            return []

    def episode_summary_exists(self, season: int, episode: int) -> bool:
        """
        Check if an episode summary already exists.

        Args:
            season: The season number
            episode: The episode number

        Returns:
            True if a non-null summary exists, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM public.episodes
                        WHERE season = :season AND episode = :episode AND summary IS NOT NULL
                        LIMIT 1
                        """
                    ),
                    {"season": season, "episode": episode}
                ).scalar()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking for existing summary for S{season:02d}E{episode:02d}: {e}")
            return False
            
    def get_season_summary(self, season: int) -> Optional[Dict[str, Any]]:
        """
        Get the summary for a specific season.
        
        Args:
            season: The season number
            
        Returns:
            Dictionary with the season summary, or None if not found
        """
        try:
            with self.engine.connect() as conn:
                query = text("""
                SELECT id, summary 
                FROM public.seasons 
                WHERE id = :season AND summary IS NOT NULL
                """)
                
                result = conn.execute(query, {"season": season}).fetchone()
                
                if result:
                    return {
                        "season": result.id,
                        "summary": result.summary
                    }
                return None
        except Exception as e:
            logger.error(f"Error retrieving season summary: {e}")
            return None

    def season_summary_exists(self, season: int) -> bool:
        """
        Check if a season summary already exists.

        Args:
            season: The season number

        Returns:
            True if a non-null summary exists, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT 1
                        FROM public.seasons
                        WHERE id = :season AND summary IS NOT NULL
                        LIMIT 1
                        """
                    ),
                    {"season": season}
                ).scalar()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking for existing summary for Season {season}: {e}")
            return False
    
    def save_season_summary(
        self,
        season: int,
        summary: dict,
        dry_run: bool = False,
        overwrite: bool = False,
        prompt_on_conflict: bool = True
    ) -> bool:
        """
        Save a season summary to the database.
        
        Args:
            season: The season number
            summary: The summary as a dictionary (from Pydantic model)
            dry_run: If True, don't actually save
            overwrite: If True, overwrite existing summary even if it exists
            prompt_on_conflict: If False, skip interactive overwrite prompts and keep existing data
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would save summary for season {season}")
            return True
            
        try:
            with self.engine.connect() as conn:
                # Check if season record exists
                check_query = text("SELECT id, summary FROM public.seasons WHERE id = :season")
                existing = conn.execute(check_query, {"season": season}).fetchone()
                
                if existing and existing.summary and not overwrite:
                    if not prompt_on_conflict:
                        logger.info(f"Existing summary found for Season {season}; skipping (overwrite disabled)")
                        return False

                    # We have an existing summary but no overwrite flag
                    # Print the new summary and ask if user wants to overwrite
                    print("\n" + "=" * 80)
                    print(f"NEW SUMMARY FOR SEASON {season}:")
                    print("-" * 80)
                    if isinstance(summary, dict) and "summary" in summary:
                        print(summary["summary"])
                    else:
                        print(json.dumps(summary, indent=2))
                    print("=" * 80)
                    
                    # Ask user for decision
                    choice = input(f"\nOverwrite existing summary for Season {season}? (y/n): ").lower().strip()
                    if choice == 'y':
                        update_query = text("""
                        UPDATE public.seasons
                        SET summary = :summary
                        WHERE id = :season
                        """)
                        
                        conn.execute(update_query, {"season": season, "summary": json.dumps(summary)})
                        conn.commit()
                        logger.info(f"Updated summary for season {season}")
                        return True
                    else:
                        logger.info(f"Kept existing summary for Season {season}")
                        return False
                elif existing:
                    # Update existing record (either no summary or overwrite flag is True)
                    update_query = text("""
                    UPDATE public.seasons
                    SET summary = :summary
                    WHERE id = :season
                    """)
                    
                    conn.execute(update_query, {"season": season, "summary": json.dumps(summary)})
                    conn.commit()
                    logger.info(f"Updated summary for season {season}")
                    return True
                else:
                    # Insert new record
                    insert_query = text("""
                    INSERT INTO public.seasons (id, summary)
                    VALUES (:season, :summary)
                    """)
                    
                    conn.execute(insert_query, {"season": season, "summary": json.dumps(summary)})
                    conn.commit()
                    logger.info(f"Inserted new summary for season {season}")
                    return True
                
        except Exception as e:
            logger.error(f"Error saving season summary: {e}")
            return False
    
    def save_episode_summary(
        self, 
        season: int, 
        episode: int, 
        summary: dict, 
        dry_run: bool = False,
        overwrite: bool = False,
        chunk_span: Optional[Tuple[int, int]] = None,
        prompt_on_conflict: bool = True
    ) -> bool:
        """
        Save an episode summary to the database.
        
        Args:
            season: The season number
            episode: The episode number
            summary: The summary as a dictionary (from Pydantic model)
            dry_run: If True, don't actually save
            overwrite: If True, overwrite existing summary even if it exists
            chunk_span: Optional tuple of (min_id, max_id) for the episode chunks
            prompt_on_conflict: If False, skip interactive overwrite prompts and keep existing data
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would save summary for S{season:02d}E{episode:02d}")
            return True
            
        # Log chunk span details
        if chunk_span:
            min_id, max_id = chunk_span
            logger.info(f"Saving S{season:02d}E{episode:02d} with chunk_span: [{min_id}, {max_id}]")
        else:
            logger.warning(f"No chunk_span provided for S{season:02d}E{episode:02d}")
            
        try:
            with self.engine.connect() as conn:
                # Prepare parameters and chunk_span clause if provided
                params = {"season": season, "episode": episode, "summary": json.dumps(summary)}
                
                # Add chunk span parameters if available
                if chunk_span:
                    min_id, max_id = chunk_span
                    params["min_id"] = min_id
                    params["max_id"] = max_id
                
                # Check if episode record exists
                check_query = text("""
                SELECT season, episode, summary FROM public.episodes 
                WHERE season = :season AND episode = :episode
                """)
                
                existing = conn.execute(check_query, {"season": season, "episode": episode}).fetchone()
                
                if existing and existing.summary and not overwrite:
                    if not prompt_on_conflict:
                        logger.info(f"Existing summary found for S{season:02d}E{episode:02d}; skipping (overwrite disabled)")
                        return False

                    # We have an existing summary but no overwrite flag
                    # Print the new summary and ask if user wants to overwrite
                    slug = EpisodeSlugParser.format(season, episode)
                    print("\n" + "=" * 80)
                    print(f"NEW SUMMARY FOR {slug}:")
                    print("-" * 80)
                    if isinstance(summary, dict) and "summary" in summary:
                        print(summary["summary"])
                    else:
                        print(json.dumps(summary, indent=2))
                    print("=" * 80)
                    
                    # Ask user for decision
                    choice = input(f"\nOverwrite existing summary for {slug}? (y/n): ").lower().strip()
                    if choice == 'y':
                        if chunk_span:
                            update_query = text("""
                            UPDATE public.episodes
                            SET summary = :summary, chunk_span = int8range(:min_id, :max_id)
                            WHERE season = :season AND episode = :episode
                            """)
                        else:
                            update_query = text("""
                            UPDATE public.episodes
                            SET summary = :summary
                            WHERE season = :season AND episode = :episode
                            """)
                        
                        conn.execute(update_query, params)
                        conn.commit()
                        logger.info(f"Updated summary for {slug}")
                        return True
                    else:
                        logger.info(f"Kept existing summary for {slug}")
                        return False
                elif existing:
                    # Update existing record (either no summary or overwrite flag is True)
                    if chunk_span:
                        update_query = text("""
                        UPDATE public.episodes
                        SET summary = :summary, chunk_span = int8range(:min_id, :max_id)
                        WHERE season = :season AND episode = :episode
                        """)
                    else:
                        update_query = text("""
                        UPDATE public.episodes
                        SET summary = :summary
                        WHERE season = :season AND episode = :episode
                        """)
                    
                    conn.execute(update_query, params)
                    conn.commit()
                    logger.info(f"Updated summary for S{season:02d}E{episode:02d}")
                    return True
                else:
                    # Insert new record
                    if chunk_span:
                        insert_query = text("""
                        INSERT INTO public.episodes (season, episode, summary, chunk_span)
                        VALUES (:season, :episode, :summary, int8range(:min_id, :max_id))
                        """)
                    else:
                        insert_query = text("""
                        INSERT INTO public.episodes (season, episode, summary)
                        VALUES (:season, :episode, :summary)
                        """)
                    
                    conn.execute(insert_query, params)
                    conn.commit()
                    logger.info(f"Inserted new summary for S{season:02d}E{episode:02d}")
                    return True
                
        except Exception as e:
            logger.error(f"Error saving episode summary: {e}")
            return False
    
    def get_episode_chunk_span(self, season: int, episode: int) -> Optional[Tuple[int, int]]:
        """
        Get the exact chunk span (min/max IDs) for a specific episode.
        
        Args:
            season: The season number
            episode: The episode number
            
        Returns:
            Tuple of (min_id, max_id) or None if no chunks found
        """
        try:
            with self.engine.connect() as conn:
                # First, get all chunk IDs for this episode with metadata
                chunk_details_query = text("""
                SELECT 
                    nc.id as chunk_id, cm.season, cm.episode, cm.scene
                FROM 
                    public.narrative_chunks nc
                JOIN 
                    public.chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    cm.season = :season AND cm.episode = :episode
                ORDER BY 
                    nc.id ASC
                """)
                
                chunk_details = list(conn.execute(chunk_details_query, {"season": season, "episode": episode}))
                
                if not chunk_details:
                    logger.warning(f"No chunks found for S{season:02d}E{episode:02d}")
                    return None
                
                # Get min and max IDs
                min_id = chunk_details[0].chunk_id
                max_id = chunk_details[-1].chunk_id
                
                # Log all chunks for debugging
                chunks_str = ", ".join([str(row.chunk_id) for row in chunk_details])
                logger.info(f"Chunks for S{season:02d}E{episode:02d}: [{chunks_str}]")
                logger.info(f"Chunk span for S{season:02d}E{episode:02d}: {min_id} to {max_id}")
                
                # Verify the boundaries to ensure they don't include other episodes
                verify_query = text("""
                SELECT 
                    cm.season, cm.episode, cm.scene
                FROM 
                    public.chunk_metadata cm
                WHERE 
                    cm.chunk_id = :min_id OR cm.chunk_id = :max_id
                """)
                
                boundaries = list(conn.execute(verify_query, {"min_id": min_id, "max_id": max_id}))
                
                for row in boundaries:
                    if row.season != season or row.episode != episode:
                        logger.error(f"Boundary issue: Chunk ID belonging to S{row.season:02d}E{row.episode:02d} included in S{season:02d}E{episode:02d} span")
                        # Don't return wrong boundaries
                        return None
                
                return (min_id, max_id)
                
        except Exception as e:
            logger.error(f"Error getting chunk span for S{season:02d}E{episode:02d}: {e}")
            return None

class SummaryGenerator:
    """
    Main class to generate summaries using OpenAI's API.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        effort: str = "medium",
        db_manager: Optional[DatabaseManager] = None,
        dry_run: bool = False,
        overwrite: bool = False,
        verbose: bool = False,
        save_prompt: bool = False,
        prompt_on_conflict: bool = True
    ):
        """
        Initialize the summary generator.
        
        Args:
            model: OpenAI model to use
            temperature: Temperature for generation (used for non-reasoning models)
            effort: Reasoning effort level (used for reasoning models)
            db_manager: Database manager instance
            dry_run: If True, don't save results
            verbose: If True, print detailed output
            save_prompt: If True, save prompts to files
            prompt_on_conflict: If False, skip interactive overwrite prompts when summaries already exist
        """
        self.model = model
        self.temperature = temperature
        self.effort = effort
        self.is_reasoning_model = model.startswith("o")
        self.db_manager = db_manager or DatabaseManager()
        self.dry_run = dry_run
        self.overwrite = overwrite
        self.verbose = verbose
        self.save_prompt = save_prompt
        self.prompt_on_conflict = prompt_on_conflict
        self.provider = self._initialize_provider()
        
    def _initialize_provider(self) -> OpenAIProvider:
        """Initialize the OpenAI provider."""
        try:
            # Use the streamlined provider initialization
            if self.is_reasoning_model:
                provider = OpenAIProvider(
                    model=self.model,
                    reasoning_effort=self.effort
                )
                logger.info(f"Initialized OpenAI provider with reasoning model: {self.model}, effort: {self.effort}")
            else:
                provider = OpenAIProvider(
                    model=self.model,
                    temperature=self.temperature
                )
                logger.info(f"Initialized OpenAI provider with standard model: {self.model}, temperature: {self.temperature}")
                
            return provider
        except Exception as e:
            logger.error(f"Error initializing OpenAI provider: {e}")
            raise
    
    def _get_system_prompt(self, mode: str) -> str:
        """
        Get the appropriate system prompt based on mode.
        
        Args:
            mode: Either 'season' or 'episode'
            
        Returns:
            System prompt string
        """
        if mode == "season":
            return """You are a narrative continuity AI that creates structured, factual summaries for an AI storytelling system.

Your SEASON summaries will be accessed by another AI to understand broad narrative patterns and maintain consistency across long stories. Focus on patterns, arcs, and transformations rather than listing every event.

You MUST provide a structured output with these exact sections:

1. OVERVIEW: A concise description of the season's overarching narrative and primary conflicts.

2. CHARACTER_EVOLUTION: For each major character, document their starting state and motivation, key transformative moments (reference episodes), ending state and motivation, and relationship dynamics that evolved.

3. NARRATIVE_ARCS: Map the major story arcs that spanned multiple episodes, including how and when each arc began, key developments across episodes, current state/resolution of the arc, and impact on the broader narrative.

4. WORLD_DEVELOPMENT: Document major additions to the story world, including new settings and their significance, new or evolved social structures/factions, important mechanics of how the world functions, and backstory elements revealed.

5. CONTINUITY_ANCHORS: List key elements that future narrative must maintain consistency with, including established facts, unresolved questions, and elements introduced that require future payoff.

Be factual, objective, and comprehensive. Organize information logically to help the AI easily access relevant details."""
        elif mode == "episode":
            return """You are a narrative continuity AI that creates structured, factual summaries for an AI storytelling system.

Your EPISODE summaries will be accessed by another AI to maintain precise narrative consistency. Focus on detailed events, immediate causality, and character states at specific moments.

You MUST provide a structured output with these exact sections:

1. OVERVIEW: A brief factual summary of what happened in this episode, focusing on major developments. Keep this concise (1-2 paragraphs maximum).

2. TIMELINE: A detailed, chronological record of events in sequential order. This should be the LONGEST section (60-70% of your total output). Use past tense, active voice, and concrete details. Break down the episode into many specific events, each beginning with "THEN:" for clear parsing. Be thorough and granular - capture all significant story beats.

3. CHARACTERS: List key characters and their emotional/physical/relationship status at the end of this episode.

4. PLOT_THREADS: List ongoing storylines and their current status, categorized as active (continuing), resolved (concluded), or introduced (new).

5. CONTINUITY_ELEMENTS: Note important objects, locations, or world states that should be tracked, including their current location/state/condition and any new information revealed.

Be factual, objective, and chronological. Focus on concrete events and states rather than analysis. Your summary must provide all essential details needed to maintain narrative continuity."""
        else:
            # Generic fallback
            return """You are a narrative continuity AI that creates structured, factual summaries for an AI storytelling system.
Your summaries will be accessed by another AI to maintain narrative consistency. Be factual, objective, and comprehensive."""
    
    def _prepare_chunks_text(self, chunks: List[Dict[str, Any]], mode: str) -> str:
        """
        Prepare chunks for inclusion in the prompt.
        
        Args:
            chunks: List of chunk dictionaries
            mode: Either 'season' or 'episode'
            
        Returns:
            Formatted chunk text for the prompt
        """
        formatted_chunks = []
        
        for chunk in chunks:
            # Skip context chunks in the final text if there are too many chunks
            if len(chunks) > 20 and chunk.get("is_context", False):
                continue
                
            # Format the chunk header
            header = "=" * 80 + "\n"
            
            if chunk.get("slug"):
                header += f"SLUG: {chunk['slug']}"
            elif chunk.get("season") is not None and chunk.get("episode") is not None:
                season = chunk["season"]
                episode = chunk["episode"]
                scene = chunk.get("scene", "?")
                header += f"S{season:02d}E{episode:02d} Scene {scene}"
            else:
                header += f"CHUNK ID: {chunk['id']}"
                
            if chunk.get("is_context", False):
                header += " [CONTEXT CHUNK]"
                
            header += "\n" + "=" * 80 + "\n"
            
            # Add the chunk text
            formatted_chunks.append(header + chunk["text"])
        
        # Join all chunks with newlines
        return "\n\n".join(formatted_chunks)
    
    def _token_check(self, text: str, mode: str) -> bool:
        """
        Check if the text is within token limits for the model.
        
        Args:
            text: The text to check
            mode: Either 'season' or 'episode'
            
        Returns:
            True if within limits, False otherwise
        """
        token_count = get_token_count(text, self.model)
        
        # Load settings to get the TPM from settings.json
        settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'settings.json')
        with open(settings_path, 'r') as f:
            settings = json.load(f)
            
        # Get the OpenAI TPM limit
        openai_tpm = settings.get("API Settings", {}).get("TPM", {}).get("openai")
        if not openai_tpm:
            raise ValueError("Could not find OpenAI TPM limit in settings.json")
            
        # Set output token limit based on mode
        expected_output_tokens = MAX_TOKENS_SEASON if mode == "season" else MAX_TOKENS_EPISODE
        
        # Calculate max input tokens (with a small buffer)
        max_input_tokens = openai_tpm - expected_output_tokens
        
        if token_count > max_input_tokens:
            logger.warning(
                f"Input too long: {token_count} tokens (limit: {max_input_tokens}). "
                f"Try using fewer chunks or a smaller range."
            )
            return False
            
        logger.info(f"Token count: {token_count} (under limit of {max_input_tokens} from settings.json)")
        return True
    
    def _save_prompt_to_file(self, prompt: str, prefix: str):
        """Save prompt to a file for debugging."""
        if not self.save_prompt:
            return
            
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}_prompt.txt"
            
            with open(filename, "w") as f:
                f.write(prompt)
                
            logger.info(f"Saved prompt to {filename}")
        except Exception as e:
            logger.error(f"Error saving prompt to file: {e}")
    
    def generate_season_summary(self, season: int) -> Optional[dict]:
        """
        Generate a comprehensive summary for an entire season.
        
        Args:
            season: The season number
            
        Returns:
            Generated summary as a dictionary, or None if failed
        """
        logger.info(f"Generating summary for Season {season}")
        
        # Get all chunks for the season
        chunks = self.db_manager.get_season_chunks(season)
        
        if not chunks:
            logger.error(f"No chunks found for Season {season}")
            return None
            
        logger.info(f"Found {len(chunks)} chunks for Season {season}")
        
        # Get summaries of previous seasons for context
        previous_summaries = self.db_manager.get_previous_season_summaries(season)
        prev_summaries_text = ""
        
        if previous_summaries:
            logger.info(f"Found {len(previous_summaries)} previous season summaries for context")
            prev_summaries_text = "## Previous Season Summaries:\n\n"
            
            for prev in previous_summaries:
                prev_season = prev["season"]
                prev_summary = prev["summary"]
                
                # Extract just the summary text from the JSONB object
                if isinstance(prev_summary, dict) and "summary" in prev_summary:
                    summary_content = prev_summary["summary"]
                else:
                    # Fallback if structure is different
                    summary_content = str(prev_summary)
                
                prev_summaries_text += f"### Season {prev_season} Summary:\n\n{summary_content}\n\n"
                prev_summaries_text += "-" * 80 + "\n\n"
            
            logger.info("Added previous season summaries to the prompt")
            
            # Print context in verbose mode
            if self.verbose and prev_summaries_text:
                print("\n" + "=" * 80)
                print("CONTEXT BEING USED FOR SUMMARY GENERATION:")
                print("=" * 80)
                print(prev_summaries_text)
                print("=" * 80 + "\n")
        
        # Prepare the prompt
        system_prompt = self._get_system_prompt("season")
        chunks_text = self._prepare_chunks_text(chunks, "season")
        
        # Build the main prompt with previous summaries
        prompt = f"""# Narrative Summary Request

I need a comprehensive, structured summary of Season {season} of the narrative. Please analyze all the provided chunks to create a structured season summary following the format specified.

{prev_summaries_text}## The Narrative Chunks:

{chunks_text}

## Important Requirements:

1. Your summary must include ALL five required sections: OVERVIEW, CHARACTER_EVOLUTION, NARRATIVE_ARCS, WORLD_DEVELOPMENT, and CONTINUITY_ANCHORS.
2. Focus on patterns, character arcs, and narrative developments that span the entire season.
3. For CHARACTER_EVOLUTION, document each major character's transformation throughout the season.
4. For NARRATIVE_ARCS, identify major storylines and track their progression across episodes.
5. Be objective, factual, and comprehensive - your summary will be used by another AI to maintain narrative continuity.
6. Maintain continuity with previous seasons - ensure your summary is compatible with the major plot developments and character arcs established in earlier seasons."""
        
        # Token check
        if not self._token_check(prompt, "season"):
            logger.warning("Token check failed - input may be too long")
            # Proceed anyway - the API will truncate if needed
        
        # Save prompt if requested
        self._save_prompt_to_file(prompt, f"season_{season}")
        
        try:
            # Use the OpenAI responses.parse API with Pydantic model
            import openai
            
            # Set up the API client - using the direct OpenAI client
            client = openai.OpenAI(api_key=self.provider.api_key)
            
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            if self.provider.system_prompt:
                messages.insert(0, {"role": "system", "content": self.provider.system_prompt})
            
            # Create a simple Pydantic model for season summary
            class SeasonSummaryModel(BaseModel):
                summary: str = Field(
                    description="A comprehensive, detailed narrative summary of the entire season capturing major plot developments, character arcs, key world-building elements, and themes."
                )
            
            logger.info(f"Using OpenAI responses.parse with model {self.provider.model}")
            
            # Call the API with appropriate parameters based on model type
            if self.is_reasoning_model:
                response = client.responses.parse(
                    model=self.provider.model,
                    input=messages,
                    reasoning={"effort": self.effort},
                    text_format=SeasonSummaryModel
                )
                logger.info(f"Used reasoning model with effort: {self.effort}")
            else:
                response = client.responses.parse(
                    model=self.provider.model,
                    input=messages,
                    temperature=self.temperature,
                    text_format=SeasonSummaryModel
                )
                logger.info(f"Used standard model with temperature: {self.temperature}")
            
            # Create a summary dict that matches our expected format
            summary_text = response.output_parsed.summary
            summary_dict = {
                "summary": summary_text
            }
            
            # Log completion info
            logger.info(
                f"Generated season summary with {response.usage.input_tokens} input tokens and "
                f"{response.usage.output_tokens} output tokens"
            )
            
            # Print summary in verbose mode
            if self.verbose:
                print("\n" + "=" * 80)
                print(f"SEASON {season} SUMMARY")
                print("=" * 80)
                print(json.dumps(summary_dict, indent=2))
                print("=" * 80 + "\n")
            
            # Save to database
            success = self.db_manager.save_season_summary(
                season=season,
                summary=summary_dict,
                dry_run=self.dry_run,
                overwrite=self.overwrite,
                prompt_on_conflict=self.prompt_on_conflict
            )
            
            if success:
                logger.info(f"Successfully saved summary for Season {season}")
                return summary_dict
            else:
                logger.error(f"Failed to save summary for Season {season}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating season summary: {e}")
            return None
    
    def generate_episode_summary(self, season: int, episode: int) -> Optional[dict]:
        """
        Generate a comprehensive summary for a single episode.
        
        Args:
            season: The season number
            episode: The episode number
            
        Returns:
            Generated summary as a dictionary, or None if failed
        """
        logger.info(f"Generating summary for S{season:02d}E{episode:02d}")
        
        # Get the exact chunk span directly from the database
        chunk_span = self.db_manager.get_episode_chunk_span(season, episode)
        if chunk_span:
            logger.info(f"Found chunk span for S{season:02d}E{episode:02d}: {chunk_span}")
        else:
            logger.warning(f"No chunk span found for S{season:02d}E{episode:02d}")
        
        # Get chunks for the episode
        chunks = self.db_manager.get_episode_chunks(season, episode, include_context=True)
        
        if not chunks:
            logger.error(f"No chunks found for S{season:02d}E{episode:02d}")
            return None
            
        # Count main chunks (excluding context)
        main_chunks = [c for c in chunks if not c.get("is_context", False)]
        logger.info(
            f"Found {len(main_chunks)} chunks for S{season:02d}E{episode:02d} "
            f"(plus {len(chunks) - len(main_chunks)} context chunks)"
        )
        
        # Get previous context based on episode number
        context_text = ""
        
        # FIRST, get previous season summaries (if any)
        # For episodes in season 2+, always add summaries of previous seasons for context
        if season > 1:
            prev_seasons = self.db_manager.get_previous_season_summaries(season)
            if prev_seasons:
                context_text += "## Previous Season Summaries:\n\n"
                # Sort seasons chronologically
                prev_seasons = sorted(prev_seasons, key=lambda x: x["season"])
                
                # If we have too many seasons, limit to the most recent ones to manage prompt size
                if len(prev_seasons) > 2:
                    logger.info(f"Found {len(prev_seasons)} previous seasons, using the 2 most recent for context")
                    prev_seasons = prev_seasons[-2:]
                
                for prev in prev_seasons:
                    prev_season_num = prev["season"]
                    prev_summary = prev["summary"]
                    
                    # Extract just the summary text from the JSONB object
                    if isinstance(prev_summary, dict) and "summary" in prev_summary:
                        summary_content = prev_summary["summary"]
                    else:
                        # Fallback if structure is different
                        summary_content = str(prev_summary)
                    
                    context_text += f"### Season {prev_season_num} Summary:\n\n{summary_content}\n\n"
                    context_text += "-" * 80 + "\n\n"
                
                logger.info(f"Added {len(prev_seasons)} previous season summaries for context")
        
        # SECOND, add any previous episode summaries from the current season
        if episode > 1:
            # For non-first episodes, include previous episode summaries in the same season
            prev_episodes = self.db_manager.get_previous_episode_summaries(season, episode)
            
            if prev_episodes:
                context_text += "## Previous Episode Summaries:\n\n"
                
                # Include ALL previous episodes from the current season, in chronological order
                prev_episodes = sorted(prev_episodes, key=lambda x: x["episode"])
                
                for prev in prev_episodes:
                    prev_episode = prev["episode"]
                    prev_summary = prev["summary"]
                    prev_slug = prev["slug"]
                    
                    # Extract just the summary text from the JSONB object
                    if isinstance(prev_summary, dict) and "summary" in prev_summary:
                        summary_content = prev_summary["summary"]
                    else:
                        # Fallback if structure is different
                        summary_content = str(prev_summary)
                    
                    context_text += f"### {prev_slug} Summary:\n\n{summary_content}\n\n"
                    context_text += "-" * 80 + "\n\n"
                
                logger.info(f"Added all {len(prev_episodes)} previous episode summaries for the current season to the prompt")
        
        # Print context in verbose mode
        if self.verbose and context_text:
            print("\n" + "=" * 80)
            print("CONTEXT BEING USED FOR SUMMARY GENERATION:")
            print("=" * 80)
            print(context_text)
            print("=" * 80 + "\n")
        
        # Prepare the prompt
        system_prompt = self._get_system_prompt("episode")
        chunks_text = self._prepare_chunks_text(chunks, "episode")
        
        # Build the main prompt with context
        prompt = f"""# Episode Summary Request

I need a comprehensive, structured summary of Season {season}, Episode {episode} of the narrative. Please analyze all the provided chunks to create a structured episode summary following the format specified.

{context_text}## The Narrative Chunks:

{chunks_text}

## Important Requirements:

1. Your summary must include ALL five sections exactly as follows:

   - OVERVIEW: A brief, concise summary of what happened (1-2 paragraphs only).
   
   - TIMELINE: The most detailed and extensive section (should be 60-70% of your total response). Break down the episode into many specific events, each starting with "THEN:". Include all significant events in chronological order.
   
   - CHARACTERS: A dictionary mapping character names to their current states.
   
   - PLOT_THREADS: A dictionary of active, resolved, and introduced storylines.
   
   - CONTINUITY_ELEMENTS: A dictionary of important objects, locations, and knowledge.

2. Be objective, factual, and focus on concrete details - your summary will be used by another AI to maintain narrative continuity.

3. Format matters! Your response must follow the exact structure required for machine processing."""
        
        # Token check
        if not self._token_check(prompt, "episode"):
            logger.warning("Token check failed - input may be too long")
            # Proceed anyway - the API will truncate if needed
        
        # Save prompt if requested
        self._save_prompt_to_file(prompt, f"s{season:02d}e{episode:02d}")
        
        try:
            # Use the OpenAI responses.parse API with Pydantic model
            import openai
            
            # Set up the API client - using the direct OpenAI client
            client = openai.OpenAI(api_key=self.provider.api_key)
            
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            if self.provider.system_prompt:
                messages.insert(0, {"role": "system", "content": self.provider.system_prompt})
            
            # Create a simple Pydantic model for episode summary
            class EpisodeSummaryModel(BaseModel):
                summary: str = Field(
                    description="A comprehensive, detailed narrative summary of the episode capturing key plot developments, character actions, revelations, and connections to larger season arcs."
                )
            
            logger.info(f"Using OpenAI responses.parse with model {self.provider.model}")
            
            # Call the API with appropriate parameters based on model type
            if self.is_reasoning_model:
                response = client.responses.parse(
                    model=self.provider.model,
                    input=messages,
                    reasoning={"effort": self.effort},
                    text_format=EpisodeSummaryModel
                )
                logger.info(f"Used reasoning model with effort: {self.effort}")
            else:
                response = client.responses.parse(
                    model=self.provider.model,
                    input=messages,
                    temperature=self.temperature,
                    text_format=EpisodeSummaryModel
                )
                logger.info(f"Used standard model with temperature: {self.temperature}")
            
            # Create a summary dict that matches our expected format
            summary_text = response.output_parsed.summary
            summary_dict = {
                "summary": summary_text
            }
            
            # Log completion info
            logger.info(
                f"Generated episode summary with {response.usage.input_tokens} input tokens and "
                f"{response.usage.output_tokens} output tokens"
            )
            
            # Print summary in verbose mode
            if self.verbose:
                print("\n" + "=" * 80)
                print(f"S{season:02d}E{episode:02d} SUMMARY")
                print("=" * 80)
                print(json.dumps(summary_dict, indent=2))
                print("=" * 80 + "\n")
            
            # Save to database
            success = self.db_manager.save_episode_summary(
                season=season,
                episode=episode,
                summary=summary_dict,
                dry_run=self.dry_run,
                overwrite=self.overwrite,
                chunk_span=chunk_span,
                prompt_on_conflict=self.prompt_on_conflict
            )
            
            if success:
                logger.info(f"Successfully saved summary for S{season:02d}E{episode:02d}")
                return summary_dict
            else:
                logger.error(f"Failed to save summary for S{season:02d}E{episode:02d}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating episode summary: {e}")
            return None
    
    def generate_episode_range_summaries(
        self, 
        start_season: int, 
        start_episode: int,
        end_season: int,
        end_episode: int
    ) -> Dict[str, Optional[dict]]:
        """
        Generate summaries for a range of episodes.
        
        Args:
            start_season: The starting season number
            start_episode: The starting episode number
            end_season: The ending season number
            end_episode: The ending episode number
            
        Returns:
            Dictionary mapping episode slugs to summaries
        """
        logger.info(
            f"Generating summaries for episodes from S{start_season:02d}E{start_episode:02d} "
            f"to S{end_season:02d}E{end_episode:02d}"
        )
        
        # Check if this is a full season
        if (start_season == end_season and 
            start_episode == 1 and 
            self._is_full_season(start_season, end_episode)):
            logger.info(f"This range covers the entire Season {start_season}")
            
            # Ask user if they want to generate a season summary instead
            if not self.dry_run:
                choice = input(
                    f"This range appears to cover the entire Season {start_season}. "
                    f"Would you like to generate a season summary instead? (y/n): "
                ).lower().strip()
                
                if choice == 'y':
                    season_summary = self.generate_season_summary(start_season)
                    return {f"Season {start_season}": season_summary}
        
        # Generate summaries for each episode in the range sequentially
        results = {}
        
        # If same season, simple loop
        if start_season == end_season:
            for episode in range(start_episode, end_episode + 1):
                slug = EpisodeSlugParser.format(start_season, episode)
                
                # Check for abort
                if is_abort_requested():
                    logger.info("Abort requested, stopping generation")
                    break
                    
                # Generate summary (using previously saved summaries as context)
                summary = self.generate_episode_summary(start_season, episode)
                results[slug] = summary
                
                # Immediately save to the database if successful, so it can be used for future episodes
                if summary and not self.dry_run:
                    # Get accurate chunk span
                    chunk_span = self.db_manager.get_episode_chunk_span(start_season, episode)
                    
                    # Save interactive mode behavior - user can decide for each episode
                    saved = self.db_manager.save_episode_summary(
                        season=start_season,
                        episode=episode,
                        summary=summary,
                        dry_run=False,
                        overwrite=self.overwrite,
                        chunk_span=chunk_span,
                        prompt_on_conflict=self.prompt_on_conflict
                    )
                    if saved:
                        logger.info(f"Saved summary for {slug} to database for future episode context")
                
        # If multiple seasons, process them in sequence
        else:
            # First season
            last_episode_of_first_season = self._get_last_episode_of_season(start_season)
            for episode in range(start_episode, last_episode_of_first_season + 1):
                slug = EpisodeSlugParser.format(start_season, episode)
                
                # Check for abort
                if is_abort_requested():
                    logger.info("Abort requested, stopping generation")
                    break
                    
                # Generate summary (using previously saved summaries as context)
                summary = self.generate_episode_summary(start_season, episode)
                results[slug] = summary
                
                # Immediately save to the database if successful, so it can be used for future episodes
                if summary and not self.dry_run:
                    # Get accurate chunk span
                    chunk_span = self.db_manager.get_episode_chunk_span(start_season, episode)
                    
                    # Save interactive mode behavior - user can decide for each episode
                    saved = self.db_manager.save_episode_summary(
                        season=start_season,
                        episode=episode,
                        summary=summary,
                        dry_run=False,
                        overwrite=self.overwrite,
                        chunk_span=chunk_span,
                        prompt_on_conflict=self.prompt_on_conflict
                    )
                    if saved:
                        logger.info(f"Saved summary for {slug} to database for future episode context")
            
            # Middle seasons (if any)
            for season in range(start_season + 1, end_season):
                last_episode = self._get_last_episode_of_season(season)
                for episode in range(1, last_episode + 1):
                    slug = EpisodeSlugParser.format(season, episode)
                    
                    # Check for abort
                    if is_abort_requested():
                        logger.info("Abort requested, stopping generation")
                        break
                        
                    # Generate summary (using previously saved summaries as context)
                    summary = self.generate_episode_summary(season, episode)
                    results[slug] = summary
                    
                    # Immediately save to the database if successful, so it can be used for future episodes
                    if summary and not self.dry_run:
                        # Get accurate chunk span
                        chunk_span = self.db_manager.get_episode_chunk_span(season, episode)
                        
                        # Save interactive mode behavior - user can decide for each episode
                        saved = self.db_manager.save_episode_summary(
                            season=season,
                            episode=episode,
                            summary=summary,
                            dry_run=False,
                            overwrite=self.overwrite,
                            chunk_span=chunk_span,
                            prompt_on_conflict=self.prompt_on_conflict
                        )
                        if saved:
                            logger.info(f"Saved summary for {slug} to database for future episode context")
            
            # Last season
            for episode in range(1, end_episode + 1):
                slug = EpisodeSlugParser.format(end_season, episode)
                
                # Check for abort
                if is_abort_requested():
                    logger.info("Abort requested, stopping generation")
                    break
                    
                # Generate summary (using previously saved summaries as context)
                summary = self.generate_episode_summary(end_season, episode)
                results[slug] = summary
                
                # Immediately save to the database if successful, so it can be used for future episodes
                if summary and not self.dry_run:
                    # Get accurate chunk span
                    chunk_span = self.db_manager.get_episode_chunk_span(end_season, episode)
                    
                    # Save interactive mode behavior - user can decide for each episode
                    saved = self.db_manager.save_episode_summary(
                        season=end_season,
                        episode=episode,
                        summary=summary,
                        dry_run=False,
                        overwrite=self.overwrite,
                        chunk_span=chunk_span,
                        prompt_on_conflict=self.prompt_on_conflict
                    )
                    if saved:
                        logger.info(f"Saved summary for {slug} to database for future episode context")
        
        return results
    
    def generate_chunk_range_summary(self, start_id: int, end_id: int) -> Optional[dict]:
        """
        Generate a summary for a specific range of chunk IDs.
        This is a fallback for manual specification.
        
        Args:
            start_id: Starting chunk ID
            end_id: Ending chunk ID
            
        Returns:
            Generated summary as a dictionary, or None if failed
        """
        logger.info(f"Generating summary for chunk range {start_id}-{end_id}")
        
        # Get chunks for the range
        chunks = self.db_manager.get_chunks_by_id_range(start_id, end_id)
        
        if not chunks:
            logger.error(f"No chunks found for range {start_id}-{end_id}")
            return None
            
        logger.info(f"Found {len(chunks)} chunks for range {start_id}-{end_id}")
        
        # Analyze chunks to determine mode
        seasons = set(chunk["season"] for chunk in chunks if chunk["season"] is not None)
        episodes = set(
            (chunk["season"], chunk["episode"]) 
            for chunk in chunks 
            if chunk["season"] is not None and chunk["episode"] is not None
        )
        
        # Determine if this is a single season, episode, or mixed
        mode = "season" if len(seasons) == 1 and len(episodes) > 1 else "episode"
        
        # Prepare the prompt
        system_prompt = self._get_system_prompt(mode)
        chunks_text = self._prepare_chunks_text(chunks, mode)
        
        # Build the main prompt
        if mode == "season":
            prompt = f"""# Narrative Summary Request

I need a comprehensive, structured summary of the provided narrative chunks (IDs {start_id}-{end_id}), treating them as a complete season. Please analyze all chunks to create a structured season summary following the format specified.

## The Narrative Chunks:

{chunks_text}

## Important Requirements:

1. Your summary must include ALL five required sections: OVERVIEW, CHARACTER_EVOLUTION, NARRATIVE_ARCS, WORLD_DEVELOPMENT, and CONTINUITY_ANCHORS.
2. Focus on patterns, character arcs, and narrative developments that span these chunks as if they were a full season.
3. For CHARACTER_EVOLUTION, document each major character's transformation throughout the chunks.
4. For NARRATIVE_ARCS, identify major storylines and track their progression.
5. Be objective, factual, and comprehensive - your summary will be used by another AI to maintain narrative continuity."""
        else:
            prompt = f"""# Narrative Summary Request

I need a comprehensive, structured summary of the provided narrative chunks (IDs {start_id}-{end_id}), treating them as a complete episode. Please analyze all chunks to create a structured episode summary following the format specified.

## The Narrative Chunks:

{chunks_text}

## Important Requirements:

1. Your summary must include ALL five sections exactly as follows:

   - OVERVIEW: A brief factual summary of what happened in this episode.
   
   - TIMELINE: A list of chronological events, each starting with "THEN:"
   
   - CHARACTERS: A dictionary mapping character names to their current states.
   
   - PLOT_THREADS: A dictionary of active, resolved, and introduced storylines.
   
   - CONTINUITY_ELEMENTS: A dictionary of important objects, locations, and knowledge.

2. Be objective, factual, and focus on concrete details - your summary will be used by another AI to maintain narrative continuity."""
        
        # Token check
        if not self._token_check(prompt, mode):
            logger.warning("Token check failed - input may be too long")
            # Proceed anyway - the API will truncate if needed
        
        # Save prompt if requested
        self._save_prompt_to_file(prompt, f"chunks_{start_id}_{end_id}")
        
        try:
            # Use the OpenAI responses.parse API with Pydantic model
            import openai
            
            # Set up the API client - using the direct OpenAI client
            client = openai.OpenAI(api_key=self.provider.api_key)
            
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            if self.provider.system_prompt:
                messages.insert(0, {"role": "system", "content": self.provider.system_prompt})
            
            # Choose the appropriate response model based on mode
            if mode == "season":
                # Create a more simple Pydantic model for season summary
                class SeasonSummaryModel(BaseModel):
                    summary: str = Field(
                        description="A comprehensive, detailed narrative summary of the entire season capturing major plot developments, character arcs, key world-building elements, and themes."
                    )
                
                logger.info(f"Using season summary model")
                
                # Call the API with appropriate parameters based on model type
                if self.is_reasoning_model:
                    response = client.responses.parse(
                        model=self.provider.model,
                        input=messages,
                        reasoning={"effort": self.effort},
                        text_format=SeasonSummaryModel
                    )
                    logger.info(f"Used reasoning model with effort: {self.effort}")
                else:
                    response = client.responses.parse(
                        model=self.provider.model,
                        input=messages,
                        temperature=self.temperature,
                        text_format=SeasonSummaryModel
                    )
                    logger.info(f"Used standard model with temperature: {self.temperature}")
                
                # Create a summary dict that matches our expected format
                summary_text = response.output_parsed.summary
                summary_dict = {
                    "summary": summary_text
                }
                
            else:
                # Create a more simple Pydantic model for episode summary
                class EpisodeSummaryModel(BaseModel):
                    summary: str = Field(
                        description="A comprehensive, detailed narrative summary of the episode capturing key plot developments, character actions, revelations, and connections to larger season arcs."
                    )
                
                logger.info(f"Using episode summary model")
                
                # Call the API with appropriate parameters based on model type
                if self.is_reasoning_model:
                    response = client.responses.parse(
                        model=self.provider.model,
                        input=messages,
                        reasoning={"effort": self.effort},
                        text_format=EpisodeSummaryModel
                    )
                    logger.info(f"Used reasoning model with effort: {self.effort}")
                else:
                    response = client.responses.parse(
                        model=self.provider.model,
                        input=messages,
                        temperature=self.temperature,
                        text_format=EpisodeSummaryModel
                    )
                    logger.info(f"Used standard model with temperature: {self.temperature}")
                
                # Create a summary dict that matches our expected format
                summary_text = response.output_parsed.summary
                summary_dict = {
                    "summary": summary_text
                }
            
            # Log completion info
            logger.info(
                f"Generated chunk range summary with {response.usage.input_tokens} input tokens and "
                f"{response.usage.output_tokens} output tokens"
            )
            
            # Print summary in verbose mode
            if self.verbose:
                print("\n" + "=" * 80)
                print(f"CHUNK RANGE {start_id}-{end_id} SUMMARY")
                print("=" * 80)
                print(json.dumps(summary_dict, indent=2))
                print("=" * 80 + "\n")
            
            # Determine where to save based on chunks
            if len(seasons) == 1 and mode == "season":
                season = list(seasons)[0]
                success = self.db_manager.save_season_summary(
                    season=season,
                    summary=summary_dict,
                    dry_run=self.dry_run,
                    prompt_on_conflict=self.prompt_on_conflict
                )
                
                if success:
                    logger.info(f"Successfully saved summary for Season {season}")
                else:
                    logger.error(f"Failed to save summary for Season {season}")
                    
            elif len(episodes) == 1:
                season, episode = list(episodes)[0]
                success = self.db_manager.save_episode_summary(
                    season=season,
                    episode=episode,
                    summary=summary_dict,
                    dry_run=self.dry_run,
                    overwrite=self.overwrite,
                    prompt_on_conflict=self.prompt_on_conflict
                )
                
                if success:
                    logger.info(f"Successfully saved summary for S{season:02d}E{episode:02d}")
                else:
                    logger.error(f"Failed to save summary for S{season:02d}E{episode:02d}")
            else:
                logger.info(
                    "Unable to save summary automatically - mixed seasons/episodes. "
                    "Summary will only be displayed."
                )
            
            return summary_dict
                
        except Exception as e:
            logger.error(f"Error generating chunk range summary: {e}")
            return None
    
    def _is_full_season(self, season: int, end_episode: int) -> bool:
        """Check if the episode range covers a full season."""
        last_episode = self._get_last_episode_of_season(season)
        return end_episode >= last_episode
    
    def _get_last_episode_of_season(self, season: int) -> int:
        """Get the last episode number of a season."""
        try:
            with self.db_manager.engine.connect() as conn:
                query = text("""
                SELECT MAX(episode) FROM public.chunk_metadata
                WHERE season = :season
                """)
                
                result = conn.execute(query, {"season": season}).fetchone()
                if result and result[0]:
                    return result[0]
                return 1  # Default to 1 if no episodes found
                
        except Exception as e:
            logger.error(f"Error getting last episode of season {season}: {e}")
            return 1  # Default to 1 on error

def main():
    """Main entry point."""
    # Set up command line argument parser
    parser = argparse.ArgumentParser(
        description="Generate comprehensive narrative summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Create mutually exclusive group for input modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--season", type=int, help="Season number to summarize")
    mode_group.add_argument("--episode", nargs='+', help="Episode(s) to summarize (e.g., s03e01 or s03e01 s03e13 for range)")
    mode_group.add_argument("--chunks", nargs=2, type=int, help="Chunk ID range to summarize (manual fallback)")
    
    # OpenAI options
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--fallback-model",
        default=FALLBACK_MODEL,
        help=f"Alternate model to try if the primary fails (default: {FALLBACK_MODEL})"
    )
    parser.add_argument(
        "--disable-fallback",
        action="store_true",
        help="Do not attempt a fallback model if the primary fails"
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                      help=f"Model temperature for standard models (default: {DEFAULT_TEMPERATURE})")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="medium",
                      help="Reasoning effort level for reasoning models (default: medium)")
    
    # Processing options
    parser.add_argument("--dry-run", action="store_true", help="Don't save summaries to database")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing summaries in the database")
    parser.add_argument("--non-interactive", action="store_true", help="Skip overwrite prompts and keep existing summaries")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output including summaries")
    parser.add_argument("--save-prompt", action="store_true", help="Save prompts to files for debugging")
    parser.add_argument("--db-url", help="Database connection URL (optional)")
    parser.add_argument("--disable-abort", action="store_true", help="Disable ESC key and Ctrl+C abort capability")
    
    args = parser.parse_args()
    
    # Set up database manager
    db_manager = DatabaseManager(db_url=args.db_url)
    
    # Set up abort handler (unless disabled)
    if not args.disable_abort:
        setup_abort_handler("Abort requested! Finishing current summary and stopping...")
        logger.info("Abort functionality enabled - Press ESC or Ctrl+C to stop processing")
    else:
        logger.info("Abort functionality disabled")
    
    # Build model preference list and helpers
    model_candidates: List[str] = []
    if args.model:
        model_candidates.append(args.model)
    if (
        not args.disable_fallback
        and args.fallback_model
        and args.fallback_model not in model_candidates
    ):
        model_candidates.append(args.fallback_model)

    def build_generator(model_name: str) -> SummaryGenerator:
        return SummaryGenerator(
            model=model_name,
            temperature=args.temperature,
            effort=args.effort,
            db_manager=db_manager,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            verbose=args.verbose,
            save_prompt=args.save_prompt,
            prompt_on_conflict=not args.non_interactive
        )

    def run_with_models(run_fn):
        for index, model_name in enumerate(model_candidates):
            generator = build_generator(model_name)
            result = run_fn(generator)
            if result:
                if model_name != args.model:
                    logger.info(f"Used fallback model {model_name}")
                return result, model_name
            if index < len(model_candidates) - 1:
                logger.warning(f"Model {model_name} did not produce a summary; trying next candidate")
            else:
                logger.error(f"Model {model_name} did not produce a summary; no more fallback models to try")
        return None, None
    
    start_time = time.time()
    
    # Process based on mode
    if args.season:
        # Season mode
        summary, used_model = run_with_models(
            lambda gen: gen.generate_season_summary(args.season)
        )
        
        if summary:
            logger.info(f"Successfully generated summary for Season {args.season} using {used_model}")
            if args.dry_run:
                logger.info("[DRY RUN] Summary not saved to database")
        else:
            logger.error(f"Failed to generate summary for Season {args.season}")
            
    elif args.episode:
        # Episode mode
        if len(args.episode) == 1:
            # Single episode
            try:
                season, episode = EpisodeSlugParser.parse(args.episode[0])
                summary, used_model = run_with_models(
                    lambda gen: gen.generate_episode_summary(season, episode)
                )
                
                if summary:
                    logger.info(
                        f"Successfully generated summary for S{season:02d}E{episode:02d} using {used_model}"
                    )
                    if args.dry_run:
                        logger.info("[DRY RUN] Summary not saved to database")
                else:
                    logger.error(f"Failed to generate summary for S{season:02d}E{episode:02d}")
                    
            except ValueError as e:
                logger.error(f"Error parsing episode slug: {e}")
                return 1
                
        elif len(args.episode) == 2:
            # Episode range
            try:
                start_slug = args.episode[0]
                end_slug = args.episode[1]
                
                if not EpisodeSlugParser.validate_range(start_slug, end_slug):
                    logger.error(f"Invalid episode range: {start_slug} to {end_slug}")
                    return 1
                
                start_season, start_episode = EpisodeSlugParser.parse(start_slug)
                end_season, end_episode = EpisodeSlugParser.parse(end_slug)
                
                results, used_model = run_with_models(
                    lambda gen: gen.generate_episode_range_summaries(
                        start_season, start_episode, end_season, end_episode
                    )
                )
                
                # Print summary
                if results:
                    success_count = sum(1 for summary in results.values() if summary is not None)
                    logger.info(
                        f"Generated {success_count} out of {len(results)} episode summaries "
                        f"for range {start_slug} to {end_slug} using {used_model}"
                    )
                    
                    if args.dry_run:
                        logger.info("[DRY RUN] Summaries not saved to database")
                else:
                    logger.error(f"Failed to generate summaries for range {start_slug} to {end_slug}")
                    
            except ValueError as e:
                logger.error(f"Error parsing episode slugs: {e}")
                return 1
                
        else:
            logger.error("Invalid number of episode arguments. Use one slug for a single episode, or two for a range.")
            return 1
            
    elif args.chunks:
        # Chunk range mode
        start_id, end_id = args.chunks
        
        if start_id > end_id:
            logger.error(f"Invalid chunk range: {start_id} to {end_id}")
            return 1
            
        summary, used_model = run_with_models(
            lambda gen: gen.generate_chunk_range_summary(start_id, end_id)
        )
        
        if summary:
            logger.info(f"Successfully generated summary for chunk range {start_id}-{end_id} using {used_model}")
            if args.dry_run:
                logger.info("[DRY RUN] Summary not saved to database")
        else:
            logger.error(f"Failed to generate summary for chunk range {start_id}-{end_id}")
    
    # Print timing info
    end_time = time.time()
    elapsed = end_time - start_time
    logger.info(f"Total processing time: {elapsed:.2f} seconds")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
