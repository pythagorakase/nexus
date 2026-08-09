"""Unit contracts for the private storyteller conspiracy channel."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import re
import tomllib
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
    hydrate_skald_turn,
    skald_gaia_lenient_schema,
    skald_gaia_strict_text_format,
    skald_wire_lenient_schema,
    skald_wire_strict_text_format,
    skald_writer_lenient_schema,
    skald_writer_strict_text_format,
)
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.lore_adapter import compute_raw_text, response_to_incubator
from nexus.config.loader import load_settings_as_dict
from nexus.config.settings_models import Settings, StorytellerCorrespondenceSettings
from nexus.memory import correspondence
from nexus.memory.correspondence import (
    CorrespondenceContext,
    CorrespondenceDigestWire,
    CorrespondenceExchange,
    GeneratedCorrespondence,
    _render_digest_budget,
    build_digest_length_validator,
    build_letter_length_validator,
    correspondence_settings,
    load_compaction_system_prompt,
    plan_correspondence_compaction,
)


PROMPTS_DIR = Path(__file__).parents[1] / "prompts"


def _exchange(chunk_id: int) -> CorrespondenceExchange:
    return CorrespondenceExchange(
        chunk_id=chunk_id,
        letters=(
            ("writer", f"writer letter {chunk_id}"),
            ("gaia", f"gaia reply {chunk_id}"),
        ),
    )


def test_compaction_prompt_keeps_digest_budget_as_a_placeholder() -> None:
    """The prompt source carries the token slot, never a copied numeric budget."""

    prompt = (PROMPTS_DIR / "correspondence_compaction.md").read_text()

    assert prompt.count("{{MAX_DIGEST_TOKENS}}") == 1
    assert re.search(r"\b\d[\d_,]*[\s-]tokens?\b", prompt) is None
    assert re.search(r"\btokens?\b[^.\n]{0,24}\b\d[\d_,]*\b", prompt) is None


def test_compaction_prompt_loader_renders_configured_budget() -> None:
    """The real loader replaces the digest token-budget placeholder."""

    prompt = load_compaction_system_prompt(max_digest_tokens=12345)

    assert "12345 tokens" in prompt
    assert "{{MAX_DIGEST_TOKENS}}" not in prompt


def test_digest_budget_render_fails_when_placeholder_is_missing() -> None:
    """Removing the digest budget slot fails loudly with its source name."""

    source = "correspondence_compaction.md"
    with pytest.raises(ValueError, match=re.escape(source)):
        _render_digest_budget(
            "The complete digest has no configured bound.",
            max_digest_tokens=12345,
            source=source,
        )


def test_compaction_prompt_and_validator_share_real_digest_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real settings bind the same digest budget to prompt and validator."""

    settings = load_settings_as_dict(PROMPTS_DIR.parent / "nexus.toml")
    configured = correspondence_settings(settings)
    expected = int(configured["max_digest_tokens"])
    prompt = load_compaction_system_prompt(max_digest_tokens=expected)
    validator = build_digest_length_validator(max_digest_tokens=expected)
    output = CorrespondenceDigestWire(digest="Complete digest.")
    monkeypatch.setattr(
        correspondence,
        "calculate_chunk_tokens",
        lambda _text: expected + 1,
    )

    assert prompt.count(str(expected)) == 1
    assert "{{MAX_DIGEST_TOKENS}}" not in prompt
    with pytest.raises(ModelRetry, match=rf"limit {expected}\)"):
        asyncio.run(validator(None, output))


@pytest.mark.parametrize(
    ("strict_format", "lenient_schema"),
    [
        (skald_writer_strict_text_format, skald_writer_lenient_schema),
        (skald_gaia_strict_text_format, skald_gaia_lenient_schema),
        (skald_wire_strict_text_format, skald_wire_lenient_schema),
    ],
)
def test_letter_compiles_required_nullable_strict_and_required_lenient(
    strict_format: Any,
    lenient_schema: Any,
) -> None:
    """OpenAI can emit null grammatically; Pydantic/repair rejects null or omission."""

    strict_schema = strict_format()["schema"]
    assert "letter" in strict_schema["required"]
    assert {"type": "null"} in strict_schema["properties"]["letter"]["anyOf"]

    lenient = lenient_schema()
    assert "letter" in lenient["required"]
    assert lenient["properties"]["letter"]["type"] == "string"


@pytest.mark.parametrize(
    "wire_type,payload",
    [
        (
            SkaldWriterWire,
            {"narrative": "A.", "choices": ["B.", "C."], "letter": None},
        ),
        (SkaldGaiaWire, {"letter": None}),
        (
            SkaldTurnWire,
            {"narrative": "A.", "choices": ["B.", "C."], "letter": None},
        ),
    ],
)
def test_null_letters_fail_semantic_validation(
    wire_type: Any,
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError, match="letter cannot be null"):
        wire_type.model_validate(payload)


def test_gaia_receives_writer_letter_verbatim() -> None:
    letter = "Do not name the informer.\nPreserve this exact second line."
    writer = SkaldWriterWire(
        narrative="The shutters close.",
        choices=["Wait.", "Leave."],
        letter=letter,
    )

    prompt = LogonUtility._format_gaia_user_prompt("TURN", writer)

    assert prompt.endswith(letter)
    assert "FINISHED WRITER LETTER (VERBATIM, PRIVATE)" in prompt


def test_private_artifacts_never_enter_public_response_or_raw_text() -> None:
    secrets = GeneratedCorrespondence(
        writer_letter="The mayor is the informant.",
        gaia_letter="I will seed the ledger two scenes from now.",
    )
    wire = SkaldTurnWire(
        narrative="Rain darkens the mayor's empty chair.",
        choices=["Inspect the desk.", "Leave quietly."],
        letter=secrets.writer_letter,
    )

    response = hydrate_skald_turn(wire)
    public_dump = response.model_dump(mode="json")
    incubator = response_to_incubator(
        response,
        parent_chunk_id=4,
        user_text="Inspect the room.",
        session_id="private-test",
        correspondence=secrets,
    )
    raw_text = compute_raw_text(
        incubator["storyteller_text"],
        incubator["choice_object"],
        incubator["choice_text"],
    )

    assert "letter" not in public_dump
    assert "correspondence" not in public_dump
    assert secrets.writer_letter not in raw_text
    assert secrets.gaia_letter not in raw_text
    assert incubator["correspondence_writer_letter"] == secrets.writer_letter
    assert incubator["correspondence_gaia_letter"] == secrets.gaia_letter


def test_hysteresis_compacts_only_after_ceiling_and_keeps_floor_plus_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ten = CorrespondenceContext(
        digest=None,
        compacted_through_chunk_id=None,
        exchanges=tuple(_exchange(chunk_id) for chunk_id in range(1, 11)),
    )
    monkeypatch.setattr(
        correspondence, "read_accepted_correspondence", lambda _cur: ten
    )
    assert (
        plan_correspondence_compaction(
            object(),
            accepting_chunk_id=10,
            floor_turns=5,
            ceiling_turns=10,
        )
        is None
    )

    eleven = CorrespondenceContext(
        digest=None,
        compacted_through_chunk_id=None,
        exchanges=tuple(_exchange(chunk_id) for chunk_id in range(1, 12)),
    )
    monkeypatch.setattr(
        correspondence,
        "read_accepted_correspondence",
        lambda _cur: eleven,
    )
    plan = plan_correspondence_compaction(
        object(),
        accepting_chunk_id=11,
        floor_turns=5,
        ceiling_turns=10,
    )

    assert plan is not None
    assert [item.chunk_id for item in plan.aging_exchanges] == [1, 2, 3, 4, 5]
    assert [item.chunk_id for item in plan.recent_exchanges] == [6, 7, 8, 9, 10, 11]
    assert plan.compacted_through_chunk_id == 5
    for exchange in plan.aging_exchanges:
        assert len(exchange.letters) == 2


def test_context_render_is_complete_and_token_cap_fails_loudly() -> None:
    context = CorrespondenceContext(
        digest="LIVE: protect the unspent bell reveal.",
        compacted_through_chunk_id=4,
        exchanges=(_exchange(5),),
    )

    rendered = context.render(max_tokens=1000)

    assert "protect the unspent bell reveal" in rendered
    assert "writer letter 5" in rendered
    assert "gaia reply 5" in rendered
    with pytest.raises(RuntimeError, match="should-never-fire invariant"):
        context.render(max_tokens=1)


def test_letter_and_digest_limits_are_repairable_semantic_errors() -> None:
    secret = "SECRET-WORD " * 20
    letter_validator = build_letter_length_validator(max_letter_tokens=2)
    digest_validator = build_digest_length_validator(max_digest_tokens=2)

    letter_outputs = [
        SkaldWriterWire(
            narrative="Public.",
            choices=["Wait.", "Leave."],
            letter=secret,
        ),
        SkaldGaiaWire(letter=secret),
        SkaldTurnWire(
            narrative="Public.",
            choices=["Wait.", "Leave."],
            letter=secret,
        ),
    ]
    for output in letter_outputs:
        with pytest.raises(ModelRetry, match="letter is too long") as letter_error:
            asyncio.run(
                letter_validator(
                    None,
                    output,
                )
            )
        assert secret not in str(letter_error.value)

    with pytest.raises(ModelRetry, match="digest is too long") as digest_error:
        asyncio.run(
            digest_validator(
                None,
                CorrespondenceDigestWire(digest=secret),
            )
        )

    assert secret not in str(digest_error.value)


def test_correspondence_settings_are_mandatory_bounded_and_use_role_ref() -> None:
    valid = {
        "floor_turns": 5,
        "ceiling_turns": 10,
        "compaction_model": "@openai.gaia",
        "max_letter_tokens": 300,
        "max_digest_tokens": 2000,
        "max_rendered_tokens": 12000,
    }
    with pytest.raises(ValidationError, match="floor_turns"):
        StorytellerCorrespondenceSettings(
            **{**valid, "floor_turns": 10, "ceiling_turns": 10}
        )
    with pytest.raises(ValidationError, match="at most 80%"):
        StorytellerCorrespondenceSettings(**{**valid, "max_letter_tokens": 400})
    with pytest.raises(ValidationError, match="plus exchange headings"):
        StorytellerCorrespondenceSettings(**{**valid, "max_rendered_tokens": 8200})

    with Path("nexus.toml").open("rb") as handle:
        raw = tomllib.load(handle)
    configured = raw["storyteller"]["correspondence"]
    assert configured["compaction_model"].startswith("@")
    assert (
        configured["ceiling_turns"] * 2 * configured["max_letter_tokens"]
        + configured["max_digest_tokens"]
        == 8000
    )

    missing = copy.deepcopy(raw)
    missing.pop("storyteller")
    with pytest.raises(
        ValidationError,
        match=r"missing required \[storyteller\.correspondence\] section",
    ):
        Settings.model_validate(missing)
