"""Unit tests for MEMNON cross-encoder reranking helpers."""

import numpy as np
import pytest

from nexus.agents.memnon.utils.cross_encoder import CrossEncoderReranker


class FakeCrossEncoderModel:
    """Small fake that records predict calls without loading a real model."""

    def __init__(self, scores=None):
        self.calls = []
        self.scores = scores

    def predict(self, pairs, batch_size=None):
        pairs = list(pairs)
        self.calls.append({"pairs": pairs, "batch_size": batch_size})
        if self.scores is not None:
            return np.array(self.scores[: len(pairs)])
        return np.array([len(passage) / 10 for _query, passage in pairs])


class BatchFailingCrossEncoderModel(FakeCrossEncoderModel):
    """Fake that models a batch-level failure plus one bad passage."""

    def predict(self, pairs, batch_size=None):
        pairs = list(pairs)
        self.calls.append({"pairs": pairs, "batch_size": batch_size})
        if len(pairs) > 1:
            raise RuntimeError("batch failed")
        _query, passage = pairs[0]
        if passage == "bad":
            raise RuntimeError("single failed")
        return np.array([len(passage) / 10])


class WrongScoreCountCrossEncoderModel(FakeCrossEncoderModel):
    """Fake that violates the CrossEncoder score-count contract."""

    def predict(self, pairs, batch_size=None):
        pairs = list(pairs)
        self.calls.append({"pairs": pairs, "batch_size": batch_size})
        return np.array([0.1])


class KeywordCrossEncoderModel(FakeCrossEncoderModel):
    """Fake whose raw logit rises with each "needle" in the passage.

    Zero needles yields a negative logit that normalization squashes through a
    sigmoid, so the maximum normalized window score can differ from the window
    with the maximum raw logit.
    """

    def predict(self, pairs, batch_size=None):
        pairs = list(pairs)
        self.calls.append({"pairs": pairs, "batch_size": batch_size})
        return np.array([keyword_logit(passage) for _query, passage in pairs])


class WindowBatchFailingCrossEncoderModel(KeywordCrossEncoderModel):
    """Keyword fake that fails every multi-pair call and any "poison" pair."""

    def predict(self, pairs, batch_size=None):
        pairs = list(pairs)
        if len(pairs) > 1 or "poison" in pairs[0][1]:
            self.calls.append({"pairs": pairs, "batch_size": batch_size})
            raise RuntimeError("predict failed")
        return super().predict(pairs, batch_size=batch_size)


def keyword_logit(passage):
    """Raw logit the keyword fakes assign to one passage."""
    return 0.3 * passage.count("needle") - 0.1


def normalized(raw_score):
    """Mirror CrossEncoderReranker score normalization for expected values."""
    if 0 <= raw_score <= 1:
        return raw_score
    return 1 / (1 + np.exp(-raw_score))


def one_sentence_windows(sentences):
    """Windows for a passage whose sentence chunks each hold one sentence.

    With ``max_length=8`` a chunk holds at most 32 characters, so sentences of
    17+ characters each form their own chunk, and with the default overlap each
    overlap window joins two whole short sentences.
    """
    windows = []
    for index, sentence in enumerate(sentences):
        windows.append(sentence)
        if index < len(sentences) - 1:
            windows.append(f"{sentence} {sentences[index + 1]}")
    return windows


def make_reranker(model, max_length=512):
    """Build a reranker around a fake model without running __init__."""
    reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
    reranker.model = model
    reranker.max_length = max_length
    reranker.sliding_window_overlap = 128
    return reranker


def test_rerank_batch_uses_predict_batches_for_direct_scoring():
    model = FakeCrossEncoderModel()
    reranker = make_reranker(model)

    scores = reranker.rerank_batch(
        "query",
        ["a", "bb", "ccc", "dddd"],
        batch_size=2,
        use_sliding_window=False,
    )

    assert scores == pytest.approx([0.1, 0.2, 0.3, 0.4])
    assert [call["batch_size"] for call in model.calls] == [2, 2]
    assert [len(call["pairs"]) for call in model.calls] == [2, 2]


def test_rerank_batch_batches_short_passages_in_sliding_window_mode():
    model = FakeCrossEncoderModel()
    reranker = make_reranker(model)

    scores = reranker.rerank_batch(
        "query",
        ["a", "bb", "ccc"],
        batch_size=3,
        use_sliding_window=True,
    )

    assert scores == pytest.approx([0.1, 0.2, 0.3])
    assert len(model.calls) == 1
    assert model.calls[0]["batch_size"] == 3
    assert model.calls[0]["pairs"] == [
        ("query", "a"),
        ("query", "bb"),
        ("query", "ccc"),
    ]


def test_rerank_batch_preserves_order_when_long_passages_use_sliding_window():
    model = KeywordCrossEncoderModel()
    reranker = make_reranker(model, max_length=8)
    first_long = [
        "Mara checks the empty yard.",
        "Pete finds a needle there.",
        "Alex finds another needle.",
    ]
    second_long = [
        "A needle and a needle here.",
        "Three needle needle needle.",
    ]
    first_windows = one_sentence_windows(first_long)
    second_windows = one_sentence_windows(second_long)

    scores = reranker.rerank_batch(
        "query",
        ["one needle", " ".join(first_long), "needle needle", " ".join(second_long)],
        batch_size=4,
    )

    assert scores == pytest.approx(
        [
            0.2,
            max(normalized(keyword_logit(window)) for window in first_windows),
            0.5,
            max(normalized(keyword_logit(window)) for window in second_windows),
        ]
    )
    assert scores[1] == pytest.approx(0.5)
    assert scores[3] == pytest.approx(1 / (1 + np.exp(-1.4)))
    assert [call["batch_size"] for call in model.calls] == [4, 4, 4]
    assert model.calls[0]["pairs"] == [
        ("query", "one needle"),
        ("query", "needle needle"),
    ]
    assert [pair for call in model.calls[1:] for pair in call["pairs"]] == [
        ("query", window) for window in first_windows + second_windows
    ]
    assert [len(call["pairs"]) for call in model.calls[1:]] == [4, 4]


def test_rerank_batch_handles_all_long_passages_in_sliding_window_mode():
    model = KeywordCrossEncoderModel()
    reranker = make_reranker(model, max_length=8)
    sentences_by_passage = [
        ["Mara hides one needle here.", "Pete sees the quiet yard."],
        [
            "Rain falls over the yard.",
            "Alex drops a needle nearby.",
            "The needle and a needle glint.",
        ],
        ["Nothing moves in the dark.", "Still nothing moves at all."],
    ]
    windows_by_passage = [
        one_sentence_windows(sentences) for sentences in sentences_by_passage
    ]

    scores = reranker.rerank_batch(
        "query",
        [" ".join(sentences) for sentences in sentences_by_passage],
        batch_size=2,
        use_sliding_window=True,
    )

    assert scores == pytest.approx(
        [
            max(normalized(keyword_logit(window)) for window in windows)
            for windows in windows_by_passage
        ]
    )
    # Rerank batches are [first, second] (3 + 5 windows) and [third] (3 windows);
    # each batch's windows are scored in slices of batch_size with no short call.
    assert [len(call["pairs"]) for call in model.calls] == [2, 2, 2, 2, 2, 1]
    assert [call["batch_size"] for call in model.calls] == [2] * 6
    assert [pair for call in model.calls for pair in call["pairs"]] == [
        ("query", window) for windows in windows_by_passage for window in windows
    ]


def test_rerank_batch_batches_sliding_windows_across_long_passages():
    """Five long passages (45 windows) no longer issue 45 single-pair calls."""
    model = FakeCrossEncoderModel()
    reranker = make_reranker(model, max_length=8)
    sentences_by_passage = [
        [f"Passage {passage} sentence {sentence} is here." for sentence in range(5)]
        for passage in range(5)
    ]
    windows = [
        window
        for sentences in sentences_by_passage
        for window in one_sentence_windows(sentences)
    ]
    assert len(windows) == 45

    scores = reranker.rerank_batch(
        "query",
        [" ".join(sentences) for sentences in sentences_by_passage],
        batch_size=8,
        use_sliding_window=True,
    )

    assert len(scores) == 5
    assert len(model.calls) == 6
    assert [len(call["pairs"]) for call in model.calls] == [8, 8, 8, 8, 8, 5]
    assert [call["batch_size"] for call in model.calls] == [8] * 6
    assert [pair for call in model.calls for pair in call["pairs"]] == [
        ("query", window) for window in windows
    ]


def test_rerank_batch_window_scores_match_per_window_scoring():
    passages = [
        "short needle",
        " ".join(
            [
                "Mara checks the empty yard.",
                "Pete finds a needle there.",
                "Alex sees nothing else.",
            ]
        ),
        "needle " * 12 + "haystack " * 20,
        " " * 40,
        " ".join(
            [
                "One needle sits here now.",
                "Two needle and needle here.",
                "No sharp things in here.",
                "Another needle lies nearby.",
            ]
        ),
        "needle needle",
    ]
    batched_model = KeywordCrossEncoderModel()
    batched = make_reranker(batched_model, max_length=8)
    reference_model = KeywordCrossEncoderModel()
    reference = make_reranker(reference_model, max_length=8)

    scores = batched.rerank_batch("query", passages, batch_size=3)

    assert scores == pytest.approx(
        [reference.score_pair_with_sliding_window("query", p) for p in passages]
    )
    # The reference is the per-window path: one single-pair call per window.
    assert {len(call["pairs"]) for call in reference_model.calls} == {1}
    assert len(batched_model.calls) < len(reference_model.calls)
    assert {call["batch_size"] for call in batched_model.calls} == {3}
    assert max(len(call["pairs"]) for call in batched_model.calls) == 3
    assert scores[1] == pytest.approx(1 / (1 + np.exp(0.1)))
    assert scores[3] == 0.0


def test_rerank_batch_window_batch_failure_matches_per_window_scoring():
    sentences = [
        "Mara finds a needle there.",
        "The poison vial is broken.",
        "A needle and a needle glint.",
    ]
    passage = " ".join(sentences)
    windows = one_sentence_windows(sentences)
    model = WindowBatchFailingCrossEncoderModel()
    reranker = make_reranker(model, max_length=8)
    reference = make_reranker(WindowBatchFailingCrossEncoderModel(), max_length=8)

    scores = reranker.rerank_batch("query", [passage], batch_size=8)

    assert scores == pytest.approx(
        [reference.score_pair_with_sliding_window("query", passage)]
    )
    assert scores == pytest.approx([0.5])
    assert [call["batch_size"] for call in model.calls] == [8] + [None] * 5
    assert [call["pairs"] for call in model.calls] == [
        [("query", window) for window in windows]
    ] + [[("query", window)] for window in windows]


def test_rerank_batch_normalizes_raw_logits_like_score_pair():
    model = FakeCrossEncoderModel(scores=[-2.0, 0.25])
    reranker = make_reranker(model)

    scores = reranker.rerank_batch(
        "query",
        ["first", "second"],
        batch_size=2,
        use_sliding_window=False,
    )

    assert scores == pytest.approx([1 / (1 + np.exp(2.0)), 0.25])


def test_rerank_batch_falls_back_to_per_passage_on_batch_error():
    model = BatchFailingCrossEncoderModel()
    reranker = make_reranker(model)

    scores = reranker.rerank_batch(
        "query",
        ["aa", "bad", "cccc"],
        batch_size=3,
        use_sliding_window=False,
    )

    assert scores == pytest.approx([0.2, 0.0, 0.4])
    assert [call["batch_size"] for call in model.calls] == [3, None, None, None]
    assert [call["pairs"] for call in model.calls] == [
        [("query", "aa"), ("query", "bad"), ("query", "cccc")],
        [("query", "aa")],
        [("query", "bad")],
        [("query", "cccc")],
    ]


def test_rerank_batch_raises_when_cross_encoder_returns_wrong_score_count():
    model = WrongScoreCountCrossEncoderModel()
    reranker = make_reranker(model)

    with pytest.raises(ValueError, match="returned 1 scores for 2 passages"):
        reranker.rerank_batch(
            "query",
            ["first", "second"],
            batch_size=2,
            use_sliding_window=False,
        )
