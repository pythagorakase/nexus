"""Unit tests for Pass 2 retrieval coverage instrumentation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Dict

from nexus.memory import ContextMemoryManager
from nexus.memory.retrieval_coverage import audit_retrieval_coverage
from scripts.report_retrieval_coverage import format_retrieval_coverage_report


class FakeMemnon:
    """MEMNON test double with retrieval but no live database path."""

    def query_memory(
        self, query: str, k: int = 5, use_hybrid: bool = True
    ) -> Dict[str, object]:
        return {"results": [{"chunk_id": 9001, "text": "A compact retrieval result."}]}


def test_handle_user_input_skips_retrieval_coverage_without_database(
    caplog,
) -> None:
    manager = ContextMemoryManager(
        {"memory": {"skip_simple_choices": False}},
        memnon=FakeMemnon(),
    )
    manager.handle_storyteller_response(
        narrative="The briefing ends.",
        warm_slice=[{"chunk_id": 1, "text": "Baseline."}],
        token_usage={"total_available": 1000, "warm_slice": 10},
    )

    update = manager.handle_user_input(
        "Continue the briefing.",
        turn_id="unit-turn",
    )

    assert update.retrieved_chunks
    assert not [
        record
        for record in caplog.records
        if record.levelname == "ERROR"
        and "Retrieval coverage audit failed" in record.getMessage()
    ]


def test_attempted_retrieval_coverage_failure_logs_and_returns(caplog) -> None:
    class FailingEngine:
        def connect(self) -> None:
            return None

        def begin(self) -> None:
            raise RuntimeError("audit database unavailable")

    retriever = SimpleNamespace(
        memnon=SimpleNamespace(
            db_manager=SimpleNamespace(engine=FailingEngine()),
        )
    )

    audit_retrieval_coverage(
        incremental_retriever=retriever,
        detector=SimpleNamespace(),
        turn_id="failed-audit-turn",
        user_input="Ask Alex.",
        raw_result_count=1,
        kept_chunks=[{"chunk_id": 42}],
        kept_tokens=3,
        available_budget=100,
    )

    errors = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "ERROR"
        and "Retrieval coverage audit failed" in record.getMessage()
    ]
    assert len(errors) == 1
    assert "failed-audit-turn" in errors[0]
    assert "Ask Alex." in errors[0]
    assert "kept_chunk_ids': [42]" in errors[0]


def test_format_retrieval_coverage_report_shows_decision_measures() -> None:
    rows = [
        {
            "user_input": "Ask Alex about Wren.",
            "detected_entities": [
                {"kind": "character", "id": 1, "name": "Alex"},
                {"kind": "character", "id": 106, "name": "Wren"},
            ],
            "gap_entities": [{"kind": "character", "id": 106, "name": "Wren"}],
        },
        {
            "user_input": "Continue without changing the plan or naming anyone.",
            "detected_entities": [],
            "gap_entities": [],
        },
    ]

    report = format_retrieval_coverage_report(2, rows)

    assert "Total turns audited: 2" in report
    assert "Detection rate: 50.0% (1/2)" in report
    assert "character   50.0% (1/2)" in report
    assert "character:Wren [106] 1 gap(s) / 1 detection(s) (100.0%)" in report
    assert "1-4 words    100.0% (1/1); audited turns=1" in report
