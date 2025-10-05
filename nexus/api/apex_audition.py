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
    Condition, Generation, Prompt, ComparisonCreate,
    ELORating, ComparisonQueueItem, GenerationRun
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


@app.get("/api/audition/comparisons/next", response_model=Optional[ComparisonQueueItem])
def get_next_comparison(
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
            where_clauses = [
                "c.id IS NULL",
                "ga.id < gb.id",  # Avoid duplicate pairs in opposite order
            ]
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
                    p.id AS prompt_id,
                    p.chunk_id AS prompt_chunk_id,
                    p.category AS prompt_category,
                    p.label AS prompt_label,
                    p.context AS prompt_context,
                    p.metadata AS prompt_metadata,
                    ca.id AS condition_a_id,
                    ca.slug AS condition_a_slug,
                    ca.provider AS condition_a_provider,
                    ca.model_name AS condition_a_model_name,
                    ca.label AS condition_a_label,
                    ca.temperature AS condition_a_temperature,
                    ca.reasoning_effort AS condition_a_reasoning_effort,
                    ca.thinking_enabled AS condition_a_thinking_enabled,
                    ca.max_output_tokens AS condition_a_max_output_tokens,
                    ca.thinking_budget_tokens AS condition_a_thinking_budget_tokens,
                    ca.is_active AS condition_a_is_active,
                    cb.id AS condition_b_id,
                    cb.slug AS condition_b_slug,
                    cb.provider AS condition_b_provider,
                    cb.model_name AS condition_b_model_name,
                    cb.label AS condition_b_label,
                    cb.temperature AS condition_b_temperature,
                    cb.reasoning_effort AS condition_b_reasoning_effort,
                    cb.thinking_enabled AS condition_b_thinking_enabled,
                    cb.max_output_tokens AS condition_b_max_output_tokens,
                    cb.thinking_budget_tokens AS condition_b_thinking_budget_tokens,
                    cb.is_active AS condition_b_is_active,
                    ga.id AS generation_a_id,
                    ga.condition_id AS generation_a_condition_id,
                    ga.prompt_id AS generation_a_prompt_id,
                    ga.replicate_index AS generation_a_replicate_index,
                    ga.status AS generation_a_status,
                    ga.response_payload AS generation_a_response_payload,
                    ga.input_tokens AS generation_a_input_tokens,
                    ga.output_tokens AS generation_a_output_tokens,
                    ga.completed_at AS generation_a_completed_at,
                    gb.id AS generation_b_id,
                    gb.condition_id AS generation_b_condition_id,
                    gb.prompt_id AS generation_b_prompt_id,
                    gb.replicate_index AS generation_b_replicate_index,
                    gb.status AS generation_b_status,
                    gb.response_payload AS generation_b_response_payload,
                    gb.input_tokens AS generation_b_input_tokens,
                    gb.output_tokens AS generation_b_output_tokens,
                    gb.completed_at AS generation_b_completed_at
                FROM apex_audition.prompts p
                JOIN apex_audition.generations ga ON ga.prompt_id = p.id
                    AND ga.status = 'completed'
                JOIN apex_audition.generations gb ON gb.prompt_id = p.id
                    AND gb.status = 'completed'
                    AND gb.condition_id != ga.condition_id
                    AND ga.replicate_index = gb.replicate_index
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

            # Assemble response objects from aliased columns
            prompt = Prompt(
                id=row["prompt_id"],
                chunk_id=row["prompt_chunk_id"],
                category=row.get("prompt_category"),
                label=row.get("prompt_label"),
                context=row["prompt_context"],
                metadata=row["prompt_metadata"],
            )

            condition_a = Condition(
                id=row["condition_a_id"],
                slug=row["condition_a_slug"],
                provider=row["condition_a_provider"],
                model=row["condition_a_model_name"],
                label=row.get("condition_a_label"),
                temperature=row.get("condition_a_temperature"),
                reasoning_effort=row.get("condition_a_reasoning_effort"),
                thinking_enabled=row.get("condition_a_thinking_enabled"),
                max_output_tokens=row.get("condition_a_max_output_tokens"),
                thinking_budget_tokens=row.get("condition_a_thinking_budget_tokens"),
                is_active=row["condition_a_is_active"],
            )

            condition_b = Condition(
                id=row["condition_b_id"],
                slug=row["condition_b_slug"],
                provider=row["condition_b_provider"],
                model=row["condition_b_model_name"],
                label=row.get("condition_b_label"),
                temperature=row.get("condition_b_temperature"),
                reasoning_effort=row.get("condition_b_reasoning_effort"),
                thinking_enabled=row.get("condition_b_thinking_enabled"),
                max_output_tokens=row.get("condition_b_max_output_tokens"),
                thinking_budget_tokens=row.get("condition_b_thinking_budget_tokens"),
                is_active=row["condition_b_is_active"],
            )

            generation_a = Generation(
                id=row["generation_a_id"],
                condition_id=row["generation_a_condition_id"],
                prompt_id=row["generation_a_prompt_id"],
                replicate_index=row["generation_a_replicate_index"],
                status=row["generation_a_status"],
                response_payload=row["generation_a_response_payload"],
                input_tokens=row.get("generation_a_input_tokens"),
                output_tokens=row.get("generation_a_output_tokens"),
                completed_at=row.get("generation_a_completed_at"),
            )

            generation_b = Generation(
                id=row["generation_b_id"],
                condition_id=row["generation_b_condition_id"],
                prompt_id=row["generation_b_prompt_id"],
                replicate_index=row["generation_b_replicate_index"],
                status=row["generation_b_status"],
                response_payload=row["generation_b_response_payload"],
                input_tokens=row.get("generation_b_input_tokens"),
                output_tokens=row.get("generation_b_output_tokens"),
                completed_at=row.get("generation_b_completed_at"),
            )

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
            cur.execute("""
                SELECT COUNT(*) as count
                FROM apex_audition.prompts p
                CROSS JOIN apex_audition.conditions c
                WHERE c.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM apex_audition.generations g
                      WHERE g.prompt_id = p.id
                        AND g.condition_id = c.id
                        AND g.replicate_index = 0
                        AND g.status = 'completed'
                        AND g.response_payload->>'content' IS NOT NULL
                        AND LENGTH(g.response_payload->>'content') > 0
                  )
            """)
            row = cur.fetchone()
            count = row["count"] if row else 0
            return {"count": count}


@app.post("/api/audition/generate/start")
def start_generation(limit: Optional[int] = None, max_workers: Optional[int] = None):
    """Start a generation job (runs run_full_sequential.py to create new generations)."""
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

    try:
        # Fetch Anthropic API key
        anthropic_result = subprocess.run(
            ["op", "read", "op://API/Anthropic/api key"],
            capture_output=True,
            text=True,
            check=True
        )
        env["ANTHROPIC_API_KEY"] = anthropic_result.stdout.strip()

        # Fetch OpenAI API key
        openai_result = subprocess.run(
            ["op", "item", "get", "tyrupcepa4wluec7sou4e7mkza", "--fields", "api key", "--reveal"],
            capture_output=True,
            text=True,
            check=True
        )
        env["OPENAI_API_KEY"] = openai_result.stdout.strip()

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve API keys from 1Password. Ensure you're signed in with 'op signin'."
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="1Password CLI (op) not found. Install from https://developer.1password.com/docs/cli/get-started/"
        )

    # Build command with optional limit and max_workers
    cmd = ["python", str(script_path)]
    if limit is not None and limit > 0:
        cmd.extend(["--limit", str(limit)])
    if max_workers is not None and max_workers > 0:
        cmd.extend(["--max-workers", str(max_workers)])

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
