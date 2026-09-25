"""Rendered prompt accounting and the single pre-generation window guard."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from nexus.config.seat_window import SeatWindow
    from nexus.config.settings_models import APIModelEntry, Settings


class RenderedSections(list[str]):
    """Keep renderer-owned section boundaries without parsing narrative text."""

    def __init__(self) -> None:
        super().__init__()
        self.kind = "intertitle"
        self.kinds: list[str] = []
        self.sources: dict[int, int] = {}

    def append(self, value: str) -> None:
        super().append(value)
        self.kinds.append(self.kind)

    def extend(self, values: Iterable[str]) -> None:
        for value in values:
            self.append(value)

    def append_chunk(self, value: str, chunk: dict[str, Any]) -> None:
        """Retain payload ownership for subtraction without rerendering."""
        self.sources[len(self)] = id(chunk)
        self.append(value)

    def blocks(self) -> list[tuple[str, str]]:
        """Return independently removable blocks with their joining separators."""
        return [
            (kind, ("\n" if index else "") + value)
            for index, (kind, value) in enumerate(zip(self.kinds, self))
        ]


class LocalRequestCounter:
    """Memoized local block counts plus the request's fixed system/schema cost."""

    def __init__(
        self,
        text_count: Callable[[str], int],
        overhead: int,
        *,
        system_tokens: int | None = None,
    ) -> None:
        self.text_count = text_count
        self.overhead = overhead
        self.system_tokens = overhead if system_tokens is None else system_tokens

    def __call__(self, text: str) -> int:
        return self.overhead + self.text_count(text)


def estimator_for(
    model_id: str, *, settings: Settings | None = None
) -> Callable[[str], int]:
    """Return the registered local estimate, never provider usage accounting."""
    from nexus.config import load_settings

    entry = (settings or load_settings()).model_entry(model_id)
    return local_text_counter(entry)


def estimate_request_tokens(model_id: str, request: dict[str, Any]) -> int:
    """Estimate visible request content and schemas, excluding transport options."""
    count = estimator_for(model_id)
    request = {**request, **request.get("extra_body", {})}

    def content_tokens(value: Any) -> int:
        if isinstance(value, str):
            return count(value)
        if isinstance(value, list):
            return sum(content_tokens(part) for part in value)
        if isinstance(value, dict):
            if "content" in value:
                return content_tokens(value["content"])
            if "text" in value:
                return content_tokens(value["text"])
            # Tool arguments/results and other structured content are estimates too.
            return count(json.dumps(value, ensure_ascii=False))
        return 0

    total = sum(
        content_tokens(request.get(key))
        for key in ("input", "messages", "system", "instructions")
    )
    for key in (
        "text",
        "response_format",
        "tools",
        "tool_choice",
        "thinking",
        "output_config",
    ):
        if request.get(key):
            total += count(json.dumps(request[key], ensure_ascii=False))
    return total


def validate_tokenizer_registry(entries: Iterable[APIModelEntry]) -> None:
    """Probe repository loaders outside the gateway's lightweight import path."""
    entries = list(entries)
    repositories = tuple(
        sorted(
            {
                entry.tokenizer_repository
                for entry in entries
                if entry.tokenizer_repository
            }
        )
    )
    errors = _validate_tokenizer_repositories(repositories) if repositories else {}
    for entry in entries:
        if entry.tokenizer_repository:
            if entry.tokenizer_repository in errors:
                raise ValueError(
                    _tokenizer_error(entry, errors[entry.tokenizer_repository])
                )
        else:
            # Encoding presence and validity require no inference/ML imports.
            local_text_counter(entry)


@lru_cache(maxsize=None)
def _validate_tokenizer_repositories(repositories: tuple[str, ...]) -> dict[str, str]:
    # Use the same installed interpreter and loader. No remote Python is trusted.
    # Batch the roster so each settings process imports Transformers just once.
    code = """import json, sys
from nexus.telemetry.prompt_window import _load_tokenizer
errors = {}
for repository in json.loads(sys.argv[1]):
    try:
        _load_tokenizer(repository)
    except Exception as exc:
        errors[repository] = f"{type(exc).__name__}: {exc}"
print(json.dumps(errors))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, json.dumps(repositories)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _tokenizer_error(entry: APIModelEntry, cause: object) -> str:
    return (
        f"Model {entry.id!r}: cannot load tokenizer_repository "
        f"{entry.tokenizer_repository!r} with trust_remote_code=False. "
        "Declare tokenizer_encoding with token_count_safety_margin using "
        "the Anthropic local trimming approximation pattern. "
        f"Cause: {cause}"
    )


def local_text_counter(entry: APIModelEntry) -> Callable[[str], int]:
    """Select only the explicitly declared tokenizer; cache within one assembly."""
    if entry.tokenizer_encoding:
        import tiktoken

        tokenizer = tiktoken.get_encoding(entry.tokenizer_encoding)
        return lru_cache(maxsize=None)(lambda text: len(tokenizer.encode(text)))
    if entry.tokenizer_repository:
        try:
            tokenizer = _load_tokenizer(entry.tokenizer_repository)
        except Exception as exc:
            raise ValueError(_tokenizer_error(entry, exc)) from exc
        return lru_cache(maxsize=None)(
            lambda text: len(tokenizer.encode(text, add_special_tokens=False))
        )
    raise ValueError(f"No local tokenizer declared for {entry.id!r}")


def local_request_counter(
    provider: Any,
    entry: APIModelEntry,
    text_count: Callable[[str], int],
    *,
    text_format: dict[str, Any] | None = None,
    anthropic_request: dict[str, Any] | None = None,
) -> LocalRequestCounter:
    """Estimate fixed request costs locally; only the final guard counts remotely."""
    system_tokens = text_count(provider.system_prompt or "")
    overhead = system_tokens
    if provider.usage_provider_name != "test":
        schema = text_format or {
            key: value
            for key, value in (anthropic_request or {}).items()
            if key in {"thinking", "tools", "tool_choice", "output_config"}
        }
        if schema:
            overhead += text_count(json.dumps(schema, ensure_ascii=False))
        if entry.tokenizer_repository:
            tokenizer = _load_tokenizer(entry.tokenizer_repository)
            messages = [{"role": "user", "content": ""}]
            if provider.system_prompt:
                messages.insert(
                    0, {"role": "system", "content": provider.system_prompt}
                )
            # Compatible transports enforce response_format as a grammar, not
            # additional user text. Match the final chat-template counter.
            overhead = len(
                tokenizer.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True
                )
            )
    return LocalRequestCounter(text_count, overhead, system_tokens=system_tokens)


@dataclass
class AssemblyRequest:
    """A rendered seat request whose removable costs are computed only once."""

    budget: SeatWindow
    blocks: list[tuple[str, str]]
    sources: dict[int, int]
    counter: LocalRequestCounter
    safety_margin: int = 0
    reserved_output: int = 0
    sizes: list[int] = field(init=False)
    removed: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.sizes = [self.counter.text_count(text) for _, text in self.blocks]

    @property
    def tokens(self) -> int:
        """Return the remaining rendered estimate without retokenizing."""
        return self.counter.overhead + sum(
            size for index, size in enumerate(self.sizes) if index not in self.removed
        )

    @property
    def target(self) -> int:
        """Reserve the writer response and configured tokenizer safety margin."""
        return self.budget.input_ceiling - self.reserved_output - self.safety_margin

    def drop(self, chunk: dict[str, Any], kind: str) -> None:
        """Subtract one appearance in the section being trimmed."""
        for index, source in self.sources.items():
            if (
                source == id(chunk)
                and self.blocks[index][0] == kind
                and index not in self.removed
            ):
                self.removed.add(index)
                break
        if kind == "recalled scenes" and not any(
            self.blocks[index][0] == kind and index not in self.removed
            for index in self.sources
        ):
            # This optional lane disappears entirely when its last entry drops.
            self.removed.update(
                index
                for index, (block_kind, _) in enumerate(self.blocks)
                if block_kind == kind
            )


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
    validation_notes: list[dict[str, Any]] = Field(default_factory=list)


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
    provider: Any,
    *,
    text_format: dict[str, Any] | None = None,
    anthropic_request: dict[str, Any] | None = None,
    settings_path: Path | None = None,
) -> Callable[[str], int]:
    """Return provider counting or the explicitly declared local request estimate."""
    if provider.usage_provider_name == "openai":
        return lambda prompt: count_openai_request(provider, prompt, text_format)
    if provider.usage_provider_name == "anthropic":

        def count(prompt: str) -> int:
            body = {
                key: value
                for key, value in (anthropic_request or {}).items()
                if key
                in {
                    "model",
                    "system",
                    "thinking",
                    "tools",
                    "tool_choice",
                    "output_config",
                }
            }
            body["model"] = provider.model
            body["system"] = provider.system_prompt or ""
            body["messages"] = [{"role": "user", "content": prompt}]
            result = provider.client.post(
                "/v1/messages/count_tokens", cast_to=dict[str, Any], body=body
            )
            return result["input_tokens"]

        return count
    from nexus.config import load_settings

    settings = load_settings(settings_path)
    entry = settings.model_entry(provider.model)
    if entry.tokenizer_encoding:
        # Explicit registry approximation; the admission margin is seat policy.
        return local_request_counter(
            provider,
            entry,
            estimator_for(provider.model, settings=settings),
            text_format=text_format,
            anthropic_request=anthropic_request,
        )
    tokenizer = _load_tokenizer(entry.tokenizer_repository)

    def count_local(prompt: str) -> int:
        messages = [{"role": "user", "content": prompt}]
        if provider.system_prompt:
            messages.insert(0, {"role": "system", "content": provider.system_prompt})
        return len(
            tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True
            )
        )

    return count_local


@lru_cache(maxsize=None)
def _load_tokenizer(repository: str) -> Any:
    """Load the model owner's tokenizer without loading inference weights."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(repository, trust_remote_code=False)


def measure_blocks(
    blocks: list[tuple[str, str]],
    count: LocalRequestCounter,
    *,
    exact_total: int | None = None,
) -> tuple[dict[str, int], int]:
    """Count each local block once and reconcile framing to the one full count."""
    counts: dict[str, int] = defaultdict(int)
    counts["system"] = count.overhead if exact_total is None else count.system_tokens
    for kind, text in blocks:
        counts[kind] += count.text_count(text)
    total = sum(counts.values())
    if exact_total is not None:
        # Request framing includes provider schema serialization and BPE joins.
        counts["request framing"] = exact_total - total
        total = exact_total
    return dict(counts), total
