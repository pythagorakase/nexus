"""Measure MEMNON presence-weighted retrieval against one database.

The harness reads accepted chunks and their exact presence rosters, then runs
the production hybrid-search entry point with the configured presence arm off
and on. Every database statement issued by this script and the scorer is a
SELECT.

Usage:
    python scripts/measure_presence_boost.py save_02 --top-k 15
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import os
from typing import Any, Dict, Iterable, Mapping, Sequence
from urllib.parse import quote

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager
from nexus.agents.memnon.utils.idf_dictionary import IDFDictionary
from nexus.agents.memnon.utils.search import SearchManager
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config import load_settings_as_dict


@dataclass(frozen=True)
class AcceptedChunk:
    """One accepted narrative chunk and its exact present-character roster."""

    chunk_id: int
    raw_text: str
    present_character_ids: tuple[int, ...]


class CachingEmbeddingManager:
    """Reuse each query embedding across the off/on counterfactual pair."""

    def __init__(self, manager: EmbeddingManager) -> None:
        self._manager = manager
        self._cache: Dict[tuple[str, str], list[float]] = {}

    def get_available_models(self) -> list[str]:
        """Return the wrapped manager's active model keys."""

        return self._manager.get_available_models()

    def generate_embedding(self, query_text: str, model_key: str) -> list[float]:
        """Return one cached embedding for a query/model pair."""

        cache_key = (query_text, model_key)
        if cache_key not in self._cache:
            embedding = self._manager.generate_embedding(query_text, model_key)
            if embedding is None:
                raise RuntimeError(
                    f"Embedding model {model_key!r} returned no query embedding"
                )
            self._cache[cache_key] = embedding
        return self._cache[cache_key]


class ReadOnlyIDFDictionary(IDFDictionary):
    """Build production query weights without reading or writing a cache file."""

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url
        self.idf_dict: Dict[str, float] = {}
        self.total_docs = 0
        self.last_updated = 0

    def _load_from_cache(self) -> bool:
        return False

    def _save_to_cache(self) -> bool:
        return True


def database_url(database: str) -> str:
    """Build a PostgreSQL URL for an explicit database name."""

    if not database or "/" in database or "\x00" in database:
        raise ValueError(f"Invalid PostgreSQL database name: {database!r}")
    user = quote(os.environ.get("PGUSER", "pythagor"), safe="")
    password = os.environ.get("PGPASSWORD")
    credentials = user if password is None else f"{user}:{quote(password, safe='')}"
    host = os.environ.get("PGHOST", "localhost")
    port = int(os.environ.get("PGPORT", "5432"))
    return f"postgresql://{credentials}@{host}:{port}/{quote(database, safe='')}"


def load_measurement_corpus(
    connection: Any,
) -> tuple[list[AcceptedChunk], Dict[int, str]]:
    """Load accepted raw chunks, presence references, and character names."""

    connection.set_session(readonly=True)
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            f"""
            SELECT
                nc.id AS chunk_id,
                nc.raw_text,
                COALESCE(
                    array_agg(DISTINCT ccr.character_id ORDER BY ccr.character_id)
                        FILTER (WHERE ccr.reference::text = 'present'),
                    ARRAY[]::bigint[]
                ) AS present_character_ids
            FROM narrative_chunks AS nc
            LEFT JOIN chunk_character_references AS ccr ON ccr.chunk_id = nc.id
            WHERE {playable_narrative_predicate()}
            GROUP BY nc.id, nc.raw_text
            ORDER BY nc.id
            """
        )
        chunks = []
        for row in cursor.fetchall():
            chunk_id = int(row["chunk_id"])
            raw_text = str(row["raw_text"] or "")
            if not raw_text.strip():
                raise RuntimeError(
                    f"Accepted chunk {chunk_id} has no raw_text retrieval query"
                )
            chunks.append(
                AcceptedChunk(
                    chunk_id=chunk_id,
                    raw_text=raw_text,
                    present_character_ids=tuple(
                        int(character_id)
                        for character_id in row["present_character_ids"]
                    ),
                )
            )
        cursor.execute("SELECT id, name FROM characters ORDER BY id")
        character_names = {
            int(row["id"]): str(row["name"]) for row in cursor.fetchall()
        }
    return chunks, character_names


def _narrative_rank_by_id(results: Iterable[Mapping[str, Any]]) -> Dict[int, int]:
    """Map narrative chunk IDs to one-based result ranks."""

    ranks: Dict[int, int] = {}
    for rank, result in enumerate(results, start=1):
        if result.get("content_type") != "narrative":
            continue
        chunk_id = result.get("chunk_id")
        if chunk_id is not None:
            ranks[int(chunk_id)] = rank
    return ranks


def _gap_entities(
    gap_counts: Counter[int], character_names: Mapping[int, str]
) -> list[Dict[str, Any]]:
    """Render aggregate character gaps in retrieval_coverage_log style."""

    return [
        {
            "kind": "character",
            "id": character_id,
            "name": character_names.get(character_id, f"character:{character_id}"),
            "gap_queries": gap_count,
        }
        for character_id, gap_count in sorted(
            gap_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def measure_presence_boost(
    chunks: Sequence[AcceptedChunk],
    character_names: Mapping[int, str],
    search_manager: SearchManager,
    *,
    top_k: int,
) -> Dict[str, Any]:
    """Run paired retrieval arms and return rank and gap counterfactuals."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")

    references_by_chunk = {
        chunk.chunk_id: set(chunk.present_character_ids) for chunk in chunks
    }
    rank_stats: Dict[str, Counter[str]] = defaultdict(Counter)
    rank_deltas: Dict[str, list[int]] = defaultdict(list)
    baseline_gaps: Counter[int] = Counter()
    boosted_gaps: Counter[int] = Counter()
    resolved_gaps: Counter[int] = Counter()
    introduced_gaps: Counter[int] = Counter()
    entity_opportunities = 0

    for chunk in chunks:
        query_type = str(
            search_manager.query_analyzer.analyze_query(chunk.raw_text).get(
                "type", "general"
            )
        )
        rank_stats[query_type]["queries"] += 1
        baseline = search_manager.perform_hybrid_search(
            query_text=chunk.raw_text,
            top_k=top_k,
            present_character_ids=chunk.present_character_ids,
            presence_boost_enabled=False,
        )
        boosted = search_manager.perform_hybrid_search(
            query_text=chunk.raw_text,
            top_k=top_k,
            present_character_ids=chunk.present_character_ids,
            presence_boost_enabled=True,
        )
        if not baseline or not boosted:
            raise RuntimeError(
                "Hybrid search returned no results for accepted chunk "
                f"{chunk.chunk_id}; baseline={len(baseline)}, boosted={len(boosted)}"
            )
        baseline_ranks = _narrative_rank_by_id(baseline)
        boosted_ranks = _narrative_rank_by_id(boosted)
        roster = set(chunk.present_character_ids)
        presence_candidates = {
            candidate_id
            for candidate_id in baseline_ranks.keys() | boosted_ranks.keys()
            if references_by_chunk.get(candidate_id, set()) & roster
        }
        missing_rank = top_k + 1
        for candidate_id in presence_candidates:
            delta = baseline_ranks.get(candidate_id, missing_rank) - boosted_ranks.get(
                candidate_id, missing_rank
            )
            rank_deltas[query_type].append(delta)
            rank_stats[query_type]["presence_candidates"] += 1
            if delta > 0:
                rank_stats[query_type]["improved"] += 1
            elif delta < 0:
                rank_stats[query_type]["regressed"] += 1
            else:
                rank_stats[query_type]["unchanged"] += 1

        baseline_result_ids = set(baseline_ranks)
        boosted_result_ids = set(boosted_ranks)
        for character_id in chunk.present_character_ids:
            entity_opportunities += 1
            baseline_gap = not any(
                character_id in references_by_chunk.get(result_id, set())
                for result_id in baseline_result_ids
            )
            boosted_gap = not any(
                character_id in references_by_chunk.get(result_id, set())
                for result_id in boosted_result_ids
            )
            if baseline_gap:
                baseline_gaps[character_id] += 1
            if boosted_gap:
                boosted_gaps[character_id] += 1
            if baseline_gap and not boosted_gap:
                resolved_gaps[character_id] += 1
            if boosted_gap and not baseline_gap:
                introduced_gaps[character_id] += 1

    per_query_type: Dict[str, Dict[str, Any]] = {}
    for query_type in sorted(rank_stats):
        stats = rank_stats[query_type]
        deltas = rank_deltas[query_type]
        per_query_type[query_type] = {
            "queries": stats["queries"],
            "presence_candidates": stats["presence_candidates"],
            "improved": stats["improved"],
            "unchanged": stats["unchanged"],
            "regressed": stats["regressed"],
            "mean_rank_delta": (
                round(sum(deltas) / len(deltas), 3) if deltas else None
            ),
            "rank_delta_distribution": dict(sorted(Counter(deltas).items())),
        }

    return {
        "accepted_chunks": len(chunks),
        "top_k": top_k,
        "per_query_type": per_query_type,
        "counterfactual_coverage": {
            "entity_opportunities": entity_opportunities,
            "baseline_gap_count": sum(baseline_gaps.values()),
            "boosted_gap_count": sum(boosted_gaps.values()),
            "baseline_gap_entities": _gap_entities(baseline_gaps, character_names),
            "boosted_gap_entities": _gap_entities(boosted_gaps, character_names),
            "resolved_gap_entities": _gap_entities(resolved_gaps, character_names),
            "introduced_gap_entities": _gap_entities(introduced_gaps, character_names),
        },
    }


def build_search_manager(db_url: str, *, top_k: int) -> SearchManager:
    """Build the production hybrid-search entry point for measurement."""

    memnon_settings = load_settings_as_dict()["Agent Settings"]["MEMNON"]
    embedding_manager = CachingEmbeddingManager(EmbeddingManager(memnon_settings))
    idf_dictionary = ReadOnlyIDFDictionary(db_url)
    idf_dictionary.build_dictionary(force_rebuild=True)
    model_weights = {
        model_name: float(model_config["weight"])
        for model_name, model_config in memnon_settings["models"].items()
    }
    return SearchManager(
        db_url=db_url,
        embedding_manager=embedding_manager,
        idf_dictionary=idf_dictionary,
        settings=memnon_settings,
        retrieval_settings={
            "default_top_k": top_k,
            "model_weights": model_weights,
        },
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the SELECT-only presence-boost measurement harness."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Explicit PostgreSQL database name")
    parser.add_argument("--top-k", type=int, default=15)
    args = parser.parse_args(argv)
    db_url = database_url(args.database)
    with psycopg2.connect(db_url) as connection:
        chunks, character_names = load_measurement_corpus(connection)
    search_manager = build_search_manager(db_url, top_k=args.top_k)
    report = measure_presence_boost(
        chunks,
        character_names,
        search_manager,
        top_k=args.top_k,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
