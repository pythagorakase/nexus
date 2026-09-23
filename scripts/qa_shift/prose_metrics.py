"""SELECT-only prose measurements; no inference or writes to a corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import tomllib
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.config.settings_models import ProseMetricsSettings
from scripts.database_targets import metrics_dbname

ROOT = Path(__file__).resolve().parent


def load_config(path: Path = ROOT / "qa_shift.toml") -> ProseMetricsSettings:
    """Validate all metric policy from the QA kit's configuration."""
    return ProseMetricsSettings.model_validate(
        tomllib.loads(path.read_text())["prose_metrics"]
    )


def plain_text(text: str) -> str:
    """Remove Markdown decoration while retaining wording and paragraph breaks."""
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"(?m)^[ \t]*[-*_]{3,}[ \t]*$", "", text)
    text = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+", "", text)
    return text.replace("*", "").replace("_", "").replace("`", "")


def legacy_sections(
    raw: str, chunk_id: int, config: ProseMetricsSettings
) -> tuple[str, str]:
    """Read observed Storyteller/You sections, including player-only boundaries.

    Missing sections are explicit empty strings; unknown, duplicate, or reversed
    sections fail instead of silently discarding prose.
    """
    matches = list(re.finditer(config.legacy_section_pattern, raw, re.MULTILINE))
    names = [m[1] for m in matches]
    if names not in (["Storyteller", "You"], ["Storyteller"], ["You"]):
        raise ValueError(f"Chunk {chunk_id}: unsupported legacy section shape {names}")
    if len(re.findall(r"^##[ \t]+", raw, re.MULTILINE)) != len(matches):
        raise ValueError(f"Chunk {chunk_id}: unknown legacy section heading")
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        sections[match[1]] = raw[match.end() : end].strip()
    if not any(sections.values()):
        raise ValueError(f"Chunk {chunk_id}: empty legacy sections")
    return sections.get("Storyteller", ""), sections.get("You", "")


def separate_legacy_menu(
    story: str, config: ProseMetricsSettings
) -> tuple[str, list[str] | None]:
    """Remove the final consecutively numbered legacy menu (a labeled heuristic).

    Only recovered option lines are removed and counted as choices; surrounding
    prose and separators stay intact. Unnumbered conversational prompts are N/A.
    """
    runs: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    lines = story.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = re.match(config.legacy_choice_pattern, line)
        if match is None:
            continue
        number = int(match["number"])
        if number == 1:
            current = []
            runs.append(current)
        if number == len(current) + 1:
            current.append((index, plain_text(match["text"]).strip()))
        else:
            current = []
    candidates = [run for run in runs if len(run) >= config.legacy_menu_min_choices]
    if not candidates:
        return story, None
    menu = candidates[-1]
    menu_lines = {index for index, _ in menu}
    narrative = "".join(
        line for index, line in enumerate(lines) if index not in menu_lines
    ).strip()
    return narrative, [choice for _, choice in menu]


def adapt_chunk(row: dict[str, Any], config: ProseMetricsSettings) -> dict[str, Any]:
    """Separate prose, selected player turn, and offered choices without mutation."""
    chunk = dict(row)
    if row["storyteller_text"] is None:
        story, player = legacy_sections(row["raw_text"] or "", row["id"], config)
        story, choices = separate_legacy_menu(story, config)
        chunk.update(story=story, player=player, text_source="raw_text_legacy_sections")
        chunk["choice_source"] = "legacy_numbered_lines_heuristic"
    else:
        if not row["storyteller_text"].strip():
            raise ValueError(f"Chunk {row['id']}: empty storyteller_text")
        chunk.update(
            story=row["storyteller_text"],
            player=row["choice_text"] or "",
            text_source="columns",
        )
        choices = None
        chunk["choice_source"] = "choice_object.presented"
    obj = row["choice_object"]
    if obj is not None:
        if not isinstance(obj, dict) or "presented" not in obj:
            raise ValueError(f"Chunk {row['id']}: malformed choice_object")
        choices = obj["presented"]
        if not isinstance(choices, list) or any(
            not isinstance(c, str) or not c.strip() for c in choices
        ):
            raise ValueError(f"Chunk {row['id']}: malformed presented choices")
        chunk["choice_source"] = "choice_object.presented"
    chunk["choices"] = choices
    return chunk


def fraction(numerator: int, denominator: int) -> float | None:
    """Represent an unavailable denominator as null, never an invented zero."""
    return numerator / denominator if denominator else None


def distribution(values: list[float] | list[int]) -> dict[str, Any]:
    """Summarize a measured population, retaining null for absent observations."""
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "sd": statistics.pstdev(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
    }


def measure(
    chunks: list[dict[str, Any]], config: ProseMetricsSettings
) -> dict[str, Any]:
    """Compute deterministic corpus metrics over ordered, adapted chunks."""

    def words(text: str) -> list[str]:
        return re.findall(config.word_pattern, text.lower().replace("’", "'"))

    narratives = [plain_text(c["story"]).strip() for c in chunks if c["story"].strip()]
    paragraphs = [
        p.strip()
        for text in narratives
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]
    sentence_words = [
        [words(s) for s in re.split(config.sentence_boundary_pattern, p) if words(s)]
        for p in paragraphs
    ]
    sentences = [s for group in sentence_words for s in group]
    last_lines = [text.splitlines()[-1].strip() for text in narratives]
    contractions = sum(
        len(re.findall(config.contraction_pattern, text, re.I)) for text in narratives
    )
    negations = {
        phrase: sum(
            len(re.findall(r"\b" + re.escape(phrase) + r"\b", text, re.I))
            for text in narratives
        )
        for phrase in config.formal_negations
    }
    motifs: Counter[str] = Counter()
    for text in narratives:
        # A motif is counted once per chunk, never multiplied by repetitions.
        tokens = words(text)
        motifs.update(
            {
                " ".join(tokens[i : i + n])
                for n in config.motif_ngram_sizes
                for i in range(len(tokens) - n + 1)
            }
        )
    menus = [c["choices"] for c in chunks if c["choices"] is not None]
    choices = [choice for menu in menus for choice in menu]
    first_verbs = Counter(words(choice)[0] for choice in choices if words(choice))
    change = sum(
        any(
            re.search(r"\b" + re.escape(keyword) + r"\b", choice, re.I)
            for keyword in config.change_keywords
        )
        for choice in choices
    )
    streaks: list[int] = []
    previous_place = None
    for c in chunks:
        # A primary place is identifiable only with exactly one setting link.
        places = c["setting_places"]
        place = places[0] if len(places) == 1 else None
        if place is not None:
            if place == previous_place:
                streaks[-1] += 1
            else:
                streaks.append(1)
        previous_place = place
    minutes = [
        (b["world_time"] - a["world_time"]).total_seconds() / 60
        for a, b in zip(chunks, chunks[1:])
        if a["world_time"] is not None and b["world_time"] is not None
    ]
    return {
        "chunks": len(chunks),
        "narrative_chunks": len(narratives),
        "player_only_chunk_ids": [c["id"] for c in chunks if not c["story"].strip()],
        "closers": {
            "question_count": sum(line.endswith("?") for line in last_lines),
            "question_rate": fraction(
                sum(line.endswith("?") for line in last_lines), len(last_lines)
            ),
            "what_do_you_count": sum(
                bool(re.search(config.closer_pattern, line, re.I))
                for line in last_lines
            ),
            "what_do_you_rate": fraction(
                sum(
                    bool(re.search(config.closer_pattern, line, re.I))
                    for line in last_lines
                ),
                len(last_lines),
            ),
        },
        "negation": {
            "contractions": contractions,
            "formal_counts": negations,
            "formal_total": sum(negations.values()),
            "contraction_ratio": fraction(
                contractions, contractions + sum(negations.values())
            ),
            "it_is_not_sentence_count": sum(
                len(re.findall(config.it_is_not_pattern, text, re.I))
                for text in narratives
            ),
        },
        "rhythm": {
            "paragraphs_per_chunk": fraction(len(paragraphs), len(narratives)),
            "median_words_per_paragraph": (
                statistics.median([len(words(p)) for p in paragraphs])
                if paragraphs
                else None
            ),
            "single_sentence_paragraph_share": fraction(
                sum(len(group) == 1 for group in sentence_words), len(paragraphs)
            ),
            "short_sentence_share": fraction(
                sum(len(s) <= config.short_sentence_max_words for s in sentences),
                len(sentences),
            ),
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
        },
        "motifs": [
            {"ngram": gram, "chunks": count}
            for gram, count in sorted(
                motifs.items(), key=lambda item: (-item[1], item[0])
            )
            if count >= config.motif_min_chunks
        ],
        "choices": {
            "status": "available" if menus else "not_applicable",
            "sources": dict(
                sorted(
                    Counter(
                        c["choice_source"] for c in chunks if c["choices"] is not None
                    ).items()
                )
            ),
            "menus": len(menus),
            "chunks_without_menu": len(chunks) - len(menus),
            "count_distribution": (
                dict(sorted(Counter(str(len(menu)) for menu in menus).items()))
                if menus
                else None
            ),
            "mean_count": (
                statistics.mean([len(menu) for menu in menus]) if menus else None
            ),
            "total": len(choices) if menus else None,
            "first_verb_mix": dict(sorted(first_verbs.items())) if menus else None,
            "speech_act_share": fraction(
                sum(first_verbs[v] for v in config.speech_act_verbs), len(choices)
            ),
            "change_place_time_company_share": fraction(change, len(choices)),
        },
        "selected_turns": {
            "count": sum(bool(c["player"].strip()) for c in chunks),
            "words": sum(len(words(c["player"])) for c in chunks),
        },
        "same_setting_streak": {
            **distribution(streaks),
            "missing_place_chunks": sum(not c["setting_places"] for c in chunks),
            "ambiguous_place_chunks": sum(len(c["setting_places"]) > 1 for c in chunks),
        },
        "world_minutes_per_turn": {
            **distribution(minutes),
            "missing_pairs": max(len(chunks) - 1, 0) - len(minutes),
            "negative_deltas": sum(value < 0 for value in minutes),
        },
        "words_per_chunk": distribution([len(words(text)) for text in narratives]),
    }


def corpus_report(
    dbname: str,
    config: ProseMetricsSettings,
    from_chunk: int | None = None,
    to_chunk: int | None = None,
) -> dict[str, Any]:
    """Read a consistent, SELECT-only snapshot with session read-only enforced."""
    metrics_dbname(dbname)
    if from_chunk is not None and to_chunk is not None and from_chunk > to_chunk:
        raise ValueError("from-chunk must not exceed to-chunk")
    with closing(
        psycopg2.connect(
            dbname=dbname,
            user=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
            options="-c default_transaction_read_only=on -c default_transaction_isolation=repeatable\\ read",
            cursor_factory=RealDictCursor,
        )
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('transaction_read_only') AS read_only")
            if cur.fetchone()["read_only"] != "on":
                raise RuntimeError("Read-only transaction is required")
            cur.execute(
                "SELECT count(*) AS count, max(version) AS level FROM schema_migrations"
            )
            migration = dict(cur.fetchone())
            cur.execute("SELECT count(*) AS count FROM narrative_chunks")
            total = cur.fetchone()["count"]
            cur.execute(
                f"""
                SELECT nc.id, nc.storyteller_text, nc.choice_text, nc.choice_object,
                       nc.raw_text, cm.world_time,
                       ARRAY(SELECT p.place_id FROM place_chunk_references p
                             WHERE p.chunk_id = nc.id AND p.reference_type::text = %s
                             ORDER BY p.place_id) AS setting_places
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                WHERE {playable_narrative_predicate()}
                  AND (%s IS NULL OR nc.id >= %s)
                  AND (%s IS NULL OR nc.id <= %s)
                ORDER BY nc.id
            """,
                (
                    config.setting_reference_type,
                    from_chunk,
                    from_chunk,
                    to_chunk,
                    to_chunk,
                ),
            )
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        raise ValueError(f"No playable chunks in {dbname} for requested range")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate metadata rows would multiply corpus measurements")
    chunks = [adapt_chunk(row, config) for row in rows]
    manifest = tomllib.loads((ROOT / "reference_corpora.toml").read_text())
    entry = next((item for item in manifest["corpora"] if item["name"] == dbname), None)
    sources = sorted({c["text_source"] for c in chunks})
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "corpus": dbname,
        "provenance_tier": entry["provenance_tier"] if entry else "unregistered",
        "provenance": {
            "manifest": entry,
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "text_source": sources[0] if len(sources) == 1 else "mixed",
            "text_source_counts": dict(Counter(c["text_source"] for c in chunks)),
            "measurement_scope": {
                "narrative": "Modern storyteller_text; legacy Storyteller section with only recovered menu option lines removed; whole section when no menu is recovered.",
                "choices": "choice_object.presented when available, otherwise the final recovered sequential numbered legacy menu; missing menus are N/A.",
                "comparable_metrics": [
                    "closers",
                    "negation",
                    "rhythm",
                    "motifs",
                    "words_per_chunk",
                    "selected_turns",
                    "same_setting_streak",
                    "world_minutes_per_turn",
                ],
                "comparability": "Narrative metrics use the same menu-excluding definitions across storage formats, conditional on legacy menu recovery. Selected turns and telemetry use the same definitions subject to source coverage.",
                "legacy_heuristics": "Menu detection can misidentify numbered prose or miss menus and continuation lines. Legacy narrative metrics inherit that uncertainty; choice statistics describe recovered menus only, not equivalent coverage to structured menus.",
                "shared_heuristics": "Sentence segmentation is punctuation-based; choice first verbs use lexical tokens and speech/change shares use keywords.",
            },
            "snapshot_sha256": digest,
            "migration": migration,
            "database_chunk_count": total,
            "from_chunk": rows[0]["id"],
            "to_chunk": rows[-1]["id"],
            "read_only": True,
            "order": "playable narrative_chunks.id ASC",
        },
        "config": config.model_dump(),
        "metrics": measure(chunks, config),
    }


def flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten scalar metrics for human output and numeric comparisons."""
    result = {}
    for key, child in value.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(flatten(child, name))
        elif not isinstance(child, list):
            result[name] = child
    return result


def print_table(report: dict[str, Any]) -> None:
    """Write a compact summary to stderr, leaving stdout valid JSON."""
    print(f"Corpus: {report['corpus']} ({report['provenance_tier']})", file=sys.stderr)
    flat = flatten(report["metrics"])
    for key in (
        "chunks",
        "narrative_chunks",
        "closers.question_rate",
        "closers.what_do_you_rate",
        "negation.contraction_ratio",
        "choices.menus",
        "choices.mean_count",
        "choices.speech_act_share",
        "choices.change_place_time_company_share",
        "rhythm.paragraphs_per_chunk",
        "rhythm.median_words_per_paragraph",
        "rhythm.single_sentence_paragraph_share",
        "rhythm.short_sentence_share",
        "same_setting_streak.max",
        "same_setting_streak.mean",
        "world_minutes_per_turn.mean",
        "words_per_chunk.mean",
        "words_per_chunk.sd",
    ):
        value = flat[key]
        rendered = (
            "N/A"
            if value is None
            else f"{value:.6f}" if isinstance(value, float) else str(value)
        )
        print(f"{key:44} {rendered:>12}", file=sys.stderr)
    print(
        f"Menu sources: {report['metrics']['choices']['sources']}; chunks without menu: {report['metrics']['choices']['chunks_without_menu']}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Measure a corpus or compare two saved JSON reports without a database."""
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--slot", type=int, choices=range(1, 6))
    target.add_argument("--dbname", type=metrics_dbname)
    target.add_argument("--compare", type=Path, nargs=2, metavar=("A", "B"))
    parser.add_argument("--from-chunk", type=int)
    parser.add_argument("--to-chunk", type=int)
    parser.add_argument("--config", type=Path, default=ROOT / "qa_shift.toml")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.compare:
        a, b = [json.loads(path.read_text()) for path in args.compare]
        if a["schema_version"] != b["schema_version"] or a["config"] != b["config"]:
            parser.error("Cannot compare different metric schemas or configurations")
        left, right = flatten(a["metrics"]), flatten(b["metrics"])
        print(f"B - A: {b['corpus']} - {a['corpus']}")
        for key in sorted(left.keys() | right.keys()):
            x, y = left.get(key), right.get(key)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                print(f"{key:65} {y - x:+.6f}")
            elif x is None or y is None:
                print(f"{key:65} N/A ({x} -> {y})")
        return 0
    report = corpus_report(
        args.dbname or f"save_{args.slot:02d}",
        load_config(args.config),
        args.from_chunk,
        args.to_chunk,
    )
    encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    print_table(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
