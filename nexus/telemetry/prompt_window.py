"""Rendered prompt accounting and the single pre-generation window guard."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

from nexus.config.seat_window import SeatWindow


class RenderedSections(list[str]):
    """Keep renderer-owned section boundaries without parsing narrative text."""

    def __init__(self) -> None:
        super().__init__()
        self.kind = "intertitle"
        self.kinds: list[str] = []

    def append(self, value: str) -> None:
        super().append(value)
        self.kinds.append(self.kind)

    def extend(self, values: Iterable[str]) -> None:
        for value in values:
            self.append(value)

    def blocks(self) -> list[tuple[str, str]]:
        """Return contiguous blocks including their exact joining separators."""
        result: list[tuple[str, str]] = []
        for index, (kind, value) in enumerate(zip(self.kinds, self)):
            value = ("\n" if index else "") + value
            if result and result[-1][0] == kind:
                result[-1] = (kind, result[-1][1] + value)
            else:
                result.append((kind, value))
        return result


class PromptWindowRecord(BaseModel):
    """Counts for precisely one rendered generation attempt; no prose."""

    model_config = ConfigDict(extra="forbid")
    generation_session: str
    seat: str
    attempt: int = Field(ge=1)
    model: str
    block_tokens: dict[str, int]
    input_tokens: int = Field(ge=0)
    effective_ceiling: int = Field(gt=0)
    policy_headroom: int = Field(ge=0)
    headroom: int
    trimming: dict[str, Any] = Field(default_factory=dict)


def count_openai_request(
    provider: Any, prompt: str, text_format: dict[str, Any] | None = None
) -> int:
    """Ask the model's tokenizer to count the same system/user request."""
    messages = [{"role": "user", "content": prompt}]
    if provider.system_prompt:
        messages.insert(0, {"role": "system", "content": provider.system_prompt})
    body: dict[str, Any] = {"model": provider.model, "input": messages}
    if text_format is not None:
        body["text"] = {"format": text_format}
    result = provider.client.post(
        "/responses/input_tokens",
        cast_to=dict[str, Any],
        body=body,
    )
    count = result["input_tokens"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"Provider returned invalid input_tokens: {count!r}")
    return count


def rendered_request_counter(
    provider: Any, *, text_format: dict[str, Any] | None = None
) -> Callable[[str], int]:
    """Return the provider's exact counter; unsupported transports fail loudly."""
    if provider.usage_provider_name == "openai":
        return lambda prompt: count_openai_request(provider, prompt, text_format)
    if provider.usage_provider_name == "anthropic":

        def count(prompt: str) -> int:
            result = provider.client.messages.count_tokens(
                model=provider.model,
                system=provider.system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
            )
            return result.input_tokens

        return count
    if provider.usage_provider_name == "test":
        # TEST has no language model; this deterministic contract is for its text.
        import tiktoken

        tokenizer = tiktoken.get_encoding("o200k_base")
        return lambda prompt: len(tokenizer.encode(provider.system_prompt or "")) + len(
            tokenizer.encode(prompt)
        )
    from nexus.config import load_settings

    entry = load_settings().model_entry(provider.model)
    if entry.tokenizer_repository is None:
        raise ValueError(f"No tokenizer declared for {provider.model!r}")
    tokenizer = _load_tokenizer(entry.tokenizer_repository)
    return lambda prompt: len(
        tokenizer.encode(provider.system_prompt or "", add_special_tokens=False)
    ) + len(tokenizer.encode(prompt, add_special_tokens=False))


@lru_cache(maxsize=None)
def _load_tokenizer(repository: str) -> Any:
    """Load the model owner's tokenizer without loading inference weights."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(repository, trust_remote_code=True)


def measure_blocks(
    blocks: list[tuple[str, str]], count: Callable[[str], int]
) -> tuple[dict[str, int], int]:
    """Attribute each exact prefix increment, including message framing once."""
    counts: dict[str, int] = defaultdict(int)
    previous = count("")
    counts["system"] = previous
    prefix = ""
    for kind, text in blocks:
        prefix += text
        current = count(prefix)
        counts[kind] += current - previous
        previous = current
    return dict(counts), previous
