#!/usr/bin/env python
"""Bake off retrieval query strategies against live MEMNON search.

This is a diagnostic harness, not runtime narrative behavior. It compares
query sources for next-turn retrieval:

* ``raw_chunk``: the full source chunk text as one query.
* ``skald_directives``: Storyteller-authored directives persisted on the source
  chunk, optionally backfilled into a local cache for older chunks.
* ``local_llm``: historical cached local-LLM queries when present. New local
  query generation has been removed from the live stack.

The turn-sample scorer uses two imperfect but useful automatic judges:

* future-oracle overlap, where the actual next chunk text retrieves an oracle
  pool of prior chunks;
* entity-continuity grades, where prior chunks sharing target-chunk character,
  place, or faction references are graded as continuity-relevant.

The existing IR golden queries can also be run as a separate labeled sanity
check for MEMNON retrieval quality. They are not a fourth contestant.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sqlite3
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, field_validator

from nexus.agents.memnon.memnon import MEMNON
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings


QUIET_LOGGERS = [
    "nexus.memnon",
    "nexus.memnon.search",
    "nexus.memnon.db_access",
    "nexus.memnon.db_schema",
    "nexus.memnon.embedding_manager",
    "nexus.memnon.cross_encoder",
    "nexus.memnon.content_processor",
    "nexus.memnon.query_analysis",
    "nexus.memnon.continuous_temporal_search",
    "nexus.lore.local_llm",
    "sentence_transformers",
    "httpx",
]


@dataclass(frozen=True)
class QuerySet:
    """A named set of queries to evaluate together."""

    name: str
    description: str
    queries: list[str]


@dataclass(frozen=True)
class ChunkRefs:
    """Entity references attached to one narrative chunk."""

    characters: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    factions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnSample:
    """One source chunk and its actual next chunk."""

    slot: int
    source_chunk_id: int
    target_chunk_id: int
    source_text: str
    target_text: str
    choice_text: str
    authorial_directives: list[str]
    source_refs: ChunkRefs
    target_refs: ChunkRefs

    @property
    def key(self) -> str:
        return f"slot{self.slot}:chunk{self.source_chunk_id}"


class DirectiveSet(BaseModel):
    """Small structured schema for offline Skald-directive backfills."""

    authorial_directives: list[str] = Field(min_length=3, max_length=5)

    @field_validator("authorial_directives")
    @classmethod
    def normalize_directives(cls, directives: list[str]) -> list[str]:
        cleaned = dedupe_queries(directives, limit=5)
        if len(cleaned) < 3:
            raise ValueError("Need at least three useful directives")
        return cleaned


class MinimalInterface:
    """MEMNON interface shim for scripts."""

    def assistant_message(self, msg: str) -> None:
        pass

    def error_message(self, msg: str) -> None:
        print(f"MEMNON error: {msg}")


class MinimalAgentState:
    """MEMNON agent-state shim for scripts."""

    state = {"name": "retrieval_query_bakeoff"}


class MinimalUser:
    """MEMNON user shim for scripts."""

    id = "retrieval_query_bakeoff"
    name = "retrieval_query_bakeoff"


class JsonCache:
    """Tiny JSON cache for expensive generated query sets."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {}
        if path.exists():
            self.data = json.loads(path.read_text())

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, default=str) + "\n")


def dedupe_queries(queries: Iterable[Optional[str]], *, limit: int = 5) -> list[str]:
    """Return non-empty unique queries while preserving order."""

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if not query:
            continue
        cleaned = " ".join(str(query).split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        deduped.append(cleaned)
        seen.add(key)
        if len(deduped) >= limit:
            break
    return deduped


def _result_chunk_id(result: dict[str, Any]) -> Optional[int]:
    result_id = result.get("id") or result.get("chunk_id")
    if isinstance(result_id, int):
        return result_id
    try:
        return int(result_id)
    except (TypeError, ValueError):
        return None


def _coerce_directives(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    return dedupe_queries([item for item in raw if isinstance(item, str)])


def _fetch_refs(cur: Any, chunk_id: int) -> ChunkRefs:
    cur.execute(
        """
        SELECT c.name
        FROM chunk_character_references r
        JOIN characters c ON c.id = r.character_id
        WHERE r.chunk_id = %s
        ORDER BY c.name
        """,
        (chunk_id,),
    )
    characters = [row["name"] for row in cur.fetchall() if row.get("name")]

    cur.execute(
        """
        SELECT p.name
        FROM place_chunk_references r
        JOIN places p ON p.id = r.place_id
        WHERE r.chunk_id = %s
        ORDER BY p.name
        """,
        (chunk_id,),
    )
    places = [row["name"] for row in cur.fetchall() if row.get("name")]

    cur.execute(
        """
        SELECT f.name
        FROM chunk_faction_references r
        JOIN factions f ON f.id = r.faction_id
        WHERE r.chunk_id = %s
        ORDER BY f.name
        """,
        (chunk_id,),
    )
    factions = [row["name"] for row in cur.fetchall() if row.get("name")]

    return ChunkRefs(characters=characters, places=places, factions=factions)


def load_turn_samples(
    slots: list[int],
    *,
    per_slot: int,
    min_chunk_id: Optional[int] = None,
    max_chunk_id: Optional[int] = None,
    require_directives: bool = False,
    seed: int = 187,
) -> list[TurnSample]:
    """Load source/target chunk pairs from each requested slot."""

    rng = random.Random(seed)
    samples: list[TurnSample] = []

    for slot in slots:
        db_url = get_slot_db_url(slot=slot)
        with psycopg2.connect(db_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                clauses = ["o.next_id IS NOT NULL"]
                params: list[Any] = []
                if min_chunk_id is not None:
                    clauses.append("o.id >= %s")
                    params.append(min_chunk_id)
                if max_chunk_id is not None:
                    clauses.append("o.id <= %s")
                    params.append(max_chunk_id)
                if require_directives:
                    clauses.append("jsonb_array_length(o.authorial_directives) > 0")

                cur.execute(
                    f"""
                    WITH ordered AS (
                        SELECT
                            id,
                            raw_text,
                            COALESCE(choice_text, '') AS choice_text,
                            COALESCE(authorial_directives, '[]'::jsonb)
                                AS authorial_directives,
                            LEAD(id) OVER (ORDER BY id) AS next_id
                        FROM narrative_chunks
                    )
                    SELECT o.*, target.raw_text AS target_raw_text
                    FROM ordered o
                    JOIN narrative_chunks target ON target.id = o.next_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY o.id
                    """,
                    tuple(params),
                )
                rows = [dict(row) for row in cur.fetchall()]
                if len(rows) > per_slot:
                    rows = rng.sample(rows, per_slot)
                    rows.sort(key=lambda row: int(row["id"]))

                for row in rows:
                    source_id = int(row["id"])
                    target_id = int(row["next_id"])
                    samples.append(
                        TurnSample(
                            slot=slot,
                            source_chunk_id=source_id,
                            target_chunk_id=target_id,
                            source_text=row["raw_text"] or "",
                            target_text=row["target_raw_text"] or "",
                            choice_text=row["choice_text"] or "",
                            authorial_directives=_coerce_directives(
                                row["authorial_directives"]
                            ),
                            source_refs=_fetch_refs(cur, source_id),
                            target_refs=_fetch_refs(cur, target_id),
                        )
                    )

    return samples


def load_chunk_context(slot: int, chunk_id: Optional[int]) -> dict[str, Any]:
    """Load a single chunk context for targeted, one-off experiments."""

    samples = load_turn_samples(
        [slot],
        per_slot=1,
        min_chunk_id=chunk_id,
        max_chunk_id=chunk_id,
        require_directives=False,
    )
    if not samples:
        raise RuntimeError(
            f"No source/target pair found for slot {slot} chunk {chunk_id}"
        )
    sample = samples[0]
    return {
        "slot": sample.slot,
        "chunk_id": sample.source_chunk_id,
        "target_chunk_id": sample.target_chunk_id,
        "raw_text": sample.source_text,
        "choice_text": sample.choice_text,
        "authorial_directives": sample.authorial_directives,
        "characters": sample.source_refs.characters,
        "places": sample.source_refs.places,
        "factions": sample.source_refs.factions,
    }


def generate_skald_directives(
    sample: TurnSample,
    *,
    cache: JsonCache,
    provider: Any,
) -> list[str]:
    """Generate or load offline Skald-style directives for older chunks."""

    if sample.authorial_directives:
        return sample.authorial_directives

    cache_key = f"{sample.key}:skald_directives"
    cached = cache.get(cache_key)
    if cached:
        return dedupe_queries(cached)

    prompt = f"""You are writing Storyteller authorial retrieval directives for the next narrative turn.

Given the completed source chunk and the player's selected/available choice text,
write 3-5 concise retrieval directives that would help LORE fetch useful prior
continuity before generating the next chunk.

Each directive should be a search instruction, not prose continuity, and should
begin with a verb such as Retrieve. Prefer concrete names, places, relationships,
objects, factions, injuries, promises, unresolved threats, and layout affordances.

Source chunk:
{sample.source_text[:8000]}

Choice text:
{sample.choice_text}

Source references:
- Characters: {', '.join(sample.source_refs.characters) or 'none'}
- Places: {', '.join(sample.source_refs.places) or 'none'}
- Factions: {', '.join(sample.source_refs.factions) or 'none'}
"""
    result, _ = provider.get_structured_completion(prompt, DirectiveSet)
    directives = result.authorial_directives
    cache.set(cache_key, directives)
    cache.save()
    return directives


def build_query_sets(
    context: dict[str, Any],
    *,
    skald_directives: Iterable[str] = (),
    local_llm_queries: Iterable[str] = (),
    raw_chars: int = 0,
) -> list[QuerySet]:
    """Build the three contestant query sets for a context dictionary."""

    raw_text = context["raw_text"] or ""
    raw_query = raw_text if raw_chars <= 0 else raw_text[:raw_chars]
    directives = dedupe_queries(
        list(skald_directives) or context.get("authorial_directives", [])
    )
    local_queries = dedupe_queries(local_llm_queries)

    query_sets = [
        QuerySet(
            name="raw_chunk",
            description="Full source chunk raw text as a single query",
            queries=dedupe_queries([raw_query], limit=1),
        ),
    ]
    if directives:
        query_sets.append(
            QuerySet(
                name="skald_directives",
                description="Storyteller-authored retrieval directives",
                queries=directives,
            )
        )
    if local_queries:
        query_sets.append(
            QuerySet(
                name="local_llm",
                description="Cached historical local-LLM retrieval queries",
                queries=local_queries,
            )
        )

    return [query_set for query_set in query_sets if query_set.queries]


def _init_memnon(slot: int) -> MEMNON:
    return MEMNON(
        interface=MinimalInterface(),
        agent_state=MinimalAgentState(),
        user=MinimalUser(),
        db_url=get_slot_db_url(slot=slot),
        debug=False,
    )


def retrieve_query_set(
    memnon: MEMNON,
    query_set: QuerySet,
    *,
    excluded_chunk_ids: set[int],
    top_k: int,
) -> dict[str, Any]:
    """Execute one query set and aggregate unique ranked results."""

    per_query: list[dict[str, Any]] = []
    unique_results: dict[int, dict[str, Any]] = {}
    self_hits = 0
    started = time.time()

    for query in query_set.queries:
        query_started = time.time()
        response = memnon.query_memory(query, filters=None, k=top_k, use_hybrid=True)
        elapsed = time.time() - query_started
        result_ids: list[int] = []
        for result in response.get("results", []):
            chunk_id = _result_chunk_id(result)
            if chunk_id is None:
                continue
            result_ids.append(chunk_id)
            if chunk_id in excluded_chunk_ids:
                self_hits += 1
                continue
            existing = unique_results.get(chunk_id)
            if existing is None or result.get("score", 0) > existing.get("score", 0):
                unique_results[chunk_id] = result
        per_query.append(
            {
                "query": query,
                "elapsed_seconds": round(elapsed, 3),
                "result_ids": result_ids,
            }
        )

    top_results = sorted(
        unique_results.values(), key=lambda result: result.get("score", 0), reverse=True
    )[:top_k]
    return {
        "query_count": len(query_set.queries),
        "elapsed_seconds": round(time.time() - started, 3),
        "self_hits": self_hits,
        "unique_result_count": len(unique_results),
        "queries": per_query,
        "top_results": [
            {
                "id": _result_chunk_id(result),
                "score": round(float(result.get("score", 0) or 0), 4),
                "text": (result.get("text") or "")[:240],
            }
            for result in top_results
        ],
    }


def _dcg(grades: list[float]) -> float:
    return sum(grade / math.log2(index + 2) for index, grade in enumerate(grades))


def _ndcg_at_k(ranked_ids: list[int], grades: dict[int, float], k: int) -> float:
    ranked_grades = [grades.get(chunk_id, 0.0) for chunk_id in ranked_ids[:k]]
    ideal_grades = sorted(grades.values(), reverse=True)[:k]
    ideal = _dcg(ideal_grades)
    if ideal <= 0:
        return 0.0
    return _dcg(ranked_grades) / ideal


def _mrr(ranked_ids: list[int], relevant: set[int]) -> float:
    for index, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant:
            return 1.0 / index
    return 0.0


def _oracle_grades(
    memnon: MEMNON,
    sample: TurnSample,
    *,
    top_k: int,
) -> dict[int, float]:
    oracle_set = QuerySet(
        name="future_oracle",
        description="Actual next chunk text",
        queries=[sample.target_text],
    )
    result = retrieve_query_set(
        memnon,
        oracle_set,
        excluded_chunk_ids={sample.source_chunk_id, sample.target_chunk_id},
        top_k=top_k,
    )
    grades: dict[int, float] = {}
    for index, row in enumerate(result["top_results"], start=1):
        chunk_id = row["id"]
        if chunk_id is None:
            continue
        if index <= max(1, top_k // 3):
            grades[chunk_id] = 3.0
        elif index <= max(2, (top_k * 2) // 3):
            grades[chunk_id] = 2.0
        else:
            grades[chunk_id] = 1.0
    return grades


def _entity_grades(slot: int, sample: TurnSample) -> dict[int, float]:
    """Grade prior chunks by shared references with the actual next chunk."""

    if not (
        sample.target_refs.characters
        or sample.target_refs.places
        or sample.target_refs.factions
    ):
        return {}

    grades: dict[int, float] = defaultdict(float)
    with psycopg2.connect(get_slot_db_url(slot=slot)) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if sample.target_refs.characters:
                cur.execute(
                    """
                    SELECT r.chunk_id
                    FROM chunk_character_references r
                    JOIN characters c ON c.id = r.character_id
                    WHERE c.name = ANY(%s) AND r.chunk_id < %s
                    """,
                    (sample.target_refs.characters, sample.source_chunk_id),
                )
                for row in cur.fetchall():
                    grades[int(row["chunk_id"])] += 1.0
            if sample.target_refs.places:
                cur.execute(
                    """
                    SELECT r.chunk_id
                    FROM place_chunk_references r
                    JOIN places p ON p.id = r.place_id
                    WHERE p.name = ANY(%s) AND r.chunk_id < %s
                    """,
                    (sample.target_refs.places, sample.source_chunk_id),
                )
                for row in cur.fetchall():
                    grades[int(row["chunk_id"])] += 0.75
            if sample.target_refs.factions:
                cur.execute(
                    """
                    SELECT r.chunk_id
                    FROM chunk_faction_references r
                    JOIN factions f ON f.id = r.faction_id
                    WHERE f.name = ANY(%s) AND r.chunk_id < %s
                    """,
                    (sample.target_refs.factions, sample.source_chunk_id),
                )
                for row in cur.fetchall():
                    grades[int(row["chunk_id"])] += 0.5

    grades.pop(sample.source_chunk_id, None)
    grades.pop(sample.target_chunk_id, None)
    return dict(grades)


def score_strategy_result(
    strategy_result: dict[str, Any],
    *,
    oracle_grades: dict[int, float],
    entity_grades: dict[int, float],
    top_k: int,
) -> dict[str, float]:
    ranked_ids = [
        row["id"] for row in strategy_result["top_results"] if row["id"] is not None
    ]
    oracle_relevant = set(oracle_grades)
    entity_relevant = set(entity_grades)
    oracle_hits = sum(
        1 for chunk_id in ranked_ids[:top_k] if chunk_id in oracle_relevant
    )
    entity_hits = sum(
        1 for chunk_id in ranked_ids[:top_k] if chunk_id in entity_relevant
    )
    return {
        "oracle_recall_at_k": (
            oracle_hits / min(top_k, len(oracle_relevant)) if oracle_relevant else 0.0
        ),
        "oracle_ndcg_at_k": _ndcg_at_k(ranked_ids, oracle_grades, top_k),
        "oracle_mrr": _mrr(ranked_ids, oracle_relevant),
        "entity_precision_at_k": entity_hits / top_k,
        "entity_ndcg_at_k": _ndcg_at_k(ranked_ids, entity_grades, top_k),
    }


def evaluate_sample(
    sample: TurnSample,
    *,
    memnon: MEMNON,
    top_k: int,
    oracle_top_k: int,
    skald_queries: list[str],
    local_queries: list[str],
    raw_chars: int,
) -> dict[str, Any]:
    context = {
        "slot": sample.slot,
        "chunk_id": sample.source_chunk_id,
        "target_chunk_id": sample.target_chunk_id,
        "raw_text": sample.source_text,
        "choice_text": sample.choice_text,
        "authorial_directives": skald_queries,
        "characters": sample.source_refs.characters,
        "places": sample.source_refs.places,
        "factions": sample.source_refs.factions,
    }
    oracle_grades = _oracle_grades(memnon, sample, top_k=oracle_top_k)
    entity_grades = _entity_grades(sample.slot, sample)
    strategies = []
    for query_set in build_query_sets(
        context,
        skald_directives=skald_queries,
        local_llm_queries=local_queries,
        raw_chars=raw_chars,
    ):
        result = retrieve_query_set(
            memnon,
            query_set,
            excluded_chunk_ids={sample.source_chunk_id, sample.target_chunk_id},
            top_k=top_k,
        )
        result.update(
            {
                "name": query_set.name,
                "description": query_set.description,
                "scores": score_strategy_result(
                    result,
                    oracle_grades=oracle_grades,
                    entity_grades=entity_grades,
                    top_k=top_k,
                ),
            }
        )
        strategies.append(result)

    return {
        "sample": {
            "slot": sample.slot,
            "source_chunk_id": sample.source_chunk_id,
            "target_chunk_id": sample.target_chunk_id,
            "source_refs": asdict(sample.source_refs),
            "target_refs": asdict(sample.target_refs),
            "stored_authorial_directive_count": len(sample.authorial_directives),
        },
        "oracle_grade_count": len(oracle_grades),
        "entity_grade_count": len(entity_grades),
        "strategies": strategies,
    }


def bootstrap_ci(
    values: list[float],
    *,
    iterations: int = 2000,
    seed: int = 187,
) -> dict[str, float]:
    """Return mean and percentile bootstrap 95% interval."""

    if not values:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    if len(values) == 1:
        value = float(values[0])
        return {"mean": value, "ci_low": value, "ci_high": value, "n": 1}

    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(sample))
    means.sort()
    low_index = int(0.025 * (len(means) - 1))
    high_index = int(0.975 * (len(means) - 1))
    return {
        "mean": statistics.fmean(values),
        "ci_low": means[low_index],
        "ci_high": means[high_index],
        "n": len(values),
    }


def summarize_samples(sample_results: list[dict[str, Any]]) -> dict[str, Any]:
    by_strategy: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    metadata: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for sample in sample_results:
        for strategy in sample["strategies"]:
            name = strategy["name"]
            metadata[name]["elapsed_seconds"].append(strategy["elapsed_seconds"])
            metadata[name]["query_count"].append(strategy["query_count"])
            metadata[name]["self_hits"].append(strategy["self_hits"])
            metadata[name]["unique_result_count"].append(
                strategy["unique_result_count"]
            )
            for metric, value in strategy["scores"].items():
                by_strategy[name][metric].append(float(value))

    summary: dict[str, Any] = {}
    for name, metrics in by_strategy.items():
        summary[name] = {
            metric: bootstrap_ci(values) for metric, values in metrics.items()
        }
        for metric, values in metadata[name].items():
            summary[name][metric] = {
                "mean": statistics.fmean(values) if values else 0.0,
                "n": len(values),
            }
    return summary


def _sqlite_golden_rows(
    sqlite_path: Path, limit: Optional[int]
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT q.id, q.text, q.category, q.name
            FROM queries q
            WHERE EXISTS (
                SELECT 1 FROM judgments j WHERE j.query_id = q.id
            )
            ORDER BY q.id
            """
        ).fetchall()
        if limit:
            rows = rows[:limit]
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _sqlite_judgments(sqlite_path: Path) -> dict[int, dict[int, int]]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        judgments: dict[int, dict[int, int]] = defaultdict(dict)
        for row in conn.execute(
            "SELECT query_id, doc_id, relevance FROM judgments"
        ).fetchall():
            try:
                judgments[int(row["query_id"])][int(row["doc_id"])] = int(
                    row["relevance"]
                )
            except (TypeError, ValueError):
                continue
        return dict(judgments)
    finally:
        conn.close()


def evaluate_golden_suite(
    *,
    db_url: str,
    sqlite_path: Path,
    limit: Optional[int],
    top_k: int,
) -> dict[str, Any]:
    """Run the existing labeled golden queries as a MEMNON sanity check."""

    queries = _sqlite_golden_rows(sqlite_path, limit)
    judgments = _sqlite_judgments(sqlite_path)
    memnon = MEMNON(
        interface=MinimalInterface(),
        agent_state=MinimalAgentState(),
        user=MinimalUser(),
        db_url=db_url,
        debug=False,
    )

    per_query = []
    for query in queries:
        query_set = QuerySet(
            name="golden_query",
            description=query.get("name") or "",
            queries=[query["text"]],
        )
        result = retrieve_query_set(
            memnon,
            query_set,
            excluded_chunk_ids=set(),
            top_k=top_k,
        )
        grades = {
            chunk_id: float(rel)
            for chunk_id, rel in judgments.get(int(query["id"]), {}).items()
        }
        relevant = {chunk_id for chunk_id, rel in grades.items() if rel > 0}
        ranked_ids = [
            row["id"] for row in result["top_results"] if row["id"] is not None
        ]
        per_query.append(
            {
                "query_id": query["id"],
                "name": query.get("name") or "",
                "category": query.get("category") or "unknown",
                "text": query["text"],
                "p_at_5": sum(1 for chunk_id in ranked_ids[:5] if chunk_id in relevant)
                / 5,
                "p_at_10": sum(
                    1 for chunk_id in ranked_ids[:10] if chunk_id in relevant
                )
                / 10,
                "mrr": _mrr(ranked_ids, relevant),
                "ndcg_at_10": _ndcg_at_k(ranked_ids, grades, 10),
                "elapsed_seconds": result["elapsed_seconds"],
                "top_ids": ranked_ids[:top_k],
            }
        )

    metrics = {
        metric: bootstrap_ci([float(row[metric]) for row in per_query])
        for metric in ("p_at_5", "p_at_10", "mrr", "ndcg_at_10")
    }
    metrics["elapsed_seconds"] = {
        "mean": (
            statistics.fmean(row["elapsed_seconds"] for row in per_query)
            if per_query
            else 0.0
        ),
        "n": len(per_query),
    }
    return {"query_count": len(per_query), "metrics": metrics, "queries": per_query}


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable bake-off report."""

    lines = [
        "# Retrieval Query Strategy Bake-Off",
        "",
        "## Turn-Sample Summary",
        "",
        f"- Samples: {len(report.get('samples', []))}",
        f"- Slots: {', '.join(str(slot) for slot in report.get('slots', []))}",
        "",
        "| Strategy | Metric | Mean | 95% CI | n |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for strategy, metrics in report.get("summary", {}).items():
        for metric, payload in metrics.items():
            if not {"mean", "n"}.issubset(payload):
                continue
            if "ci_low" in payload:
                ci = f"{payload['ci_low']:.4f}-{payload['ci_high']:.4f}"
            else:
                ci = "n/a"
            lines.append(
                f"| {strategy} | {metric} | {payload['mean']:.4f} | {ci} | {payload['n']} |"
            )

    golden = report.get("golden_suite")
    if golden:
        lines.extend(["", "## Golden Query Sanity Check", ""])
        lines.append(f"- Queries: {golden['query_count']}")
        lines.append("")
        lines.append("| Metric | Mean | 95% CI | n |")
        lines.append("| --- | ---: | ---: | ---: |")
        for metric, payload in golden["metrics"].items():
            ci = (
                f"{payload['ci_low']:.4f}-{payload['ci_high']:.4f}"
                if "ci_low" in payload
                else "n/a"
            )
            lines.append(
                f"| {metric} | {payload['mean']:.4f} | {ci} | {payload['n']} |"
            )

    lines.extend(["", "## Sample Details", ""])
    for sample in report.get("samples", [])[:20]:
        meta = sample["sample"]
        lines.append(
            f"### Slot {meta['slot']} Chunk {meta['source_chunk_id']} -> {meta['target_chunk_id']}"
        )
        lines.append("")
        lines.append(
            f"- Oracle grades: {sample['oracle_grade_count']}; entity grades: {sample['entity_grade_count']}"
        )
        for strategy in sample["strategies"]:
            scores = strategy["scores"]
            lines.append(
                f"- {strategy['name']}: oracle_ndcg={scores['oracle_ndcg_at_k']:.3f}, "
                f"entity_ndcg={scores['entity_ndcg_at_k']:.3f}, "
                f"queries={strategy['query_count']}, seconds={strategy['elapsed_seconds']:.1f}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slot",
        action="append",
        type=int,
        dest="slots",
        help="Save slot number; repeat for multiple slots",
    )
    parser.add_argument("--chunk-id", type=int, help="Single chunk to use")
    parser.add_argument("--samples-per-slot", type=int, default=12)
    parser.add_argument("--min-chunk-id", type=int)
    parser.add_argument("--max-chunk-id", type=int)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--oracle-top-k", type=int, default=20)
    parser.add_argument("--raw-chars", type=int, default=0)
    parser.add_argument(
        "--require-stored-directives",
        action="store_true",
        help="Only sample chunks that already have stored directives",
    )
    parser.add_argument(
        "--generate-skald-missing",
        action="store_true",
        help="Backfill missing Skald directives into the cache via OpenAI",
    )
    parser.add_argument("--skald-model", default="@openai.default")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("temp/retrieval_bakeoff/query_cache.json"),
    )
    parser.add_argument(
        "--golden-sqlite",
        type=Path,
        default=Path("ir_eval/ir_eval.db"),
        help="SQLite IR database containing golden queries and judgments",
    )
    parser.add_argument(
        "--golden-db-url",
        default=None,
        help="DB URL for golden-query sanity check; omitted skips the suite",
    )
    parser.add_argument("--golden-limit", type=int, default=None)
    parser.add_argument(
        "--skald-reasoning-effort",
        default="medium",
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning effort for Skald-style directive backfills",
    )
    parser.add_argument(
        "--verbose-logs",
        action="store_true",
        help="Keep MEMNON/LLM library logs visible during long bake-off runs",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def configure_logging(*, verbose: bool) -> None:
    """Keep long bake-off runs readable unless low-level logs are requested."""

    if verbose:
        return
    for logger_name in QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _init_skald_provider(model: str, *, reasoning_effort: str) -> Any:
    from scripts.api_openai import OpenAIProvider

    resolved_model = resolve_api_model_reference(model)
    return OpenAIProvider(
        model=resolved_model,
        max_output_tokens=1200,
        reasoning_effort=reasoning_effort,
        system_prompt=(
            "You write concise retrieval directives for a narrative memory system. "
            "Return only structured directives."
        ),
    )


def resolve_api_model_reference(model: str) -> str:
    """Resolve ``@provider.role`` model references through ``nexus.toml``."""

    if not model.startswith("@"):
        return model

    try:
        provider, role = model[1:].split(".", 1)
    except ValueError as exc:
        raise ValueError(
            f"Expected model reference like '@openai.default', got {model!r}"
        ) from exc

    settings = load_settings()
    provider_config = settings.global_.model.api_models.get(provider)
    if provider_config is None:
        raise ValueError(f"Unknown API model provider in {model!r}")
    resolved = provider_config.roles.get(role)
    if not resolved:
        raise ValueError(f"Unknown API model role in {model!r}")
    return resolved


def main() -> None:
    args = parse_args()
    configure_logging(verbose=args.verbose_logs)
    slots = args.slots or [5]
    cache = JsonCache(args.cache)
    min_chunk_id = args.chunk_id if args.chunk_id is not None else args.min_chunk_id
    max_chunk_id = args.chunk_id if args.chunk_id is not None else args.max_chunk_id

    samples = load_turn_samples(
        slots,
        per_slot=args.samples_per_slot,
        min_chunk_id=min_chunk_id,
        max_chunk_id=max_chunk_id,
        require_directives=args.require_stored_directives,
    )
    if not samples:
        raise RuntimeError("No samples selected")

    skald_provider = (
        _init_skald_provider(
            args.skald_model,
            reasoning_effort=args.skald_reasoning_effort,
        )
        if args.generate_skald_missing
        else None
    )

    memnon_by_slot = {slot: _init_memnon(slot) for slot in sorted(set(slots))}
    sample_results = []
    for index, sample in enumerate(samples, start=1):
        print(
            f"[{index}/{len(samples)}] slot {sample.slot} chunk {sample.source_chunk_id}",
            flush=True,
        )
        skald_queries = sample.authorial_directives
        if not skald_queries and skald_provider is not None:
            skald_queries = generate_skald_directives(
                sample, cache=cache, provider=skald_provider
            )

        local_queries = dedupe_queries(cache.get(f"{sample.key}:local_llm") or [])

        sample_results.append(
            evaluate_sample(
                sample,
                memnon=memnon_by_slot[sample.slot],
                top_k=args.top_k,
                oracle_top_k=args.oracle_top_k,
                skald_queries=skald_queries,
                local_queries=local_queries,
                raw_chars=args.raw_chars,
            )
        )

    report = {
        "slots": slots,
        "parameters": vars(args) | {"cache": str(args.cache)},
        "summary": summarize_samples(sample_results),
        "samples": sample_results,
    }
    if args.golden_db_url:
        report["golden_suite"] = evaluate_golden_suite(
            db_url=args.golden_db_url,
            sqlite_path=args.golden_sqlite,
            limit=args.golden_limit,
            top_k=args.top_k,
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.suffix == ".json":
            args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
        else:
            args.output.write_text(render_markdown(report))
        return

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_markdown(report))


if __name__ == "__main__":
    main()
