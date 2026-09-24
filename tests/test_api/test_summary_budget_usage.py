"""Real registry arithmetic, TEST exchanges, and disposable PostgreSQL proof."""

from contextlib import closing
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import tomlkit

from nexus.api.native_structured_output import openai_response_text_format
from nexus.api.summary_errors import SummaryInputTooLong
from nexus.api.summary_triggers import SummaryTask, schedule_summary_generation
from nexus.config import load_settings_as_dict
from nexus.config.seat_window import resolve_seat_window, resolve_summary_window
from nexus.jobs.scheduler import SlotScheduler
from nexus.telemetry.attempt_manifest import (
    finish_attempt,
    identity_hash,
    manifest_scope,
    record_response,
    start_attempt,
)
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import summarize_usage, usage_context
from scripts.api_openai import OpenAIProvider
from tests.pg_fixtures import connect, disposable_slot_database
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401


class SummaryPayload(BaseModel):
    """Strict summary contract used by the real local TEST endpoint."""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(description="Narrative summary of the supplied interval.")


@pytest.mark.parametrize("mode", ["episode", "season"])
def test_summary_budget_matches_real_registry_seat_window(mode):
    """Use the checked-in config and the same policy on both consumer paths."""
    settings = load_settings_as_dict()
    model = settings["summaries"]["model"]
    summaries = settings["summaries"]
    seat_settings = deepcopy(settings)
    seat_settings["apex"].update(summaries["window"])
    output = summaries[f"{mode}_max_output_tokens"]
    seat_settings["apex"]["max_output_tokens"] = output
    entry = next(
        entry
        for provider in settings["global"]["model"]["api_models"].values()
        for entry in provider["models"]
        if entry["id"] == model
    )
    seat = resolve_seat_window(
        seat_settings, model, seat="skald", window=entry["context_window"]
    )
    summary = resolve_summary_window(settings, model, mode=mode)
    assert summary.input_ceiling == (
        seat.input_ceiling - entry["token_count_safety_margin"]
    )
    print(f"{mode} registry budget: {summary.model_dump()}")


def test_responses_create_preserves_parse_wire_kwargs(mock_openai_server):
    """Compare actual SDK parse/create HTTP bodies, including strict schema."""
    provider = OpenAIProvider(
        model="TEST",
        api_key="test-key",
        base_url=mock_openai_server,
        system_prompt="Summarize the interval.",
        temperature=0.2,
        max_tokens=8000,
        structured_output_retries=0,
    )
    requests = []
    provider.client._client.event_hooks["request"].append(
        lambda request: requests.append(json.loads(request.content))
    )
    try:
        params = provider._build_native_structured_request_params(
            "The travelers arrive.", SummaryPayload, prompt_cache_key="summary-proof"
        )
        legacy = deepcopy(params)
        del legacy["text"]
        legacy["text_format"] = SummaryPayload
        before = provider.client.responses.parse(**legacy)
        after, _ = provider.get_structured_completion(
            "The travelers arrive.", SummaryPayload, prompt_cache_key="summary-proof"
        )
        assert after == before.output_parsed
        assert requests[0] == requests[1]
        assert params["text"]["format"] == requests[1]["text"]["format"]
        wire = requests[1]["text"]["format"]
        assert wire["strict"] is True
        assert wire["schema"]["additionalProperties"] is False
        assert wire["schema"]["required"] == ["summary"]
        print("Responses parse/create request bodies identical; strict schema retained")
    finally:
        provider.client.close()


@pytest.mark.requires_postgres
@pytest.mark.parametrize("mode", ["episode", "season"])
def test_summary_budget_fails_job_before_test_provider_call(
    monkeypatch, tmp_path, mock_openai_server, mode
):
    """Scheduler failure on a populated save_04 clone is terminal without spend."""
    path = configure_test(tmp_path, mock_openai_server, monkeypatch)
    config = tomlkit.parse(path.read_text())
    # Keep the registry's real TEST input capacity; reserve it down to a small
    # positive budget so the clone's actual narrative is oversized.
    config["summaries"]["window"]["response_reserve_tokens"] = 871999
    config["summaries"]["model"] = "TEST"
    config["runtime"]["scheduler"]["summaries"]["max_attempts"] = 3
    path.write_text(tomlkit.dumps(config))
    with disposable_slot_database(
        "qa640_937_budget", source_db="save_04", include_data=True
    ) as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            for table in (
                "correspondence_compaction_jobs",
                "narrative_parent_embedding_claims",
                "narrative_embedding_jobs",
                "narrative_summary_jobs",
                "relationship_milestone_queue",
            ):
                cur.execute(f"DELETE FROM {table}")
            cur.execute(
                "UPDATE orrery_resolutions SET promotion_status='promoted' "
                "WHERE promotion_status='pending'"
            )
            cur.execute("UPDATE episodes SET summary=NULL WHERE season=1 AND episode=2")
            cur.execute("UPDATE seasons SET summary=NULL WHERE id=1")
            schedule_summary_generation(
                [SummaryTask(mode, 1, 2 if mode == "episode" else None)],
                cur=cur,
                session_id=None,
            )
        scheduler = SlotScheduler(4, dbname=dbname, settings=load_settings_as_dict())
        with pytest.raises(SummaryInputTooLong, match="model 'TEST'") as caught:
            scheduler.run_pass(
                narration_limit=0, experience_limit=0, maturation_limit=0
            )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT state::text, attempts, error_class, last_error, lease_until "
                "FROM narrative_summary_jobs"
            )
            row = cur.fetchone()
        assert row == ("failed", 1, "SummaryInputTooLong", str(caught.value), None)
        assert "input_budget=1" in str(caught.value)
        assert summarize_usage(usage_dir=tmp_path / "usage")["events"] == []
        # The server's access log proves there was no exchange, even one whose
        # ledger recorder might be broken. Readiness only calls /health.
        assert "POST /v1/responses" not in (tmp_path / "mock_openai.log").read_text()
        print(f"Budget job proof: {row}")


@pytest.mark.requires_postgres
@pytest.mark.parametrize("response_check", [False, True])
def test_schema_invalid_usage_and_manifest_survive_validation(
    tmp_path, mock_openai_server, response_check
):
    """The real SDK raises ValidationError after raw-response manifest capture."""
    with disposable_slot_database("qa640_938_usage") as dbname:
        session = str(uuid4())
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_generation_sessions (session_id, operation, status) "
                "VALUES (%s, 'continue', 'initiated')",
                (session,),
            )
        record = PromptWindowRecord(
            generation_session=session,
            seat="summaries",
            attempt=1,
            model="TEST",
            block_tokens={"story": 1},
            input_tokens=1,
            effective_ceiling=100,
            policy_headroom=0,
            headroom=99,
        )
        provider = OpenAIProvider(
            model="TEST",
            api_key="test-key",
            base_url=mock_openai_server,
            usage_seat="summaries",
            usage_provider_name="test",
            structured_output_retries=0,
        )
        responses = []

        def capture(response):
            record_response(record, response)
            responses.append(response)

        provider.attempt_manifest_response = capture
        provider.attempt_manifest_result = partial(finish_attempt, record)
        if response_check:
            from nexus.api.summary_errors import check_summary_response

            provider.response_check = partial(
                check_summary_response, mode="episode", max_output_tokens=8000
            )
        prompt = "[TEST:SCHEMA_INVALID] Summarize the interval."
        try:
            with (
                manifest_scope(lambda: connect(dbname)),
                usage_context(seat="summaries", slot=4, run_id=session),
            ):
                start_attempt(
                    record,
                    blocks=[],
                    system_prompt="",
                    prompt=prompt,
                    settings=load_settings_as_dict(),
                    wire_schema=openai_response_text_format(SummaryPayload),
                )
                with pytest.raises(ValidationError):
                    provider.get_structured_completion(prompt, SummaryPayload)
        finally:
            provider.client.close()
        events = summarize_usage(usage_dir=tmp_path / "usage")["events"]
        assert len(events) == len(responses) == 1
        event = events[0]
        assert event["request_id"] == responses[0].id
        assert event["input_tokens"] == 1000
        assert event["output_tokens"] == 800
        assert event["total_tokens"] == 1800
        assert event["outcome"] == "rejected_validation"
        assert event["run_id"] == session
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT response_sha256, provider_outcome FROM generation_attempt_manifests "
                "WHERE generation_session_id=%s",
                (session,),
            )
            manifest = cur.fetchone()
        assert manifest == (
            identity_hash(responses[0].model_dump(mode="json")),
            "rejected_validation",
        )
        print(
            f"Recorded usage proof: {json.dumps(event, sort_keys=True)}; manifest={manifest}"
        )
