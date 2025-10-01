"""
FastAPI application for Apex Audition comparison system.

Provides REST API endpoints for:
- Fetching comparison queues
- Recording judgments
- Updating ELO ratings
- Viewing leaderboards
- Exporting comparisons
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from uuid import UUID
from datetime import datetime

from nexus.api.models import (
    Condition, Generation, Prompt, Comparison, ComparisonCreate,
    ELORating, ComparisonQueue, ComparisonQueueItem, GenerationRun
)
from nexus.audition.elo import calculate_elo_update, outcome_from_winner
from nexus.audition.comparisons import generate_round_robin_pairs, filter_already_judged

# Database connection parameters
DB_PARAMS = {
    "dbname": "NEXUS",
    "user": "pythagor",
    "host": "localhost",
    "port": 5432
}

app = FastAPI(title="Apex Audition API", version="1.0.0")

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)


@app.get("/api/audition/runs", response_model=List[GenerationRun])
async def list_generation_runs():
    """List all generation runs."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    gr.id::text,
                    gr.label,
                    gr.started_at,
                    gr.completed_at,
                    COUNT(g.id) as total_generations,
                    COUNT(g.id) FILTER (WHERE g.status = 'completed') as completed_generations,
                    COUNT(g.id) FILTER (WHERE g.status = 'error') as failed_generations
                FROM apex_audition.generation_runs gr
                LEFT JOIN apex_audition.generations g ON g.run_id = gr.id
                GROUP BY gr.id, gr.label, gr.started_at, gr.completed_at
                ORDER BY gr.started_at DESC
            """)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


@app.get("/api/audition/comparisons/next", response_model=Optional[ComparisonQueueItem])
async def get_next_comparison(
    run_id: Optional[str] = Query(None),
    condition_a_id: Optional[int] = Query(None),
    condition_b_id: Optional[int] = Query(None),
):
    """
    Get the next pending comparison.

    If run_id is specified, only return comparisons from that run.
    If condition IDs are specified, only return comparisons between those conditions.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build query conditions
            where_clauses = ["c.id IS NULL"]  # Not already judged
            params = []

            if run_id:
                where_clauses.append("ga.run_id = %s AND gb.run_id = %s")
                params.extend([run_id, run_id])

            if condition_a_id and condition_b_id:
                where_clauses.append("""
                    ((ga.condition_id = %s AND gb.condition_id = %s) OR
                     (ga.condition_id = %s AND gb.condition_id = %s))
                """)
                params.extend([condition_a_id, condition_b_id, condition_b_id, condition_a_id])

            where_sql = " AND ".join(where_clauses)

            query = f"""
                SELECT
                    p.*,
                    ca.*,
                    cb.*,
                    ga.*,
                    gb.*
                FROM apex_audition.prompts p
                JOIN apex_audition.generations ga ON ga.prompt_id = p.id
                    AND ga.status = 'completed'
                JOIN apex_audition.generations gb ON gb.prompt_id = p.id
                    AND gb.status = 'completed'
                    AND gb.condition_id != ga.condition_id
                JOIN apex_audition.conditions ca ON ca.id = ga.condition_id
                JOIN apex_audition.conditions cb ON cb.id = gb.condition_id
                LEFT JOIN apex_audition.comparisons c ON c.prompt_id = p.id
                    AND ((c.condition_a_id = ga.condition_id AND c.condition_b_id = gb.condition_id)
                         OR (c.condition_a_id = gb.condition_id AND c.condition_b_id = ga.condition_id))
                WHERE {where_sql}
                ORDER BY RANDOM()
                LIMIT 1
            """

            cur.execute(query, params)
            row = cur.fetchone()

            if not row:
                return None

            # Parse row into structured response
            # This is simplified - in production, you'd properly parse all fields
            return ComparisonQueueItem(
                prompt=Prompt(
                    id=row['id'],
                    chunk_id=row['chunk_id'],
                    category=row.get('category'),
                    label=row.get('label'),
                    context=row['context'],
                    metadata=row['metadata']
                ),
                condition_a=Condition(
                    id=row['ca.id'],
                    slug=row['ca.slug'],
                    provider=row['ca.provider'],
                    model_name=row['ca.model_name'],
                    parameters=row['ca.parameters'],
                    is_active=row['ca.is_active']
                ),
                condition_b=Condition(
                    id=row['cb.id'],
                    slug=row['cb.slug'],
                    provider=row['cb.provider'],
                    model_name=row['cb.model_name'],
                    parameters=row['cb.parameters'],
                    is_active=row['cb.is_active']
                ),
                generation_a=Generation(
                    id=row['ga.id'],
                    condition_id=row['ga.condition_id'],
                    prompt_id=row['ga.prompt_id'],
                    replicate_index=row['ga.replicate_index'],
                    status=row['ga.status'],
                    response_payload=row['ga.response_payload'],
                    input_tokens=row.get('ga.input_tokens'),
                    output_tokens=row.get('ga.output_tokens'),
                    cost_usd=row.get('ga.cost_usd'),
                    completed_at=row.get('ga.completed_at')
                ),
                generation_b=Generation(
                    id=row['gb.id'],
                    condition_id=row['gb.condition_id'],
                    prompt_id=row['gb.prompt_id'],
                    replicate_index=row['gb.replicate_index'],
                    status=row['gb.status'],
                    response_payload=row['gb.response_payload'],
                    input_tokens=row.get('gb.input_tokens'),
                    output_tokens=row.get('gb.output_tokens'),
                    cost_usd=row.get('gb.cost_usd'),
                    completed_at=row.get('gb.completed_at')
                )
            )


@app.post("/api/audition/comparisons", response_model=dict)
async def create_comparison(comparison: ComparisonCreate):
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
async def get_leaderboard(limit: int = Query(10, ge=1, le=100)):
    """Get ELO leaderboard."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.condition_id,
                    e.rating,
                    e.games_played,
                    e.last_updated,
                    c.id, c.slug, c.provider, c.model_name, c.parameters, c.is_active
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
                        parameters=row['parameters'],
                        is_active=row['is_active']
                    ),
                    rating=row['rating'],
                    games_played=row['games_played'],
                    last_updated=row['last_updated']
                )
                for row in rows
            ]


@app.get("/api/audition/export/{comparison_id}")
async def export_comparison(comparison_id: int):
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
