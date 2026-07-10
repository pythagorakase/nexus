"""API key status, storage, and verification endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from nexus.config.loader import load_settings
from nexus.config.settings_models import NATIVE_API_PROVIDERS
from nexus.util.secret_manager import MissingSecretError, get_secret, set_secret

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


@dataclass(frozen=True)
class SecretProvider:
    """A UI-visible provider and its canonical secret-store account."""

    provider: str
    account: str
    base_url: str | None = None


class SecretStatus(BaseModel):
    """Browser-safe secret metadata; never includes credential material."""

    provider: str
    account: str
    present: bool
    last4: str | None


class SecretWriteRequest(BaseModel):
    """Request body accepted by the secret writer."""

    model_config = ConfigDict(extra="forbid")

    key: str


class SecretVerification(BaseModel):
    """Result of a live provider credentials check."""

    provider: str
    verified: bool
    detail: str


def get_secret_providers() -> list[SecretProvider]:
    """Derive writable providers and accounts from the active model registry.

    Native SDK providers use their provider name as the account. Visible
    OpenAI-compatible providers participate only when ``api_key_secret``
    declares an account; keyless and UI-hidden providers stay out of the API.
    """
    registry = load_settings().global_.model.api_models
    providers: list[SecretProvider] = []
    for provider, entry in registry.items():
        if not entry.ui_visible:
            continue
        if provider in NATIVE_API_PROVIDERS:
            account = provider
        elif entry.api_key_secret:
            account = entry.api_key_secret
        else:
            continue
        providers.append(
            SecretProvider(
                provider=provider,
                account=account.lower(),
                base_url=entry.base_url,
            )
        )
    return providers


def _provider_or_404(provider: str) -> SecretProvider:
    """Return a registry-derived provider or reject an unknown route value."""
    for candidate in get_secret_providers():
        if candidate.provider == provider:
            return candidate
    raise HTTPException(status_code=404, detail="Unknown secret provider.")


def _status_for(provider: SecretProvider) -> SecretStatus:
    """Read the masked status for one provider."""
    try:
        value = get_secret(provider.account)
    except MissingSecretError:
        # MissingSecretError is the reader's public absence contract. This is
        # the one endpoint where missing credentials are expected first-run
        # state rather than an exceptional response.
        return SecretStatus(
            provider=provider.provider,
            account=provider.account,
            present=False,
            last4=None,
        )
    return SecretStatus(
        provider=provider.provider,
        account=provider.account,
        present=True,
        last4=value[-4:],
    )


def _failure_detail(exc: Exception) -> str:
    """Describe a verification failure without rendering provider messages."""
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    detail = type(exc).__name__
    if status_code is not None:
        detail += f" (status {status_code})"
    return detail


def _verify_provider(provider: SecretProvider, key: str) -> None:
    """Make one bounded, read-only models-list call with ``key``."""
    if provider.provider == "anthropic":
        import anthropic

        with anthropic.Anthropic(
            api_key=key,
            max_retries=0,
            timeout=10.0,
        ) as client:
            client.models.list(limit=1)
        return

    if provider.provider == "openai" or provider.base_url is not None:
        import openai

        kwargs: dict[str, Any] = {
            "api_key": key,
            "max_retries": 0,
            "timeout": 10.0,
        }
        if provider.base_url is not None:
            kwargs["base_url"] = provider.base_url
        with openai.OpenAI(**kwargs) as client:
            client.models.list()
        return

    raise RuntimeError("No verification path exists for this native provider.")


@router.get("/status", response_model=list[SecretStatus])
def get_secrets_status() -> list[SecretStatus]:
    """Return masked status rows for all UI-visible keyed providers."""
    return [_status_for(provider) for provider in get_secret_providers()]


@router.put("/{provider}", response_model=SecretStatus)
def put_secret(provider: str, body: SecretWriteRequest) -> SecretStatus:
    """Store or replace one registry-approved provider key."""
    selected = _provider_or_404(provider)
    try:
        set_secret(selected.account, body.key)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="API key must not be empty or whitespace.",
        ) from None
    return _status_for(selected)


@router.post("/{provider}/verify", response_model=SecretVerification)
def verify_secret(provider: str) -> SecretVerification:
    """Verify one stored key against the provider's real models endpoint."""
    selected = _provider_or_404(provider)
    try:
        key = get_secret(selected.account)
        _verify_provider(selected, key)
    except Exception as exc:  # noqa: BLE001 - verification failures are results
        return SecretVerification(
            provider=selected.provider,
            verified=False,
            detail=_failure_detail(exc),
        )
    return SecretVerification(
        provider=selected.provider,
        verified=True,
        detail="Models endpoint reachable.",
    )
