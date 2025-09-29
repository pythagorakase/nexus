"""Persistence utilities for the Apex audition engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    BigInteger,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from .models import ConditionSpec, GenerationResult, GenerationRun, PromptSnapshot

BASE_DIR = Path(__file__).resolve().parents[2]
SETTINGS_PATH = BASE_DIR / "settings.json"
DEFAULT_DB_URL = "postgresql://pythagor@localhost/NEXUS"


class AuditionRepository:
    """Lightweight repository facade backed by PostgreSQL."""

    def __init__(
        self,
        *,
        settings_path: Path | None = None,
        db_url: Optional[str] = None,
        engine: Optional[Engine] = None,
    ) -> None:
        self.settings_path = settings_path or SETTINGS_PATH
        if engine is not None:
            self.engine = engine
        else:
            db_url = db_url or self._load_db_url(self.settings_path)
            self.engine = create_engine(db_url)

        self.metadata = MetaData(schema="apex_audition")
        self._define_tables()
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------
    def _define_tables(self) -> None:
        self.conditions = Table(
            "conditions",
            self.metadata,
            Column("id", Integer, primary_key=True),
            Column("slug", String(128), nullable=False, unique=True, index=True),
            Column("provider", String(32), nullable=False),
            Column("model_name", String(128), nullable=False),
            Column("label", String(128)),
            Column("description", Text),
            Column("parameters", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
            Column("system_prompt", Text),
            Column("is_active", Boolean, nullable=False, server_default=text("true")),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.prompts = Table(
            "prompts",
            self.metadata,
            Column("id", Integer, primary_key=True),
            Column("chunk_id", Integer, nullable=False),
            Column("context_sha", String(64), nullable=False, unique=True, index=True),
            Column("category", String(128)),
            Column("label", String(256)),
            Column("source_path", Text),
            Column("context", JSONB, nullable=False),
            Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.generation_runs = Table(
            "generation_runs",
            self.metadata,
            Column("id", PGUUID(as_uuid=True), primary_key=True),
            Column("provider", String(32), nullable=False),
            Column("storyteller_prompt", Text),
            Column("description", Text),
            Column("created_by", String(128)),
            Column("notes", Text),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.generations = Table(
            "generations",
            self.metadata,
            Column("id", BigInteger, primary_key=True),
            Column(
                "run_id",
                PGUUID(as_uuid=True),
                ForeignKey("apex_audition.generation_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "condition_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "prompt_id",
                Integer,
                ForeignKey("apex_audition.prompts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column("replicate_index", Integer, nullable=False),
            Column("status", String(32), nullable=False),
            Column("prompt_text", Text, nullable=False),
            Column("request_payload", JSONB, nullable=False),
            Column("response_payload", JSONB),
            Column("input_tokens", Integer, nullable=False, server_default=text("0")),
            Column("output_tokens", Integer, nullable=False, server_default=text("0")),
            Column("cost_usd", Float, nullable=False, server_default=text("0")),
            Column("error_message", Text),
            Column("started_at", DateTime(timezone=True)),
            Column("completed_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.comparisons = Table(
            "comparisons",
            self.metadata,
            Column("id", BigInteger, primary_key=True),
            Column(
                "prompt_id",
                Integer,
                ForeignKey("apex_audition.prompts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "condition_a_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "condition_b_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "winner_condition_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="SET NULL"),
            ),
            Column(
                "run_id",
                PGUUID(as_uuid=True),
                ForeignKey("apex_audition.generation_runs.id", ondelete="SET NULL"),
            ),
            Column("evaluator", String(128)),
            Column("notes", Text),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.elo_ratings = Table(
            "elo_ratings",
            self.metadata,
            Column(
                "condition_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            Column("rating", Float, nullable=False, server_default=text("1500")),
            Column("games_played", Integer, nullable=False, server_default=text("0")),
            Column("last_updated", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

        self.elo_history = Table(
            "elo_history",
            self.metadata,
            Column("id", BigInteger, primary_key=True),
            Column(
                "condition_id",
                Integer,
                ForeignKey("apex_audition.conditions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column(
                "comparison_id",
                BigInteger,
                ForeignKey("apex_audition.comparisons.id", ondelete="SET NULL"),
            ),
            Column("rating", Float, nullable=False),
            Column("rating_delta", Float, nullable=False),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        )

    def _ensure_schema(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS apex_audition")
            self.metadata.create_all(connection)

    # ------------------------------------------------------------------
    # Condition management
    # ------------------------------------------------------------------
    def upsert_condition(self, condition: ConditionSpec) -> ConditionSpec:
        stmt = (
            pg_insert(self.conditions)
            .values(
                slug=condition.slug,
                provider=condition.provider,
                model_name=condition.model,
                label=condition.label,
                description=condition.description,
                parameters=condition.parameters,
                system_prompt=condition.system_prompt,
                is_active=condition.is_active,
            )
            .on_conflict_do_update(
                index_elements=[self.conditions.c.slug],
                set_={
                    "provider": condition.provider,
                    "model_name": condition.model,
                    "label": condition.label,
                    "description": condition.description,
                    "parameters": condition.parameters,
                    "system_prompt": condition.system_prompt,
                    "is_active": condition.is_active,
                },
            )
            .returning(self.conditions.c.id, self.conditions.c.created_at)
        )
        with self.engine.begin() as connection:
            row = connection.execute(stmt).one()
        return condition.with_id(row.id, row.created_at)

    def get_condition_by_slug(self, slug: str) -> Optional[ConditionSpec]:
        query = self.conditions.select().where(self.conditions.c.slug == slug)
        with self.engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if not row:
            return None
        spec = ConditionSpec(
            slug=row["slug"],
            provider=row["provider"],
            model=row["model_name"],
            parameters=dict(row["parameters"] or {}),
            label=row["label"],
            description=row["description"],
            system_prompt=row["system_prompt"],
            is_active=row["is_active"],
        )
        spec.id = row["id"]
        spec.created_at = row["created_at"]
        return spec

    def list_conditions(self, *, active_only: bool = False) -> List[ConditionSpec]:
        query = self.conditions.select()
        if active_only:
            query = query.where(self.conditions.c.is_active.is_(True))
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        specs: List[ConditionSpec] = []
        for row in rows:
            spec = ConditionSpec(
                slug=row["slug"],
                provider=row["provider"],
                model=row["model_name"],
                parameters=dict(row["parameters"] or {}),
                label=row["label"],
                description=row["description"],
                system_prompt=row["system_prompt"],
                is_active=row["is_active"],
            )
            spec.id = row["id"]
            spec.created_at = row["created_at"]
            specs.append(spec)
        return specs

    # ------------------------------------------------------------------
    # Prompt snapshots
    # ------------------------------------------------------------------
    def upsert_prompt(self, snapshot: PromptSnapshot) -> PromptSnapshot:
        stmt = (
            pg_insert(self.prompts)
            .values(
                chunk_id=snapshot.chunk_id,
                context_sha=snapshot.context_sha,
                category=snapshot.category,
                label=snapshot.label,
                source_path=snapshot.source_path,
                context=snapshot.context,
                metadata=snapshot.metadata,
            )
            .on_conflict_do_update(
                index_elements=[self.prompts.c.context_sha],
                set_={
                    "chunk_id": snapshot.chunk_id,
                    "category": snapshot.category,
                    "label": snapshot.label,
                    "source_path": snapshot.source_path,
                    "context": snapshot.context,
                    "metadata": snapshot.metadata,
                },
            )
            .returning(self.prompts.c.id, self.prompts.c.created_at)
        )
        with self.engine.begin() as connection:
            row = connection.execute(stmt).one()
        return snapshot.with_id(row.id, row.created_at)

    def list_prompts(self) -> List[PromptSnapshot]:
        query = self.prompts.select().order_by(self.prompts.c.chunk_id)
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        prompts: List[PromptSnapshot] = []
        for row in rows:
            snapshot = PromptSnapshot(
                chunk_id=row["chunk_id"],
                context_sha=row["context_sha"],
                context=row["context"],
                category=row["category"],
                label=row["label"],
                source_path=row["source_path"],
                metadata=row["metadata"],
            )
            snapshot.id = row["id"]
            snapshot.created_at = row["created_at"]
            prompts.append(snapshot)
        return prompts

    def get_prompt_by_id(self, prompt_id: int) -> Optional[PromptSnapshot]:
        query = self.prompts.select().where(self.prompts.c.id == prompt_id)
        with self.engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        if not row:
            return None
        snapshot = PromptSnapshot(
            chunk_id=row["chunk_id"],
            context_sha=row["context_sha"],
            context=row["context"],
            category=row["category"],
            label=row["label"],
            source_path=row["source_path"],
            metadata=row["metadata"],
        )
        snapshot.id = row["id"]
        snapshot.created_at = row["created_at"]
        return snapshot

    # ------------------------------------------------------------------
    # Generation runs and results
    # ------------------------------------------------------------------
    def create_generation_run(self, run: GenerationRun) -> GenerationRun:
        stmt = (
            pg_insert(self.generation_runs)
            .values(
                id=run.run_id,
                provider=run.provider,
                storyteller_prompt=run.storyteller_prompt,
                description=run.description,
                created_by=run.created_by,
                notes=run.notes,
            )
            .returning(self.generation_runs.c.created_at)
        )
        with self.engine.begin() as connection:
            created_at = connection.execute(stmt).scalar_one()
        run.created_at = created_at
        return run

    def record_generation(self, result: GenerationResult) -> GenerationResult:
        stmt = (
            pg_insert(self.generations)
            .values(
                run_id=result.run_id,
                condition_id=result.condition_id,
                prompt_id=result.prompt_id,
                replicate_index=result.replicate_index,
                status=result.status,
                prompt_text=result.prompt_text,
                request_payload=result.request_payload,
                response_payload=result.response_payload,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                error_message=result.error_message,
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            .returning(self.generations.c.id)
        )
        with self.engine.begin() as connection:
            identifier = connection.execute(stmt).scalar_one()
        result.id = identifier
        return result

    def list_generations_for_run(self, run_id) -> List[GenerationResult]:
        query = self.generations.select().where(self.generations.c.run_id == run_id)
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        results: List[GenerationResult] = []
        for row in rows:
            results.append(
                GenerationResult(
                    run_id=row["run_id"],
                    condition_id=row["condition_id"],
                    prompt_id=row["prompt_id"],
                    replicate_index=row["replicate_index"],
                    status=row["status"],
                    prompt_text=row["prompt_text"],
                    request_payload=row["request_payload"],
                    response_payload=row["response_payload"],
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    cost_usd=row["cost_usd"],
                    error_message=row["error_message"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    id=row["id"],
                )
            )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_db_url(settings_path: Path) -> str:
        try:
            with settings_path.open("r", encoding="utf-8") as handle:
                settings = json.load(handle)
            memnon = settings.get("Agent Settings", {}).get("MEMNON", {})
            database = memnon.get("database", {})
            return database.get("url", DEFAULT_DB_URL)
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to load database URL from {settings_path}: {exc}") from exc

    # Debugging convenience -------------------------------------------------
    def truncate_all(self) -> None:
        """Erase audition tables. Use with caution in development only."""
        with self.engine.begin() as connection:
            connection.execute(self.generations.delete())
            connection.execute(self.comparisons.delete())
            connection.execute(self.elo_history.delete())
            connection.execute(self.elo_ratings.delete())
            connection.execute(self.generation_runs.delete())
            connection.execute(self.prompts.delete())
            connection.execute(self.conditions.delete())


__all__ = ["AuditionRepository"]
