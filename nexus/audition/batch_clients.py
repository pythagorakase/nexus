"""Batch API clients for OpenAI and Anthropic."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None

try:
    import requests
except ImportError:
    requests = None

LOGGER = logging.getLogger("nexus.apex_audition.batch_clients")


class BatchStatus(Enum):
    """Universal batch status across providers."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class BatchRequest:
    """A single request in a batch."""
    custom_id: str
    prompt_id: int
    replicate_index: int
    prompt_text: str
    model: str
    temperature: Optional[float]
    max_tokens: int
    system_prompt: Optional[str] = None
    enable_cache: bool = True
    # OpenAI-specific parameters
    reasoning_effort: Optional[str] = None
    max_output_tokens: Optional[int] = None
    top_p: Optional[float] = None
    min_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    repetition_penalty: Optional[float] = None
    cache_key: Optional[str] = None  # Chunk-based cache key for prompt caching
    # Anthropic-specific parameters
    thinking_enabled: bool = False
    thinking_budget_tokens: Optional[int] = None
    # Lane tracking
    lane_id: Optional[str] = None


@dataclass
class BatchResult:
    """Result of a single request from a batch."""
    custom_id: str
    status: str  # "succeeded" or "failed"
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class BatchJob:
    """Metadata for a submitted batch job."""
    batch_id: str
    provider: str
    status: BatchStatus
    total_requests: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    results_url: Optional[str] = None
    request_counts: Optional[Dict[str, int]] = None


class AnthropicBatchClient:
    """Client for Anthropic Message Batch API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize client with API key from 1Password if not provided."""
        self.api_key = api_key or self._get_api_key()
        if anthropic:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        else:
            raise ImportError("anthropic package not installed")

    def _get_api_key(self) -> str:
        """Get Anthropic API key from environment or 1Password CLI."""
        # First, check if API key is already in environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return api_key

        # Otherwise, fetch from 1Password
        try:
            result = subprocess.run(
                ["op", "read", "op://API/Anthropic/api key"],
                capture_output=True,
                text=True,
                check=True
            )
            api_key = result.stdout.strip()
            if not api_key:
                raise ValueError("Empty API key returned from 1Password")
            return api_key
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise ValueError(
                f"Failed to retrieve Anthropic API key from 1Password: {e}. "
                "Ensure 1Password CLI is installed and you're signed in."
            )

    def create_batch(self, requests: List[BatchRequest]) -> str:
        """
        Create a message batch.

        Args:
            requests: List of batch requests

        Returns:
            Batch ID

        Raises:
            ValueError: If batch exceeds limits (100k requests or 256MB)
        """
        if len(requests) > 100_000:
            raise ValueError(f"Batch size {len(requests)} exceeds limit of 100,000 requests")

        # Format requests for Anthropic API
        batch_requests = []
        for req in requests:
            # Build user message content with cache control
            if req.enable_cache:
                # Structure prompt as content block with cache control
                # Estimate tokens (rough approximation: 1 token ~= 4 characters)
                estimated_tokens = len(req.prompt_text) // 4
                user_content = [
                    {
                        "type": "text",
                        "text": req.prompt_text,
                        "cache_control": {"type": "ephemeral"} if estimated_tokens > 1024 else None
                    }
                ]
                # Remove None cache_control if not needed
                if not user_content[0]["cache_control"]:
                    del user_content[0]["cache_control"]
            else:
                user_content = req.prompt_text

            # Build message params
            params: Dict[str, Any] = {
                "model": req.model,
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
                "messages": [{"role": "user", "content": user_content}]
            }

            if req.top_p is not None:
                params["top_p"] = req.top_p

            # Add extended thinking parameters if enabled
            if req.thinking_enabled:
                params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": req.thinking_budget_tokens
                }

            # Add system prompt with cache control if enabled
            if req.system_prompt:
                if req.enable_cache:
                    params["system"] = [
                        {
                            "type": "text",
                            "text": req.system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                else:
                    params["system"] = req.system_prompt

            batch_requests.append({
                "custom_id": req.custom_id,
                "params": params
            })

        # Estimate size
        batch_json = json.dumps({"requests": batch_requests})
        size_mb = len(batch_json.encode('utf-8')) / (1024 * 1024)
        if size_mb > 256:
            raise ValueError(f"Batch size {size_mb:.2f}MB exceeds limit of 256MB")

        LOGGER.info(f"Creating Anthropic batch with {len(requests)} requests ({size_mb:.2f}MB)")

        # Submit batch
        response = self.client.messages.batches.create(requests=batch_requests)

        LOGGER.info(f"Batch created: {response.id} (status: {response.processing_status})")
        return response.id

    def get_status(self, batch_id: str) -> BatchJob:
        """
        Get batch status.

        Args:
            batch_id: Batch ID

        Returns:
            BatchJob with current status
        """
        response = self.client.messages.batches.retrieve(batch_id)

        # Map Anthropic status to universal status
        status_map = {
            "in_progress": BatchStatus.IN_PROGRESS,
            "canceling": BatchStatus.IN_PROGRESS,
            "ended": BatchStatus.COMPLETED,
        }
        status = status_map.get(response.processing_status, BatchStatus.PENDING)

        # Check if any requests failed
        if status == BatchStatus.COMPLETED and response.request_counts.errored > 0:
            LOGGER.warning(f"Batch {batch_id} completed with {response.request_counts.errored} errors")

        # Parse timestamps
        created_at_str = response.created_at.replace('Z', '+00:00') if isinstance(response.created_at, str) else response.created_at.isoformat()
        ended_at_str = response.ended_at.replace('Z', '+00:00') if response.ended_at and isinstance(response.ended_at, str) else None

        return BatchJob(
            batch_id=batch_id,
            provider="anthropic",
            status=status,
            total_requests=sum([
                response.request_counts.processing,
                response.request_counts.succeeded,
                response.request_counts.errored,
                response.request_counts.canceled,
                response.request_counts.expired
            ]),
            created_at=datetime.fromisoformat(created_at_str),
            completed_at=datetime.fromisoformat(ended_at_str) if ended_at_str else None,
            results_url=response.results_url,
            request_counts={
                "processing": response.request_counts.processing,
                "succeeded": response.request_counts.succeeded,
                "errored": response.request_counts.errored,
                "canceled": response.request_counts.canceled,
                "expired": response.request_counts.expired
            }
        )

    def retrieve_results(self, batch_job: BatchJob) -> List[BatchResult]:
        """
        Retrieve results from a completed batch.

        Args:
            batch_job: Completed batch job with results_url

        Returns:
            List of batch results
        """
        if not batch_job.results_url:
            raise ValueError(f"Batch {batch_job.batch_id} has no results_url (status: {batch_job.status})")

        LOGGER.info(f"Retrieving results from {batch_job.results_url}")

        # Download results (JSONL format)
        response = requests.get(
            batch_job.results_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
        )
        response.raise_for_status()

        # Explicitly decode as UTF-8 to avoid encoding issues
        # (response.text can misdetect encoding, causing mojibake with emojis and special chars)
        content = response.content.decode('utf-8')

        # Parse JSONL
        results = []
        for line in content.strip().split('\n'):
            if not line:
                continue
            result_data = json.loads(line)

            if result_data["result"]["type"] == "succeeded":
                results.append(BatchResult(
                    custom_id=result_data["custom_id"],
                    status="succeeded",
                    response=result_data["result"]["message"]
                ))
            else:
                # Error case
                error_msg = result_data["result"].get("error", {}).get("message", "Unknown error")
                results.append(BatchResult(
                    custom_id=result_data["custom_id"],
                    status="failed",
                    error=error_msg
                ))

        LOGGER.info(f"Retrieved {len(results)} results from batch {batch_job.batch_id}")
        return results

    def cancel_batch(self, batch_id: str) -> None:
        """Cancel a batch."""
        self.client.messages.batches.cancel(batch_id)
        LOGGER.info(f"Cancelled batch {batch_id}")


class OpenAIBatchClient:
    """Client for OpenAI Batch API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize client with API key from 1Password if not provided."""
        self.api_key = api_key or self._get_api_key()
        if openai:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            raise ImportError("openai package not installed")

    def _get_api_key(self) -> str:
        """Get OpenAI API key from 1Password CLI."""
        try:
            result = subprocess.run(
                ["op", "item", "get", "tyrupcepa4wluec7sou4e7mkza", "--fields", "api key", "--reveal"],
                capture_output=True,
                text=True,
                check=True
            )
            api_key = result.stdout.strip()
            if not api_key:
                raise ValueError("Empty API key returned from 1Password")
            return api_key
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise ValueError(
                f"Failed to retrieve OpenAI API key from 1Password: {e}. "
                "Ensure 1Password CLI is installed and you're signed in."
            )

    def create_batch(self, requests: List[BatchRequest], output_dir: Path) -> str:
        """
        Create a batch.

        Args:
            requests: List of batch requests
            output_dir: Directory to write input JSONL file

        Returns:
            Batch ID
        """
        # Create JSONL input file
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / f"batch_input_{int(time.time())}.jsonl"

        with open(input_file, 'w') as f:
            for req in requests:
                # Use unified /v1/responses endpoint for all OpenAI models
                # Build input messages
                input_messages = [{"role": "user", "content": req.prompt_text}]
                if req.system_prompt:
                    input_messages.insert(0, {"role": "system", "content": req.system_prompt})

                # Build request body
                body: Dict[str, Any] = {
                    "model": req.model,
                    "input": input_messages,
                    "max_output_tokens": req.max_output_tokens or req.max_tokens
                }

                # Add cache key for prompt caching so all lanes share the stored prompt
                if req.cache_key:
                    body["prompt_cache_key"] = req.cache_key

                # Add temperature if provided (GPT-4o and other non-reasoning models)
                if req.temperature is not None:
                    body["temperature"] = req.temperature

                if req.top_p is not None:
                    body["top_p"] = req.top_p
                if req.min_p is not None:
                    body["min_p"] = req.min_p
                if req.frequency_penalty is not None:
                    body["frequency_penalty"] = req.frequency_penalty
                if req.presence_penalty is not None:
                    body["presence_penalty"] = req.presence_penalty
                if req.repetition_penalty is not None:
                    body["repetition_penalty"] = req.repetition_penalty

                # Add reasoning effort if provided (GPT-5, o3)
                if req.reasoning_effort:
                    body["reasoning"] = {"effort": req.reasoning_effort}

                batch_request = {
                    "custom_id": req.custom_id,
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": body
                }
                f.write(json.dumps(batch_request) + '\n')

        LOGGER.info(f"Created batch input file: {input_file} ({len(requests)} requests)")

        # Upload file
        with open(input_file, 'rb') as f:
            upload_response = self.client.files.create(
                file=f,
                purpose="batch"
            )

        LOGGER.info(f"Uploaded file: {upload_response.id}")

        # Create batch (all OpenAI models use /v1/responses)
        batch_response = self.client.batches.create(
            input_file_id=upload_response.id,
            endpoint="/v1/responses",
            completion_window="24h"
        )

        LOGGER.info(f"Batch created: {batch_response.id} (status: {batch_response.status})")
        return batch_response.id

    def get_status(self, batch_id: str) -> BatchJob:
        """Get batch status."""
        response = self.client.batches.retrieve(batch_id)

        # Map OpenAI status to universal status
        status_map = {
            "validating": BatchStatus.PENDING,
            "in_progress": BatchStatus.IN_PROGRESS,
            "finalizing": BatchStatus.IN_PROGRESS,
            "completed": BatchStatus.COMPLETED,
            "failed": BatchStatus.FAILED,
            "expired": BatchStatus.EXPIRED,
            "cancelling": BatchStatus.IN_PROGRESS,
            "cancelled": BatchStatus.CANCELLED
        }
        status = status_map.get(response.status, BatchStatus.PENDING)

        return BatchJob(
            batch_id=batch_id,
            provider="openai",
            status=status,
            total_requests=response.request_counts.total,
            created_at=datetime.fromtimestamp(response.created_at, tz=timezone.utc),
            completed_at=datetime.fromtimestamp(response.completed_at, tz=timezone.utc) if response.completed_at else None,
            results_url=response.output_file_id,
            request_counts={
                "completed": response.request_counts.completed,
                "failed": response.request_counts.failed
            }
        )

    def retrieve_results(self, batch_job: BatchJob) -> List[BatchResult]:
        """Retrieve results from a completed batch."""
        if not batch_job.results_url:
            raise ValueError(f"Batch {batch_job.batch_id} has no output_file_id")

        LOGGER.info(f"Retrieving results from file {batch_job.results_url}")

        # Download output file
        file_response = self.client.files.content(batch_job.results_url)
        content = file_response.read().decode('utf-8')

        # Parse JSONL
        results = []
        for line in content.strip().split('\n'):
            if not line:
                continue
            result_data = json.loads(line)

            response_payload = result_data.get("response")
            if response_payload and response_payload.get("status_code") == 200:
                body = response_payload.get("body")
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:  # pragma: no cover - defensive
                        LOGGER.warning(
                            "Failed to decode OpenAI batch response body for %s; leaving as raw string",
                            result_data.get("custom_id"),
                        )

                results.append(BatchResult(
                    custom_id=result_data["custom_id"],
                    status="succeeded",
                    response=body
                ))
            else:
                # Start with top-level error (generic)
                error_msg = result_data.get("error", {}).get("message", "Unknown error")
                # Override with structured error from response body if available (more specific)
                if response_payload:
                    error_body = response_payload.get("body")
                    if isinstance(error_body, str):
                        try:
                            error_body = json.loads(error_body)
                        except json.JSONDecodeError:  # pragma: no cover - defensive
                            pass
                    if isinstance(error_body, dict):
                        error_field = error_body.get("error")
                        if isinstance(error_field, dict):
                            error_msg = error_field.get("message", error_msg)
                results.append(BatchResult(
                    custom_id=result_data["custom_id"],
                    status="failed",
                    error=error_msg
                ))

        LOGGER.info(f"Retrieved {len(results)} results from batch {batch_job.batch_id}")
        return results

    def cancel_batch(self, batch_id: str) -> None:
        """Cancel a batch."""
        self.client.batches.cancel(batch_id)
        LOGGER.info(f"Cancelled batch {batch_id}")


__all__ = [
    "BatchStatus",
    "BatchRequest",
    "BatchResult",
    "BatchJob",
    "AnthropicBatchClient",
    "OpenAIBatchClient",
]
