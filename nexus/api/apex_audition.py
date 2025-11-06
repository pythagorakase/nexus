"""
FastAPI application for Apex Audition comparison system.

Provides REST API endpoints for:
- Fetching comparison queues
- Recording judgments
- Updating ELO ratings
- Viewing leaderboards
- Exporting comparisons
- Generation job management
"""
from datetime import datetime
import logging
import random
import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import hashlib

from nexus.api.models import (
    Condition,
    Generation,
    Prompt,
    ComparisonCreate,
    ELORating,
    ComparisonQueueItem,
    GenerationRun,
    AsyncGenerationStatus,
    RegenerateGenerationRequest,
    RegenerateGenerationResponse,
)
from nexus.audition.elo import calculate_elo_update, outcome_from_winner
from nexus.audition import AuditionEngine

# Database connection parameters
DB_PARAMS = {
    "dbname": "NEXUS",
    "user": "pythagor",
    "host": "localhost",
    "port": 5432
}

app = FastAPI(title="Apex Audition API", version="1.0.0")

LOGGER = logging.getLogger(__name__)

# Configure CORS for local development
# Allow all localhost origins since UI uses dynamic port selection
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for generation jobs
generation_jobs: Dict[str, Dict] = {}
ROOT_DIR = Path(__file__).resolve().parents[2]
AUTO_POLL_STATUS_FILE = ROOT_DIR / "logs" / "auto_poll_status.json"


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)


@app.get("/api/audition/runs", response_model=List[GenerationRun])
def list_generation_runs():
    """List all generation runs."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    gr.id::text,
                    gr.description as label,
                    gr.created_at as started_at,
                    NULL::timestamp as completed_at,
                    COUNT(g.id) as total_generations,
                    COUNT(g.id) FILTER (WHERE g.status = 'completed') as completed_generations,
                    COUNT(g.id) FILTER (WHERE g.status = 'error') as failed_generations
                FROM apex_audition.generation_runs gr
                LEFT JOIN apex_audition.generations g ON g.run_id = gr.id
                GROUP BY gr.id, gr.description, gr.created_at
                ORDER BY gr.created_at DESC
            """)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


@app.get("/api/audition/conditions", response_model=List[Condition])
def list_conditions():
    """List all active conditions."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, slug, provider, model_name, label,
                    temperature, reasoning_effort, thinking_enabled,
                    max_output_tokens, thinking_budget_tokens, is_active, notes
                FROM apex_audition.conditions
                WHERE is_active = true
                ORDER BY provider, model_name, temperature
            """)
            rows = cur.fetchall()
            return [
                Condition(
                    id=row['id'],
                    slug=row['slug'],
                    provider=row['provider'],
                    model=row['model_name'],
                    label=row.get('label'),
                    temperature=row.get('temperature'),
                    reasoning_effort=row.get('reasoning_effort'),
                    thinking_enabled=row.get('thinking_enabled'),
                    max_output_tokens=row.get('max_output_tokens'),
                    thinking_budget_tokens=row.get('thinking_budget_tokens'),
                    is_active=row['is_active'],
                    notes=row.get('notes'),
                )
                for row in rows
            ]


@app.get("/api/audition/prompts", response_model=List[Prompt])
def list_prompts():
    """List all prompts."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, chunk_id, category, label, context, metadata
                FROM apex_audition.prompts
                ORDER BY chunk_id
            """)
            rows = cur.fetchall()
            return [
                Prompt(
                    id=row['id'],
                    chunk_id=row['chunk_id'],
                    category=row.get('category'),
                    label=row.get('label'),
                    context=row['context'],
                    metadata=row['metadata'],
                )
                for row in rows
            ]


@app.get("/api/audition/comparisons/next", response_model=Optional[ComparisonQueueItem])
def get_next_comparison(
    run_id: Optional[str] = Query(None),
    condition_a_id: Optional[int] = Query(None),
    condition_b_id: Optional[int] = Query(None),
    condition_ids: Optional[str] = Query(None),
    prompt_id: Optional[int] = Query(None),
    prompt_ids: Optional[str] = Query(None),
):
    """
    Get the next pending comparison.

    Uses a two-step selection process to balance exposure:
    1. Select one condition with bias towards low exposure (games_played)
    2. Select a random pairing condition from valid candidates

    This ensures under-exposed lanes compete against a random mix of lanes
    rather than primarily against other under-exposed lanes.

    If run_id is specified, only return comparisons from that run.
    If condition IDs are specified, only return comparisons between those conditions.
    If condition_ids is specified (comma-separated), filter to comparisons within that pool.
    If prompt_id or prompt_ids is specified, filter to those prompts.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build base filter conditions for both queries
            base_conditions = []
            params = []

            if run_id:
                base_conditions.append("g.run_id = %s")
                params.append(run_id)

            if condition_a_id and condition_b_id:
                # Special case: specific pair requested
                base_conditions.append("g.condition_id IN (%s, %s)")
                params.extend([condition_a_id, condition_b_id])
            elif condition_ids:
                # Parse comma-separated condition IDs
                cond_id_list = [int(cid.strip()) for cid in condition_ids.split(',') if cid.strip()]
                if cond_id_list:
                    placeholders = ','.join(['%s'] * len(cond_id_list))
                    base_conditions.append(f"g.condition_id IN ({placeholders})")
                    params.extend(cond_id_list)

            prompt_filter = ""
            prompt_params = []
            if prompt_id:
                prompt_filter = "AND g.prompt_id = %s"
                prompt_params.append(prompt_id)
            elif prompt_ids:
                # Parse comma-separated prompt IDs
                prompt_id_list = [int(pid.strip()) for pid in prompt_ids.split(',') if pid.strip()]
                if prompt_id_list:
                    placeholders = ','.join(['%s'] * len(prompt_id_list))
                    prompt_filter = f"AND g.prompt_id IN ({placeholders})"
                    prompt_params.extend(prompt_id_list)

            base_where = " AND ".join(base_conditions) if base_conditions else "TRUE"

            # Step 1: Select one condition with bias towards low exposure
            query_biased = f"""
                SELECT
                    g.id as generation_id,
                    g.condition_id,
                    g.prompt_id,
                    g.replicate_index,
                    COALESCE(e.games_played, 0) as exposure
                FROM apex_audition.generations g
                JOIN apex_audition.conditions c ON c.id = g.condition_id
                LEFT JOIN apex_audition.elo_ratings e ON e.condition_id = g.condition_id
                WHERE g.status = 'completed'
                  AND c.is_active = true
                  AND {base_where}
                  {prompt_filter}
                ORDER BY exposure ASC, RANDOM()
                LIMIT 1
            """

            cur.execute(query_biased, params + prompt_params)
            biased_row = cur.fetchone()

            if not biased_row:
                return None

            biased_generation_id = biased_row["generation_id"]
            biased_condition_id = biased_row["condition_id"]
            biased_prompt_id = biased_row["prompt_id"]
            biased_replicate_index = biased_row["replicate_index"]

            # Step 2: Select a random pairing condition that:
            # - Is from the same prompt
            # - Has the same replicate_index
            # - Is a different condition
            # - Has no existing comparison with the biased condition
            query_random = f"""
                SELECT g.id as generation_id
                FROM apex_audition.generations g
                JOIN apex_audition.conditions c ON c.id = g.condition_id
                WHERE g.status = 'completed'
                  AND {base_where}
                  AND g.prompt_id = %s
                  AND g.replicate_index = %s
                  AND g.condition_id != %s
                  AND c.is_active = true
                  AND NOT EXISTS (
                    SELECT 1 FROM apex_audition.comparisons comp
                    WHERE comp.prompt_id = g.prompt_id
                      AND ((comp.condition_a_id = %s AND comp.condition_b_id = g.condition_id)
                           OR (comp.condition_a_id = g.condition_id AND comp.condition_b_id = %s))
                  )
                ORDER BY RANDOM()
                LIMIT 1
            """

            random_params = params + [
                biased_prompt_id,
                biased_replicate_index,
                biased_condition_id,
                biased_condition_id,
                biased_condition_id,
            ]
            cur.execute(query_random, random_params)
            random_row = cur.fetchone()

            if not random_row:
                return None

            random_generation_id = random_row["generation_id"]

            # Step 3: Fetch full details for both generations
            fetch_query = """
                SELECT
                    p.id AS prompt_id,
                    p.chunk_id AS prompt_chunk_id,
                    p.category AS prompt_category,
                    p.label AS prompt_label,
                    p.context AS prompt_context,
                    p.metadata AS prompt_metadata,
                    c.id AS condition_id,
                    c.slug AS condition_slug,
                    c.provider AS condition_provider,
                    c.model_name AS condition_model_name,
                    c.label AS condition_label,
                    c.temperature AS condition_temperature,
                    c.reasoning_effort AS condition_reasoning_effort,
                    c.thinking_enabled AS condition_thinking_enabled,
                    c.max_output_tokens AS condition_max_output_tokens,
                    c.thinking_budget_tokens AS condition_thinking_budget_tokens,
                    c.is_active AS condition_is_active,
                    g.id AS generation_id,
                    g.condition_id AS generation_condition_id,
                    g.prompt_id AS generation_prompt_id,
                    g.replicate_index AS generation_replicate_index,
                    g.status AS generation_status,
                    g.response_payload AS generation_response_payload,
                    g.input_tokens AS generation_input_tokens,
                    g.output_tokens AS generation_output_tokens,
                    g.completed_at AS generation_completed_at
                FROM apex_audition.generations g
                JOIN apex_audition.conditions c ON c.id = g.condition_id
                JOIN apex_audition.prompts p ON p.id = g.prompt_id
                WHERE g.id IN (%s, %s)
            """

            cur.execute(fetch_query, [biased_generation_id, random_generation_id])
            detail_rows = cur.fetchall()

            if len(detail_rows) != 2:
                return None

            # Build response objects
            # First row is biased, second is random (but we'll shuffle at the end)
            row_map = {row["generation_id"]: row for row in detail_rows}
            biased_detail = row_map[biased_generation_id]
            random_detail = row_map[random_generation_id]

            # Use the first row for prompt details (they're the same)
            prompt_row = detail_rows[0]
            prompt = Prompt(
                id=prompt_row["prompt_id"],
                chunk_id=prompt_row["prompt_chunk_id"],
                category=prompt_row.get("prompt_category"),
                label=prompt_row.get("prompt_label"),
                context=prompt_row["prompt_context"],
                metadata=prompt_row["prompt_metadata"],
            )

            # Build condition and generation objects for biased selection
            condition_a = Condition(
                id=biased_detail["condition_id"],
                slug=biased_detail["condition_slug"],
                provider=biased_detail["condition_provider"],
                model=biased_detail["condition_model_name"],
                label=biased_detail.get("condition_label"),
                temperature=biased_detail.get("condition_temperature"),
                reasoning_effort=biased_detail.get("condition_reasoning_effort"),
                thinking_enabled=biased_detail.get("condition_thinking_enabled"),
                max_output_tokens=biased_detail.get("condition_max_output_tokens"),
                thinking_budget_tokens=biased_detail.get("condition_thinking_budget_tokens"),
                is_active=biased_detail["condition_is_active"],
            )

            generation_a = Generation(
                id=biased_detail["generation_id"],
                condition_id=biased_detail["generation_condition_id"],
                prompt_id=biased_detail["generation_prompt_id"],
                replicate_index=biased_detail["generation_replicate_index"],
                status=biased_detail["generation_status"],
                response_payload=biased_detail["generation_response_payload"],
                input_tokens=biased_detail.get("generation_input_tokens"),
                output_tokens=biased_detail.get("generation_output_tokens"),
                completed_at=biased_detail.get("generation_completed_at"),
            )

            # Build condition and generation objects for random selection
            condition_b = Condition(
                id=random_detail["condition_id"],
                slug=random_detail["condition_slug"],
                provider=random_detail["condition_provider"],
                model=random_detail["condition_model_name"],
                label=random_detail.get("condition_label"),
                temperature=random_detail.get("condition_temperature"),
                reasoning_effort=random_detail.get("condition_reasoning_effort"),
                thinking_enabled=random_detail.get("condition_thinking_enabled"),
                max_output_tokens=random_detail.get("condition_max_output_tokens"),
                thinking_budget_tokens=random_detail.get("condition_thinking_budget_tokens"),
                is_active=random_detail["condition_is_active"],
            )

            generation_b = Generation(
                id=random_detail["generation_id"],
                condition_id=random_detail["generation_condition_id"],
                prompt_id=random_detail["generation_prompt_id"],
                replicate_index=random_detail["generation_replicate_index"],
                status=random_detail["generation_status"],
                response_payload=random_detail["generation_response_payload"],
                input_tokens=random_detail.get("generation_input_tokens"),
                output_tokens=random_detail.get("generation_output_tokens"),
                completed_at=random_detail.get("generation_completed_at"),
            )

            # Randomly shuffle left/right assignment
            if random.random() < 0.5:
                condition_a, condition_b = condition_b, condition_a
                generation_a, generation_b = generation_b, generation_a

            return ComparisonQueueItem(
                prompt=prompt,
                condition_a=condition_a,
                condition_b=condition_b,
                generation_a=generation_a,
                generation_b=generation_b,
            )


@app.post("/api/audition/comparisons", response_model=dict)
def create_comparison(comparison: ComparisonCreate):
    """
    Record a comparison judgment and update ELO ratings.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Insert comparison
            cur.execute("""
                INSERT INTO apex_audition.comparisons
                (prompt_id, condition_a_id, condition_b_id, winner_condition_id, evaluator, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                comparison.prompt_id,
                comparison.condition_a_id,
                comparison.condition_b_id,
                comparison.winner_condition_id,
                comparison.evaluator,
                comparison.notes
            ))
            result = cur.fetchone()
            comparison_id = result['id']
            created_at = result['created_at']

            # Get current ELO ratings (or initialize if not exists)
            cur.execute("""
                INSERT INTO apex_audition.elo_ratings (condition_id, rating, games_played)
                VALUES (%s, 1500, 0), (%s, 1500, 0)
                ON CONFLICT (condition_id) DO NOTHING
            """, (comparison.condition_a_id, comparison.condition_b_id))

            cur.execute("""
                SELECT condition_id, rating, games_played
                FROM apex_audition.elo_ratings
                WHERE condition_id IN (%s, %s)
            """, (comparison.condition_a_id, comparison.condition_b_id))
            ratings = {row['condition_id']: row for row in cur.fetchall()}

            rating_a = ratings[comparison.condition_a_id]['rating']
            rating_b = ratings[comparison.condition_b_id]['rating']

            # Calculate outcome
            outcome = outcome_from_winner(
                comparison.winner_condition_id,
                comparison.condition_a_id,
                comparison.condition_b_id
            )

            # Update ELO ratings
            new_a, new_b = calculate_elo_update(rating_a, rating_b, outcome)

            # Update database
            cur.execute("""
                UPDATE apex_audition.elo_ratings
                SET rating = %s, games_played = games_played + 1, last_updated = NOW()
                WHERE condition_id = %s
            """, (new_a, comparison.condition_a_id))

            cur.execute("""
                UPDATE apex_audition.elo_ratings
                SET rating = %s, games_played = games_played + 1, last_updated = NOW()
                WHERE condition_id = %s
            """, (new_b, comparison.condition_b_id))

            # Record ELO history
            cur.execute("""
                INSERT INTO apex_audition.elo_history
                (condition_id, comparison_id, rating, rating_delta)
                VALUES
                (%s, %s, %s, %s),
                (%s, %s, %s, %s)
            """, (
                comparison.condition_a_id, comparison_id, new_a, new_a - rating_a,
                comparison.condition_b_id, comparison_id, new_b, new_b - rating_b
            ))

            conn.commit()

            return {
                "id": comparison_id,
                "created_at": created_at,
                "elo_ratings": {
                    "condition_a": {"rating": new_a, "delta": new_a - rating_a},
                    "condition_b": {"rating": new_b, "delta": new_b - rating_b}
                }
            }


@app.get("/api/audition/leaderboard", response_model=List[ELORating])
def get_leaderboard(limit: int = Query(10, ge=1, le=100)):
    """Get ELO leaderboard."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.condition_id,
                    e.rating,
                    e.games_played,
                    e.last_updated,
                    c.id, c.slug, c.provider, c.model_name, c.label,
                    c.temperature, c.reasoning_effort, c.thinking_enabled,
                    c.max_output_tokens, c.thinking_budget_tokens, c.is_active, c.notes
                FROM apex_audition.elo_ratings e
                JOIN apex_audition.conditions c ON c.id = e.condition_id
                WHERE c.is_active = true
                ORDER BY e.rating DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()

            return [
                ELORating(
                    condition_id=row['condition_id'],
                    condition=Condition(
                        id=row['id'],
                        slug=row['slug'],
                        provider=row['provider'],
                        model_name=row['model_name'],
                        label=row['label'],
                        temperature=row['temperature'],
                        reasoning_effort=row['reasoning_effort'],
                        thinking_enabled=row['thinking_enabled'],
                        max_output_tokens=row['max_output_tokens'],
                        thinking_budget_tokens=row['thinking_budget_tokens'],
                        is_active=row['is_active'],
                        notes=row['notes']
                    ),
                    rating=row['rating'],
                    games_played=row['games_played'],
                    last_updated=row['last_updated']
                )
                for row in rows
            ]


@app.get("/api/audition/export/{comparison_id}")
def export_comparison(comparison_id: int):
    """Export a comparison to JSON for external review."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    c.*,
                    p.context, p.metadata,
                    ga.response_payload as response_a,
                    gb.response_payload as response_b,
                    ca.slug as condition_a_slug,
                    cb.slug as condition_b_slug
                FROM apex_audition.comparisons c
                JOIN apex_audition.prompts p ON p.id = c.prompt_id
                JOIN apex_audition.generations ga ON ga.condition_id = c.condition_a_id
                    AND ga.prompt_id = c.prompt_id
                JOIN apex_audition.generations gb ON gb.condition_id = c.condition_b_id
                    AND gb.prompt_id = c.prompt_id
                JOIN apex_audition.conditions ca ON ca.id = c.condition_a_id
                JOIN apex_audition.conditions cb ON cb.id = c.condition_b_id
                WHERE c.id = %s
            """, (comparison_id,))
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Comparison not found")

            return dict(row)


# ============================================================================
# Generation Job Management Endpoints
# ============================================================================

@app.get("/api/audition/generate/count")
def get_missing_generation_count():
    """Get count of prompt×condition combinations that need generation."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get replicate count from global settings
            cur.execute("SELECT replicate_count FROM apex_audition.global_settings WHERE id = TRUE")
            settings_row = cur.fetchone()
            replicate_count = settings_row["replicate_count"] if settings_row else 1

            cur.execute("""
                SELECT COUNT(*) as count
                FROM apex_audition.prompts p
                CROSS JOIN apex_audition.conditions c
                WHERE c.is_active = TRUE
                  AND (
                      SELECT COUNT(*)
                      FROM apex_audition.generations g
                      WHERE g.prompt_id = p.id
                        AND g.condition_id = c.id
                        AND g.status = 'completed'
                        AND g.response_payload->>'content' IS NOT NULL
                        AND LENGTH(g.response_payload->>'content') > 0
                  ) < %s
            """, (replicate_count,))
            row = cur.fetchone()
            count = row["count"] if row else 0
            return {"count": count}


@app.get("/api/audition/generate/missing")
def get_missing_generations():
    """Get detailed list of prompt×condition combinations that need generation."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get replicate count from global settings
            cur.execute("SELECT replicate_count FROM apex_audition.global_settings WHERE id = TRUE")
            settings_row = cur.fetchone()
            replicate_count = settings_row["replicate_count"] if settings_row else 1

            cur.execute("""
                SELECT
                    p.id as prompt_id,
                    p.chunk_id,
                    p.label as prompt_label,
                    p.category as prompt_category,
                    c.id as condition_id,
                    c.slug as condition_slug,
                    c.label as condition_label,
                    c.provider,
                    c.model_name
                FROM apex_audition.prompts p
                CROSS JOIN apex_audition.conditions c
                WHERE c.is_active = TRUE
                  AND (
                      SELECT COUNT(*)
                      FROM apex_audition.generations g
                      WHERE g.prompt_id = p.id
                        AND g.condition_id = c.id
                        AND g.status = 'completed'
                        AND g.response_payload->>'content' IS NOT NULL
                        AND LENGTH(g.response_payload->>'content') > 0
                  ) < %s
                ORDER BY c.slug, p.chunk_id
            """, (replicate_count,))
            rows = cur.fetchall()
            return [dict(row) for row in rows]


@app.get("/api/audition/generate/task-count")
def get_generation_task_count(
    limit: Optional[int] = None,
    async_providers: Optional[str] = None
):
    """
    Calculate how many tasks will be executed with the given parameters.

    This pre-flight calculation matches the logic in run_full_sequential.py
    to show exactly how many tasks will run when Start Generation is clicked.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get replicate count from global settings
            cur.execute("SELECT replicate_count FROM apex_audition.global_settings WHERE id = TRUE")
            settings_row = cur.fetchone()
            replicate_count = settings_row["replicate_count"] if settings_row else 1

            # Get all active conditions
            cur.execute("""
                SELECT id, slug, provider
                FROM apex_audition.conditions
                WHERE is_active = TRUE
                ORDER BY provider, slug
            """)
            conditions = cur.fetchall()

            # Get all prompts (excluding test fixtures)
            TEST_CHUNK_IDS = {4242}
            cur.execute("""
                SELECT id, chunk_id
                FROM apex_audition.prompts
                WHERE chunk_id NOT IN %s
                ORDER BY chunk_id, id
            """, (tuple(TEST_CHUNK_IDS),))
            prompts = cur.fetchall()

            # Build task list using same logic as run_full_sequential.py
            tasks = []

            if limit is not None and limit > 0:
                # Limit mode: sample one incomplete task per condition (up to limit)
                conditions_sampled = 0
                for condition in conditions:
                    if conditions_sampled >= limit:
                        break
                    # Find first incomplete task for this condition
                    for prompt in prompts:
                        # Check if all replicates are completed
                        cur.execute("""
                            SELECT COUNT(*) as completed_count
                            FROM apex_audition.generations
                            WHERE condition_id = %s
                              AND prompt_id = %s
                              AND status = 'completed'
                        """, (condition['id'], prompt['id']))
                        result = cur.fetchone()
                        completed_count = result['completed_count'] if result else 0

                        if completed_count < replicate_count:
                            tasks.append((condition['id'], prompt['id']))
                            conditions_sampled += 1
                            break  # Move to next condition
            else:
                # No limit: execute all incomplete tasks
                for prompt in prompts:
                    for condition in conditions:
                        # Check if all replicates are completed
                        cur.execute("""
                            SELECT COUNT(*) as completed_count
                            FROM apex_audition.generations
                            WHERE condition_id = %s
                              AND prompt_id = %s
                              AND status = 'completed'
                        """, (condition['id'], prompt['id']))
                        result = cur.fetchone()
                        completed_count = result['completed_count'] if result else 0

                        if completed_count < replicate_count:
                            tasks.append((condition['id'], prompt['id']))

            return {"task_count": len(tasks)}


@app.post("/api/audition/generate/start")
def start_generation(
    limit: Optional[int] = None,
    max_workers: Optional[int] = None,
    async_providers: Optional[str] = None
):
    """Start a generation job with optional async provider routing."""
    job_id = str(uuid.uuid4())

    # Get project root (parent of nexus/api/)
    project_root = Path(__file__).parent.parent.parent
    script_path = project_root / "scripts" / "run_full_sequential.py"

    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_path}")

    # Pre-fetch API keys from 1Password to avoid multiple TouchID prompts
    # This is done once here instead of in each parallel worker
    import os
    env = os.environ.copy()

    def _prefetch_required_secret(command: List[str], env_key: str) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail=(
                    "1Password CLI (op) not found. Install from "
                    "https://developer.1password.com/docs/cli/get-started/"
                ),
            )
        except subprocess.CalledProcessError:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve API keys from 1Password. Ensure you're signed in with 'op signin'.",
            )

        env[env_key] = result.stdout.strip()

    def _prefetch_optional_secret(command: List[str], env_key: str, label: str) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError:
            LOGGER.warning("1Password CLI not found; unable to prefetch %s", label)
            return
        except subprocess.CalledProcessError as exc:
            LOGGER.warning(
                "Failed to prefetch %s (exit %s). Continuing without cached key.",
                label,
                exc.returncode,
            )
            return

        value = result.stdout.strip()
        if not value:
            LOGGER.warning("Prefetched empty %s; continuing without cached key", label)
            return

        env[env_key] = value

    # Fetch native provider API keys only for async providers (batch mode)
    # Parse async_providers to determine which keys to fetch
    if async_providers:
        providers_list = [p.strip().lower() for p in async_providers.split(',') if p.strip()]

        if "anthropic" in providers_list:
            _prefetch_required_secret(
                ["op", "read", "op://API/Anthropic/api key"],
                "ANTHROPIC_API_KEY"
            )

        if "openai" in providers_list:
            _prefetch_required_secret(
                [
                    "op",
                    "item",
                    "get",
                    "tyrupcepa4wluec7sou4e7mkza",
                    "--fields",
                    "api key",
                    "--reveal",
                ],
                "OPENAI_API_KEY",
            )

    # Build command with optional limit and max_workers
    cmd = ["python", str(script_path)]
    if limit is not None and limit > 0:
        cmd.extend(["--limit", str(limit)])
    if max_workers is not None and max_workers > 0:
        cmd.extend(["--max-workers", str(max_workers)])
    if async_providers:
        cmd.extend(["--async-providers", async_providers])

    # Start subprocess with pre-fetched API keys in environment
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(project_root),
        bufsize=1,  # Line buffered
        env=env  # Pass environment with API keys
    )

    # Buffer to capture output
    output_lines = []

    def capture_output():
        """Capture subprocess output in background thread."""
        try:
            for line in process.stdout:
                output_lines.append(line.rstrip())
        except Exception:
            pass  # Process terminated

    # Start capture thread
    thread = threading.Thread(target=capture_output, daemon=True)
    thread.start()

    # Store job info
    generation_jobs[job_id] = {
        "process": process,
        "thread": thread,
        "output": output_lines,
        "started_at": datetime.now(),
        "script": "run_full_sequential.py"
    }

    return {"job_id": job_id, "status": "started"}


@app.get("/api/audition/generate/status")
def get_generation_status(job_id: str = Query(...)):
    """Get status of a generation job."""
    job = generation_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    process = job["process"]

    if process.poll() is None:
        return {"status": "running", "job_id": job_id}
    else:
        exit_code = process.returncode
        return {
            "status": "completed" if exit_code == 0 else "failed",
            "job_id": job_id,
            "exit_code": exit_code
        }


@app.get("/api/audition/generate/output")
def get_generation_output(job_id: str = Query(...)):
    """Get output and stats from a generation job."""
    job = generation_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get output lines
    output_lines = job["output"]
    output = "\n".join(output_lines)

    # Parse latest stats from output
    stats = None
    for line in reversed(output_lines):
        match = re.search(
            r'Total: (\d+) \| Remaining: (\d+) \| Completed: (\d+) \| Failed: (\d+)',
            line
        )
        if match:
            stats = {
                "total": int(match.group(1)),
                "remaining": int(match.group(2)),
                "completed": int(match.group(3)),
                "failed": int(match.group(4))
            }
            break

    # Get status
    process = job["process"]
    status = "running" if process.poll() is None else "completed"

    return {
        "output": output,
        "stats": stats,
        "status": status,
        "job_id": job_id
    }


@app.get("/api/audition/generate/async-status", response_model=AsyncGenerationStatus)
def get_async_generation_status():
    """Expose pending async workload and last poll heartbeat."""
    remaining_generations = 0
    pending_requests = 0
    pending_batches = 0
    oldest_batch_age_hours = None
    has_aging_batches = False

    statuses = ['batch_pending', 'pending', 'queued', 'submitted', 'in_progress', 'processing']

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT replicate_count FROM apex_audition.global_settings WHERE id = TRUE")
            settings_row = cur.fetchone()
            replicate_count = settings_row["replicate_count"] if settings_row else 1

            cur.execute(
                """
                SELECT COUNT(*) as count
                FROM apex_audition.prompts p
                CROSS JOIN apex_audition.conditions c
                WHERE c.is_active = TRUE
                  AND (
                      SELECT COUNT(*)
                      FROM apex_audition.generations g
                      WHERE g.prompt_id = p.id
                        AND g.condition_id = c.id
                        AND g.status = 'completed'
                        AND g.response_payload->>'content' IS NOT NULL
                        AND LENGTH(g.response_payload->>'content') > 0
                  ) < %s
                """,
                (replicate_count,),
            )
            remaining_row = cur.fetchone()
            remaining_generations = remaining_row["count"] if remaining_row else 0

            # Count only actual async batch requests (not orphaned records)
            cur.execute(
                """
                SELECT COUNT(*) AS pending
                FROM apex_audition.generations
                WHERE status = 'batch_pending'
                  AND batch_job_id IS NOT NULL
                """
            )
            pending_row = cur.fetchone()
            pending_requests = pending_row["pending"] if pending_row else 0

            cur.execute(
                """
                SELECT COUNT(DISTINCT batch_job_id) AS batch_count
                FROM apex_audition.generations
                WHERE status = 'batch_pending'
                  AND batch_job_id IS NOT NULL
                """
            )
            batch_row = cur.fetchone()
            pending_batches = batch_row["batch_count"] if batch_row else 0

            # Get age of oldest pending batch
            if pending_batches > 0:
                cur.execute(
                    """
                    SELECT MIN(started_at) AS oldest_start
                    FROM apex_audition.generations
                    WHERE status = 'batch_pending'
                      AND batch_job_id IS NOT NULL
                    """
                )
                age_row = cur.fetchone()
                if age_row and age_row["oldest_start"]:
                    from datetime import timezone
                    oldest_start = age_row["oldest_start"]
                    if oldest_start.tzinfo is None:
                        oldest_start = oldest_start.replace(tzinfo=timezone.utc)
                    age_delta = datetime.now(timezone.utc) - oldest_start
                    oldest_batch_age_hours = age_delta.total_seconds() / 3600
                    has_aging_batches = oldest_batch_age_hours > 24

    last_poll_at = None
    next_poll_at = None
    polling_interval_seconds = None
    last_duration_seconds = None

    if AUTO_POLL_STATUS_FILE.exists():
        try:
            payload = json.loads(AUTO_POLL_STATUS_FILE.read_text())
            last_raw = payload.get("last_poll_at")
            if last_raw:
                try:
                    last_poll_at = datetime.fromisoformat(last_raw)
                except ValueError:
                    LOGGER.warning("Unable to parse last_poll_at from status file: %s", last_raw)
            next_raw = payload.get("next_poll_at")
            if next_raw:
                try:
                    next_poll_at = datetime.fromisoformat(next_raw)
                except ValueError:
                    LOGGER.warning("Unable to parse next_poll_at from status file: %s", next_raw)

            polling_interval_seconds = payload.get("polling_interval_seconds")
            last_duration_seconds = payload.get("last_duration_seconds")
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Failed to read auto poll status heartbeat: %s", exc)

    return AsyncGenerationStatus(
        pending_requests=pending_requests,
        pending_batches=pending_batches,
        remaining_generations=remaining_generations,
        last_poll_at=last_poll_at,
        next_poll_at=next_poll_at,
        polling_interval_seconds=polling_interval_seconds,
        last_duration_seconds=last_duration_seconds,
        oldest_batch_age_hours=oldest_batch_age_hours,
        has_aging_batches=has_aging_batches,
    )


@app.post("/api/audition/generate/regenerate", response_model=RegenerateGenerationResponse)
def regenerate_generation(request: RegenerateGenerationRequest):
    """Delete a malformed generation, remove dependent comparisons, and requeue it."""
    async_providers = sorted({provider.lower() for provider in (request.async_providers or [])})

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    g.id,
                    g.prompt_id,
                    g.condition_id,
                    g.run_id,
                    g.replicate_index,
                    c.slug AS condition_slug,
                    c.provider,
                    c.model_name,
                    c.temperature,
                    c.reasoning_effort,
                    c.thinking_enabled,
                    c.max_output_tokens,
                    c.thinking_budget_tokens
                FROM apex_audition.generations g
                JOIN apex_audition.conditions c ON c.id = g.condition_id
                WHERE g.id = %s
                """,
                (request.generation_id,),
            )
            generation_row = cur.fetchone()

            if not generation_row:
                raise HTTPException(status_code=404, detail="Generation not found")

            prompt_id = generation_row["prompt_id"]
            condition_id = generation_row["condition_id"]
            run_id = generation_row["run_id"]
            condition_slug = generation_row["condition_slug"]
            provider = generation_row["provider"].lower()

            # Locate impacted comparisons for this prompt/condition lane
            cur.execute(
                """
                SELECT id
                FROM apex_audition.comparisons
                WHERE prompt_id = %s
                  AND (%s = condition_a_id OR %s = condition_b_id)
                """,
                (prompt_id, condition_id, condition_id),
            )
            comparison_ids = [row["id"] for row in cur.fetchall()]
            comparisons_deleted = 0

            if comparison_ids:
                # Roll back ELO adjustments tied to those comparisons
                cur.execute(
                    """
                    SELECT condition_id, rating_delta, comparison_id
                    FROM apex_audition.elo_history
                    WHERE comparison_id = ANY(%s)
                    """,
                    (comparison_ids,),
                )
                elo_rows = cur.fetchall()

                for elo_row in elo_rows:
                    cur.execute(
                        """
                        UPDATE apex_audition.elo_ratings
                        SET rating = rating - %s,
                            games_played = GREATEST(games_played - 1, 0),
                            last_updated = NOW()
                        WHERE condition_id = %s
                        """,
                        (elo_row["rating_delta"], elo_row["condition_id"]),
                    )

                if elo_rows:
                    cur.execute(
                        """
                        DELETE FROM apex_audition.elo_history
                        WHERE comparison_id = ANY(%s)
                        """,
                        (comparison_ids,),
                    )

                cur.execute(
                    """
                    DELETE FROM apex_audition.comparisons
                    WHERE id = ANY(%s)
                    RETURNING id
                    """,
                    (comparison_ids,),
                )
                comparisons_deleted = len(cur.fetchall())

            # Delete the generation row itself
            cur.execute(
                "DELETE FROM apex_audition.generations WHERE id = %s",
                (request.generation_id,),
            )

            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Generation was already removed")

            # Optionally delete empty runs to avoid residue
            cur.execute(
                "SELECT COUNT(*) AS remaining FROM apex_audition.generations WHERE run_id = %s",
                (run_id,),
            )
            remaining = cur.fetchone()["remaining"]
            if remaining == 0:
                cur.execute(
                    "DELETE FROM apex_audition.generation_runs WHERE id = %s",
                    (run_id,),
                )

        # Commit transactional cleanup before triggering new work
        conn.commit()

    engine = AuditionEngine(async_providers=async_providers)

    if provider in async_providers:
        run, batch_id = engine.submit_batch_generation(
            condition_slug=condition_slug,
            prompt_ids=[prompt_id],
            replicate_count=1,
            run_label="Arena regeneration (async)",
            created_by="arena-debugger",
            notes=f"Regenerated generation {request.generation_id}",
        )
        new_generations = engine.repository.list_generations_for_run(run.run_id)
        new_generation_id = new_generations[0].id if new_generations else None
        return RegenerateGenerationResponse(
            mode="async",
            run_id=str(run.run_id),
            generation_id=new_generation_id,
            batch_id=batch_id,
            comparisons_deleted=comparisons_deleted,
        )

    # Synchronous regeneration
    run = engine.run_generation_batch(
        condition_slug=condition_slug,
        prompt_ids=[prompt_id],
        replicate_count=1,
        run_label="Arena regeneration (sync)",
        created_by="arena-debugger",
        notes=f"Regenerated generation {request.generation_id}",
    )
    new_generations = engine.repository.list_generations_for_run(run.run_id)
    new_generation_id = new_generations[0].id if new_generations else None

    return RegenerateGenerationResponse(
        mode="sync",
        run_id=str(run.run_id),
        generation_id=new_generation_id,
        batch_id=None,
        comparisons_deleted=comparisons_deleted,
    )


@app.post("/api/audition/generate/stop")
def stop_generation(job_id: str = Query(...)):
    """Stop a running generation job."""
    job = generation_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    process = job["process"]

    if process.poll() is None:
        # Process is still running, kill it forcefully
        # Use kill() instead of terminate() to immediately stop all worker threads
        process.kill()
        return {"status": "stopped", "job_id": job_id}
    else:
        return {"status": "already_completed", "job_id": job_id}


@app.post("/api/audition/import/prompt")
async def import_prompt(file: UploadFile = File(...)):
    """
    Import a context package JSON file and register it as a prompt.

    Accepts a single JSON file upload, parses it, and creates/updates
    the corresponding prompt in the database.
    """
    try:
        # Read and parse JSON file
        contents = await file.read()
        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")

        # Extract metadata and context
        meta = payload.get("metadata", {})
        context_payload = payload.get("context_payload")

        if not context_payload:
            raise HTTPException(status_code=400, detail="Missing context_payload in JSON file")

        chunk_id = meta.get("chunk_id")
        if chunk_id is None:
            # Try to extract chunk_id from filename as fallback
            import re
            match = re.search(r'chunk_(\d+)_', file.filename or "")
            if match:
                chunk_id = int(match.group(1))
            else:
                raise HTTPException(status_code=400, detail="Missing chunk_id in metadata and could not extract from filename")

        chunk_id = int(chunk_id)

        # Initialize engine and purify context (remove future contamination)
        engine = AuditionEngine()
        purified_context = engine._purify_context_payload(context_payload, chunk_id)

        # Calculate context hash
        context_hash = hashlib.sha256(
            json.dumps(purified_context, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        # Extract additional metadata
        extra_metadata = {
            "authorial_directives": meta.get("authorial_directives") or [],
            "warm_span": meta.get("warm_span"),
            "notes": meta.get("notes"),
        }

        # Create PromptSnapshot
        from nexus.audition.models import PromptSnapshot
        snapshot = PromptSnapshot(
            chunk_id=chunk_id,
            context_sha=context_hash,
            context=purified_context,
            category=meta.get("category"),
            label=meta.get("label"),
            source_path=file.filename,
            metadata=extra_metadata,
        )

        # Upsert into database
        stored = engine.repository.upsert_prompt(snapshot)

        return {
            "success": True,
            "chunk_id": stored.chunk_id,
            "prompt_id": stored.id,
            "message": f"Successfully imported prompt for chunk {stored.chunk_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import prompt: {str(e)}")


@app.post("/api/audition/conditions/{condition_id}/notes")
def add_condition_note(condition_id: int, note: Dict[str, str]):
    """Add a note to a condition's notes array."""
    note_text = note.get("note", "").strip()

    if not note_text:
        raise HTTPException(status_code=400, detail="Note cannot be empty")

    with get_db() as conn:
        with conn.cursor() as cur:
            # Check if condition exists
            cur.execute("""
                SELECT id, notes FROM apex_audition.conditions WHERE id = %s
            """, (condition_id,))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Condition {condition_id} not found")

            # Get current notes or initialize empty array
            current_notes = row['notes'] or []

            # Add timestamp to note
            timestamped_note = {
                "text": note_text,
                "timestamp": datetime.now().isoformat()
            }

            # Append new note
            current_notes.append(timestamped_note)

            # Update condition
            cur.execute("""
                UPDATE apex_audition.conditions
                SET notes = %s::jsonb
                WHERE id = %s
            """, (json.dumps(current_notes), condition_id))

            conn.commit()

            return {
                "success": True,
                "condition_id": condition_id,
                "note_count": len(current_notes)
            }
