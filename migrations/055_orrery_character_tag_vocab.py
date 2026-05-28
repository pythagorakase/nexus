"""Seed accepted durable character vocabulary and resolve registry collisions."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from psycopg2.extensions import connection


# (category, entity_kind, prompt_order, description)
NEW_CATEGORY_REGISTRY: Sequence[tuple[str, str, int, str]] = (
    (
        "bodyform.lineage",
        "character",
        10,
        "Essential character lineage or personhood substrate.",
    ),
    (
        "bodyform.condition",
        "character",
        11,
        "Fundamental character embodiment conditions layered onto lineage.",
    ),
    (
        "role.function",
        "character",
        40,
        "Multi-valued social or operational function recognized by others.",
    ),
)

# (legacy_category, entity_kind, replacement_categories)
DEPRECATED_CATEGORY_REPLACEMENTS: Sequence[
    tuple[str, str, Optional[tuple[str, ...]]]
] = (
    ("bodyform", "character", ("bodyform.lineage", "bodyform.condition")),
    ("role", "character", ("role.function",)),
    ("profession_lite", "character", ("role.function",)),
)

BODYFORM_LINEAGE_TAGS: Sequence[str] = (
    "human",
    "elf",
    "dwarf",
    "orc",
    "goblinoid",
    "beastfolk",
    "animal",
    "dragon",
    "fey",
    "giant",
    "eldritch",
    "spirit",
    "inorganic",
    "alien",
)

BODYFORM_CONDITION_TAGS: Sequence[str] = (
    "undead",
    "lycanthrope",
    "enchanted",
    "awakened",
    "virtual",
    "extraplanar",
    "cybernetic",
)

DISPOSITION_TAGS: Sequence[str] = (
    "brave",
    "cowardly",
    "reckless",
    "cautious",
    "aggressive",
    "peaceable",
    "belligerent",
    "gentle",
    "fierce",
    "loyal",
    "treacherous",
    "trusting",
    "suspicious",
    "compassionate",
    "callous",
    "merciful",
    "cruel",
    "generous",
    "miserly",
    "forthright",
    "deceitful",
    "honorable",
    "manipulative",
    "dutiful",
    "independent",
    "tradition_bound",
    "iconoclast",
    "principled",
    "expedient",
    "reciprocal",
    "transactional",
    "cooperative",
    "exploitative",
    "ambitious",
    "complacent",
    "industrious",
    "indolent",
    "disciplined",
    "impulsive",
    "temperate",
    "hedonistic",
    "stoic",
    "volatile",
    "resolute",
    "wavering",
    "humble",
    "proud",
    "arrogant",
    "self_effacing",
    "secure",
    "insecure",
    "optimistic",
    "cynical",
    "idealistic",
    "romantic",
    "realistic",
    "dispassionate",
    "gregarious",
    "solitary",
    "reserved",
)

CAPACITY_TAGS: Sequence[str] = (
    "strong",
    "agile",
    "hardy",
    "frail",
    "clumsy",
    "sickly",
    "educated",
    "perceptive",
    "resourceful",
    "tactician",
    "unlettered",
    "oblivious",
    "persuasive",
    "intimidating",
    "deceptive",
    "empathic",
    "inarticulate",
    "martial",
    "medical",
    "mechanical",
    "stealthy",
    "arcane",
    "wild",
    "urban",
)

ROLE_FUNCTION_TAGS: Sequence[str] = (
    "advocate",
    "artisan",
    "artist",
    "caregiver",
    "clergy",
    "entertainer",
    "farmer",
    "functionary",
    "healer",
    "hunter",
    "investigator",
    "laborer",
    "leader",
    "merchant",
    "scholar",
    "sex_worker",
    "spy",
    "teacher",
    "technician",
    "thief",
    "warrior",
)

ALLOWED_CATEGORY_REWRITES: dict[str, frozenset[str]] = {
    tag: frozenset({"role"}) for tag in ROLE_FUNCTION_TAGS
}
# ``hunter`` used to be a capacity anchor before the role.function split.
ALLOWED_CATEGORY_REWRITES["hunter"] = frozenset({"capacity", "role"})


def run(conn: connection) -> None:
    """Seed durable character vocabulary rows idempotently."""

    expected = _expected_rows()
    with conn.cursor() as cur:
        _ensure_category_cutover_columns(cur)
        _assert_no_unexpected_category_conflicts(cur, expected)
        for category, entity_kind, prompt_order, description in NEW_CATEGORY_REGISTRY:
            _upsert_category(
                cur,
                category=category,
                entity_kind=entity_kind,
                prompt_order=prompt_order,
                description=description,
            )

        for (
            legacy_category,
            entity_kind,
            replacements,
        ) in DEPRECATED_CATEGORY_REPLACEMENTS:
            cur.execute(
                """
                UPDATE tag_category_registry
                SET deprecated = TRUE,
                    replacement_categories = %s
                WHERE category = %s
                  AND entity_kind = %s::entity_kind
                """,
                (
                    list(replacements) if replacements else None,
                    legacy_category,
                    entity_kind,
                ),
            )

        for tag, (category, description) in expected.items():
            _upsert_tag(cur, tag=tag, category=category, description=description)

        _assert_seeded_tags(cur, expected)
    conn.commit()


def _ensure_category_cutover_columns(cur: Any) -> None:
    cur.execute(
        """
        ALTER TABLE tag_category_registry
        ADD COLUMN IF NOT EXISTS deprecated boolean NOT NULL DEFAULT false
        """
    )
    cur.execute(
        """
        ALTER TABLE tag_category_registry
        ADD COLUMN IF NOT EXISTS replacement_categories text[]
        """
    )
    cur.execute(
        """
        COMMENT ON COLUMN tag_category_registry.deprecated IS
            'Category-level cutover marker; existing tag rows remain live '
            'until a reviewed data migration rewrites or clears them.'
        """
    )
    cur.execute(
        """
        COMMENT ON COLUMN tag_category_registry.replacement_categories IS
            'Preferred successor categories for deprecated category rows, '
            'when any exist.'
        """
    )


def _upsert_category(
    cur: Any,
    *,
    category: str,
    entity_kind: str,
    prompt_order: int,
    description: str,
) -> None:
    cur.execute(
        """
        INSERT INTO tag_category_registry (
            category, entity_kind, prompt_order, description,
            deprecated, replacement_categories
        ) VALUES (
            %s, %s::entity_kind, %s, %s,
            FALSE, NULL
        )
        ON CONFLICT (category, entity_kind) DO UPDATE SET
            prompt_order = EXCLUDED.prompt_order,
            description = EXCLUDED.description,
            deprecated = FALSE,
            replacement_categories = NULL
        """,
        (category, entity_kind, prompt_order, description),
    )


def _upsert_tag(cur: Any, *, tag: str, category: str, description: str) -> None:
    cur.execute(
        """
        INSERT INTO tags (
            tag, category, is_ephemeral,
            clearance_kind, reapplication_policy, clear_on,
            synonym_for, deprecated, description
        ) VALUES (
            %s, %s, FALSE,
            NULL, NULL, NULL,
            NULL, FALSE, %s
        )
        ON CONFLICT (tag) DO UPDATE SET
            category = EXCLUDED.category,
            is_ephemeral = EXCLUDED.is_ephemeral,
            clearance_kind = EXCLUDED.clearance_kind,
            reapplication_policy = EXCLUDED.reapplication_policy,
            clear_on = EXCLUDED.clear_on,
            synonym_for = NULL,
            deprecated = FALSE,
            description = EXCLUDED.description
        """,
        (tag, category, description),
    )


def _assert_no_unexpected_category_conflicts(
    cur: Any,
    expected: dict[str, tuple[str, str]],
) -> None:
    cur.execute(
        """
        SELECT tag, category
             , deprecated
             , synonym_for
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected),),
    )
    conflicts = []
    for tag, existing_category, deprecated, synonym_for in cur.fetchall():
        expected_category = expected[tag][0]
        if deprecated:
            conflicts.append(f"{tag}: deprecated row cannot be promoted implicitly")
            continue
        if synonym_for is not None:
            conflicts.append(f"{tag}: synonym row cannot be promoted implicitly")
            continue
        if existing_category == expected_category:
            continue
        if existing_category in ALLOWED_CATEGORY_REWRITES.get(tag, frozenset()):
            continue
        conflicts.append(f"{tag}: {existing_category} -> {expected_category}")
    if conflicts:
        detail = ", ".join(conflicts)
        raise RuntimeError(f"Character vocabulary tag name collisions: {detail}")


def _assert_seeded_tags(
    cur: Any,
    expected: dict[str, tuple[str, str]],
) -> None:
    cur.execute(
        """
        SELECT tag, category, is_ephemeral, deprecated, synonym_for, description
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected),),
    )
    actual = {
        tag: (category, is_ephemeral, deprecated, synonym_for, description)
        for tag, category, is_ephemeral, deprecated, synonym_for, description in (
            cur.fetchall()
        )
    }
    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(
        f"{tag}={actual[tag]}"
        for tag, (category, description) in expected.items()
        if tag in actual and actual[tag] != (category, False, False, None, description)
    )
    if missing or mismatched:
        message = "Orrery character vocabulary seed mismatch"
        if missing:
            message += f"; missing={missing}"
        if mismatched:
            message += f"; mismatched={mismatched}"
        raise RuntimeError(message)


def _expected_rows() -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}
    expected.update(
        {
            tag: ("bodyform.lineage", f"Bodyform lineage anchor: {tag}.")
            for tag in BODYFORM_LINEAGE_TAGS
        }
    )
    expected.update(
        {
            tag: ("bodyform.condition", f"Bodyform condition anchor: {tag}.")
            for tag in BODYFORM_CONDITION_TAGS
        }
    )
    expected.update(
        {
            tag: ("disposition", f"Disposition anchor: {tag}.")
            for tag in DISPOSITION_TAGS
        }
    )
    expected.update(
        {tag: ("capacity", f"Capacity anchor: {tag}.") for tag in CAPACITY_TAGS}
    )
    expected.update(
        {
            tag: ("role.function", f"Role function anchor: {tag}.")
            for tag in ROLE_FUNCTION_TAGS
        }
    )
    return expected
