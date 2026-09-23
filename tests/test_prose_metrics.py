"""Real save_01 excerpts; no database or provider substitutes."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from scripts.database_targets import evaluation_dbname, metrics_dbname
from scripts.qa_shift.prose_metrics import (
    adapt_chunk,
    legacy_sections,
    load_config,
    main,
    measure,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/prose_metrics/save_01_excerpts.json").read_text()
)


def chunk(chunk_id: int) -> dict:
    """Adapt a verbatim save_01 excerpt with explicit absent telemetry."""
    return adapt_chunk(
        dict(
            id=chunk_id,
            raw_text=FIXTURES[str(chunk_id)],
            storyteller_text=None,
            choice_text=None,
            choice_object=None,
            world_time=None,
            setting_places=[],
        ),
        load_config(),
    )


def test_observed_legacy_variants() -> None:
    """Chunks 101/1425 lack You, 686/1383 lack Storyteller, 771 has whitespace."""
    for chunk_id in (1, 2, 351, 651, 771, 951):
        assert chunk(chunk_id)["story"]
        assert chunk(chunk_id)["player"]
    for chunk_id in (101, 1425):
        assert chunk(chunk_id)["story"]
        assert not chunk(chunk_id)["player"]
    for chunk_id in (686, 1383):
        assert not chunk(chunk_id)["story"]
        assert chunk(chunk_id)["player"]
    assert chunk(686)["player"].startswith("Before beginning the lesson")
    assert "## You" not in chunk(2)["story"]


def test_real_menus_and_not_applicable() -> None:
    """Chunks 1/2 have decimal menus; 351/651 have keycaps; 951 has none."""
    assert len(chunk(1)["choices"]) == 3
    assert chunk(2)["choices"][0].startswith("Accept immediately")
    assert len(chunk(351)["choices"]) == 4
    assert len(chunk(651)["choices"]) == 4
    assert chunk(951)["choices"] is None
    result = measure([chunk(951)], load_config())
    assert result["choices"]["status"] == "not_applicable"
    assert result["choices"]["mean_count"] is None
    assert result["choices"]["count_distribution"] is None
    assert result["choices"]["speech_act_share"] is None


def test_real_excerpt_text_metrics() -> None:
    """Verbatim contiguous paragraph excerpts from save_01 chunk 951."""
    real = chunk(951)
    real["story"] = "A pause.  \n\nThen, from the intercom, **calm and precise:**"
    assert real["story"] in FIXTURES["951"]
    result = measure([real], load_config())
    assert result["rhythm"]["paragraphs_per_chunk"] == 2
    assert result["rhythm"]["median_words_per_paragraph"] == 4.5
    assert result["rhythm"]["single_sentence_paragraph_share"] == 1
    assert result["rhythm"]["short_sentence_share"] == 0.5
    assert result["words_per_chunk"]["mean"] == 9
    assert result["words_per_chunk"]["sd"] == 0
    # Final question is bold in the original; Markdown must not hide it.
    result = measure([chunk(951)], load_config())
    assert result["closers"]["question_rate"] == 1
    assert result["negation"]["formal_counts"]["does not"] == 1
    assert result["negation"]["contractions"] == 1
    assert result["negation"]["contraction_ratio"] == 0.5


@pytest.mark.parametrize("chunk_id,paragraphs", [(651, 38), (1425, 53)])
def test_markdown_preserves_real_excerpt_paragraphs(
    chunk_id: int, paragraphs: int
) -> None:
    """Measure the full excerpts to isolate decoration cleanup from menu removal."""
    cfg = load_config()
    real = chunk(chunk_id)
    real["story"], _ = legacy_sections(FIXTURES[str(chunk_id)], chunk_id, cfg)
    assert measure([real], cfg)["rhythm"]["paragraph_count"] == paragraphs


def test_recovered_menus_are_excluded_from_narrative_metrics() -> None:
    """Real option lines affect choices only; prose before/after them survives."""
    cfg = load_config().model_copy(update={"motif_min_chunks": 1})
    real = chunk(2)
    result = measure([real], cfg)
    assert result["words_per_chunk"]["mean"] == 173
    assert result["choices"]["total"] == 3
    assert real["story"].endswith("What’s the move, corpo?")
    assert "you don't ask" not in {m["ngram"] for m in result["motifs"]}
    assert result["negation"]["contractions"] == 1
    result = measure([chunk(651)], cfg)
    assert result["closers"]["what_do_you_count"] == 1
    assert result["rhythm"]["paragraph_count"] == 34
    assert result["choices"]["total"] == 4
    story, _ = legacy_sections(FIXTURES["951"], 951, cfg)
    assert chunk(951)["story"] == story


def test_real_excerpt_motifs_and_missing_telemetry() -> None:
    """Chunk occurrence counts must not become token occurrence counts."""
    cfg = load_config().model_copy(update={"motif_min_chunks": 2})
    result = measure([chunk(951), chunk(951), chunk(686)], cfg)
    motif = next(m for m in result["motifs"] if m["ngram"] == "a pause then")
    assert motif["chunks"] == 2
    assert result["narrative_chunks"] == 2
    assert result["player_only_chunk_ids"] == [686]
    assert result["world_minutes_per_turn"]["mean"] is None
    assert result["world_minutes_per_turn"]["missing_pairs"] == 2
    assert result["same_setting_streak"]["max"] is None
    assert result["same_setting_streak"]["missing_place_chunks"] == 3


def test_telemetry_breaks_at_missing_or_ambiguous_places() -> None:
    """Only adjacent known timestamps and unique settings have measurements."""
    rows = [chunk(951) for _ in range(5)]
    start = datetime(2073, 10, 13, tzinfo=timezone.utc)
    for index, row in enumerate(rows):
        row["world_time"] = start + timedelta(minutes=index * 5)
        row["setting_places"] = [1]
    rows[2]["setting_places"] = [1, 2]
    rows[2]["world_time"] = None
    result = measure(rows, load_config())
    assert result["same_setting_streak"]["max"] == 2
    assert result["same_setting_streak"]["mean"] == 2
    assert result["same_setting_streak"]["ambiguous_place_chunks"] == 1
    assert result["world_minutes_per_turn"]["mean"] == 5
    assert result["world_minutes_per_turn"]["count"] == 2


def test_unknown_sections_fail_loudly() -> None:
    with pytest.raises(ValueError, match="unsupported legacy"):
        legacy_sections(
            FIXTURES["951"]
            .replace("## Storyteller", "## Narrator")
            .replace("## You", "## Player"),
            951,
            load_config(),
        )
    with pytest.raises(ValueError, match="unknown legacy"):
        legacy_sections(FIXTURES["951"] + "\n## Unknown\ntext", 951, load_config())


@pytest.mark.parametrize(
    "name", ["save_01", "NEXUS_template", "ref_", "qa640_", "ref_x;drop", "other"]
)
def test_mutation_target_guard(name: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        evaluation_dbname(name)
    result = subprocess.run(
        [sys.executable, "scripts/migrate.py", "--dbname", name],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Database must match" in result.stderr


@pytest.mark.parametrize("name", ["ref_codex_bakeoff_2026_07", "qa640_metrics"])
def test_evaluation_target_guard(name: str) -> None:
    assert evaluation_dbname(name) == name
    assert metrics_dbname(name) == name
    assert metrics_dbname("save_01") == "save_01"


def test_invalid_config() -> None:
    with pytest.raises(ValidationError):
        type(load_config()).model_validate(
            {**load_config().model_dump(), "motif_min_chunks": 0}
        )


def test_comparison_handles_na(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    a = {
        "schema_version": 1,
        "corpus": "a",
        "config": {},
        "metrics": {"closer": 0.2, "choices": None},
    }
    b = {**a, "corpus": "b", "metrics": {"closer": 0.5, "choices": 4}}
    paths = [tmp_path / "a.json", tmp_path / "b.json"]
    for path, value in zip(paths, [a, b]):
        path.write_text(json.dumps(value))
    assert main(["--compare", *map(str, paths)]) == 0
    output = capsys.readouterr().out
    assert "+0.300000" in output
    assert "N/A (None -> 4)" in output
