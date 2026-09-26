"""API key status, storage, and verification endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from nexus.config.loader import load_settings
from nexus.config.settings_models import (
    NATIVE_API_PROVIDERS,
    ProviderModels,
    Settings,
)
from nexus.config.story_model import AUXILIARY_SEATS, SeatResolution, resolve_seat
from nexus.util.secret_manager import MissingSecretError, get_secret, set_secret

router = APIRouter(prefix="/api/secrets", tags=["secrets"])

# Seats that make a provider key required. ir_eval judgment is offline
# evaluation tooling, and global.model.default_model is display-only with no
# generation consumer, so neither marks a key required. The UI labels exactly
# these seats (SEAT_LABELS in ui/client/src/components/nexus/SettingsPane.tsx).
_NON_GENERATION_SEATS = frozenset(
    {"ir_eval.judgment.model", "global.model.default_model"}
)
REQUIRED_SECRET_SEATS: tuple[str, ...] = (
    "skald",
    "gaia",
    "wizard",
    *(seat for seat in AUXILIARY_SEATS if seat not in _NON_GENERATION_SEATS),
)


@dataclass(frozen=True)
class SecretProvider:
    """A UI-visible provider and its canonical secret-store account."""

    provider: str
    account: str
    base_url: str | None = None


class SecretRequirement(BaseModel):
    """One model seat whose resolved provider reads this account's key."""

    seat: str
    model: str


class SecretStatus(BaseModel):
    """Browser-safe secret metadata; never includes credential material."""

    provider: str
    account: str
    present: bool
    last4: str | None
    required: bool
    required_by: list[SecretRequirement]


class SecretWriteRequest(BaseModel):
    """Request body accepted by the secret writer."""

    model_config = ConfigDict(extra="forbid")

    key: str


class SecretVerification(BaseModel):
    """Result of a live provider credentials check."""

    provider: str
    verified: bool
    detail: str


def _secret_account(provider: str, entry: ProviderModels) -> str | None:
    """Return the secret-store account ``provider`` reads, or None if keyless.

    Native SDK providers use their provider name as the account; other
    providers read the account their ``api_key_secret`` declares.
    """
    if provider in NATIVE_API_PROVIDERS:
        return provider
    if entry.api_key_secret:
        return entry.api_key_secret.lower()
    return None


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
        account = _secret_account(provider, entry)
        if account is None:
            continue
        providers.append(
            SecretProvider(
                provider=provider,
                account=account,
                base_url=entry.base_url,
            )
        )
    return providers


def required_secret_accounts(settings: Settings) -> dict[str, list[SeatResolution]]:
    """Map each secret account the configured model seats read to those seats.

    Every seat in ``REQUIRED_SECRET_SEATS`` resolves through ``resolve_seat``
    without a story, so the answer reflects the repository defaults and the
    player's wizard preference rather than any one slot's pins. Seats on
    keyless providers need no account. Resolution errors propagate.
    """
    registry = settings.global_.model.api_models
    required: dict[str, list[SeatResolution]] = {}
    for seat in REQUIRED_SECRET_SEATS:
        resolution = resolve_seat(seat, settings=settings)
        account = _secret_account(resolution.provider, registry[resolution.provider])
        if account is not None:
            required.setdefault(account, []).append(resolution)
    return required


def _provider_or_404(provider: str) -> SecretProvider:
    """Return a registry-derived provider or reject an unknown route value."""
    for candidate in get_secret_providers():
        if candidate.provider == provider:
            return candidate
    raise HTTPException(status_code=404, detail="Unknown secret provider.")


def _status_for(
    provider: SecretProvider, requirements: list[SeatResolution]
) -> SecretStatus:
    """Read the masked status for one provider and attach its seat needs."""
    try:
        value: str | None = get_secret(provider.account)
    except MissingSecretError:
        # MissingSecretError is the reader's public absence contract. This is
        # the one endpoint where missing credentials are expected first-run
        # state rather than an exceptional response.
        value = None
    return SecretStatus(
        provider=provider.provider,
        account=provider.account,
        present=value is not None,
        last4=None if value is None else value[-4:],
        required=bool(requirements),
        required_by=[
            SecretRequirement(seat=item.seat, model=item.model) for item in requirements
        ],
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
    """Return masked status and seat requiredness for UI-visible keyed providers."""
    providers = get_secret_providers()
    required = required_secret_accounts(load_settings())
    return [
        _status_for(provider, required.get(provider.account, []))
        for provider in providers
    ]


@router.put("/{provider}", response_model=SecretStatus)
def put_secret(provider: str, body: SecretWriteRequest) -> SecretStatus:
    """Store or replace one registry-approved provider key."""
    selected = _provider_or_404(provider)
    # Resolve seats before writing so a seat error never follows a stored key.
    requirements = required_secret_accounts(load_settings()).get(selected.account, [])
    try:
        set_secret(selected.account, body.key)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="API key must not be empty or whitespace.",
        ) from None
    return _status_for(selected, requirements)


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
