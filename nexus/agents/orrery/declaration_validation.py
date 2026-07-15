"""Shared closed-vocabulary checks for storyteller entity declarations."""

from __future__ import annotations

from typing import Any, Sequence

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import (
    validate_pair_tag_endpoint,
    validate_tag_bestowal,
)


def collect_new_entity_declaration_vocabulary_issues(
    cur: Any,
    declarations: Sequence[NewEntityDeclaration],
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
            bestowal = OrreryTagBestowal(applied_tags=list(declaration.tag_hints))
            for issue in validate_tag_bestowal(
                cur,
                entity_kind=declaration.kind,
                bestowal=bestowal,
            ):
                detail = issue.removeprefix("applied_tags: ")
                issues.append(f"{path}.tag_hints: {detail}")

        for hint_index, hint in enumerate(declaration.pair_tag_hints):
            try:
                validate_pair_tag_endpoint(
                    cur,
                    tag=hint.tag,
                    entity_kind=declaration.kind,
                    role=hint.declared_entity_role,
                )
            except ValueError as exc:
                issues.append(f"{path}.pair_tag_hints[{hint_index}].tag: {exc}")

    return issues
