"""Terminal summary response failures that require an operator change."""

from __future__ import annotations

import json
from typing import Any


class SummaryOutputTruncated(RuntimeError):
    """The provider exhausted or interrupted a summary's output allowance."""


def check_summary_response(response: Any, *, mode: str, max_output_tokens: int) -> None:
    """Reject an incomplete Responses result before attempting JSON parsing."""
    if response.status != "incomplete":
        return
    details = response.incomplete_details
    reason = details.reason if details is not None else None
    usage = response.usage.model_dump(mode="json") if response.usage else None
    raise SummaryOutputTruncated(
        f"{mode} summary incomplete: configured allowance={max_output_tokens} "
        f"output tokens; incomplete_details.reason={reason}; "
        f"usage={json.dumps(usage, sort_keys=True)}"
    )
