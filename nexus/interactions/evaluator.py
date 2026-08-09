"""Canonical term binding and fail-closed interaction authorization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationEnvelope,
    AuthorizationGrantState,
    AuthorizationPolicy,
    DenialReason,
)


def canonical_envelope_hash(
    policy: AuthorizationPolicy, envelope: AuthorizationEnvelope
) -> str:
    """Hash action, transition type, and policy-declared material terms."""
    rule = policy.actions.get(envelope.action)
    if rule is None:
        raise ValueError(f"authorization action is not declared: {envelope.action}")
    material_terms: dict[str, dict[str, Any]] = {}
    for field in sorted(rule.material_fields):
        if field in envelope.payload:
            material_terms[field] = {
                "present": True,
                "value": envelope.payload[field],
            }
        else:
            material_terms[field] = {"present": False}
    canonical = json.dumps(
        {
            "action": envelope.action,
            "transition_type": envelope.transition_type,
            "material_terms": material_terms,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_authorizations(
    *,
    participant_entity_ids: Iterable[int],
    authorization_rows: Iterable[dict[str, Any]],
    action: str,
    envelope_hash: str,
    continuation_id: UUID,
    interaction_revision: int,
    evaluated_at: datetime,
) -> AuthorizationDecision:
    """Require one exact current-envelope grant from every active participant."""
    rows_by_participant: dict[int, list[dict[str, Any]]] = {}
    for row in authorization_rows:
        participant_id = row.get("participant_entity_id")
        if not isinstance(participant_id, int):
            return AuthorizationDecision(
                allowed=False, reason=DenialReason.MALFORMED_AUTHORIZATION
            )
        rows_by_participant.setdefault(participant_id, []).append(row)

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
        exact_rows = [
            row for row in current_rows if row.get("envelope_hash") == envelope_hash
        ]
        if not exact_rows:
            return AuthorizationDecision(
                allowed=False,
                reason=DenialReason.AUTHORIZATION_TERMS_CHANGED,
                participant_entity_id=participant_id,
            )

        validated: list[AuthorizationGrantState] = []
        for row in exact_rows:
            try:
                grant = AuthorizationGrantState.model_validate(row)
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
            validated.append(grant)

        if any(
            grant.revoked_at is None
            and grant.granted_at <= evaluated_at < grant.expires_at
            for grant in validated
        ):
            continue
        if any(grant.granted_at > evaluated_at for grant in validated):
            reason = DenialReason.MALFORMED_AUTHORIZATION
        elif all(grant.revoked_at is not None for grant in validated):
            reason = DenialReason.REVOKED_AUTHORIZATION
        else:
            reason = DenialReason.EXPIRED_AUTHORIZATION
        return AuthorizationDecision(
            allowed=False,
            reason=reason,
            participant_entity_id=participant_id,
        )

    return AuthorizationDecision(allowed=True)
