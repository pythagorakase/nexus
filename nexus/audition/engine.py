"""High-level orchestration for Apex audition generations."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:
    from scripts.api_openai import OpenAIProvider
except ImportError:  # pragma: no cover - providers optional in tests
    OpenAIProvider = None  # type: ignore

try:
    from scripts.api_anthropic import AnthropicProvider
except ImportError:  # pragma: no cover
    AnthropicProvider = None  # type: ignore

from .models import ConditionSpec, GenerationResult, GenerationRun, PromptSnapshot
from .repository import AuditionRepository, SETTINGS_PATH as DEFAULT_SETTINGS_PATH

LOGGER = logging.getLogger("nexus.apex_audition.engine")
DEFAULT_CONTEXT_DIR = Path("context_packages") / "apex_audition"


class AuditionEngine:
    """Coordinate context ingestion, condition management, and batch execution."""

    def __init__(
        self,
        *,
        repository: Optional[AuditionRepository] = None,
        settings_path: Optional[Path] = None,
        context_dir: Optional[Path] = None,
    ) -> None:
        self.settings_path = settings_path or DEFAULT_SETTINGS_PATH
        self.repository = repository or AuditionRepository(settings_path=self.settings_path)
        self.context_dir = Path(context_dir) if context_dir else DEFAULT_CONTEXT_DIR

    # ------------------------------------------------------------------
    # Context ingestion
    # ------------------------------------------------------------------
    def ingest_context_packages(
        self,
        *,
        directory: Optional[Path] = None,
        limit: Optional[int] = None,
    ) -> List[PromptSnapshot]:
        """Load audition context JSON files into the repository."""
        source_dir = Path(directory) if directory else self.context_dir
        if not source_dir.exists():
            raise FileNotFoundError(f"Context directory does not exist: {source_dir}")

        snapshots: List[PromptSnapshot] = []
        files = sorted(p for p in source_dir.glob("*.json") if p.is_file())
        if limit is not None:
            files = files[:limit]

        for path in files:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)

            meta = payload.get("metadata", {})
            context_payload = payload.get("context_payload")
            if not context_payload:
                LOGGER.warning("Skipping %s; missing context_payload", path)
                continue

            chunk_id = meta.get("chunk_id")
            if chunk_id is None:
                LOGGER.warning("Skipping %s; missing chunk_id in metadata", path)
                continue

            context_hash = self._hash_payload(context_payload)
            extra_metadata = {
                "authorial_directives": meta.get("authorial_directives") or [],
                "warm_span": meta.get("warm_span"),
                "notes": meta.get("notes"),
                "storyteller_chunk": payload.get("storyteller_chunk"),
            }

            snapshot = PromptSnapshot(
                chunk_id=int(chunk_id),
                context_sha=context_hash,
                context=context_payload,
                category=meta.get("category"),
                label=meta.get("label"),
                source_path=str(path),
                metadata=extra_metadata,
            )
            stored = self.repository.upsert_prompt(snapshot)
            snapshots.append(stored)
            LOGGER.debug("Registered context package %s (chunk %s)", stored.id, stored.chunk_id)

        return snapshots

    # ------------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------------
    def register_conditions(self, specs: Iterable[ConditionSpec]) -> List[ConditionSpec]:
        registered: List[ConditionSpec] = []
        for spec in specs:
            stored = self.repository.upsert_condition(spec)
            registered.append(stored)
            LOGGER.debug("Condition %s stored with id %s", stored.slug, stored.id)
        return registered

    # ------------------------------------------------------------------
    # Batch execution
    # ------------------------------------------------------------------
    def run_generation_batch(
        self,
        *,
        condition_slug: str,
        prompt_ids: Optional[Sequence[int]] = None,
        limit: Optional[int] = None,
        replicate_count: int = 1,
        dry_run: bool = False,
        run_label: Optional[str] = None,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> GenerationRun:
        if replicate_count < 1:
            raise ValueError("replicate_count must be >= 1")

        condition = self.repository.get_condition_by_slug(condition_slug)
        if not condition or condition.id is None:
            raise ValueError(f"Unknown condition slug: {condition_slug}")

        prompts = self.repository.list_prompts()
        if prompt_ids is not None:
            prompt_filter = set(prompt_ids)
            prompts = [p for p in prompts if p.id in prompt_filter]
        if limit is not None:
            prompts = prompts[:limit]
        if not prompts:
            raise ValueError("No prompts available for generation")

        run = GenerationRun(
            provider=condition.provider,
            storyteller_prompt=condition.system_prompt,
            created_by=created_by,
            notes=notes,
            description=run_label,
        )
        run = self.repository.create_generation_run(run)

        provider = None
        if not dry_run:
            provider = self._build_provider(condition)

        LOGGER.info(
            "Starting audition run %s with condition %s over %s prompts (replicates=%s, dry_run=%s)",
            run.run_id,
            condition.slug,
            len(prompts),
            replicate_count,
            dry_run,
        )

        for prompt in prompts:
            if prompt.id is None:
                raise ValueError(f"Prompt {prompt.chunk_id} has no database identifier; re-ingest contexts before running.")
            for replicate_index in range(replicate_count):
                prompt_text, request_payload = self._format_prompt(condition, prompt, replicate_index)
                result = GenerationResult(
                    run_id=run.run_id,
                    condition_id=condition.id,
                    prompt_id=prompt.id,  # type: ignore[arg-type]
                    replicate_index=replicate_index,
                    status="pending",
                    prompt_text=prompt_text,
                    request_payload=request_payload,
                    started_at=datetime.now(timezone.utc),
                )

                if dry_run:
                    result.status = "dry_run"
                    result.completed_at = result.started_at
                else:
                    try:
                        llm_response = provider.get_completion(prompt_text)  # type: ignore[union-attr]
                        result.status = "completed"
                        result.response_payload = self._serialize_response(llm_response)
                        result.input_tokens = getattr(llm_response, "input_tokens", 0) or 0
                        result.output_tokens = getattr(llm_response, "output_tokens", 0) or 0
                        result.cost_usd = self._estimate_cost(provider, result.input_tokens, result.output_tokens)
                        result.completed_at = datetime.now(timezone.utc)
                    except Exception as exc:  # pragma: no cover - defensive
                        LOGGER.error("Generation failed for prompt %s replicate %s: %s", prompt.id, replicate_index, exc)
                        result.status = "error"
                        result.error_message = str(exc)
                        result.completed_at = datetime.now(timezone.utc)

                self.repository.record_generation(result)

        return run

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _hash_payload(payload: Dict[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _build_provider(self, condition: ConditionSpec):
        params = dict(condition.parameters)
        temperature = params.get("temperature", 0.7)
        max_tokens = params.get("max_output_tokens", params.get("max_tokens", 2048))

        if condition.provider.lower() == "openai":
            if OpenAIProvider is None:
                raise RuntimeError("OpenAI provider not available. Install dependencies or configure differently.")
            provider = OpenAIProvider(
                model=condition.model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=condition.system_prompt,
                reasoning_effort=params.get("reasoning_effort"),
            )
            return provider
        if condition.provider.lower() == "anthropic":
            if AnthropicProvider is None:
                raise RuntimeError("Anthropic provider not available. Install dependencies or configure differently.")
            provider = AnthropicProvider(
                model=condition.model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=condition.system_prompt,
                top_p=params.get("top_p"),
                top_k=params.get("top_k"),
            )
            return provider
        raise ValueError(f"Unsupported provider: {condition.provider}")

    def _format_prompt(
        self,
        condition: ConditionSpec,
        prompt: PromptSnapshot,
        replicate_index: int,
    ) -> tuple[str, Dict[str, object]]:
        data = prompt.context
        sections: List[str] = []

        sections.append("=== CHUNK METADATA ===")
        sections.append(
            json.dumps(
                {
                    "chunk_id": prompt.chunk_id,
                    "category": prompt.category,
                    "label": prompt.label,
                    "replicate": replicate_index,
                    "condition": condition.slug,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        meta_payload = prompt.metadata if isinstance(prompt.metadata, dict) else {}
        storyteller_chunk = meta_payload.get("storyteller_chunk") if meta_payload else None
        if storyteller_chunk:
            sections.append("\n=== TARGET STORYTELLER CHUNK ===")
            sections.append(storyteller_chunk.get("storyteller", ""))

        sections.append("\n=== USER INPUT ===")
        user_input = data.get("user_input") or ""
        if isinstance(user_input, str):
            sections.append(user_input.strip())
        else:
            sections.append(json.dumps(user_input, indent=2, ensure_ascii=False))

        warm_slice = data.get("warm_slice") or {}
        chunks = warm_slice.get("chunks") if isinstance(warm_slice, dict) else None
        if chunks:
            sections.append("\n=== RECENT STORYTELLER CONTEXT ===")
            for chunk in chunks:
                text = chunk.get("text") if isinstance(chunk, dict) else None
                if text:
                    sections.append(text)

        entity_data = data.get("entity_data") or {}
        if isinstance(entity_data, dict) and any(entity_data.values()):
            sections.append("\n=== ENTITY DOSSIER ===")
            characters = entity_data.get("characters") or []
            if characters:
                sections.append("Characters:")
                for entry in characters:
                    if isinstance(entry, dict):
                        name = entry.get("name") or entry.get("alias") or "(unnamed)"
                        summary = entry.get("summary") or entry.get("background") or ""
                        sections.append(f"- {name}: {summary}")
            locations = entity_data.get("locations") or []
            if locations:
                sections.append("Locations:")
                for entry in locations:
                    if isinstance(entry, dict):
                        name = entry.get("name") or entry.get("alias") or "(unnamed)"
                        summary = entry.get("summary") or entry.get("description") or ""
                        sections.append(f"- {name}: {summary}")

        structured_passages = data.get("structured_passages") or []
        if structured_passages:
            sections.append("\n=== STRUCTURED SUMMARIES ===")
            for entry in structured_passages:
                if not isinstance(entry, dict):
                    continue
                label = entry.get("query") or entry.get("structured_table")
                summary = entry.get("summary") or entry.get("text")
                if summary:
                    sections.append(f"- {label}: {summary}")

        retrieved_passages = data.get("contextual_augmentation") or data.get("retrieved_passages")
        if isinstance(retrieved_passages, dict):
            passages = retrieved_passages.get("results")
        else:
            passages = retrieved_passages
        if passages:
            sections.append("\n=== HISTORICAL PASSAGES ===")
            for passage in passages[:10]:
                if isinstance(passage, dict):
                    text_value = passage.get("text")
                    if text_value:
                        sections.append(text_value)

        analysis = data.get("analysis") or {}
        keywords = [k for k in analysis.get("keywords", []) if isinstance(k, str)]
        themes = [t for t in analysis.get("themes", []) if isinstance(t, str)]
        expected = analysis.get("expected")
        if keywords or themes or expected:
            sections.append("\n=== ANALYSIS NOTES ===")
            if keywords:
                sections.append("Keywords: " + ", ".join(keywords))
            if themes:
                sections.append("Themes: " + ", ".join(themes))
            if expected:
                if isinstance(expected, dict):
                    section_bits = []
                    for key, value in expected.items():
                        if isinstance(value, list):
                            section_bits.append(f"{key}: {', '.join(str(v) for v in value)}")
                    if section_bits:
                        sections.append("Expected focus: " + " | ".join(section_bits))
                elif isinstance(expected, list):
                    sections.append("Expected focus: " + ", ".join(str(item) for item in expected))

        sections.append("\n=== INSTRUCTIONS ===")
        sections.append(
            "Continue the story from the perspective of the Storyteller, honoring continuity, tone, and user agency."
        )
        sections.append(
            "Leave decision prompts for the user when the scene naturally branches. Keep outputs around 400-600 words unless the context implies otherwise."
        )

        prompt_text = "\n".join(section for section in sections if section)
        request_payload = {
            "prompt_id": prompt.id,
            "chunk_id": prompt.chunk_id,
            "replicate_index": replicate_index,
            "condition": condition.slug,
        }
        return prompt_text, request_payload

    @staticmethod
    def _serialize_response(response) -> Dict[str, object]:
        if response is None:
            return {}
        payload: Dict[str, object] = {
            "content": getattr(response, "content", None),
            "model": getattr(response, "model", None),
            "input_tokens": getattr(response, "input_tokens", None),
            "output_tokens": getattr(response, "output_tokens", None),
        }
        raw = getattr(response, "raw_response", None)
        if raw is not None:
            try:
                if hasattr(raw, "model_dump"):
                    payload["raw"] = raw.model_dump()
                elif hasattr(raw, "to_dict"):
                    payload["raw"] = raw.to_dict()
                elif hasattr(raw, "__dict__"):
                    payload["raw"] = dict(raw.__dict__)
            except Exception:  # pragma: no cover - best effort
                payload["raw"] = "<unserializable>"
        return payload

    @staticmethod
    def _estimate_cost(provider, input_tokens: int, output_tokens: int) -> float:
        try:
            input_rate = provider.get_input_token_cost()
            output_rate = provider.get_output_token_cost()
        except Exception:  # pragma: no cover - some providers might not implement
            return 0.0
        return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


__all__ = ["AuditionEngine"]
