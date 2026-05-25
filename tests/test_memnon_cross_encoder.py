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
    model = FakeCrossEncoderModel()
    reranker = make_reranker(model, max_length=2)
    long_passage_calls = []

    def fake_sliding_window_score(query, passage):
        long_passage_calls.append((query, passage))
        return 0.9

    reranker.score_pair_with_sliding_window = fake_sliding_window_score

    scores = reranker.rerank_batch(
        "query",
        ["aa", "this passage is long", "bbb"],
        batch_size=3,
    )

    assert scores == pytest.approx([0.2, 0.9, 0.3])
    assert long_passage_calls == [("query", "this passage is long")]
    assert len(model.calls) == 1
    assert model.calls[0]["pairs"] == [("query", "aa"), ("query", "bbb")]


def test_rerank_batch_handles_all_long_passages_in_sliding_window_mode():
    model = FakeCrossEncoderModel()
    reranker = make_reranker(model, max_length=2)
    long_passage_calls = []

    def fake_sliding_window_score(query, passage):
        long_passage_calls.append((query, passage))
        return len(long_passage_calls) / 10

    reranker.score_pair_with_sliding_window = fake_sliding_window_score

    scores = reranker.rerank_batch(
        "query",
        ["first long passage", "second long passage"],
        batch_size=2,
        use_sliding_window=True,
    )

    assert scores == pytest.approx([0.1, 0.2])
    assert long_passage_calls == [
        ("query", "first long passage"),
        ("query", "second long passage"),
    ]
    assert model.calls == []


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
