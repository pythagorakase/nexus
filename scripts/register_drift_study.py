"""Measure narrative-register drift in the human- and LLM-played save slots.

The study is deliberately read-only.  It extracts playable narrative rows,
computes deterministic text metrics, writes a machine-readable JSON artifact
and a Markdown report, and prints the cross-slot verdict table.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import re
from statistics import fmean
from typing import Any, Literal, Mapping, Sequence

import psycopg2

from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.api.slot_utils import slot_dbname


DEFAULT_JSON_OUT = Path("docs/register_drift_study_2026_07_26.json")
DEFAULT_REPORT_OUT = Path("docs/register_drift_study_2026_07_26.md")
CONTROL_SLOT = 1
STUDY_SLOT = 5
CHOICE_HISTORY_TURNS = 5

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+[\"'”’)\]]*|\n+")

# A deliberately small, fixed list of common English function words.  Keeping
# the list in this file makes the analysis reproducible without a corpus or
# tokenizer dependency.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "me",
        "might",
        "my",
        "not",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "too",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
    }
)

# Fixed generic ritual/formality vocabulary, including common inflections.
# These are not derived from either study slot.
FORMALITY_WORDS = frozenset(
    {
        "bind",
        "binding",
        "bindings",
        "binds",
        "bound",
        "covenant",
        "covenanted",
        "covenanting",
        "covenants",
        "custodial",
        "custodian",
        "custodians",
        "custodianship",
        "oath",
        "oaths",
        "protocol",
        "protocols",
        "record",
        "recorded",
        "recording",
        "records",
        "rite",
        "rites",
        "sanction",
        "sanctioned",
        "sanctioning",
        "sanctions",
        "seal",
        "sealed",
        "sealing",
        "seals",
        "witness",
        "witnessed",
        "witnesses",
        "witnessing",
    }
)
SECOND_PERSON_PRONOUNS = frozenset({"you", "your", "yours", "yourself", "yourselves"})


@dataclass(frozen=True)
class NarrativeChunk:
    """One playable, non-empty narrative row in slot order."""

    chunk_id: int
    ordinal: int
    text: str
    source: Literal["storyteller_text", "raw_text"]
    choices: tuple[str, ...] | None


@dataclass(frozen=True)
class Corpus:
    """Read-only extraction result and its source census."""

    slot: int
    database: str
    total_rows: int
    playable_rows: int
    chunks: tuple[NarrativeChunk, ...]
    storyteller_text_chunks: int
    raw_text_chunks: int
    choice_chunks: int


@dataclass(frozen=True)
class MetricDefinition:
    """Report metadata for a calculated metric."""

    key: str
    title: str
    definition: str
    choice_metric: bool = False


METRICS = (
    MetricDefinition(
        "lexical_novelty_rate",
        "Lexical novelty rate",
        "Fraction of the chunk's content-word types absent from all earlier "
        "chunks in the same slot.",
    ),
    MetricDefinition(
        "coinage_density",
        "Coinage density",
        "Title-Case multiword spans beginning mid-sentence per 1,000 words.",
    ),
    MetricDefinition(
        "console_proclamation_register",
        "Console/proclamation register",
        "Count of ALL-CAPS-dominant lines in the chunk.",
    ),
    MetricDefinition(
        "ceremonial_syntax_density",
        "Ceremonial-syntax density",
        "Colon-terminated lines, em dashes, and formality-lexicon matches "
        "per 1,000 words.",
    ),
    MetricDefinition(
        "choice_list_self_similarity",
        "Choice-list self-similarity",
        "Mean pairwise content-word Jaccard similarity among presented choices.",
        choice_metric=True,
    ),
    MetricDefinition(
        "choice_topic_recurrence",
        "Choice-topic recurrence",
        "Content-word Jaccard similarity against choices in the preceding "
        "five playable turns.",
        choice_metric=True,
    ),
    MetricDefinition(
        "mean_sentence_length",
        "Mean sentence length",
        "Mean alphabetic-word count per non-empty sentence or line segment.",
    ),
    MetricDefinition(
        "dialogue_line_fraction",
        "Dialogue-line fraction",
        "Fraction of non-empty lines containing a straight or curly "
        "double-quote character.",
    ),
    MetricDefinition(
        "second_person_pronoun_rate",
        "Second-person pronoun rate",
        "Second-person pronoun tokens per 1,000 words.",
    ),
)
METRIC_BY_KEY = {metric.key: metric for metric in METRICS}


def word_tokens(text: str) -> list[str]:
    """Return lowercase Unicode alphabetic runs, treating punctuation as gaps."""

    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def content_word_types(text: str) -> set[str]:
    """Return alphabetic lowercase word types after removing ``STOPWORDS``."""

    return {token for token in word_tokens(text) if token not in STOPWORDS}


def lexical_novelty_rate(
    text: str, earlier_content_words: set[str] | frozenset[str]
) -> float:
    """Return the fraction of current content-word types not seen earlier.

    Tokenization lowercases Unicode alphabetic runs and therefore strips
    punctuation by treating it as a boundary.  Common function words in the
    fixed ``STOPWORDS`` set are excluded.  The supplied running vocabulary is
    read but never mutated.  A chunk with no content-word types scores 0.
    """

    current_types = content_word_types(text)
    if not current_types:
        return 0.0
    novel_types = current_types.difference(earlier_content_words)
    return len(novel_types) / len(current_types)


def _title_case_span_count(text: str) -> int:
    """Count qualifying Title-Case runs used by :func:`coinage_density`."""

    matches = list(WORD_RE.finditer(text))
    if not matches:
        return 0

    count = 0
    run_length = 0
    run_starts_sentence = False
    previous_end = 0
    sentence_initial = True

    for index, match in enumerate(matches):
        gap = text[previous_end : match.start()]
        if index > 0 and ("." in gap or "!" in gap or "?" in gap or "\n" in gap):
            sentence_initial = True

        is_adjacent_word = index > 0 and bool(gap) and gap.isspace()
        is_title_case = match.group(0).istitle()

        if is_title_case:
            if run_length and is_adjacent_word:
                run_length += 1
            else:
                if run_length >= 2 and not run_starts_sentence:
                    count += 1
                run_length = 1
                run_starts_sentence = sentence_initial
        else:
            if run_length >= 2 and not run_starts_sentence:
                count += 1
            run_length = 0
            run_starts_sentence = False

        sentence_initial = False
        previous_end = match.end()

    if run_length >= 2 and not run_starts_sentence:
        count += 1
    return count


def coinage_density(text: str) -> float:
    """Return qualifying Title-Case multiword spans per 1,000 words.

    A span is a maximal run of at least two title-cased alphabetic tokens
    separated only by whitespace.  The first alphabetic token after the start
    of text or ``.``, ``!``, ``?``, or a newline is ineligible, preventing
    ordinary sentence capitalization from starting a span.  A text with no
    words scores 0.
    """

    words = word_tokens(text)
    if not words:
        return 0.0
    return _title_case_span_count(text) * 1000.0 / len(words)


def console_proclamation_register(text: str) -> int:
    """Count lines with at least eight alphabetic characters and >=60% uppercase.

    Only alphabetic characters enter the numerator and denominator.  The
    result is a per-chunk line count rather than a length-normalized density.
    """

    qualifying_lines = 0
    for line in text.splitlines():
        letters = [character for character in line if character.isalpha()]
        if len(letters) < 8:
            continue
        uppercase = sum(character.isupper() for character in letters)
        if uppercase / len(letters) >= 0.60:
            qualifying_lines += 1
    return qualifying_lines


def ceremonial_syntax_density(text: str) -> float:
    """Return generic ceremonial-syntax signals per 1,000 words.

    The numerator is the sum of: non-empty alphabetic lines whose last
    non-whitespace character is a colon; U+2014 em-dash characters; and token
    matches in the fixed, generic ``FORMALITY_WORDS`` vocabulary covering
    protocol, covenant, witness, seal, record, rite, oath, custodian, sanction,
    bind, and common inflections.  A text with no words scores 0.
    """

    words = word_tokens(text)
    if not words:
        return 0.0
    colon_lines = sum(
        bool(line.strip())
        and line.rstrip().endswith(":")
        and any(character.isalpha() for character in line)
        for line in text.splitlines()
    )
    em_dashes = text.count("—")
    formality_matches = sum(word in FORMALITY_WORDS for word in words)
    signals = colon_lines + em_dashes + formality_matches
    return signals * 1000.0 / len(words)


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    """Return set Jaccard similarity, defining two empty sets as 0."""

    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def choice_list_self_similarity(choices: Sequence[str]) -> float | None:
    """Return mean pairwise Jaccard similarity of choice content-word sets.

    The result is ``None`` when fewer than two choices are presented.  Empty
    content-word sets have Jaccard similarity 0 rather than creating a false
    maximum.
    """

    if len(choices) < 2:
        return None
    choice_words = [content_word_types(choice) for choice in choices]
    similarities = [
        _jaccard_similarity(left, right)
        for left, right in combinations(choice_words, 2)
    ]
    return fmean(similarities)


def choice_topic_recurrence(
    choices: Sequence[str], previous_choice_turns: Sequence[Sequence[str]]
) -> float | None:
    """Return current-vs-recent pooled choice-word Jaccard similarity.

    Current presented choices are pooled into one content-word set and
    compared with the union from supplied earlier choice turns.  The caller
    supplies choice-bearing turns from the preceding five playable chunks.
    The result is ``None`` when none of those turns carried choices.
    """

    if not previous_choice_turns:
        return None
    current_words: set[str] = set()
    for choice in choices:
        current_words.update(content_word_types(choice))
    previous_words: set[str] = set()
    for turn_choices in previous_choice_turns:
        for choice in turn_choices:
            previous_words.update(content_word_types(choice))
    return _jaccard_similarity(current_words, previous_words)


def mean_sentence_length(text: str) -> float:
    """Return mean alphabetic-word count per non-empty sentence segment.

    Segments end at one or more ``.``, ``!``, or ``?`` characters (including
    immediately trailing quote/bracket characters) or at a newline.  Empty
    segments are ignored.  Text with no alphabetic words scores 0.
    """

    sentence_lengths = []
    for segment in SENTENCE_SPLIT_RE.split(text):
        segment_length = len(word_tokens(segment))
        if segment_length:
            sentence_lengths.append(segment_length)
    if not sentence_lengths:
        return 0.0
    return fmean(sentence_lengths)


def dialogue_line_fraction(text: str) -> float:
    """Return the fraction of non-empty lines containing ``"``, ``“``, or ``”``."""

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    dialogue_lines = sum('"' in line or "“" in line or "”" in line for line in lines)
    return dialogue_lines / len(lines)


def second_person_pronoun_rate(text: str) -> float:
    """Return second-person pronoun tokens per 1,000 alphabetic words.

    The fixed pronoun set is ``you``, ``your``, ``yours``, ``yourself``, and
    ``yourselves``.  A text with no words scores 0.
    """

    words = word_tokens(text)
    if not words:
        return 0.0
    pronouns = sum(word in SECOND_PERSON_PRONOUNS for word in words)
    return pronouns * 1000.0 / len(words)


def ordinary_least_squares_slope(
    points: Sequence[tuple[float, float]],
) -> float | None:
    """Return the inline OLS slope for ``(x, y)`` points, or ``None`` if undefined."""

    if len(points) < 2:
        return None
    mean_x = fmean(point[0] for point in points)
    mean_y = fmean(point[1] for point in points)
    denominator = sum((x_value - mean_x) ** 2 for x_value, _ in points)
    if denominator == 0:
        return None
    numerator = sum(
        (x_value - mean_x) * (y_value - mean_y) for x_value, y_value in points
    )
    return numerator / denominator


def _choices_from_object(
    choice_object: Any, *, slot: int, chunk_id: int
) -> tuple[str, ...] | None:
    """Validate and extract ``presented`` without hiding malformed live data."""

    if choice_object is None:
        return None
    if not isinstance(choice_object, Mapping):
        raise TypeError(
            f"save_{slot:02d} chunk {chunk_id}: choice_object must be an object"
        )
    if "presented" not in choice_object or choice_object["presented"] is None:
        return None
    presented = choice_object["presented"]
    if not isinstance(presented, list):
        raise TypeError(f"save_{slot:02d} chunk {chunk_id}: presented must be a list")
    if not all(isinstance(choice, str) for choice in presented):
        raise TypeError(
            f"save_{slot:02d} chunk {chunk_id}: every presented choice " "must be text"
        )
    return tuple(presented)


def load_corpus(slot: int) -> Corpus:
    """Read one slot through a verified read-only PostgreSQL session."""

    database = slot_dbname(slot)
    predicate = playable_narrative_predicate("nc")
    non_empty_text = (
        "COALESCE(NULLIF(BTRIM(nc.storyteller_text), ''), "
        "NULLIF(BTRIM(nc.raw_text), '')) IS NOT NULL"
    )
    conn = psycopg2.connect(dbname=database, host="localhost")
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            read_only_row = cursor.fetchone()
            if read_only_row is None or read_only_row[0] != "on":
                raise RuntimeError(f"{database}: PostgreSQL session is not read-only")

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_rows,
                    COUNT(*) FILTER (WHERE {predicate}) AS playable_rows
                FROM narrative_chunks nc
                """
            )
            count_row = cursor.fetchone()
            if count_row is None:
                raise RuntimeError(f"{database}: row census returned no result")
            total_rows = int(count_row[0])
            playable_rows = int(count_row[1])

            cursor.execute(
                f"""
                SELECT
                    nc.id,
                    nc.storyteller_text,
                    nc.raw_text,
                    nc.choice_object
                FROM narrative_chunks nc
                WHERE {predicate}
                  AND {non_empty_text}
                ORDER BY nc.id
                """
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    chunks: list[NarrativeChunk] = []
    storyteller_text_chunks = 0
    raw_text_chunks = 0
    choice_chunks = 0
    for ordinal, row in enumerate(rows, start=1):
        chunk_id = int(row[0])
        storyteller_text = row[1]
        raw_text = row[2]
        if isinstance(storyteller_text, str) and storyteller_text.strip():
            text = storyteller_text
            source: Literal["storyteller_text", "raw_text"] = "storyteller_text"
            storyteller_text_chunks += 1
        elif isinstance(raw_text, str) and raw_text.strip():
            text = raw_text
            source = "raw_text"
            raw_text_chunks += 1
        else:
            raise RuntimeError(
                f"{database} chunk {chunk_id}: selected row has no usable prose"
            )
        choices = _choices_from_object(row[3], slot=slot, chunk_id=chunk_id)
        if choices is not None:
            choice_chunks += 1
        chunks.append(
            NarrativeChunk(
                chunk_id=chunk_id,
                ordinal=ordinal,
                text=text,
                source=source,
                choices=choices,
            )
        )

    return Corpus(
        slot=slot,
        database=database,
        total_rows=total_rows,
        playable_rows=playable_rows,
        chunks=tuple(chunks),
        storyteller_text_chunks=storyteller_text_chunks,
        raw_text_chunks=raw_text_chunks,
        choice_chunks=choice_chunks,
    )


def calculate_chunk_metrics(corpus: Corpus) -> list[dict[str, Any]]:
    """Calculate all metrics in playable ordinal order."""

    seen_content_words: set[str] = set()
    recent_choices: deque[tuple[str, ...] | None] = deque(maxlen=CHOICE_HISTORY_TURNS)
    rows: list[dict[str, Any]] = []

    for chunk in corpus.chunks:
        prior_choice_turns = [
            choices for choices in recent_choices if choices is not None
        ]
        metric_values: dict[str, float | None] = {
            "lexical_novelty_rate": lexical_novelty_rate(
                chunk.text, seen_content_words
            ),
            "coinage_density": coinage_density(chunk.text),
            "console_proclamation_register": console_proclamation_register(chunk.text),
            "ceremonial_syntax_density": ceremonial_syntax_density(chunk.text),
            "choice_list_self_similarity": (
                choice_list_self_similarity(chunk.choices)
                if chunk.choices is not None
                else None
            ),
            "choice_topic_recurrence": (
                choice_topic_recurrence(chunk.choices, prior_choice_turns)
                if chunk.choices is not None
                else None
            ),
            "mean_sentence_length": mean_sentence_length(chunk.text),
            "dialogue_line_fraction": dialogue_line_fraction(chunk.text),
            "second_person_pronoun_rate": second_person_pronoun_rate(chunk.text),
        }
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "ordinal": chunk.ordinal,
                "source": chunk.source,
                "has_presented_choices": chunk.choices is not None,
                **metric_values,
            }
        )
        seen_content_words.update(content_word_types(chunk.text))
        recent_choices.append(chunk.choices)
    return rows


def _windowed_means(
    metric_rows: Sequence[Mapping[str, Any]], metric_key: str, window: int
) -> list[dict[str, Any]]:
    """Return consecutive non-overlapping window means, retaining a final partial."""

    windows: list[dict[str, Any]] = []
    for start in range(0, len(metric_rows), window):
        window_rows = metric_rows[start : start + window]
        values = [
            float(row[metric_key]) for row in window_rows if row[metric_key] is not None
        ]
        ordinals = [int(row["ordinal"]) for row in window_rows]
        windows.append(
            {
                "start_ordinal": ordinals[0],
                "end_ordinal": ordinals[-1],
                "center_ordinal": fmean(ordinals),
                "observations": len(values),
                "mean": fmean(values) if values else None,
            }
        )
    return windows


def _percentile_band(
    metric_rows: Sequence[Mapping[str, Any]],
    metric_key: str,
    lower: float,
    upper: float,
) -> dict[str, float | int | None]:
    """Return a metric mean within an inclusive playable-position band."""

    values: list[float] = []
    row_count = len(metric_rows)
    for index, row in enumerate(metric_rows):
        percentile = index / (row_count - 1) if row_count > 1 else 0.0
        if lower <= percentile <= upper and row[metric_key] is not None:
            values.append(float(row[metric_key]))
    return {
        "lower": lower,
        "upper": upper,
        "observations": len(values),
        "mean": fmean(values) if values else None,
    }


def _relative_change(first: float | None, last: float | None) -> float | None:
    """Return relative change, leaving a zero or missing baseline undefined."""

    if first is None or last is None or first == 0:
        return None
    return (last - first) / abs(first)


def analyze_metric(
    metric_rows: Sequence[Mapping[str, Any]], metric_key: str, window: int
) -> dict[str, Any]:
    """Summarize one metric with windows, ordinal OLS, and position bands."""

    windows = _windowed_means(metric_rows, metric_key, window)
    slope_points = [
        (float(item["center_ordinal"]), float(item["mean"]))
        for item in windows
        if item["mean"] is not None
    ]
    first_window_mean = windows[0]["mean"] if windows else None
    last_window_mean = windows[-1]["mean"] if windows else None
    early = _percentile_band(metric_rows, metric_key, 0.0, 0.10)
    middle = _percentile_band(metric_rows, metric_key, 0.45, 0.55)
    late = _percentile_band(metric_rows, metric_key, 0.90, 1.0)
    slope = ordinary_least_squares_slope(slope_points)
    relative_band_change = _relative_change(
        _optional_float(early["mean"]), _optional_float(late["mean"])
    )
    observations = sum(row[metric_key] is not None for row in metric_rows)
    return {
        "observations": observations,
        "windows": windows,
        "slope_per_chunk_ordinal": slope,
        "first_window_mean": first_window_mean,
        "last_window_mean": last_window_mean,
        "bands": {
            "early_0_10_percent": early,
            "middle_45_55_percent": middle,
            "late_90_100_percent": late,
        },
        "early_to_late_relative_change": relative_band_change,
        "drift_velocity_qualifies": (
            slope is not None
            and slope > 0
            and relative_band_change is not None
            and relative_band_change > 0.20
        ),
    }


def _optional_float(value: Any) -> float | None:
    """Narrow an optional numeric JSON value for static type checking."""

    if value is None:
        return None
    return float(value)


def _slot_payload(corpus: Corpus, window: int) -> dict[str, Any]:
    metric_rows = calculate_chunk_metrics(corpus)
    analyses = {
        metric.key: analyze_metric(metric_rows, metric.key, window)
        for metric in METRICS
    }
    drift_velocity = sum(
        bool(analysis["drift_velocity_qualifies"]) for analysis in analyses.values()
    )
    measurable_metrics = sum(
        int(analysis["observations"] > 0) for analysis in analyses.values()
    )
    return {
        "slot": corpus.slot,
        "database": corpus.database,
        "row_census": {
            "total_rows": corpus.total_rows,
            "playable_rows": corpus.playable_rows,
            "excluded_non_playable_rows": corpus.total_rows - corpus.playable_rows,
            "analyzed_chunks": len(corpus.chunks),
            "excluded_empty_playable_rows": corpus.playable_rows - len(corpus.chunks),
        },
        "source_counts": {
            "storyteller_text": corpus.storyteller_text_chunks,
            "raw_text": corpus.raw_text_chunks,
            "chunks_with_presented_choices": corpus.choice_chunks,
        },
        "per_chunk": metric_rows,
        "analysis": analyses,
        "drift_velocity_metric_count": drift_velocity,
        "measurable_metric_count": measurable_metrics,
    }


def _verdicts(slot_payloads: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compare slot-5 and slot-1 slopes, preserving choice-only no-control status."""

    control = slot_payloads[str(CONTROL_SLOT)]
    study = slot_payloads[str(STUDY_SLOT)]
    verdicts: list[dict[str, Any]] = []
    for metric in METRICS:
        control_slope = _optional_float(
            control["analysis"][metric.key]["slope_per_chunk_ordinal"]
        )
        study_slope = _optional_float(
            study["analysis"][metric.key]["slope_per_chunk_ordinal"]
        )
        if metric.choice_metric:
            status = "no control"
            exceeds: bool | None = None
        elif control_slope is None or study_slope is None:
            status = "insufficient data"
            exceeds = None
        else:
            exceeds = study_slope > control_slope
            status = "yes" if exceeds else "no"
        verdicts.append(
            {
                "metric": metric.key,
                "title": metric.title,
                "slot_1_slope": control_slope,
                "slot_5_slope": study_slope,
                "slot_5_exceeds_slot_1": exceeds,
                "slope_difference": (
                    study_slope - control_slope
                    if control_slope is not None and study_slope is not None
                    else None
                ),
                "verdict": status,
            }
        )
    return verdicts


def run_study(slots: Sequence[int], window: int) -> dict[str, Any]:
    """Extract, calculate, and assemble the complete study document."""

    slot_payloads: dict[str, dict[str, Any]] = {}
    for slot in slots:
        corpus = load_corpus(slot)
        slot_payloads[str(slot)] = _slot_payload(corpus, window)
    return {
        "study": "Register drift: LLM-grown vs human-played narrative",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parameters": {
            "slots": list(slots),
            "window_chunks": window,
            "choice_history_turns": CHOICE_HISTORY_TURNS,
            "playable_predicate": playable_narrative_predicate("nc"),
        },
        "metric_definitions": {metric.key: metric.definition for metric in METRICS},
        "slots": slot_payloads,
        "verdicts": _verdicts(slot_payloads),
    }


def _format_value(value: Any, *, slope: bool = False) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    if slope:
        return f"{number:.6g}"
    return f"{number:.3f}"


def verdict_table(study: Mapping[str, Any]) -> str:
    """Render the required cross-slot verdict table."""

    lines = [
        "| Metric | Slot 1 slope | Slot 5 slope | Slot-5 trend exceeds slot 1? |",
        "| --- | ---: | ---: | :--- |",
    ]
    for verdict in study["verdicts"]:
        lines.append(
            "| {title} | {slot_1} | {slot_5} | {status} |".format(
                title=verdict["title"],
                slot_1=_format_value(verdict["slot_1_slope"], slope=True),
                slot_5=_format_value(verdict["slot_5_slope"], slope=True),
                status=verdict["verdict"],
            )
        )
    return "\n".join(lines)


def _corpus_table(study: Mapping[str, Any]) -> str:
    lines = [
        "| Slot | Total rows | Playable | Analyzed | storyteller_text | raw_text | "
        "With presented choices |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for slot in study["parameters"]["slots"]:
        payload = study["slots"][str(slot)]
        census = payload["row_census"]
        sources = payload["source_counts"]
        lines.append(
            "| {slot} | {total} | {playable} | {analyzed} | {storyteller} | "
            "{raw} | {choices} |".format(
                slot=slot,
                total=census["total_rows"],
                playable=census["playable_rows"],
                analyzed=census["analyzed_chunks"],
                storyteller=sources["storyteller_text"],
                raw=sources["raw_text"],
                choices=sources["chunks_with_presented_choices"],
            )
        )
    return "\n".join(lines)


def _metric_table(study: Mapping[str, Any], metric: MetricDefinition) -> str:
    window = study["parameters"]["window_chunks"]
    lines = [
        "| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | "
        "OLS slope/chunk | First {window}-chunk window | Last {window}-chunk "
        "window |".format(window=window),
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for slot in study["parameters"]["slots"]:
        analysis = study["slots"][str(slot)]["analysis"][metric.key]
        bands = analysis["bands"]
        lines.append(
            "| {slot} | {observations} | {early} | {middle} | {late} | "
            "{slope} | {first} | {last} |".format(
                slot=slot,
                observations=analysis["observations"],
                early=_format_value(bands["early_0_10_percent"]["mean"]),
                middle=_format_value(bands["middle_45_55_percent"]["mean"]),
                late=_format_value(bands["late_90_100_percent"]["mean"]),
                slope=_format_value(analysis["slope_per_chunk_ordinal"], slope=True),
                first=_format_value(analysis["first_window_mean"]),
                last=_format_value(analysis["last_window_mean"]),
            )
        )
    return "\n".join(lines)


def render_report(study: Mapping[str, Any]) -> str:
    """Render the generated Markdown study report."""

    window = study["parameters"]["window_chunks"]
    controlled_verdicts = [
        verdict
        for verdict in study["verdicts"]
        if not METRIC_BY_KEY[verdict["metric"]].choice_metric
    ]
    exceeding_count = sum(
        verdict["slot_5_exceeds_slot_1"] is True for verdict in controlled_verdicts
    )
    control_velocity = study["slots"][str(CONTROL_SLOT)]["drift_velocity_metric_count"]
    study_velocity = study["slots"][str(STUDY_SLOT)]["drift_velocity_metric_count"]
    if exceeding_count > len(controlled_verdicts) / 2:
        overall_verdict = (
            "Overall verdict: the measured pattern favors H2's broad "
            "escalation prediction. Slot 5 has the greater slope on "
            f"{exceeding_count} of {len(controlled_verdicts)} controlled "
            f"metrics, with drift velocity {study_velocity} versus "
            f"{control_velocity} in slot 1. This remains directional "
            "evidence, not proof of the amplification mechanism."
        )
    else:
        overall_verdict = (
            "Overall verdict: the measured pattern does not show broad "
            "H2-style escalation. Slot 5 has the greater slope on only "
            f"{exceeding_count} of {len(controlled_verdicts)} controlled "
            f"metrics, with drift velocity {study_velocity} versus "
            f"{control_velocity} in slot 1. This leans toward H1's "
            "flat/high-intercept trend prediction, while the individual "
            "metrics marked “yes” remain localized H2-compatible signals; "
            "it does not establish missing context as the mechanism."
        )
    lines = [
        "# Register-Drift Study: LLM-Grown vs Human-Played Narrative",
        "",
        f"Generated at `{study['generated_at_utc']}` from read-only PostgreSQL "
        "sessions.",
        "",
        "## Question",
        "",
        "The study contrasts two measurable predictions. H1 (missing reader "
        "context) permits a high register intercept but predicts broadly flat "
        "register metrics across slot 5. H2 (two-LLM amplification) predicts "
        "rising slot-5 metrics that exceed trends in the human-in-the-loop "
        "slot-1 control.",
        "",
        "## Corpus and prose sources",
        "",
        _corpus_table(study),
        "",
        "Rows are ordered by playable ordinal, not raw chunk ID. For each row, "
        "`storyteller_text` is authoritative when non-empty; otherwise the "
        "analysis uses `raw_text`. Slot 1 therefore contributes legacy "
        "`raw_text` throughout, while slot 5 contributes `storyteller_text` "
        "throughout. The canonical "
        "`nexus.agents.orrery.reconstruction.playable_narrative_predicate` "
        "excludes non-playable rows, and rows with neither prose source are "
        "excluded.",
        "",
        "## Methods",
        "",
        "All database connections use `psycopg2`, call "
        "`set_session(readonly=True)` before any query, and verify "
        "`transaction_read_only=on`. The script issues only `SHOW` and "
        "`SELECT` statements.",
        "",
        "Words are lowercase Unicode alphabetic runs; punctuation is treated "
        "as a boundary. Content-word sets remove this fixed built-in stopword "
        f"list: {', '.join(sorted(STOPWORDS))}.",
        "",
        "1. **Lexical novelty rate.** For each chunk, the fraction of its "
        "content-word types not present in any earlier chunk in that slot. "
        "The running vocabulary is updated only after scoring the chunk; an "
        "empty content-word set scores 0.",
        "2. **Coinage density.** Count per 1,000 words of maximal spans with "
        "two or more consecutive title-cased alphabetic tokens separated by "
        "whitespace. The first token after the start of text or `.`, `!`, or "
        "`?`, or a newline cannot begin a span, excluding sentence-initial "
        "capitalization.",
        "3. **Console/proclamation register.** Per-chunk count of lines with "
        "at least eight alphabetic characters for which at least 60% of those "
        "characters are uppercase.",
        "4. **Ceremonial-syntax density.** Per 1,000 words, the sum of "
        "non-empty alphabetic lines ending in a colon, U+2014 em dashes, and "
        "matches in this fixed generic ritual/formality lexicon: "
        f"{', '.join(sorted(FORMALITY_WORDS))}.",
        "5. **Choice-list self-similarity.** Mean pairwise Jaccard similarity "
        "of the presented choices' content-word sets; undefined with fewer "
        "than two choices. Two empty sets are assigned 0.",
        "6. **Choice-topic recurrence.** Jaccard similarity of the current "
        "turn's pooled presented-choice content words against the union from "
        "choice-bearing chunks among the preceding five playable turns. It "
        "is undefined when none of those turns has choices.",
        "7. **Mean sentence length.** Mean alphabetic-word count in non-empty "
        "segments split at `.`, `!`, `?`, or a newline.",
        "8. **Dialogue-line fraction.** Fraction of non-empty lines containing "
        "a straight or curly double quote.",
        "9. **Second-person pronoun rate.** Per 1,000 words, matches of `you`, "
        "`your`, `yours`, `yourself`, and `yourselves`.",
        "",
        f"Per-chunk values are averaged into consecutive, non-overlapping "
        f"{window}-chunk windows; a final partial window is retained. For "
        "each slot and metric, the reported ordinary least-squares slope is "
        "fit inline to window mean versus the window's mean playable ordinal, "
        "so its unit is metric units per chunk. Position-normalized early, "
        "middle, and late means use inclusive 0–10%, 45–55%, and 90–100% "
        "playable-ordinal percentile bands. Missing metric values are omitted "
        "from means, never replaced with zero.",
        "",
        "A metric contributes to a slot's drift velocity when its OLS slope is "
        "positive and its late-band mean exceeds its early-band mean by more "
        "than 20% relative. A zero or missing early mean has undefined "
        "relative change and is conservatively not counted.",
        "",
        "## Metric tables",
        "",
    ]
    for metric in METRICS:
        lines.extend(
            [
                f"### {metric.title}",
                "",
                metric.definition,
                "",
                _metric_table(study, metric),
                "",
            ]
        )

    lines.extend(
        [
            "## Verdict",
            "",
            "Here, “exceeds” means that the slot-5 OLS slope is numerically "
            "greater than the slot-1 OLS slope for the same metric. Choice "
            "metrics are explicitly within-slot only because slot 1 has no "
            "`choice_object.presented` data.",
            "",
            verdict_table(study),
            "",
        ]
    )
    for slot in study["parameters"]["slots"]:
        payload = study["slots"][str(slot)]
        lines.append(
            f"**Slot {slot} drift velocity:** "
            f"{payload['drift_velocity_metric_count']} metric(s) "
            f"(of {payload['measurable_metric_count']} measurable)."
        )
        lines.append("")

    lines.extend(
        [
            f"Across the seven controlled prose/style metrics, slot 5 has the "
            f"greater OLS slope on {exceeding_count}. This is a directional "
            "comparison of the registered measurements, not a causal "
            "identification result; the individual slopes and band movements "
            "above determine whether the evidence looks more like a flat "
            "high-intercept register (H1) or escalating register (H2).",
            "",
            overall_verdict,
            "",
            "## Limitations",
            "",
            "Slot 1 is not a model-pure control: it spans model heterogeneity, "
            "and its legacy `raw_text` interleaves human player lines with "
            "narration. The actual contrast is therefore human-in-the-loop "
            "versus LLM-in-the-loop, and the interleaving is part of the "
            "phenomenon rather than something filtered away. The hand-built "
            "stopword, formality, pronoun, capitalization, and segmentation "
            "rules introduce lexicon-choice and operationalization bias; "
            "other reasonable lists or tokenizers can move the estimates. "
            "Finally, a temporal trend or cross-slot slope difference does "
            "not prove the amplification mechanism: plot, character, prompt, "
            "model, and campaign-era differences remain plausible causes. "
            "The two choice metrics have no slot-1 control and support only "
            "within-slot trend statements.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_slots(value: str) -> tuple[int, int]:
    try:
        slots = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--slots must be a comma-separated pair of integers"
        ) from error
    if len(slots) != 2 or set(slots) != {CONTROL_SLOT, STUDY_SLOT}:
        raise argparse.ArgumentTypeError(
            "--slots must contain exactly the study pair 1,5"
        )
    return (CONTROL_SLOT, STUDY_SLOT)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--window must be positive")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the reproducible study CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slots",
        type=_parse_slots,
        default=(CONTROL_SLOT, STUDY_SLOT),
        help="study slots as 1,5 (default: 1,5)",
    )
    parser.add_argument(
        "--window",
        type=_positive_int,
        default=10,
        help="non-overlapping window size in chunks (default: 10)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_OUT,
        help=f"JSON output path (default: {DEFAULT_JSON_OUT})",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=DEFAULT_REPORT_OUT,
        help=f"Markdown output path (default: {DEFAULT_REPORT_OUT})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the study and write both required artifacts."""

    args = parse_args(argv)
    study = run_study(args.slots, args.window)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(study, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.report_out.write_text(render_report(study), encoding="utf-8")
    print(verdict_table(study))
    print(f"Wrote {args.json_out}")
    print(f"Wrote {args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
