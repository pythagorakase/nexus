"""Shared model and seat arithmetic for rendered generation requests."""

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from nexus.config.settings_models import APIModelEntry, SeatWindowPolicy


class SeatWindow(BaseModel):
    """Resolved input limit and its explicit policy headroom."""

    model_config = ConfigDict(frozen=True)
    model: str
    seat: str
    input_ceiling: int
    policy_headroom: int
    max_output_tokens: int


def resolve_seat_window(
    settings: Mapping[str, Any], model: str, *, seat: str, window: int
) -> SeatWindow:
    """Apply a seat policy to an owner's prompt spend without double reserving."""
    apex = settings["apex"]
    raw = apex["gaia"] if seat == "gaia" else apex
    policy = SeatWindowPolicy.model_validate(
        {key: raw[key] for key in SeatWindowPolicy.model_fields}
    )
    return resolve_model_window(
        settings, model, seat=seat, window=window, policy=policy
    )


def resolve_model_window(
    settings: Mapping[str, Any],
    model: str,
    *,
    seat: str,
    window: int | None,
    policy: SeatWindowPolicy,
) -> SeatWindow:
    """Apply the shared registry limits and headroom to a consumer policy."""
    registry = settings["global"]["model"]["api_models"]
    entries = [
        (name, entry)
        for name, provider in registry.items()
        for entry in provider["models"]
        if entry["id"] == model
    ]
    if len(entries) != 1:
        raise ValueError(f"Model {model!r} must have one registry entry")
    provider_name, declaration = entries[0]
    entry = APIModelEntry.model_validate(declaration).require_window_capabilities()
    assert entry.max_output_tokens is not None
    assert entry.context_window is not None
    if policy.max_output_tokens > entry.max_output_tokens:
        raise ValueError(
            f"Seat {seat!r} output allowance {policy.max_output_tokens} exceeds model maximum {entry.max_output_tokens}"
        )
    if (
        entry.reasoning_accounting == "inside_output"
        and policy.reasoning_reserve_tokens > policy.max_output_tokens
    ):
        raise ValueError(
            f"Seat {seat!r} reasoning reserve exceeds its output allowance"
        )
    outside = (
        policy.reasoning_reserve_tokens
        if entry.reasoning_accounting == "outside_output"
        else 0
    )
    context_window = entry.context_window
    if provider_name == "local":
        from nexus.config.local_window import local_context_window

        context_window = local_context_window(settings)
        if context_window > entry.context_window:
            raise ValueError(
                f"Local serving context_window {context_window} exceeds model architectural window {entry.context_window}"
            )
    available_input = context_window - policy.max_output_tokens - outside
    maximum_input = (
        min(entry.max_input_tokens, available_input)
        if entry.max_input_tokens is not None
        else available_input
    )
    ceiling = min(window, maximum_input) if window is not None else maximum_input
    headroom = policy.response_reserve_tokens
    if ceiling <= headroom:
        raise ValueError(
            f"Seat {seat!r} input ceiling {ceiling} cannot hold policy headroom {headroom}"
        )
    return SeatWindow(
        model=model,
        seat=seat,
        input_ceiling=ceiling - headroom,
        policy_headroom=headroom,
        max_output_tokens=policy.max_output_tokens,
    )


def resolve_summary_window(
    settings: Mapping[str, Any], model: str, *, mode: str
) -> SeatWindow:
    """Resolve a summary input budget, including the registry safety margin."""
    from nexus.config.settings_models import SummariesSettings

    if mode not in {"episode", "season"}:
        raise ValueError(f"Unsupported summary mode: {mode!r}")
    summaries = SummariesSettings.model_validate(settings["summaries"])
    policy = SeatWindowPolicy(
        max_output_tokens=getattr(summaries, f"{mode}_max_output_tokens"),
        **summaries.window.model_dump(),
    )
    budget = resolve_model_window(
        settings, model, seat="summaries", window=None, policy=policy
    )
    entry = next(
        entry
        for provider in settings["global"]["model"]["api_models"].values()
        for entry in provider["models"]
        if entry["id"] == model
    )
    margin = APIModelEntry.model_validate(entry).token_count_safety_margin
    if budget.input_ceiling <= margin:
        raise ValueError(
            f"Summary model {model!r} has no input budget after safety margin {margin}"
        )
    return budget.model_copy(update={"input_ceiling": budget.input_ceiling - margin})
