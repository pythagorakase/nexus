"""Unit tests for the pure register-drift metric functions."""

from __future__ import annotations

import pytest

from scripts.register_drift_study import (
    analyze_metric,
    ceremonial_syntax_density,
    choice_list_self_similarity,
    choice_topic_recurrence,
    coinage_density,
    console_proclamation_register,
    content_word_types,
    dialogue_line_fraction,
    extract_legacy_choices,
    lexical_novelty_rate,
    mean_sentence_length,
    ordinary_least_squares_fit,
    ordinary_least_squares_slope,
    permutation_slope_difference_p_value,
    second_person_pronoun_rate,
    split_legacy_channels,
    word_tokens,
)


def test_lexical_novelty_rate_uses_types_and_does_not_mutate_history() -> None:
    history = {"brass"}

    result = lexical_novelty_rate("The brass lantern, and lantern again.", history)

    assert result == pytest.approx(2 / 3)
    assert history == {"brass"}
    assert lexical_novelty_rate("the and you", history) == 0.0


def test_coinage_density_counts_mid_sentence_title_case_spans() -> None:
    text = (
        "We invoke the Care Chain before naming the Presenting Witness. "
        "Sentence Initial words do not all count."
    )

    assert coinage_density(text) == pytest.approx(2 * 1000 / len(word_tokens(text)))
    assert coinage_density("Care Chain gathers.") == 0.0
    assert coinage_density("The Care Chain gathers.") == 0.0


def test_console_proclamation_register_counts_uppercase_dominant_lines() -> None:
    text = "ordinary line\nTHE RECORD SHALL STAND\nABCD\nUPPER lower lower"

    assert console_proclamation_register(text) == pytest.approx(
        1000 / len(word_tokens(text))
    )


def test_console_proclamation_register_is_length_normalized() -> None:
    short = "THE RECORD SHALL STAND\nquiet words wait here"
    long = short + "\nquiet words wait here softly now please stay"

    assert console_proclamation_register(short) == pytest.approx(
        2 * console_proclamation_register(long)
    )


def test_ceremonial_syntax_density_counts_all_three_signal_classes() -> None:
    text = "The record follows:\nWe bind the covenant — the witness sealed an oath."
    expected_signals = 8  # colon line, em dash, and six lexicon matches

    assert ceremonial_syntax_density(text) == pytest.approx(
        expected_signals * 1000 / len(word_tokens(text))
    )


def test_choice_list_self_similarity_is_mean_pairwise_jaccard() -> None:
    choices = [
        "Open the iron gate",
        "Open the brass gate",
        "Sing softly",
    ]

    assert choice_list_self_similarity(choices) == pytest.approx(1 / 6)
    assert choice_list_self_similarity(["Wait here"]) is None


def test_choice_topic_recurrence_uses_pooled_previous_turns() -> None:
    current = ["Open the iron gate"]
    previous = [["Open the brass gate"], ["Wait at home"]]

    assert choice_topic_recurrence(current, previous) == pytest.approx(1 / 3)
    assert choice_topic_recurrence(current, []) is None


def test_mean_sentence_length_counts_words_in_nonempty_segments() -> None:
    assert mean_sentence_length("One two three. Four five!") == pytest.approx(2.5)
    assert mean_sentence_length("...") == 0.0


def test_dialogue_line_fraction_uses_nonempty_lines() -> None:
    text = '"Hello," she said.\n\nNo dialogue here.\n“Then go,” he said.'

    assert dialogue_line_fraction(text) == pytest.approx(2 / 3)
    assert dialogue_line_fraction("\n\n") == 0.0


def test_second_person_pronoun_rate_uses_fixed_pronoun_set() -> None:
    text = "You guard your oath; it belongs to yours, so steady yourself."

    assert second_person_pronoun_rate(text) == pytest.approx(
        4 * 1000 / len(word_tokens(text))
    )


def test_drift_flavored_fixture_ranks_above_plain_fixture() -> None:
    plain = "The courier walks through the market and waits by the door."
    drift = (
        "We name the Presenting Witness beneath the Care Chain:\n"
        "THE COVENANT SHALL BIND — THE RECORD SHALL STAND."
    )

    assert coinage_density(drift) > coinage_density(plain)
    assert ceremonial_syntax_density(drift) > ceremonial_syntax_density(plain)
    assert console_proclamation_register(drift) > console_proclamation_register(plain)


def test_content_word_types_lowercases_strips_punctuation_and_stopwords() -> None:
    assert content_word_types("The Brass-chain, binds.") == {
        "brass",
        "chain",
        "binds",
    }


def test_ordinary_least_squares_slope_is_inline_and_exact() -> None:
    assert ordinary_least_squares_slope(
        [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]
    ) == pytest.approx(2.0)
    assert ordinary_least_squares_slope([(1.0, 2.0)]) is None


def test_ordinary_least_squares_fit_reports_slope_standard_error() -> None:
    slope, standard_error = ordinary_least_squares_fit(
        [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]
    )

    assert slope == pytest.approx(2.0)
    assert standard_error == pytest.approx(0.0)
    assert ordinary_least_squares_fit([(1.0, 2.0), (2.0, 4.0)]) == (
        pytest.approx(2.0),
        None,
    )


def test_analyze_metric_fits_slope_per_campaign_position() -> None:
    rows = [
        {"ordinal": ordinal, "fixture_metric": float(ordinal)}
        for ordinal in range(1, 5)
    ]

    analysis = analyze_metric(rows, "fixture_metric", window=1)

    assert analysis["slope_per_campaign"] == pytest.approx(4.0)
    assert analysis["slope_standard_error"] == pytest.approx(0.0)
    assert analysis["slope_window_count"] == 4


def test_permutation_slope_difference_detects_known_signal_deterministically() -> None:
    control = [(index / 11, 0.0) for index in range(12)]
    study = [(index / 11, 10.0 * index / 11) for index in range(12)]

    first = permutation_slope_difference_p_value(control, study)
    second = permutation_slope_difference_p_value(control, study)

    assert first == second
    assert first < 0.05


def test_permutation_slope_difference_returns_one_for_known_null() -> None:
    control = [(index / 11, index / 11) for index in range(12)]
    study = list(control)

    assert permutation_slope_difference_p_value(control, study) == 1.0


def test_split_legacy_channels_handles_multiple_alternations() -> None:
    text = """Prelude belongs to the narrator.
<!-- SCENE BREAK:
legacy marker -->
## Storyteller
First narrated section.
## You
First player move.
## Storyteller
Second narrated section.
## You
Second player move."""

    storyteller, player = split_legacy_channels(text)

    assert storyteller == (
        "Prelude belongs to the narrator.\n\n"
        "First narrated section.\nSecond narrated section."
    )
    assert player == "First player move.\nSecond player move."
    assert "SCENE BREAK" not in storyteller
    assert "## Storyteller" not in storyteller
    assert "## You" not in player


def test_split_legacy_channels_without_heading_is_all_storyteller() -> None:
    text = "<!-- SCENE BREAK: marker -->\n### A retained heading\nPlain narration."

    assert split_legacy_channels(text) == (
        "### A retained heading\nPlain narration.",
        "",
    )


def test_extract_legacy_choices_uses_final_sequential_block() -> None:
    text = """Two clues:
1. **The first clue**
2. **The second clue**

Choose:
### **1. Open the brass gate**
An intervening description.
### **2) Seal the iron door**
Another description."""

    assert extract_legacy_choices(text) == (
        "Open the brass gate",
        "Seal the iron door",
    )


def test_extract_legacy_choices_requires_two_to_six_items() -> None:
    assert extract_legacy_choices("1. Wait here") is None
    seven_items = "\n".join(f"{number}. Option {number}" for number in range(1, 8))
    assert extract_legacy_choices(seven_items) is None
