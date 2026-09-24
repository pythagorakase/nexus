"""Terminal summary response failures that require an operator change."""

from __future__ import annotations

import json
from typing import Any


class SummaryInputTooLong(RuntimeError):
    """The assembled summary input exceeds the configured model's capacity."""


class SummaryOutputTruncated(RuntimeError):
    """The provider exhausted or interrupted a summary's output allowance."""


def check_summary_response(response: Any, *, mode: str, max_output_tokens: int) -> None:
    """Reject truncated Responses or Chat output before attempting JSON parsing."""
    if response.object == "chat.completion":
        if not any(choice.finish_reason == "length" for choice in response.choices):
            return
        reason = "finish_reason=length"
    else:
        if response.status != "incomplete":
            return
        details = response.incomplete_details
        reason = f"incomplete_details.reason={details.reason if details else None}"
    usage = response.usage.model_dump(mode="json") if response.usage else None
    raise SummaryOutputTruncated(
        f"{mode} summary incomplete: configured allowance={max_output_tokens} "
        f"output tokens; {reason}; "
        f"usage={json.dumps(usage, sort_keys=True)}"
    )
