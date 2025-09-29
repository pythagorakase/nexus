from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from nexus.audition import AuditionEngine, AuditionRepository, ConditionSpec


@pytest.fixture(scope="module")
def audition_repo():
    repo = AuditionRepository()
    try:
        with repo.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return repo


def test_upsert_condition_round_trip(audition_repo):
    slug = f"pytest-{uuid4().hex[:8]}"
    spec = ConditionSpec(
        slug=slug,
        provider="openai",
        model="gpt-test",
        parameters={"temperature": 0.5, "max_output_tokens": 512},
        description="pytest condition",
    )
    stored = audition_repo.upsert_condition(spec)
    assert stored.id is not None

    fetched = audition_repo.get_condition_by_slug(slug)
    assert fetched is not None
    assert fetched.id == stored.id
    assert fetched.parameters["temperature"] == 0.5


def test_ingest_and_dry_run_batch(tmp_path: Path, audition_repo):
    engine = AuditionEngine(repository=audition_repo, context_dir=tmp_path)

    # Register condition
    condition_slug = f"pytest-{uuid4().hex[:8]}"
    condition = ConditionSpec(
        slug=condition_slug,
        provider="anthropic",
        model="claude-test",
        parameters={"temperature": 0.2, "max_output_tokens": 300},
    )
    engine.register_conditions([condition])

    # Create sample context package
    sample_package = {
        "metadata": {
            "chunk_id": 4242,
            "category": "Test",
            "label": "Pytest Scenario",
        },
        "storyteller_chunk": {
            "storyteller": "## Storyteller\nAlex watches the rain bead across the glass dome.",
            "user_input": "## You\nI take a breath and speak to the crew.",
            "raw_text": "## Storyteller ...",
        },
        "context_payload": {
            "user_input": "You steady yourself before the next move.",
            "warm_slice": {
                "chunks": [
                    {"text": "## Storyteller\nThe bridge hums with quiet energy."}
                ]
            },
            "entity_data": {
                "characters": [{"name": "Alex", "summary": "Player proxy."}],
                "locations": [{"name": "The Ghost", "summary": "Primary operations vessel."}],
            },
            "structured_passages": [
                {
                    "structured_table": "characters",
                    "query": "Alex",
                    "summary": "Alex leads the Ghost crew and mediates between factions.",
                }
            ],
            "retrieved_passages": {
                "results": [
                    {"text": "## Storyteller\nPreviously, Alex negotiated a fragile truce."}
                ]
            },
            "analysis": {
                "keywords": ["strategy", "trust"],
                "themes": ["Duty"],
                "expected": ["crew alignment"],
            },
        },
    }
    package_path = tmp_path / "chunk_4242_test.json"
    package_path.write_text(json.dumps(sample_package, indent=2), encoding="utf-8")

    snapshots = engine.ingest_context_packages(directory=tmp_path)
    assert len(snapshots) == 1
    assert snapshots[0].id is not None

    run = engine.run_generation_batch(
        condition_slug=condition_slug,
        limit=1,
        dry_run=True,
    )

    generations = audition_repo.list_generations_for_run(run.run_id)
    assert generations, "Expected at least one generation record"
    assert generations[0].status == "dry_run"
    assert "RECENT STORYTELLER CONTEXT" in generations[0].prompt_text
