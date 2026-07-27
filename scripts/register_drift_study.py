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
from math import sqrt
from pathlib import Path
import random
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
PARTIAL_CONTROL_THRESHOLD = 0.30
PERMUTATION_COUNT = 2_000
PERMUTATION_SEED = 20_260_726
SIGNIFICANCE_THRESHOLD = 0.05

CONTROL_STORYTELLER_SERIES = "slot_1_storyteller"
CONTROL_PLAYER_SERIES = "slot_1_player"
STUDY_SERIES = "slot_5"

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+[\"'”’)\]]*|\n+")
LEGACY_CHANNEL_HEADING_RE = re.compile(
    r"^\s*##\s+(?P<channel>Storyteller|You)\s*$", re.IGNORECASE
)
SCENE_BREAK_COMMENT_RE = re.compile(
    r"<!--\s*SCENE\s+BREAK\b.*?-->", re.IGNORECASE | re.DOTALL
)
LEGACY_OPTION_LINE_RE = re.compile(
    r"^\s*(?:###\s*)?\*{0,2}(?P<number>\d+)[.)]\s*(?P<text>.+?)\s*$"
)
MARKDOWN_EMPHASIS_RE = re.compile(r"[*_`]+")

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
class SeriesChunk:
    """One playable position projected into a study series."""

    chunk_id: int
    ordinal: int
    text: str
    choices: tuple[str, ...] | None
    choice_source: Literal["structured", "recovered"] | None


@dataclass(frozen=True)
class MetricDefinition:
    """Report metadata for a calculated metric."""

    key: str
    title: str
    definition: str
    choice_metric: bool = False


@dataclass(frozen=True)
class SeriesDefinition:
    """Display and provenance metadata for one analyzed text channel."""

    key: str
    label: str
    slot: int
    channel: str


SERIES = (
    SeriesDefinition(
        CONTROL_STORYTELLER_SERIES,
        "Slot 1 storyteller",
        CONTROL_SLOT,
        "storyteller",
    ),
    SeriesDefinition(
        CONTROL_PLAYER_SERIES,
        "Slot 1 player",
        CONTROL_SLOT,
        "player",
    ),
    SeriesDefinition(STUDY_SERIES, "Slot 5", STUDY_SLOT, "storyteller_text"),
)


METRICS = (
    MetricDefinition(
        "lexical_novelty_rate",
        "Lexical novelty rate",
        "Fraction of the chunk's content-word types absent from all earlier "
        "chunks in the same channel series.",
    ),
    MetricDefinition(
        "coinage_density",
        "Coinage density",
        "Title-Case multiword spans beginning mid-sentence per 1,000 words.",
    ),
    MetricDefinition(
        "console_proclamation_register",
        "Console/proclamation register",
        "ALL-CAPS-dominant lines per 1,000 words.",
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
        "Mean pairwise content-word Jaccard similarity among presented or "
        "recovered choices.",
        choice_metric=True,
    ),
    MetricDefinition(
        "choice_topic_recurrence",
        "Choice-topic recurrence",
        "Content-word Jaccard similarity against presented or recovered choices "
        "in the preceding five playable turns.",
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
PROSE_METRICS = tuple(metric for metric in METRICS if not metric.choice_metric)


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


def console_proclamation_register(text: str) -> float:
    """Return ALL-CAPS-dominant lines per 1,000 alphabetic words.

    A qualifying line has at least eight alphabetic characters, at least 60%
    of which are uppercase.  Only alphabetic characters enter that case
    ratio.  The qualifying-line count is divided by the chunk's alphabetic
    word count and multiplied by 1,000.  A text with no words scores 0.
    """

    words = word_tokens(text)
    if not words:
        return 0.0
    qualifying_lines = 0
    for line in text.splitlines():
        letters = [character for character in line if character.isalpha()]
        if len(letters) < 8:
            continue
        uppercase = sum(character.isupper() for character in letters)
        if uppercase / len(letters) >= 0.60:
            qualifying_lines += 1
    return qualifying_lines * 1000.0 / len(words)


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

    slope, _ = ordinary_least_squares_fit(points)
    return slope


def ordinary_least_squares_fit(
    points: Sequence[tuple[float, float]],
) -> tuple[float | None, float | None]:
    """Return an OLS slope and its residual standard error.

    The slope is undefined with fewer than two points or no variation in
    ``x``.  Its conventional standard error is
    ``sqrt((SSE / (n - 2)) / Sxx)`` and is therefore undefined with fewer
    than three points.  The intercept is fitted inline only to calculate
    residuals; it is not returned.
    """

    if len(points) < 2:
        return None, None
    mean_x = fmean(point[0] for point in points)
    mean_y = fmean(point[1] for point in points)
    denominator = sum((x_value - mean_x) ** 2 for x_value, _ in points)
    if denominator == 0:
        return None, None
    numerator = sum(
        (x_value - mean_x) * (y_value - mean_y) for x_value, y_value in points
    )
    slope = numerator / denominator
    if len(points) < 3:
        return slope, None
    intercept = mean_y - slope * mean_x
    squared_error = sum(
        (y_value - (intercept + slope * x_value)) ** 2 for x_value, y_value in points
    )
    standard_error = sqrt((squared_error / (len(points) - 2)) / denominator)
    return slope, standard_error


def permutation_slope_difference_p_value(
    control_points: Sequence[tuple[float, float]],
    study_points: Sequence[tuple[float, float]],
    *,
    permutations: int = PERMUTATION_COUNT,
    seed: int = PERMUTATION_SEED,
) -> float:
    """Return a deterministic two-sided permutation p-value for slope difference.

    The observed statistic is ``study slope - control slope``.  All window
    points are pooled, shuffled, and split back into groups of the original
    sizes before both slopes are refitted.  The two-sided tail compares
    absolute differences.  Exactly ``permutations`` valid label shuffles are
    used, and the return value applies the standard plus-one Monte Carlo
    correction: ``(extreme + 1) / (permutations + 1)``.

    Undefined observed or permuted slopes are loud errors because silently
    dropping such samples would change the requested null distribution.
    """

    if permutations <= 0:
        raise ValueError("permutations must be positive")
    control_slope = ordinary_least_squares_slope(control_points)
    study_slope = ordinary_least_squares_slope(study_points)
    if control_slope is None or study_slope is None:
        raise ValueError("both observed series must have defined slopes")

    pooled_points = list(control_points) + list(study_points)
    control_size = len(control_points)
    observed_difference = study_slope - control_slope
    random_generator = random.Random(seed)
    extreme_count = 0
    for _ in range(permutations):
        shuffled_points = pooled_points.copy()
        random_generator.shuffle(shuffled_points)
        permuted_control_slope = ordinary_least_squares_slope(
            shuffled_points[:control_size]
        )
        permuted_study_slope = ordinary_least_squares_slope(
            shuffled_points[control_size:]
        )
        if permuted_control_slope is None or permuted_study_slope is None:
            raise RuntimeError("permutation produced an undefined slope")
        permuted_difference = permuted_study_slope - permuted_control_slope
        if abs(permuted_difference) >= abs(observed_difference):
            extreme_count += 1
    return (extreme_count + 1) / (permutations + 1)


def split_legacy_channels(text: str) -> tuple[str, str]:
    """Split legacy raw text into storyteller and player channels.

    ``## Storyteller`` and ``## You`` heading lines switch the destination
    channel and are omitted.  Text before the first channel heading belongs
    to the storyteller.  All ``<!-- SCENE BREAK ... -->`` comments are
    removed before splitting, including multiline comments.  Repeated
    alternations are concatenated in source order within their channel.
    """

    without_scene_breaks = SCENE_BREAK_COMMENT_RE.sub("", text)
    channel = "storyteller"
    storyteller_lines: list[str] = []
    player_lines: list[str] = []

    for line in without_scene_breaks.splitlines():
        heading = LEGACY_CHANNEL_HEADING_RE.fullmatch(line)
        if heading is not None:
            channel = (
                "storyteller"
                if heading.group("channel").lower() == "storyteller"
                else "player"
            )
            continue
        if channel == "storyteller":
            storyteller_lines.append(line)
        else:
            player_lines.append(line)

    return (
        "\n".join(storyteller_lines).strip(),
        "\n".join(player_lines).strip(),
    )


def _clean_legacy_option_text(text: str) -> str:
    """Remove Markdown emphasis markers from a recovered option line."""

    cleaned = MARKDOWN_EMPHASIS_RE.sub("", text).strip()
    if not cleaned:
        raise ValueError("legacy numbered option has no text")
    return cleaned


def extract_legacy_choices(text: str) -> tuple[str, ...] | None:
    """Recover the final sequential 2-6-item numbered option block.

    Candidate item lines match ``LEGACY_OPTION_LINE_RE`` and must number
    sequentially from 1.  Non-item lines may contain option descriptions, so
    they do not terminate a candidate; a new item numbered 1 starts a new
    candidate.  If a storyteller section contains multiple qualifying
    blocks, the final block is used because legacy turns place the presented
    menu after explanatory numbered material.  Markdown emphasis markers are
    removed from the returned option text.
    """

    candidates: list[tuple[str, ...]] = []
    current: list[str] = []

    def finish_current() -> None:
        if 2 <= len(current) <= 6:
            candidates.append(tuple(current))

    for line in text.splitlines():
        match = LEGACY_OPTION_LINE_RE.match(line)
        if match is None:
            continue
        number = int(match.group("number"))
        option_text = _clean_legacy_option_text(match.group("text"))
        if number == 1:
            finish_current()
            current = [option_text]
        elif current and number == len(current) + 1:
            current.append(option_text)
        else:
            finish_current()
            current = []

    finish_current()
    return candidates[-1] if candidates else None


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


def calculate_chunk_metrics(
    chunks: Sequence[SeriesChunk],
) -> list[dict[str, Any]]:
    """Calculate all metrics for one channel series in playable order.

    Every source chunk retains its playable ordinal.  If that chunk has no
    text in this channel, prose metrics are ``None`` rather than zero; this
    preserves slot-position windows without treating channel absence as a
    stylistic measurement.
    """

    seen_content_words: set[str] = set()
    recent_choices: deque[tuple[str, ...] | None] = deque(maxlen=CHOICE_HISTORY_TURNS)
    rows: list[dict[str, Any]] = []

    for chunk in chunks:
        prior_choice_turns = [
            choices for choices in recent_choices if choices is not None
        ]
        has_text = bool(chunk.text.strip())
        prose_values: dict[str, float | None]
        if has_text:
            prose_values = {
                "lexical_novelty_rate": lexical_novelty_rate(
                    chunk.text, seen_content_words
                ),
                "coinage_density": coinage_density(chunk.text),
                "console_proclamation_register": (
                    console_proclamation_register(chunk.text)
                ),
                "ceremonial_syntax_density": ceremonial_syntax_density(chunk.text),
                "mean_sentence_length": mean_sentence_length(chunk.text),
                "dialogue_line_fraction": dialogue_line_fraction(chunk.text),
                "second_person_pronoun_rate": second_person_pronoun_rate(chunk.text),
            }
        else:
            prose_values = {metric.key: None for metric in PROSE_METRICS}

        choice_values: dict[str, float | None] = {
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
        }
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "ordinal": chunk.ordinal,
                "has_text": has_text,
                "has_presented_choices": chunk.choices is not None,
                "choice_source": chunk.choice_source,
                **prose_values,
                **choice_values,
            }
        )
        if has_text:
            seen_content_words.update(content_word_types(chunk.text))
        recent_choices.append(chunk.choices)
    return rows


def _windowed_means(
    metric_rows: Sequence[Mapping[str, Any]], metric_key: str, window: int
) -> list[dict[str, Any]]:
    """Return non-overlapping window means with campaign-position centers."""

    if not metric_rows:
        return []
    max_ordinal = max(int(row["ordinal"]) for row in metric_rows)
    if max_ordinal <= 0:
        raise ValueError("playable ordinals must be positive")
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
                "center_campaign_position": (
                    fmean(ordinal / max_ordinal for ordinal in ordinals)
                ),
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
    """Summarize one metric with windows, campaign-position OLS, and bands."""

    windows = _windowed_means(metric_rows, metric_key, window)
    slope_points = [
        (float(item["center_campaign_position"]), float(item["mean"]))
        for item in windows
        if item["mean"] is not None
    ]
    first_window_mean = windows[0]["mean"] if windows else None
    last_window_mean = windows[-1]["mean"] if windows else None
    early = _percentile_band(metric_rows, metric_key, 0.0, 0.10)
    middle = _percentile_band(metric_rows, metric_key, 0.45, 0.55)
    late = _percentile_band(metric_rows, metric_key, 0.90, 1.0)
    slope, slope_standard_error = ordinary_least_squares_fit(slope_points)
    relative_band_change = _relative_change(
        _optional_float(early["mean"]), _optional_float(late["mean"])
    )
    observations = sum(row[metric_key] is not None for row in metric_rows)
    return {
        "observations": observations,
        "windows": windows,
        "slope_window_count": len(slope_points),
        "slope_per_campaign": slope,
        "slope_standard_error": slope_standard_error,
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


def _corpus_payload(corpus: Corpus) -> dict[str, Any]:
    """Return extraction metadata without duplicating channel analyses."""

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
            "chunks_with_structured_presented_choices": corpus.choice_chunks,
        },
    }


def _build_series_chunks(
    corpora: Mapping[int, Corpus],
) -> dict[str, tuple[SeriesChunk, ...]]:
    """Project the two corpora into storyteller, player, and study series."""

    control_storyteller: list[SeriesChunk] = []
    control_player: list[SeriesChunk] = []
    for chunk in corpora[CONTROL_SLOT].chunks:
        if chunk.source == "raw_text":
            storyteller_text, player_text = split_legacy_channels(chunk.text)
        else:
            storyteller_text = chunk.text
            player_text = ""

        recovered_choices = extract_legacy_choices(storyteller_text)
        if chunk.choices is not None and recovered_choices is not None:
            raise RuntimeError(
                f"save_{CONTROL_SLOT:02d} chunk {chunk.chunk_id}: both "
                "structured and recovered choices are present"
            )
        control_choices = (
            chunk.choices if chunk.choices is not None else recovered_choices
        )
        if chunk.choices is not None:
            choice_source: Literal["structured", "recovered"] | None = "structured"
        elif recovered_choices is not None:
            choice_source = "recovered"
        else:
            choice_source = None

        control_storyteller.append(
            SeriesChunk(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                text=storyteller_text,
                choices=control_choices,
                choice_source=choice_source,
            )
        )
        control_player.append(
            SeriesChunk(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                text=player_text,
                choices=None,
                choice_source=None,
            )
        )

    study_chunks = tuple(
        SeriesChunk(
            chunk_id=chunk.chunk_id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            choices=chunk.choices,
            choice_source="structured" if chunk.choices is not None else None,
        )
        for chunk in corpora[STUDY_SLOT].chunks
    )
    return {
        CONTROL_STORYTELLER_SERIES: tuple(control_storyteller),
        CONTROL_PLAYER_SERIES: tuple(control_player),
        STUDY_SERIES: study_chunks,
    }


def _series_payload(
    definition: SeriesDefinition,
    chunks: Sequence[SeriesChunk],
    window: int,
) -> dict[str, Any]:
    """Analyze one projected channel series."""

    metric_rows = calculate_chunk_metrics(chunks)
    analyses = {
        metric.key: analyze_metric(metric_rows, metric.key, window)
        for metric in METRICS
    }
    drift_velocity_candidates = sum(
        bool(analysis["drift_velocity_qualifies"]) for analysis in analyses.values()
    )
    measurable_metrics = sum(
        int(analysis["observations"] > 0) for analysis in analyses.values()
    )
    text_chunks = sum(bool(chunk.text.strip()) for chunk in chunks)
    choice_chunks = sum(chunk.choices is not None for chunk in chunks)
    structured_choice_chunks = sum(
        chunk.choice_source == "structured" for chunk in chunks
    )
    recovered_choice_chunks = sum(
        chunk.choice_source == "recovered" for chunk in chunks
    )
    return {
        "key": definition.key,
        "label": definition.label,
        "slot": definition.slot,
        "channel": definition.channel,
        "playable_positions": len(chunks),
        "chunks_with_text": text_chunks,
        "chunks_with_choices": choice_chunks,
        "choice_coverage": choice_chunks / len(chunks) if chunks else 0.0,
        "choice_source_counts": {
            "structured": structured_choice_chunks,
            "recovered": recovered_choice_chunks,
        },
        "per_chunk": metric_rows,
        "analysis": analyses,
        "drift_velocity_candidate_count": drift_velocity_candidates,
        "measurable_metric_count": measurable_metrics,
    }


def _analysis_slope_points(
    analysis: Mapping[str, Any],
) -> list[tuple[float, float]]:
    """Recover non-empty campaign-position window points from an analysis."""

    return [
        (float(window["center_campaign_position"]), float(window["mean"]))
        for window in analysis["windows"]
        if window["mean"] is not None
    ]


def _verdicts(
    series_payloads: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare campaign-position slopes with deterministic uncertainty."""

    control = series_payloads[CONTROL_STORYTELLER_SERIES]
    study = series_payloads[STUDY_SERIES]
    control_choice_coverage = float(control["choice_coverage"])
    verdicts: list[dict[str, Any]] = []
    for metric in METRICS:
        control_analysis = control["analysis"][metric.key]
        study_analysis = study["analysis"][metric.key]
        control_slope = _optional_float(control_analysis["slope_per_campaign"])
        control_standard_error = _optional_float(
            control_analysis["slope_standard_error"]
        )
        study_slope = _optional_float(study_analysis["slope_per_campaign"])
        study_standard_error = _optional_float(study_analysis["slope_standard_error"])
        if not metric.choice_metric:
            comparison_basis = "full control"
        elif int(control["analysis"][metric.key]["observations"]) == 0:
            comparison_basis = "no control"
        elif control_choice_coverage < PARTIAL_CONTROL_THRESHOLD:
            comparison_basis = "partial control"
        else:
            comparison_basis = "recovered control"

        if control_slope is None or study_slope is None:
            comparison = "insufficient data"
            exceeds = None
            p_value = None
        else:
            exceeds = study_slope > control_slope
            p_value = permutation_slope_difference_p_value(
                _analysis_slope_points(control_analysis),
                _analysis_slope_points(study_analysis),
            )
            if not exceeds:
                comparison = "no"
            elif p_value >= SIGNIFICANCE_THRESHOLD:
                comparison = "provisional (underpowered)"
            else:
                comparison = "yes"
        verdicts.append(
            {
                "metric": metric.key,
                "title": metric.title,
                "slot_1_storyteller_slope_per_campaign": control_slope,
                "slot_1_storyteller_slope_standard_error": (control_standard_error),
                "slot_5_slope_per_campaign": study_slope,
                "slot_5_slope_standard_error": study_standard_error,
                "slot_5_exceeds_slot_1_storyteller": exceeds,
                "slope_difference_per_campaign": (
                    study_slope - control_slope
                    if control_slope is not None and study_slope is not None
                    else None
                ),
                "permutation_p_value": p_value,
                "permutations": PERMUTATION_COUNT if p_value is not None else None,
                "comparison_basis": comparison_basis,
                "verdict": comparison,
            }
        )
    return verdicts


def run_study(slots: Sequence[int], window: int) -> dict[str, Any]:
    """Extract, calculate, and assemble the complete study document."""

    corpora = {slot: load_corpus(slot) for slot in slots}
    series_chunks = _build_series_chunks(corpora)
    series_payloads = {
        definition.key: _series_payload(
            definition, series_chunks[definition.key], window
        )
        for definition in SERIES
    }
    verdicts = _verdicts(series_payloads)
    confirmed_metric_keys = {
        verdict["metric"] for verdict in verdicts if verdict["verdict"] == "yes"
    }
    for payload in series_payloads.values():
        payload["drift_velocity_metric_count"] = sum(
            metric.key in confirmed_metric_keys
            and bool(payload["analysis"][metric.key]["drift_velocity_qualifies"])
            for metric in METRICS
        )
    generated_at = datetime.now(timezone.utc)
    return {
        "study": "Register drift: LLM-grown vs human-played narrative",
        "study_date": generated_at.astimezone().date().isoformat(),
        "generated_at_utc": generated_at.isoformat(timespec="seconds"),
        "parameters": {
            "slots": list(slots),
            "window_chunks": window,
            "choice_history_turns": CHOICE_HISTORY_TURNS,
            "partial_control_threshold": PARTIAL_CONTROL_THRESHOLD,
            "permutation_count": PERMUTATION_COUNT,
            "permutation_seed": PERMUTATION_SEED,
            "significance_threshold": SIGNIFICANCE_THRESHOLD,
            "playable_predicate": playable_narrative_predicate("nc"),
        },
        "metric_definitions": {metric.key: metric.definition for metric in METRICS},
        "slots": {
            str(slot): _corpus_payload(corpus) for slot, corpus in corpora.items()
        },
        "series": series_payloads,
        "verdicts": verdicts,
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
        "| Metric | Slot 1 slope/campaign | Slot 1 SE | Slot 5 slope/campaign | "
        "Slot 5 SE | Difference | Permutation p | Control basis | "
        "Slot-5 trend exceeds storyteller? |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |",
    ]
    for verdict in study["verdicts"]:
        lines.append(
            "| {title} | {slot_1} | {slot_1_se} | {slot_5} | {slot_5_se} | "
            "{difference} | {p_value} | {basis} | {status} |".format(
                title=verdict["title"],
                slot_1=_format_value(
                    verdict["slot_1_storyteller_slope_per_campaign"],
                    slope=True,
                ),
                slot_1_se=_format_value(
                    verdict["slot_1_storyteller_slope_standard_error"],
                    slope=True,
                ),
                slot_5=_format_value(verdict["slot_5_slope_per_campaign"], slope=True),
                slot_5_se=_format_value(
                    verdict["slot_5_slope_standard_error"], slope=True
                ),
                difference=_format_value(
                    verdict["slope_difference_per_campaign"], slope=True
                ),
                p_value=_format_value(verdict["permutation_p_value"], slope=True),
                basis=verdict["comparison_basis"],
                status=verdict["verdict"],
            )
        )
    return "\n".join(lines)


def _corpus_table(study: Mapping[str, Any]) -> str:
    lines = [
        "| Slot | Total rows | Playable | Analyzed | storyteller_text | raw_text | "
        "Structured choice chunks |",
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
                choices=sources["chunks_with_structured_presented_choices"],
            )
        )
    return "\n".join(lines)


def _series_census_table(study: Mapping[str, Any]) -> str:
    """Render projected channel and menu coverage."""

    lines = [
        "| Series | Playable positions | Chunks with text | Choice/menu chunks | "
        "Choice coverage |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for definition in SERIES:
        payload = study["series"][definition.key]
        lines.append(
            "| {label} | {positions} | {text_chunks} | {choice_chunks} | "
            "{coverage:.1%} |".format(
                label=definition.label,
                positions=payload["playable_positions"],
                text_chunks=payload["chunks_with_text"],
                choice_chunks=payload["chunks_with_choices"],
                coverage=float(payload["choice_coverage"]),
            )
        )
    return "\n".join(lines)


def _metric_table(study: Mapping[str, Any], metric: MetricDefinition) -> str:
    window = study["parameters"]["window_chunks"]
    analyses = [
        study["series"][definition.key]["analysis"][metric.key] for definition in SERIES
    ]
    lines = [
        "| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |",
        "| :--- | ---: | ---: | ---: |",
        "| Observations | {values} |".format(
            values=" | ".join(str(analysis["observations"]) for analysis in analyses)
        ),
        "| Early 0–10% | {values} |".format(
            values=" | ".join(
                _format_value(
                    analysis["bands"]["early_0_10_percent"]["mean"],
                )
                for analysis in analyses
            )
        ),
        "| Middle 45–55% | {values} |".format(
            values=" | ".join(
                _format_value(
                    analysis["bands"]["middle_45_55_percent"]["mean"],
                )
                for analysis in analyses
            )
        ),
        "| Late 90–100% | {values} |".format(
            values=" | ".join(
                _format_value(
                    analysis["bands"]["late_90_100_percent"]["mean"],
                )
                for analysis in analyses
            )
        ),
        "| OLS slope/campaign | {values} |".format(
            values=" | ".join(
                _format_value(analysis["slope_per_campaign"], slope=True)
                for analysis in analyses
            )
        ),
        "| OLS slope SE | {values} |".format(
            values=" | ".join(
                _format_value(analysis["slope_standard_error"], slope=True)
                for analysis in analyses
            )
        ),
        f"| First {window}-chunk window | {{values}} |".format(
            values=" | ".join(
                _format_value(analysis["first_window_mean"]) for analysis in analyses
            )
        ),
        f"| Last {window}-chunk window | {{values}} |".format(
            values=" | ".join(
                _format_value(analysis["last_window_mean"]) for analysis in analyses
            )
        ),
    ]
    return "\n".join(lines)


def _band_gap(
    study: Mapping[str, Any],
    metric_key: str,
    band_key: str,
) -> float | None:
    """Return slot-1 storyteller mean minus player mean for a band."""

    storyteller = _optional_float(
        study["series"][CONTROL_STORYTELLER_SERIES]["analysis"][metric_key]["bands"][
            band_key
        ]["mean"]
    )
    player = _optional_float(
        study["series"][CONTROL_PLAYER_SERIES]["analysis"][metric_key]["bands"][
            band_key
        ]["mean"]
    )
    if storyteller is None or player is None:
        return None
    return storyteller - player


def _format_gap(value: float | None) -> str:
    """Format a signed storyteller-minus-player band gap."""

    if value is None:
        return "n/a"
    return f"{value:+.3f}"


def _human_dampener_table(study: Mapping[str, Any]) -> str:
    """Render the observational slot-1 channel-gap table."""

    lines = [
        "| Metric | Early 0–10% gap | Middle 45–55% gap | Late 90–100% gap |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric in PROSE_METRICS:
        lines.append(
            "| {title} | {early} | {middle} | {late} |".format(
                title=metric.title,
                early=_format_gap(
                    _band_gap(
                        study,
                        metric.key,
                        "early_0_10_percent",
                    )
                ),
                middle=_format_gap(
                    _band_gap(
                        study,
                        metric.key,
                        "middle_45_55_percent",
                    )
                ),
                late=_format_gap(
                    _band_gap(
                        study,
                        metric.key,
                        "late_90_100_percent",
                    )
                ),
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
        verdict["verdict"] == "yes" for verdict in controlled_verdicts
    )
    provisional_count = sum(
        verdict["verdict"] == "provisional (underpowered)"
        for verdict in controlled_verdicts
    )
    control_velocity = study["series"][CONTROL_STORYTELLER_SERIES][
        "drift_velocity_metric_count"
    ]
    study_velocity = study["series"][STUDY_SERIES]["drift_velocity_metric_count"]
    slot_5_analysis = study["series"][STUDY_SERIES]["analysis"]
    slot_5_window_counts = {
        int(slot_5_analysis[metric.key]["slope_window_count"]) for metric in METRICS
    }
    if len(slot_5_window_counts) == 1:
        slot_5_window_count_statement = (
            f"Slot 5 contributes {next(iter(slot_5_window_counts))} non-empty "
            "window points to every slope fit."
        )
    else:
        slot_5_window_count_statement = (
            "Slot-5 non-empty slope-window counts vary by metric: "
            + ", ".join(
                f"{metric.title}={slot_5_analysis[metric.key]['slope_window_count']}"
                for metric in METRICS
            )
            + "."
        )
    control_choice_payload = study["series"][CONTROL_STORYTELLER_SERIES]
    control_choice_chunks = int(control_choice_payload["chunks_with_choices"])
    control_positions = int(control_choice_payload["playable_positions"])
    control_choice_coverage = float(control_choice_payload["choice_coverage"])
    if control_choice_chunks == 0:
        choice_control_statement = (
            "No legacy menus were recovered, so choice metrics have no control."
        )
    elif control_choice_coverage < PARTIAL_CONTROL_THRESHOLD:
        choice_control_statement = (
            f"Legacy recovery found menus in {control_choice_chunks} of "
            f"{control_positions} slot-1 chunks ({control_choice_coverage:.1%}). "
            "Because coverage is below 30%, both choice metrics are marked "
            "“partial control” in the verdict table."
        )
    else:
        choice_control_statement = (
            f"Legacy recovery found menus in {control_choice_chunks} of "
            f"{control_positions} slot-1 chunks ({control_choice_coverage:.1%}); "
            "the choice metrics are marked as recovered controls."
        )
    positive_gap_counts = {
        label: sum(
            (_band_gap(study, metric.key, band_key) or 0.0) > 0
            for metric in PROSE_METRICS
        )
        for label, band_key in (
            ("early", "early_0_10_percent"),
            ("middle", "middle_45_55_percent"),
            ("late", "late_90_100_percent"),
        )
    }
    if exceeding_count > len(controlled_verdicts) / 2:
        overall_verdict = (
            "Overall verdict: the measured prose pattern favors H2's broad "
            "escalation prediction. Slot 5 has a significantly greater slope on "
            f"{exceeding_count} of {len(controlled_verdicts)} fully controlled "
            f"prose metrics; {provisional_count} additional comparison(s) are "
            "provisional. Uncertainty-filtered drift velocity is "
            f"{study_velocity} versus {control_velocity} in the slot-1 "
            "storyteller series. This "
            "remains directional evidence, not proof of the amplification "
            "mechanism."
        )
    else:
        overall_verdict = (
            "Overall verdict: the measured prose pattern does not show broad "
            "H2-style escalation. Slot 5 has a significantly greater slope on "
            "only "
            f"{exceeding_count} of {len(controlled_verdicts)} fully controlled "
            f"prose metrics; {provisional_count} additional comparison(s) are "
            "provisional. Uncertainty-filtered drift velocity is "
            f"{study_velocity} versus {control_velocity} in the slot-1 "
            "storyteller series. This leans "
            "toward H1's flat/high-intercept trend prediction, while metrics "
            "marked “yes” remain localized H2-compatible signals; it does not "
            "establish missing context as the mechanism."
        )
    lines = [
        "# Register-Drift Study: LLM-Grown vs Human-Played Narrative",
        "",
        f"Study date: **{study['study_date']}**. Generated at "
        f"`{study['generated_at_utc']}` from read-only PostgreSQL sessions.",
        "",
        "## Question",
        "",
        "The study contrasts two measurable predictions. H1 (missing reader "
        "context) permits a high register intercept but predicts broadly flat "
        "register metrics across slot 5. H2 (two-LLM amplification) predicts "
        "rising slot-5 metrics that exceed trends in the slot-1 storyteller "
        "channel. The separately measured slot-1 player channel is an "
        "observational human-register series.",
        "",
        "## Corpus and prose sources",
        "",
        _corpus_table(study),
        "",
        _series_census_table(study),
        "",
        "Rows are ordered by playable ordinal, not raw chunk ID. For each row, "
        "`storyteller_text` is authoritative when non-empty; otherwise the "
        "analysis uses `raw_text`. The source census shows exactly how many "
        "chunks used each field in each slot. Slot 1's legacy `raw_text` is "
        "split at recurring `## Storyteller` and `## You` headings; text before "
        "the first heading belongs to the storyteller channel. The delimiter "
        "headings and `<!-- SCENE BREAK ... -->` comments are removed. Slot 5 "
        "uses its `storyteller_text` unchanged. The canonical "
        "`nexus.agents.orrery.reconstruction.playable_narrative_predicate` "
        "excludes non-playable rows, and rows with neither prose source are "
        "excluded.",
        "",
        choice_control_statement,
        "",
        "## Methods",
        "",
        "All database connections use `psycopg2`, call "
        "`set_session(readonly=True)` before any query, and verify "
        "`transaction_read_only=on`. The script issues only `SHOW` and "
        "`SELECT` statements.",
        "",
        "The three prose series are slot 1 storyteller, slot 1 player, and "
        "slot 5. A missing channel in a playable chunk is omitted from metric "
        "means rather than scored as zero, while the chunk still retains its "
        "slot position. Running lexical vocabularies are independent for all "
        "three series.",
        "",
        "Legacy slot-1 choices are recovered only from storyteller-channel "
        "lines matching the numbered-option pattern "
        "`^\\s*(?:###\\s*)?\\*{0,2}\\d+[.)]`. Items must form a sequential "
        "1-based block of 2–6 options. Description lines may intervene, and "
        "when several blocks qualify, the final block is used. The two choice "
        "metrics remain undefined for the player channel.",
        "",
        "Words are lowercase Unicode alphabetic runs; punctuation is treated "
        "as a boundary. Content-word sets remove this fixed built-in stopword "
        f"list: {', '.join(sorted(STOPWORDS))}.",
        "",
        "1. **Lexical novelty rate.** For each chunk, the fraction of its "
        "content-word types not present in any earlier chunk in the same "
        "series. The running vocabulary is updated only after scoring the "
        "chunk; an empty content-word set scores 0.",
        "2. **Coinage density.** Count per 1,000 words of maximal spans with "
        "two or more consecutive title-cased alphabetic tokens separated by "
        "whitespace. The first token after the start of text or `.`, `!`, or "
        "`?`, or a newline cannot begin a span, excluding sentence-initial "
        "capitalization.",
        "3. **Console/proclamation register.** Per 1,000 words, lines with at "
        "least eight alphabetic characters for which at least 60% of those "
        "characters are uppercase. Only alphabetic characters enter the case "
        "ratio.",
        "4. **Ceremonial-syntax density.** Per 1,000 words, the sum of "
        "non-empty alphabetic lines ending in a colon, U+2014 em dashes, and "
        "matches in this fixed generic ritual/formality lexicon: "
        f"{', '.join(sorted(FORMALITY_WORDS))}.",
        "5. **Choice-list self-similarity.** Mean pairwise Jaccard similarity "
        "of the presented or recovered choices' content-word sets; undefined "
        "with fewer than two choices. Two empty sets are assigned 0.",
        "6. **Choice-topic recurrence.** Jaccard similarity of the current "
        "turn's pooled choice content words against the union from "
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
        f"{window}-chunk windows; a final partial window is retained. For each "
        "series and metric, ordinary least squares is fit inline to window "
        "mean versus the window's mean campaign position, where each chunk "
        "position is its playable ordinal divided by the maximum playable "
        "ordinal in that series. The x axis is therefore normalized to "
        "(0, 1], and the slope unit is metric units per campaign. Each slope's "
        "standard error uses the inline OLS residual estimate "
        "`sqrt((SSE / (n - 2)) / Sxx)` and is undefined with fewer than three "
        "window points. Position-normalized early, middle, and late means use "
        "inclusive 0–10%, 45–55%, and 90–100% playable-position bands. Missing "
        "metric values are omitted from means, never replaced with zero.",
        "",
        "For every slot-5 minus slot-1 storyteller slope difference, the two "
        "series' non-empty window points are pooled, labels are shuffled while "
        "preserving the original group sizes, and both slopes are refitted. "
        f"The reported two-sided p-value uses {PERMUTATION_COUNT:,} "
        "permutations, compares absolute slope differences, uses fixed random "
        f"seed `{PERMUTATION_SEED}`, and applies the plus-one Monte Carlo "
        "correction. A numerically greater slot-5 slope is “yes” only when "
        f"`p < {SIGNIFICANCE_THRESHOLD:.2f}`; otherwise it is “provisional "
        "(underpowered)”.",
        "",
        "A metric contributes to a series' drift velocity when its OLS slope "
        "is positive and its late-band mean exceeds its early-band mean by "
        "more than 20% relative. A zero or missing early mean has undefined "
        "relative change and is conservatively not counted. The reported "
        "uncertainty-aware summary further requires that metric's cross-slot "
        "verdict to be a non-provisional “yes”; provisional, no, and "
        "insufficient comparisons are not counted.",
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
            "## Human-dampener contrast",
            "",
            "Each value below is the slot-1 storyteller band mean minus the "
            "slot-1 player band mean; a positive value means the storyteller "
            "channel is higher on that metric.",
            "",
            _human_dampener_table(study),
            "",
            "The storyteller-minus-player gap is positive for "
            f"{positive_gap_counts['early']} of {len(PROSE_METRICS)} prose "
            "metrics early, "
            f"{positive_gap_counts['middle']} of {len(PROSE_METRICS)} in the "
            "middle, and "
            f"{positive_gap_counts['late']} of {len(PROSE_METRICS)} late. "
            "This describes channel separation at comparable campaign "
            "positions; gap magnitudes are not comparable across metrics "
            "because their units differ. It does not show that a human "
            "utterance caused the next storyteller response to dampen, and it "
            "is not a causal estimate.",
            "",
            "## Verdict",
            "",
            "The slope difference is slot 5 minus slot-1 storyteller in metric "
            "units per campaign. “Yes” means that difference is positive and "
            "its two-sided permutation p-value is below 0.05; a positive "
            "difference at p ≥ 0.05 is “provisional (underpowered)”. The "
            "storyteller channel is the model-output control; the player "
            "channel remains observational. Choice comparisons use only the "
            "sparse structurally recovered slot-1 menus and are labeled by "
            "their coverage.",
            "",
            verdict_table(study),
            "",
        ]
    )
    for definition in SERIES:
        payload = study["series"][definition.key]
        lines.append(
            f"**{definition.label} drift velocity:** "
            f"{payload['drift_velocity_metric_count']} metric(s) "
            f"(of {payload['drift_velocity_candidate_count']} within-series "
            "candidate(s) and "
            f"{payload['measurable_metric_count']} measurable; provisional "
            "comparisons excluded)."
        )
        lines.append("")

    lines.extend(
        [
            "Across the seven fully controlled prose/style metrics, slot 5 "
            f"has a non-provisional greater OLS slope on {exceeding_count}; "
            f"{provisional_count} additional positive difference(s) are "
            "underpowered. This is an uncertainty-qualified comparison of the "
            "registered measurements, not a causal identification result; the "
            "individual slopes and band movements determine whether the "
            "evidence looks more like a flat high-intercept register (H1) or "
            "escalating register (H2).",
            "",
            overall_verdict,
            "",
            "## Limitations",
            "",
            "Slot 1 is not a model-pure control: it spans model heterogeneity, "
            "and the controlling storyteller channel was generated inside a "
            "human-in-the-loop campaign. The actual contrast is therefore "
            "human-in-the-loop versus LLM-in-the-loop, not one model versus "
            "another under purified conditions. Its legacy `raw_text` "
            "interleaves narration with human player lines; the structural "
            "split makes those channels separately observable, but the human "
            "input and its downstream influence are part of the phenomenon, "
            "not filtered away. The section parser depends on the legacy "
            "headings, and recovered numbered menus are a sparse heuristic "
            "sample that can include or miss list-like prose. The hand-built "
            "stopword, formality, pronoun, capitalization, and segmentation "
            "rules introduce lexicon-choice and operationalization bias; "
            "other reasonable lists or tokenizers can move the estimates. "
            f"{slot_5_window_count_statement} That small slot-5 window count "
            "limits slope precision and the power of the permutation "
            "comparisons; the p-values quantify sampling extremeness under "
            "label exchangeability, not freedom from corpus dependence. "
            "Finally, a temporal trend, channel gap, or cross-slot slope "
            "difference does not prove the amplification or dampening "
            "mechanism: plot, character, prompt, model, and campaign-era "
            "differences remain plausible causes.",
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
