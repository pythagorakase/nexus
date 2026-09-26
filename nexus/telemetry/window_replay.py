"""Provider-free counterfactual replay of recorded per-attempt prompt windows.

Every rendered generation attempt leaves a ``PromptWindowRecord`` in the usage
ledger: its exact input tokens, per-block counts, and the seat ceiling it was
admitted against. A replay keeps those recorded tokens and recomputes only the
seat window under candidate settings through the same ``resolve_seat_window``
arithmetic the trimming pass and the final guard use. Nothing is re-rendered,
re-counted, or sent to a provider, and nothing is priced: tokens only, per
Decision 9 (#858).
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from nexus.agents.lore.seat_blocks import TRIMMABLE_BLOCKS
from nexus.config.seat_window import resolve_seat_window
from nexus.config.settings_models import NATIVE_API_PROVIDERS
from nexus.telemetry.prompt_window import PromptWindowRecord
from nexus.telemetry.usage import read_prompt_windows, validate_usage_day


class NoPromptWindowsError(LookupError):
    """The usage ledger holds no rendered attempts for the requested run."""


class ReplayRow(BaseModel):
    """One recorded attempt's window under candidate settings, in tokens.

    ``capped`` marks a recorded spend bounded by the model's maximum input, so
    a zero ``headroom_delta`` may hide capacity the candidate frees. ``feasible``
    is an upper bound: trimmable counts include section headings and the
    protected newest scene, trimming drops memory from both seats jointly, and
    the approximated-tokenizer safety margin is not subtracted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generation_session: str
    seat: str
    attempt: int
    recorded_model: str
    candidate_model: str
    window: int
    recorded_input_tokens: int
    recorded_ceiling: int
    candidate_ceiling: int
    candidate_policy_headroom: int
    capped: bool
    headroom_delta: int
    overflow_tokens: int
    trimmable_tokens: int
    feasible: bool
    freed_tokens: int


def recorded_window(record: PromptWindowRecord) -> int:
    """Return the prompt spend the recorded ceiling was carved from.

    The guard admits ``min(window, model maximum input) - policy headroom``, so
    adding the recorded headroom back recovers the spend the attempt ran under.
    """
    return record.effective_ceiling + record.policy_headroom


def configured_window(settings: Mapping[str, Any], model: str) -> int:
    """Return the configured prompt spend for a model's registry provider."""
    from nexus.memory.manager import resolve_storyteller_context_window

    providers = [
        name
        for name, provider in settings["global"]["model"]["api_models"].items()
        if any(entry["id"] == model for entry in provider["models"])
    ]
    if len(providers) != 1:
        raise ValueError(f"Model {model!r} must have one registry entry")
    [provider] = providers
    # Every non-native registry provider is served over a base_url wire.
    wire = provider if provider in NATIVE_API_PROVIDERS else "local"
    return resolve_storyteller_context_window(settings, wire, provider)


def replay_record(
    record: PromptWindowRecord,
    settings: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    model: str | None = None,
    window: int | None = None,
) -> ReplayRow:
    """Recompute one attempt's seat window under candidate settings.

    ``baseline`` is the configuration the attempt was recorded under. ``model``
    replaces the recorded model and ``window`` replaces the recorded prompt
    spend. Without ``window`` each attempt keeps its recorded spend, so a
    candidate whose configured window differs from the baseline's is refused
    rather than replayed at the old spend. The recorded token counts are kept
    as measured, including under a candidate model with a different tokenizer.
    Resolution errors (an unregistered model, an output allowance above the
    model maximum) propagate unchanged.
    """
    candidate_model = record.model if model is None else model
    spend = recorded_window(record) if window is None else window
    budget = resolve_seat_window(
        settings, candidate_model, seat=record.seat, window=spend
    )
    if window is None:
        recorded = configured_window(baseline, record.model)
        candidate = configured_window(settings, candidate_model)
        if candidate != recorded:
            raise ValueError(
                f"Candidate configured window {candidate} for {candidate_model!r} "
                f"differs from the baseline's {recorded} for {record.model!r}; "
                f"the replay holds the recorded spend {spend}, so pass --window "
                "to replay a different spend"
            )
    maximum = resolve_seat_window(baseline, record.model, seat=record.seat, window=None)
    ceiling = budget.input_ceiling
    overflow = max(0, record.input_tokens - ceiling)
    # A kind absent from the record was not rendered for this attempt.
    trimmable = sum(record.block_tokens.get(kind, 0) for kind in TRIMMABLE_BLOCKS)
    return ReplayRow(
        generation_session=record.generation_session,
        seat=record.seat,
        attempt=record.attempt,
        recorded_model=record.model,
        candidate_model=candidate_model,
        window=spend,
        recorded_input_tokens=record.input_tokens,
        recorded_ceiling=record.effective_ceiling,
        candidate_ceiling=ceiling,
        candidate_policy_headroom=budget.policy_headroom,
        capped=recorded_window(record)
        >= maximum.input_ceiling + maximum.policy_headroom,
        headroom_delta=ceiling - record.effective_ceiling,
        overflow_tokens=overflow,
        trimmable_tokens=trimmable,
        feasible=overflow <= trimmable,
        freed_tokens=max(0, ceiling - record.input_tokens),
    )


def replay_run(
    run_id: str,
    day: str,
    settings: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    model: str | None = None,
    window: int | None = None,
) -> list[ReplayRow]:
    """Replay every recorded attempt of one generation run on one UTC day."""
    validate_usage_day(day)
    records = read_prompt_windows(run_id, day)
    if not records:
        raise NoPromptWindowsError(
            f"No prompt window records for run {run_id!r} on UTC day {day}"
        )
    return [
        replay_record(record, settings, baseline=baseline, model=model, window=window)
        for record in records
    ]
