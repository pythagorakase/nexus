"""Shared closed-vocabulary checks for storyteller entity declarations."""

from __future__ import annotations

from typing import AbstractSet, Any, Literal, Mapping, Optional, Sequence

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import (
    validate_pair_tag_endpoint,
    validate_tag_bestowal,
)


def collect_new_entity_declaration_vocabulary_issues(
    cur: Any,
    declarations: Sequence[NewEntityDeclaration],
    *,
    tag_names_by_kind: Optional[Mapping[str, AbstractSet[str]]] = None,
    pair_tag_names: Optional[AbstractSet[str]] = None,
) -> list[str]:
    """Return path-qualified vocabulary issues without mutating the database.

    The same collector runs at generation time (where issues become a
    ``ModelRetry``) and again immediately before commit-time stub processing.
    This keeps both boundaries on one closed-vocabulary contract.
    """

    issues: list[str] = []
    for declaration_index, declaration in enumerate(declarations):
        path = f"new_entities[{declaration_index}]"

        if declaration.tag_hints:
            if tag_names_by_kind is None:
                bestowal = OrreryTagBestowal(applied_tags=list(declaration.tag_hints))
                tag_issues = validate_tag_bestowal(
                    cur,
                    entity_kind=declaration.kind,
                    bestowal=bestowal,
                )
                for issue in tag_issues:
                    detail = issue.removeprefix("applied_tags: ")
                    issues.append(f"{path}.tag_hints: {detail}")
            else:
                allowed_tags = tag_names_by_kind.get(declaration.kind, set())
                for tag_name in declaration.tag_hints:
                    if tag_name not in allowed_tags:
                        issues.append(
                            f"{path}.tag_hints: Unknown or "
                            f"entity-kind-incompatible tag {tag_name!r} for "
                            f"{declaration.kind!r}"
                        )

        for hint_index, hint in enumerate(declaration.pair_tag_hints):
            hint_path = f"{path}.pair_tag_hints[{hint_index}]"
            tag_is_valid = True
            if pair_tag_names is not None and hint.tag not in pair_tag_names:
                tag_is_valid = False
                issues.append(
                    f"{hint_path}.tag: Unknown or deprecated pair_tag {hint.tag!r}"
                )
            else:
                try:
                    validate_pair_tag_endpoint(
                        cur,
                        tag=hint.tag,
                        entity_kind=declaration.kind,
                        role=hint.declared_entity_role,
                    )
                except ValueError as exc:
                    tag_is_valid = False
                    issues.append(f"{hint_path}.tag: {exc}")

            endpoint_kind, endpoint_issue = _resolve_hint_endpoint_kind(
                cur,
                declarations=declarations,
                declaration_index=declaration_index,
                other_entity_name=hint.other_entity_name,
            )
            if endpoint_issue is not None:
                issues.append(f"{hint_path}.other_entity_name: {endpoint_issue}")
                continue

            if endpoint_kind is not None and tag_is_valid:
                other_role: Literal["subject", "object"] = (
                    "object" if hint.declared_entity_role == "subject" else "subject"
                )
                try:
                    validate_pair_tag_endpoint(
                        cur,
                        tag=hint.tag,
                        entity_kind=endpoint_kind,
                        role=other_role,
                    )
                except ValueError as exc:
                    issues.append(f"{hint_path}.other_entity_name: {exc}")

    return issues


def _resolve_hint_endpoint_kind(
    cur: Any,
    *,
    declarations: Sequence[NewEntityDeclaration],
    declaration_index: int,
    other_entity_name: str,
) -> tuple[str | None, str | None]:
    """Resolve a declaration hint endpoint without mutating the database."""

    declaration = declarations[declaration_index]
    if other_entity_name == declaration.name:
        return None, "pair-tag hint cannot name the declared entity itself"

    cur.execute(
        """
        SELECT entity_kind
        FROM (
            SELECT 'character' AS entity_kind
            FROM characters WHERE name = %s
            UNION ALL
            SELECT 'place' AS entity_kind
            FROM places WHERE name = %s
            UNION ALL
            SELECT 'faction' AS entity_kind
            FROM factions WHERE name = %s
        ) AS matches
        ORDER BY entity_kind
        """,
        (other_entity_name, other_entity_name, other_entity_name),
    )
    existing_kinds = [str(_row_value(row, "entity_kind", 0)) for row in cur.fetchall()]
    if len(existing_kinds) > 1:
        return None, (
            f"pair-tag hint endpoint {other_entity_name!r} is ambiguous: "
            f"{len(existing_kinds)} entities match"
        )

    batch_matches = [
        candidate
        for candidate_index, candidate in enumerate(declarations)
        if candidate_index != declaration_index and candidate.name == other_entity_name
    ]
    batch_kinds = {candidate.kind for candidate in batch_matches}
    if existing_kinds:
        existing_kind = existing_kinds[0]
        if any(kind != existing_kind for kind in batch_kinds):
            return None, (
                f"pair-tag hint endpoint {other_entity_name!r} is ambiguous: "
                "the same declaration batch would create another entity kind"
            )
        return existing_kind, None

    if not batch_matches:
        return None, (
            f"pair-tag hint endpoint {other_entity_name!r} does not resolve to "
            "an entity or another declaration in this batch"
        )
    if len(batch_kinds) > 1:
        return None, (
            f"pair-tag hint endpoint {other_entity_name!r} is ambiguous across "
            f"same-batch declaration kinds {sorted(batch_kinds)}"
        )
    return next(iter(batch_kinds)), None


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row[key]
    return row[index]
