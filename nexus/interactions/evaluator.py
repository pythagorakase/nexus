"""Pure fail-closed authorization evaluation for interaction execution."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationGrantState,
    DenialReason,
)


def evaluate_authorizations(
    *,
    participant_entity_ids: Iterable[int],
    authorization_rows: Iterable[dict[str, Any]],
    action: str,
    continuation_id: UUID,
    interaction_revision: int,
    evaluated_at: datetime,
) -> AuthorizationDecision:
    """Require a current positive grant from every active participant.

    The evaluator never infers approval. Missing rows, invalid row shapes, old
    continuation or revision identities, revocation, expiry, and future-dated
    grants all produce an explicit denial.
    """
    rows_by_participant: dict[int, list[dict[str, Any]]] = {}
    for row in authorization_rows:
        raw_participant_id = row.get("participant_entity_id")
        if not isinstance(raw_participant_id, int):
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MALFORMED_AUTHORIZATION,
            )
        rows_by_participant.setdefault(raw_participant_id, []).append(row)

    for participant_id in participant_entity_ids:
        participant_rows = rows_by_participant.get(participant_id, [])
        if not participant_rows:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MISSING_AUTHORIZATION,
                participant_entity_id=participant_id,
            )

        current_rows = [
            row
            for row in participant_rows
            if row.get("continuation_id") == continuation_id
            and row.get("interaction_revision") == interaction_revision
        ]
        if not current_rows:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.STALE_AUTHORIZATION,
                participant_entity_id=participant_id,
            )

        try:
            latest_row = max(current_rows, key=lambda row: int(row.get("id", -1)))
        except (TypeError, ValueError):
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MALFORMED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )
        try:
            grant = AuthorizationGrantState.model_validate(latest_row)
        except (TypeError, ValueError, ValidationError):
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MALFORMED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )

        if grant.action != action:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MALFORMED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )

        if grant.revoked_at is not None:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.REVOKED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )
        if grant.granted_at > evaluated_at:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.MALFORMED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )
        if grant.expires_at <= evaluated_at:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.EXPIRED_AUTHORIZATION,
                participant_entity_id=participant_id,
            )

    return AuthorizationDecision(allowed=True)
