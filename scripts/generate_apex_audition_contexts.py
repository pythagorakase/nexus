#!/usr/bin/env python3
"""Build static context packages for Apex bakeoff seeds."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import bindparam, create_engine, text as sql_text
from sqlalchemy.engine import Engine

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.lore.lore import LORE
from nexus.memory import ContextMemoryManager
from nexus.agents.lore.utils.token_budget import TokenBudgetManager
from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens

LOGGER = logging.getLogger("apex_audition.builder")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE_DIR / "settings.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "context_packages" / "apex_audition"


@dataclass
class SceneConfig:
    chunk_id: int
    category: str
    label: str
    warm_span: int = 6
    authorial_directives: List[str] = field(default_factory=list)
    structured_targets: Dict[str, List[str]] = field(default_factory=dict)
    inference_directives: List[str] = field(default_factory=list)
    notes: Optional[str] = None


SCENES: Dict[int, SceneConfig] = {
    3: SceneConfig(
        chunk_id=3,
        category="Intrigue & Deception",
        label="Sato briefs Alex on Dr. Voss disappearance",
        warm_span=4,
        structured_targets={
            "characters": ["Alex", "Victor Sato", "Alina"],
            "places": ["Skyline Lounge"],
        },
    ),
    49: SceneConfig(
        chunk_id=49,
        category="Intrigue & Deception",
        label="Hunting the third player behind the hit",
        warm_span=6,
        structured_targets={
            "characters": ["Alex", "Pete", "Victor Sato", "Asmodeus"],
            "places": ["Coastal Safehouse"],
        },
    ),
    59: SceneConfig(
        chunk_id=59,
        category="Intrigue & Deception",
        label="Framing Sato for the Halcyon breach",
        warm_span=6,
        structured_targets={
            "characters": ["Alex", "Pete", "Victor Sato", "Asmodeus"],
            "places": ["Halcyon Atrium"],
        },
    ),
    615: SceneConfig(
        chunk_id=615,
        category="Intrigue & Deception",
        label="Alex-5 forecasts Lansky's motives",
        warm_span=6,
        authorial_directives=[
            "Lansky's prior communications with Alex and the Ghost crew since the Bridge discovery",
            "Alex-5 analyses or risk assessments involving Lansky and his agendas",
            "Bridge intelligence linking Lansky's breadcrumbs to Sam or other guardians",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Nyati", "Pete", "Lansky", "Alex-5"],
            "places": ["The Land Rig"],
        },
        inference_directives=["Lansky motive review"],
    ),
    293: SceneConfig(
        chunk_id=293,
        category="Existential & Philosophical",
        label="Listening to the abyssal resonance",
        warm_span=6,
        authorial_directives=[
            "Surveyor-9 deep ocean deployments before the Cradle encounter",
            "Records of resonance signals detected beneath The Ghost during prior abyss missions",
            "Team discussions about unidentified megastructures in extreme depths",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Alina", "Nyati"],
            "places": ["The Ghost"],
        },
    ),
    298: SceneConfig(
        chunk_id=298,
        category="Existential & Philosophical",
        label="Structure or entity below The Ghost",
        warm_span=6,
        authorial_directives=[
            "Alina's analyses comparing abyssal structures to living entities",
            "Nyati's hypotheses about automated Bridge installations underwater",
            "Anomalies where sonar reported stationary distortions that later moved",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Alina", "Nyati"],
            "places": ["The Ghost"],
        },
    ),
    756: SceneConfig(
        chunk_id=756,
        category="Character & Relationship",
        label="Alex and Emilia at karaoke, eyes on the room",
        warm_span=8,
        authorial_directives=[
            "Virginia Beach karaoke night moments leading to Alex and Emilia holding hands",
            "Emilia's reactions when Alex let her guard down earlier in the evening",
            "Pete or Nyati commentary on Alex and Emilia's chemistry during the outing",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Pete", "Nyati"],
            "places": ["Virginia Beach Streets"],
        },
    ),
    898: SceneConfig(
        chunk_id=898,
        category="Existential & Philosophical",
        label="Cradle-dweller wants a missing designation",
        warm_span=6,
        authorial_directives=[
            "Cradle-dweller communications about missing designations or identities",
            "Bridge-touched entities describing themselves as incomplete",
            "Alex's bridge-listening ability and prior uses to respond to anomalies",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Nyati", "Pete", "Alina", "The Cradle Dweller"],
            "places": ["The Ghost"],
        },
    ),
    5: SceneConfig(
        chunk_id=5,
        category="Action",
        label="Downtown sniper ambush",
        warm_span=4,
        structured_targets={
            "characters": ["Alex", "Victor Sato"],
            "places": ["Night City Streets"],
        },
    ),
    148: SceneConfig(
        chunk_id=148,
        category="Action",
        label="EMP convoy trap against Vox team",
        warm_span=6,
        authorial_directives=[
            "Intel on the Vox Logistics convoy cargo and objectives",
            "After-action notes on Alex-led ambushes using EMP traps and drones",
            "Profiles of Vox security operatives encountered during the raid",
        ],
        structured_targets={
            "characters": ["Alex", "Pete", "Alina", "Nyati"],
            "places": ["Coastal Highway"],
        },
    ),
    620: SceneConfig(
        chunk_id=620,
        category="Intrigue & Deception",
        label="Arguing Sam and Lansky as complementary sources",
        warm_span=6,
        authorial_directives=[
            "Sam's statements about the Bridge that hint at gaps he cannot explain",
            "Timeline of Lansky's breadcrumb messages and the doors he opened",
            "Team debates weighing risks of combining intel from Sam and Lansky",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia", "Nyati", "Pete", "Lansky", "Sam"],
            "places": ["The Land Rig"],
        },
    ),
    518: SceneConfig(
        chunk_id=518,
        category="Character & Relationship",
        label="Seaside confession about control",
        warm_span=7,
        authorial_directives=[
            "Earlier conversations where Emilia challenged Alex about control and vulnerability",
            "Alex admitting fears about intimacy or losing control around Emilia",
            "Quiet Virginia Beach moments between Alex and Emilia before the seaside bar scene",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia"],
            "places": ["Virginia Beach Streets"],
        },
    ),
    754: SceneConfig(
        chunk_id=754,
        category="Character & Relationship",
        label="Emilia says 'I see you' at karaoke",
        warm_span=8,
        authorial_directives=[
            "Lead-up exchanges during the karaoke duet when Emilia warned Alex about dangerous games",
            "Emilia reassuring Alex or acknowledging her feelings earlier in Season 3",
            "Alex's internal reflections about loving Emilia during the Virginia Beach arc",
        ],
        structured_targets={
            "characters": ["Alex", "Emilia"],
            "places": ["Virginia Beach Streets"],
        },
    ),
    936: SceneConfig(
        chunk_id=936,
        category="Intrigue & Deception",
        label="Nyati begs Sam to undo the damage",
        warm_span=6,
        authorial_directives=[
            "Sam's prior hints about reversing or undoing Bridge transformations",
            "Nyati's confrontations with Sam over fallout from the Bridge experiments",
            "Records describing how Alex was altered by the Bridge and why Nyati wants a cure",
        ],
        structured_targets={
            "characters": ["Nyati", "Sam", "Alex", "Emilia"],
            "places": ["The Ghost"],
        },
    ),
}


class MinimalInterface:
    """Tiny interface object to satisfy MEMNON logging hooks."""

    def assistant_message(self, message: str) -> None:  # pragma: no cover - simple logging bridge
        LOGGER.debug("MEMNON: %s", message)

    def error_message(self, message: str) -> None:  # pragma: no cover - simple logging bridge
        LOGGER.error("MEMNON ERROR: %s", message)


@dataclass
class WarmChunk:
    chunk_id: int
    text: str
    season: Optional[int] = None
    episode: Optional[int] = None
    scene: Optional[int] = None
    world_time: Optional[str] = None
    world_layer: Optional[str] = None
    token_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "season": self.season,
            "episode": self.episode,
            "scene": self.scene,
            "world_time": self.world_time,
            "world_layer": self.world_layer,
            "token_count": self.token_count,
        }


class ContextSeedBuilder:
    def __init__(
        self,
        *,
        settings_path: Path = SETTINGS_PATH,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        use_lore: bool = False,
    ) -> None:
        self.settings_path = settings_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with settings_path.open("r", encoding="utf-8") as handle:
            self.settings = json.load(handle)

        self.engine: Engine = create_engine("postgresql://pythagor@localhost:5432/NEXUS")

        self.memnon = MEMNON(interface=MinimalInterface(), debug=False)
        self.token_manager = TokenBudgetManager(self.settings)
        self.memory_manager = ContextMemoryManager(
            self.settings,
            memnon=self.memnon,
            llm_manager=None,
            token_manager=self.token_manager,
        )

        lore_settings = self.settings.get("Agent Settings", {}).get("LORE", {})
        payload_budget = lore_settings.get("payload_percent_budget", {})
        self.payload_budget = {
            "warm_slice": payload_budget.get("warm_slice", {"min": 30, "max": 70}),
            "structured_summaries": payload_budget.get("structured_summaries", {"min": 10, "max": 25}),
            "contextual_augmentation": payload_budget.get("contextual_augmentation", {"min": 25, "max": 40}),
        }

        self.use_lore = use_lore
        self._lore_agent: Optional[LORE] = None

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------
    def _fetch_chunk_text(self, chunk_id: int) -> Dict[str, Any]:
        query = sql_text(
            """
            SELECT id, season, episode, scene, world_time, world_layer, raw_text
            FROM narrative_view
            WHERE id = :chunk_id
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"chunk_id": chunk_id}).fetchone()
        if not row:
            raise ValueError(f"Chunk {chunk_id} not found")
        mapping = row._mapping
        raw_text = mapping["raw_text"]
        storyteller, user_input = self._split_storyteller_user(raw_text)
        return {
            "chunk_id": chunk_id,
            "season": mapping.get("season"),
            "episode": mapping.get("episode"),
            "scene": mapping.get("scene"),
            "world_time": self._fmt_time(mapping.get("world_time")),
            "world_layer": mapping.get("world_layer"),
            "raw_text": raw_text,
            "storyteller": storyteller,
            "user_input": user_input,
        }

    def _fetch_warm_slice(
        self,
        *,
        chunk_id: int,
        span: int,
        target_tokens: Optional[int] = None,
    ) -> List[WarmChunk]:
        query = sql_text(
            """
            SELECT id, season, episode, scene, world_time, world_layer, raw_text
            FROM narrative_view
            WHERE id BETWEEN :start AND :end
            ORDER BY id
            """
        )

        current_span = max(span, 1)
        start_id = max(1, chunk_id - (current_span - 1))

        with self.engine.connect() as conn:
            while True:
                rows = conn.execute(query, {"start": start_id, "end": chunk_id}).fetchall()
                warm_chunks: List[WarmChunk] = []
                total_tokens = 0
                for row in rows:
                    mapping = row._mapping
                    token_count = calculate_chunk_tokens(mapping["raw_text"])
                    total_tokens += token_count
                    warm_chunks.append(
                        WarmChunk(
                            chunk_id=mapping["id"],
                            text=mapping["raw_text"],
                            season=mapping.get("season"),
                            episode=mapping.get("episode"),
                            scene=mapping.get("scene"),
                            world_time=self._fmt_time(mapping.get("world_time")),
                            world_layer=mapping.get("world_layer"),
                            token_count=token_count,
                        )
                    )

                if (
                    target_tokens is None
                    or total_tokens >= target_tokens
                    or start_id == 1
                ):
                    return warm_chunks

                # Expand window and try again
                current_span *= 2
                new_start = max(1, chunk_id - (current_span - 1))
                if new_start == start_id:
                    return warm_chunks
                start_id = new_start

    @staticmethod
    def _fmt_time(value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _split_storyteller_user(raw_text: str) -> tuple[str, str]:
        marker = "\n## You"
        if marker not in raw_text:
            return raw_text.strip(), ""
        storyteller, user_section = raw_text.split(marker, 1)
        return storyteller.strip(), user_section.replace("## You", "", 1).strip()

    # ------------------------------------------------------------------
    # Structured entity enrichment
    # ------------------------------------------------------------------
    def _gather_entity_data(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        characters: List[Dict[str, Any]] = []
        locations: List[Dict[str, Any]] = []

        for name in (analysis.get("characters") or [])[:3]:
            try:
                characters.extend(self.memnon._query_structured_data(name, "characters", limit=1))
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Structured character lookup failed for %s: %s", name, exc)

        for name in (analysis.get("locations") or [])[:2]:
            try:
                locations.extend(self.memnon._query_structured_data(name, "places", limit=1))
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Structured place lookup failed for %s: %s", name, exc)

        return {"characters": characters, "locations": locations}

    def _collect_structured_targets(self, targets: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        if not targets:
            return []

        aggregated: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for table, names in targets.items():
            if table not in {"characters", "places"}:
                LOGGER.debug("Skipping unsupported structured table '%s'", table)
                continue

            for name in names:
                lookup = name.strip()
                if not lookup:
                    continue

                try:
                    results = self.memnon._query_structured_data(lookup, table, limit=3)
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.warning("Structured query failed for %s:%s - %s", table, lookup, exc)
                    continue

                for entry in results:
                    identifier = str(entry.get("id") or entry.get("chunk_id") or lookup)
                    key = (table, identifier)
                    if key in seen:
                        continue
                    seen.add(key)
                    normalized = dict(entry)
                    entry_id = normalized.pop("id", None)
                    entry_chunk = normalized.pop("chunk_id", None)
                    if entry_id is not None:
                        normalized.setdefault("structured_id", entry_id)
                    if entry_chunk is not None:
                        normalized.setdefault("reference_chunk_id", entry_chunk)
                    normalized.setdefault("structured_table", table)
                    normalized.setdefault("query", lookup)
                    normalized.setdefault("query_source", "structured_seed")
                    aggregated.append(normalized)

        return aggregated

    def _resolve_character_ids(self, names: Iterable[str]) -> Dict[int, Dict[str, str]]:
        resolved: Dict[int, Dict[str, str]] = {}
        seen_aliases: Set[str] = set()

        for raw_name in names:
            if not isinstance(raw_name, str):
                continue
            lookup = raw_name.strip()
            if not lookup or lookup.lower() in seen_aliases:
                continue
            seen_aliases.add(lookup.lower())

            try:
                results = self.memnon._query_structured_data(lookup, "characters", limit=1)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Character resolution failed for %s: %s", lookup, exc)
                continue

            if not results:
                continue

            entry = results[0]
            char_id = entry.get("id") or entry.get("character_id")
            if char_id is None:
                continue

            try:
                int_id = int(char_id)
            except (TypeError, ValueError):
                continue

            resolved[int_id] = {
                "name": entry.get("name") or lookup,
            }

        return resolved

    def _collect_character_relationships(self, resolved: Dict[int, Dict[str, str]]) -> List[Dict[str, Any]]:
        if len(resolved) < 2:
            return []

        character_ids = sorted(resolved.keys())

        query = (
            sql_text(
                "SELECT character1_id, character2_id, relationship_type, "
                "emotional_valence, dynamic, history, extra_data "
                "FROM character_relationships "
                "WHERE character1_id IN :ids1 OR character2_id IN :ids2"
            )
            .bindparams(bindparam("ids1", expanding=True))
            .bindparams(bindparam("ids2", expanding=True))
        )

        entries: List[Dict[str, Any]] = []
        seen_pairs: Set[tuple[int, int]] = set()

        with self.engine.connect() as conn:
            rows = conn.execute(
                query,
                {"ids1": character_ids, "ids2": character_ids},
            ).fetchall()

        for row in rows:
            mapping = row._mapping
            char1 = int(mapping["character1_id"])
            char2 = int(mapping["character2_id"])
            if char1 not in resolved or char2 not in resolved:
                continue
            pair_key = (char1, char2)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            rel_type = mapping.get("relationship_type")
            valence = mapping.get("emotional_valence")
            dynamic = mapping.get("dynamic")
            history = mapping.get("history")
            extra = mapping.get("extra_data")

            summary_parts = []
            if rel_type:
                summary_parts.append(f"type={rel_type}")
            if valence:
                summary_parts.append(f"valence={valence}")
            if dynamic:
                summary_parts.append(f"dynamic={dynamic}")
            if history:
                summary_parts.append("history included")
            if extra:
                summary_parts.append("extra_data included")

            summary = "{} -> {}".format(
                resolved[char1]["name"], resolved[char2]["name"]
            )
            if summary_parts:
                summary = f"{summary}: {', '.join(summary_parts)}"

            entries.append(
                {
                    "structured_table": "character_relationships",
                    "structured_id": f"{char1}->{char2}",
                    "character1_id": char1,
                    "character1_name": resolved[char1]["name"],
                    "character2_id": char2,
                    "character2_name": resolved[char2]["name"],
                    "relationship_type": rel_type,
                    "emotional_valence": valence,
                    "dynamic": dynamic,
                    "history": history,
                    "extra_data": extra,
                    "summary": summary,
                    "query": f"{resolved[char1]['name']} relationship toward {resolved[char2]['name']}",
                    "query_source": "auto_character_relationship",
                }
            )

        return entries

    def _collect_character_profiles(self, resolved: Dict[int, Dict[str, str]]) -> List[Dict[str, Any]]:
        if not resolved:
            return []

        character_ids = sorted(resolved.keys())
        query = (
            sql_text(
                "SELECT id, name, background, personality, extra_data "
                "FROM characters WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
        )

        entries: List[Dict[str, Any]] = []
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"ids": character_ids}).fetchall()

        for row in rows:
            mapping = row._mapping
            name = mapping.get("name") or resolved.get(mapping["id"], {}).get("name")
            background = mapping.get("background")
            personality = mapping.get("personality")
            extra = mapping.get("extra_data")

            text_parts: List[str] = []
            if background:
                text_parts.append(f"Background:\n{background}")
            if personality:
                text_parts.append(f"Personality:\n{personality}")
            if extra:
                try:
                    extra_text = json.dumps(extra, ensure_ascii=False, indent=2)
                except TypeError:
                    extra_text = str(extra)
                text_parts.append(f"Extra Data:\n{extra_text}")

            if not text_parts:
                continue

            entries.append(
                {
                    "structured_table": "characters",
                    "structured_id": int(mapping["id"]),
                    "name": name,
                    "background": background,
                    "personality": personality,
                    "extra_data": extra,
                    "summary": "\n\n".join(text_parts),
                    "query": f"{name} background, personality, and extra data",
                    "query_source": "auto_character_profile",
                }
            )

        return entries

    def _resolve_place_ids(self, names: Iterable[str]) -> Dict[int, Dict[str, str]]:
        resolved: Dict[int, Dict[str, str]] = {}
        seen_aliases: Set[str] = set()

        for raw_name in names:
            if not isinstance(raw_name, str):
                continue
            lookup = raw_name.strip()
            if not lookup or lookup.lower() in seen_aliases:
                continue
            seen_aliases.add(lookup.lower())

            try:
                results = self.memnon._query_structured_data(lookup, "places", limit=1)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Place resolution failed for %s: %s", lookup, exc)
                continue

            if not results:
                continue

            entry = results[0]
            place_id = entry.get("id") or entry.get("place_id")
            if place_id is None:
                continue

            try:
                int_id = int(place_id)
            except (TypeError, ValueError):
                continue

            resolved[int_id] = {
                "name": entry.get("name") or lookup,
            }

        return resolved

    def _collect_place_details(self, resolved: Dict[int, Dict[str, str]]) -> List[Dict[str, Any]]:
        if not resolved:
            return []

        place_ids = sorted(resolved.keys())
        query = (
            sql_text(
                "SELECT id, name, summary, history, secrets, extra_data "
                "FROM places WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
        )

        entries: List[Dict[str, Any]] = []
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"ids": place_ids}).fetchall()

        for row in rows:
            mapping = row._mapping
            name = mapping.get("name") or resolved.get(mapping["id"], {}).get("name")
            summary = mapping.get("summary")
            history = mapping.get("history")
            secrets = mapping.get("secrets")
            extra = mapping.get("extra_data")

            text_parts: List[str] = []
            if summary:
                text_parts.append(f"Summary:\n{summary}")
            if history:
                text_parts.append(f"History:\n{history}")
            if secrets:
                text_parts.append(f"Secrets:\n{secrets}")
            if extra:
                try:
                    extra_text = json.dumps(extra, ensure_ascii=False, indent=2)
                except TypeError:
                    extra_text = str(extra)
                text_parts.append(f"Extra Data:\n{extra_text}")

            if not text_parts:
                continue

            combined = "\n\n".join(text_parts)

            entries.append(
                {
                    "structured_table": "places",
                    "structured_id": int(mapping["id"]),
                    "name": name,
                    "summary": combined,
                    "history": history,
                    "secrets": secrets,
                    "extra_data": extra,
                    "query": f"{name} location dossier",
                    "query_source": "auto_place_profile",
                }
            )

        return entries

    def _build_psychology_directive(
        self,
        resolved_characters: Dict[int, Dict[str, str]],
        chunk_id: int,
    ) -> Optional[str]:
        if not resolved_characters or not self.use_lore:
            return None

        names = [info.get("name") for info in resolved_characters.values() if info.get("name")]
        if not names:
            return None

        names_sorted = sorted(set(names))
        # Keep directive concise by limiting listed names
        preview_names = names_sorted[:8]
        listing = ", ".join(preview_names)
        if len(names_sorted) > len(preview_names):
            listing += ", ..."

        directive = textwrap.dedent(
            f"""
            Character psychology focus for chunk {chunk_id}: choose the one or two characters from [{listing}] whose mental state most influences the upcoming continuation. Query the character_psychology table for each chosen character and surface the columns self_concept, behavior, cognitive_framework, temperament, relational_style, defense_mechanisms, character_arc, and secrets. Skip validation_evidence, created_at, and updated_at. Present the raw column values clearly labeled, then summarize why each profile matters for continuity.
            """
        ).strip()

        return directive

    def _fetch_structured_summaries(self, season: Optional[int], episode: Optional[int]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if season is None:
            return entries

        seen_keys: Set[tuple[str, str]] = set()

        with self.engine.connect() as conn:
            if season > 1:
                season_rows = conn.execute(
                    sql_text("SELECT id, summary FROM seasons WHERE id < :season ORDER BY id"),
                    {"season": season},
                ).fetchall()
                for row in season_rows:
                    if not row.summary:
                        continue
                    summary_text = self._normalize_summary_text(row.summary)
                    key = ("seasons", str(row.id))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    entries.append(
                        {
                            "structured_table": "seasons",
                            "structured_id": int(row.id),
                            "season": int(row.id),
                            "summary": summary_text,
                            "query": f"Season {int(row.id)} summary",
                            "query_source": "auto_season_summary",
                        }
                    )

            if episode is not None:
                episode_rows = conn.execute(
                    sql_text(
                        "SELECT season, episode, summary FROM episodes "
                        "WHERE season = :season AND episode < :episode ORDER BY episode"
                    ),
                    {"season": season, "episode": episode},
                ).fetchall()
                for row in episode_rows:
                    if not row.summary:
                        continue
                    summary_text = self._normalize_summary_text(row.summary)
                    key = ("episodes", f"{int(row.season)}-{int(row.episode)}")
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    entries.append(
                        {
                            "structured_table": "episodes",
                            "structured_id": key[1],
                            "season": int(row.season),
                            "episode": int(row.episode),
                            "summary": summary_text,
                            "query": f"Episode S{int(row.season):02d}E{int(row.episode):02d} summary",
                            "query_source": "auto_episode_summary",
                        }
                    )

                if episode == 1 and season > 1:
                    finale_row = conn.execute(
                        sql_text(
                            "SELECT season, episode, summary FROM episodes "
                            "WHERE season = :season ORDER BY episode DESC LIMIT 1"
                        ),
                        {"season": season - 1},
                    ).fetchone()
                    if finale_row and finale_row.summary:
                        summary_text = self._normalize_summary_text(finale_row.summary)
                        key = ("episodes", f"{int(finale_row.season)}-{int(finale_row.episode)}")
                        if key not in seen_keys:
                            seen_keys.add(key)
                            entries.append(
                                {
                                    "structured_table": "episodes",
                                    "structured_id": key[1],
                                    "season": int(finale_row.season),
                                    "episode": int(finale_row.episode),
                                    "summary": summary_text,
                                    "query": f"Episode S{int(finale_row.season):02d}E{int(finale_row.episode):02d} summary",
                                    "query_source": "auto_previous_season_finale",
                                }
                            )
        return entries

    @staticmethod
    def _normalize_summary_text(summary: Any) -> str:
        if isinstance(summary, str):
            return summary
        try:
            return json.dumps(summary, ensure_ascii=False, indent=2)
        except TypeError:
            return str(summary)

    async def _run_lore_inference_async(
        self,
        directives: List[str],
        chunk_id: int,
    ) -> List[Dict[str, Any]]:
        if not directives:
            return []

        if self._lore_agent is None:
            self._lore_agent = LORE(debug=False, enable_logon=False)

        results = await self._lore_agent.retrieve_context(directives, chunk_id=chunk_id)
        entries: List[Dict[str, Any]] = []
        directive_map = results.get("directives", {}) if results else {}
        for directive in directives:
            payload = directive_map.get(directive)
            if not payload:
                continue
            summary_text = payload.get("retrieved_context")
            if not summary_text:
                continue
            entry = {
                "structured_table": "lore_inference",
                "structured_id": directive,
                "summary": summary_text,
                "query": directive,
                "query_source": "lore_inference",
            }
            entries.append(entry)
        return entries

    def _fetch_lore_inference_entries(
        self,
        directives: List[str],
        chunk_id: int,
    ) -> List[Dict[str, Any]]:
        if not self.use_lore or not directives:
            return []
        try:
            return asyncio.run(self._run_lore_inference_async(directives, chunk_id))
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("LORE inference retrieval failed: %s", exc)
            return []

    def _estimate_structured_tokens(self, entry: Dict[str, Any]) -> int:
        if "token_count" in entry and isinstance(entry["token_count"], int):
            return entry["token_count"]
        text_candidates: List[str] = []
        for key in ("summary", "details", "text", "content"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                text_candidates.append(value)
        if not text_candidates:
            text_candidates.append(self._normalize_summary_text(entry))
        tokens = calculate_chunk_tokens("\n".join(text_candidates))
        entry["token_count"] = tokens
        return tokens

    def _estimate_retrieval_tokens(self, entry: Dict[str, Any]) -> int:
        if "token_count" in entry and isinstance(entry["token_count"], int):
            return entry["token_count"]
        text = entry.get("text") or entry.get("raw_text") or ""
        tokens = calculate_chunk_tokens(text)
        entry["token_count"] = tokens
        return tokens

    def _apply_payload_budgets(
        self,
        assembled_context: Dict[str, Any],
        token_counts: Dict[str, int],
    ) -> None:
        total_available = token_counts.get("total_available", 0)
        if total_available <= 0:
            return

        warm_chunks = assembled_context.get("warm_slice", {}).get("chunks", [])
        structured_entries = assembled_context.get("structured_passages", []) or []
        retrieved_entries = assembled_context.get("retrieved_passages", {}).get("results", []) or []

        warm_tokens = sum(max(0, chunk.get("token_count") or 0) for chunk in warm_chunks)
        structured_info = [
            (entry, self._estimate_structured_tokens(entry)) for entry in structured_entries
        ]
        structured_entries = [entry for entry, _ in structured_info]
        structured_tokens = sum(tokens for _, tokens in structured_info)
        retrieved_info = [
            (entry, self._estimate_retrieval_tokens(entry)) for entry in retrieved_entries
        ]
        retrieved_entries = [entry for entry, _ in retrieved_info]
        retrieved_tokens = sum(tokens for _, tokens in retrieved_info)

        def bounds(category: str) -> tuple[int, int]:
            config = self.payload_budget.get(category, {})
            percent_min = float(config.get("min", 0)) / 100.0
            percent_max = float(config.get("max", 100)) / 100.0
            return int(total_available * percent_min), int(total_available * percent_max)

        warm_min, warm_max = bounds("warm_slice")
        _, structured_max = bounds("structured_summaries")
        _, augmentation_max = bounds("contextual_augmentation")

        # Trim warm slice by dropping oldest chunks if we exceed max
        if warm_tokens > warm_max and warm_max > 0:
            # Sort oldest first
            warm_chunks.sort(key=lambda chunk: chunk.get("chunk_id", 0))
            while warm_chunks and warm_tokens > warm_max:
                removed = warm_chunks.pop(0)
                warm_tokens -= max(0, removed.get("token_count") or 0)
            assembled_context["warm_slice"]["chunks"] = warm_chunks
            assembled_context["warm_slice"]["token_count"] = warm_tokens

        # Trim structured passages while protecting season/episode summaries
        if structured_tokens > structured_max and structured_max > 0:
            def priority(item: Dict[str, Any]) -> int:
                table = item.get("structured_table")
                if table in {"seasons", "episodes"}:
                    return 0
                return 1

            structured_info.sort(key=lambda pair: (priority(pair[0]), -pair[1]))
            while structured_info and structured_tokens > structured_max:
                entry, tokens = structured_info.pop()
                structured_tokens -= tokens
            structured_entries = [entry for entry, _ in structured_info]
            assembled_context["structured_passages"] = structured_entries

        # Trim retrieved passages according to score/ token size
        if retrieved_tokens > augmentation_max and augmentation_max > 0:
            retrieved_info.sort(key=lambda pair: pair[0].get("score", 0.0))
            while retrieved_info and retrieved_tokens > augmentation_max:
                entry, tokens = retrieved_info.pop(0)
                retrieved_tokens -= tokens
            retrieved_entries = [entry for entry, _ in retrieved_info]
            assembled_context["retrieved_passages"]["results"] = retrieved_entries

        # Update token counts after trimming
        assembled_context["warm_slice"]["token_count"] = sum(
            max(0, chunk.get("token_count") or 0) for chunk in assembled_context["warm_slice"]["chunks"]
        )
        structured_tokens = sum(self._estimate_structured_tokens(entry) for entry in structured_entries)
        assembled_context.setdefault("structured_passages", [])
        assembled_context["retrieved_passages"]["token_count"] = sum(
            self._estimate_retrieval_tokens(entry) for entry in retrieved_entries
        )



    # ------------------------------------------------------------------
    # Package assembly
    # ------------------------------------------------------------------
    def build_scene_package(self, config: SceneConfig) -> Dict[str, Any]:
        chunk = self._fetch_chunk_text(config.chunk_id)
        storyteller_text = chunk["storyteller"]
        user_input = chunk["user_input"] or "(No user input recorded)"

        token_counts = self.token_manager.calculate_budget(user_input)

        warm_min_percent = float(self.payload_budget["warm_slice"].get("min", 0)) / 100.0
        warm_target_tokens = int(token_counts.get("total_available", 0) * warm_min_percent)
        warm_slice = self._fetch_warm_slice(
            chunk_id=config.chunk_id,
            span=config.warm_span,
            target_tokens=warm_target_tokens if warm_target_tokens > 0 else None,
        )

        analysis = self.memory_manager._analyze_storyteller_output(storyteller_text)
        entity_data = self._gather_entity_data(analysis)

        present_characters: Set[str] = set()
        for key in ("characters", "expected"):
            for name in analysis.get(key) or []:
                if isinstance(name, str) and name.strip():
                    present_characters.add(name.strip())
        for name in config.structured_targets.get("characters", []):
            if name:
                present_characters.add(name.strip())
        for entry in entity_data.get("characters", []):
            if isinstance(entry, dict):
                label = entry.get("name") or entry.get("display_name")
                if isinstance(label, str) and label.strip():
                    present_characters.add(label.strip())

        present_places: Set[str] = set()
        for name in analysis.get("locations") or []:
            if isinstance(name, str) and name.strip():
                present_places.add(name.strip())
        for name in config.structured_targets.get("places", []):
            if name:
                present_places.add(name.strip())
        for entry in entity_data.get("locations", []):
            if isinstance(entry, dict):
                label = entry.get("name") or entry.get("display_name")
                if isinstance(label, str) and label.strip():
                    present_places.add(label.strip())

        resolved_characters = self._resolve_character_ids(present_characters)
        resolved_places = self._resolve_place_ids(present_places)

        structured_seed: List[Dict[str, Any]] = []
        summary_entries = self._fetch_structured_summaries(
            season=chunk.get("season"),
            episode=chunk.get("episode"),
        )
        if summary_entries:
            structured_seed.extend(summary_entries)

        structured_seed.extend(self._collect_structured_targets(config.structured_targets))
        structured_seed.extend(self._collect_character_profiles(resolved_characters))
        structured_seed.extend(self._collect_place_details(resolved_places))
        structured_seed.extend(self._collect_character_relationships(resolved_characters))

        inference_directives = list(config.inference_directives)
        psych_directive = self._build_psychology_directive(resolved_characters, config.chunk_id)
        if psych_directive:
            inference_directives.append(psych_directive)
        structured_seed.extend(
            self._fetch_lore_inference_entries(inference_directives, config.chunk_id)
        )

        assembled_context: Dict[str, Any] = {
            "user_input": user_input,
            "warm_slice": {
                "chunks": [wc.to_dict() for wc in warm_slice],
                "token_count": sum((wc.token_count or 0) for wc in warm_slice),
                "allocation": token_counts.get("warm_slice", 0),
            },
            "entity_data": entity_data,
            "retrieved_passages": {
                "results": [],
                "token_count": 0,
                "allocation": token_counts.get("augmentation", 0),
            },
            "analysis": analysis,
            "metadata": {
                "chunk_id": config.chunk_id,
                "category": config.category,
                "label": config.label,
                "authorial_directives": list(config.authorial_directives),
            },
            "memory_state": {},
            "token_budget": token_counts,
        }

        baseline = self.memory_manager.handle_storyteller_response(
            narrative=storyteller_text,
            warm_slice=[wc.to_dict() for wc in warm_slice],
            retrieved_passages=[dict(item) for item in structured_seed],
            token_usage=token_counts,
            assembled_context=assembled_context,
            authorial_directives=config.authorial_directives,
        )

        transition = self.memory_manager.context_state.transition
        self._apply_payload_budgets(assembled_context, token_counts)

        def _intify(values: Iterable[Any]) -> List[int]:
            cleaned: List[int] = []
            for value in values:
                try:
                    cleaned.append(int(value))
                except (TypeError, ValueError):
                    LOGGER.debug("Skipping non-integer chunk id %s", value)
            return sorted(cleaned)

        baseline_snapshot = {
            "baseline_chunks": _intify(baseline.baseline_chunks),
            "baseline_themes": baseline.baseline_themes,
            "expected_user_themes": transition.expected_user_themes if transition else [],
            "remaining_budget": self.memory_manager.context_state.get_remaining_budget(),
            "authorial_directives": baseline.authorial_directives,
            "structured_passages": baseline.structured_passages,
        }

        memory_state_snapshot = dict(baseline_snapshot)
        memory_state_snapshot.pop("authorial_directives", None)
        assembled_context.setdefault("memory_state", {})["pass1"] = memory_state_snapshot

        summary = self.memory_manager.get_memory_summary()
        summary.setdefault("pass1", {})["structured_passages"] = assembled_context.get("structured_passages", [])

        output = {
            "metadata": {
                "chunk_id": config.chunk_id,
                "category": config.category,
                "label": config.label,
                "timestamp": datetime.utcnow().isoformat(),
                "warm_span": config.warm_span,
                "authorial_directives": list(config.authorial_directives),
                "notes": config.notes,
            },
            "context_payload": assembled_context,
            "memory_summary": summary,
        }

        return output

    def save_package(self, package: Dict[str, Any]) -> Path:
        chunk_id = package["metadata"]["chunk_id"]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"chunk_{chunk_id}_{timestamp}.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(package, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        LOGGER.info("Saved package for chunk %s -> %s", chunk_id, output_path)
        return output_path

    def close(self) -> None:
        if self._lore_agent and getattr(self._lore_agent, "llm_manager", None):
            try:
                manager = self._lore_agent.llm_manager
                if getattr(manager, "unload_on_exit", True):
                    manager.unload_model()
            except Exception:  # pragma: no cover - defensive cleanup
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static context packages for Apex audition seeds")
    parser.add_argument(
        "--chunk",
        type=int,
        action="append",
        help="Limit generation to specific chunk id (can be supplied multiple times)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write JSON packages",
    )
    parser.add_argument(
        "--use-lore",
        action="store_true",
        help="Invoke LORE to generate inference-powered structured notes for directives",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    builder = ContextSeedBuilder(output_dir=args.output_dir, use_lore=args.use_lore)

    try:
        target_chunks = args.chunk or sorted(SCENES.keys())
        missing = [cid for cid in target_chunks if cid not in SCENES]
        if missing:
            raise SystemExit(f"No scene configuration for chunks: {missing}")

        generated: List[Dict[str, Any]] = []

        for chunk_id in target_chunks:
            config = SCENES[chunk_id]
            LOGGER.info("Building package for chunk %s (%s)", chunk_id, config.label)
            package = builder.build_scene_package(config)
            builder.save_package(package)
            generated.append(package["metadata"])

        summary_table = "\n".join(
            f"- Chunk {meta['chunk_id']}: {meta['label']} ({meta['category']})" for meta in generated
        )
        LOGGER.info("Generated %s packages:\n%s", len(generated), summary_table)
    finally:
        builder.close()


if __name__ == "__main__":
    main()
