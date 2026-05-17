"""Seed semantic tag vocabulary surfaced by the slot 2 backfill draft."""

from __future__ import annotations

from typing import Any, Sequence

from psycopg2.extensions import connection


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    # Template-referenced tags that were rediscovered or exposed by the
    # slot-2 audit but not registered before this migration.
    (
        "extended_household",
        "role",
        "Character belongs to a household, found-family unit, or equivalent "
        "shared domestic support structure.",
    ),
    (
        "forager",
        "capacity",
        "Character can gather usable food or supplies from wild or marginal "
        "terrain.",
    ),
    (
        "hunter",
        "capacity",
        "Character can track and hunt game or equivalent prey.",
    ),
    (
        "married",
        "state",
        "Character is in a marriage or marriage-equivalent household bond.",
    ),
    (
        "parent",
        "role",
        "Character has a parent or parent-equivalent relationship role.",
    ),
    (
        "survivalist",
        "capacity",
        "Character is skilled at surviving austere, wild, or infrastructure-poor "
        "conditions.",
    ),
    (
        "travel_provisioned",
        "orrery_state",
        "Character is supplied or prepared enough for a travel-oriented package "
        "to fire.",
    ),
    # High-frequency character concepts from the slot-2 proposal report.
    (
        "ancient_being",
        "state",
        "Character is unusually old, continuous, or pre-Collapse in a way that "
        "matters narratively.",
    ),
    (
        "archivum_adjacent",
        "state",
        "Character is tied to Archivum systems, people, or historical knowledge.",
    ),
    (
        "augmented_prosthetic",
        "capacity",
        "Character has a consequential prosthetic or replacement body part.",
    ),
    (
        "black_market_operator",
        "profession_lite",
        "Character works through black-market trade, brokerage, or logistics.",
    ),
    (
        "bridge_aware",
        "state",
        "Character is aware of or meaningfully affected by the Bridge phenomenon.",
    ),
    (
        "broker",
        "profession_lite",
        "Character brokers deals, access, favors, or information.",
    ),
    (
        "cell_handler",
        "profession_lite",
        "Character manages cells, assets, or clandestine operators.",
    ),
    (
        "corporate_exile",
        "state",
        "Character has been forced out of, hunted by, or materially cut off from "
        "a corporate power structure.",
    ),
    (
        "cybernetic_augmentation",
        "capacity",
        "Character has consequential cybernetic augmentation beyond ordinary "
        "tools or wearable devices.",
    ),
    (
        "digital_mind",
        "bodyform",
        "Character's personhood substantially exists as software, upload, or "
        "digital consciousness.",
    ),
    (
        "fixer",
        "profession_lite",
        "Character habitually solves problems through contacts, leverage, and "
        "practical arrangement.",
    ),
    (
        "fugitive",
        "state",
        "Character is wanted, hunted, or living under an active need to evade "
        "authorities or pursuers.",
    ),
    (
        "insomniac",
        "state",
        "Character has a persistent difficulty sleeping that may modulate sleep "
        "need packages.",
    ),
    (
        "memory_fragmented",
        "state",
        "Character's memory is incomplete, discontinuous, or narratively damaged.",
    ),
    (
        "mutual_aid_patron",
        "disposition",
        "Character materially supports mutual-aid networks or vulnerable "
        "dependents.",
    ),
    (
        "nomad",
        "role",
        "Character belongs to or operates through mobile, road, or migrant "
        "social structures.",
    ),
    (
        "nuclear_specialist",
        "capacity",
        "Character has specialized knowledge of nuclear systems, materials, or "
        "hazards.",
    ),
    (
        "paranoid",
        "disposition",
        "Character exhibits persistent suspicion, threat-scanning, or "
        "conspiracy-minded caution.",
    ),
    (
        "salvager",
        "role",
        "Character recovers value from ruins, wreckage, abandoned systems, or "
        "discarded technology.",
    ),
    (
        "sandboxed",
        "state",
        "Character or mind-state is constrained inside a sandbox, containment "
        "environment, or limited operating context.",
    ),
    (
        "smuggler",
        "profession_lite",
        "Character moves goods, people, or information outside ordinary legal "
        "channels.",
    ),
    (
        "trauma_survivor",
        "state",
        "Character has survived major trauma that remains behaviorally relevant.",
    ),
    (
        "uploaded_consciousness",
        "bodyform",
        "Character's consciousness has been uploaded, transferred, or hosted "
        "outside their original body.",
    ),
    (
        "veteran",
        "role",
        "Character has significant prior service in military, paramilitary, or "
        "conflict institutions.",
    ),
    (
        "whistleblower",
        "role",
        "Character has exposed or is positioned to expose institutional wrongdoing.",
    ),
    # Faction concepts from the slot-2 proposal report.
    (
        "ancient_continuous",
        "history_class",
        "Faction has unusually long institutional continuity.",
    ),
    (
        "anarchist_collective",
        "ideology_axis",
        "Faction operates through anarchist or anti-hierarchical ideals.",
    ),
    (
        "barter_economy",
        "resource_class",
        "Faction relies heavily on barter, informal exchange, or nonstandard "
        "currency.",
    ),
    (
        "cellular_clandestine",
        "operational_secrecy",
        "Faction is organized into covert cells or compartmented clandestine units.",
    ),
    (
        "compartmented",
        "operational_secrecy",
        "Faction limits knowledge and responsibility across internal compartments.",
    ),
    (
        "contract_kinetic",
        "power_posture",
        "Faction sells or deploys force through contract violence or security work.",
    ),
    (
        "covert_loyalty_play",
        "hidden_agenda_class",
        "Faction is engaged in covert allegiance, betrayal, or loyalty-shaping "
        "maneuvers.",
    ),
    (
        "criminal_underground",
        "legitimacy_status",
        "Faction operates primarily through criminal or underground legitimacy.",
    ),
    (
        "decentralized_federation",
        "power_posture",
        "Faction is a federated network rather than a centralized hierarchy.",
    ),
    (
        "esoteric_metaphysical",
        "ideology_axis",
        "Faction is organized around occult, metaphysical, or reality-bending "
        "beliefs.",
    ),
    (
        "expansionist_ambition",
        "hidden_agenda_class",
        "Faction is pushing to expand territory, influence, or institutional reach.",
    ),
    (
        "gray_legal",
        "legitimacy_status",
        "Faction operates in a gray zone between lawful, tolerated, and illicit.",
    ),
    (
        "infiltration_specialist",
        "power_posture",
        "Faction is especially capable at infiltration and embedded operations.",
    ),
    (
        "information_intensive",
        "resource_class",
        "Faction's power depends heavily on information, records, surveillance, "
        "or analysis.",
    ),
    (
        "materiel_stockpile",
        "resource_class",
        "Faction controls significant equipment, supplies, weapons, or materiel.",
    ),
    (
        "militarized",
        "power_posture",
        "Faction is organized or armed in a military or paramilitary posture.",
    ),
    (
        "mobile_basing",
        "power_posture",
        "Faction can relocate operations or maintain mobile bases.",
    ),
    (
        "mutual_aid_norms",
        "ideology_axis",
        "Faction is materially shaped by mutual aid or reciprocal support norms.",
    ),
    (
        "patron_dependent",
        "resource_class",
        "Faction depends materially on a patron, sponsor, or larger protector.",
    ),
    (
        "salvage_economy",
        "resource_class",
        "Faction's economy or logistics center on salvage and recovery.",
    ),
    (
        "smuggling_corridor",
        "power_posture",
        "Faction controls or exploits routes for smuggling goods, people, or "
        "information.",
    ),
    (
        "transhumanist_program",
        "ideology_axis",
        "Faction pursues transhumanist transformation, enhancement, or continuity.",
    ),
)


# (tag, category, clearance_kind, clear_on_json, description)
EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str | None, str]] = (
    (
        "schismatic_internal_threat",
        "hidden_agenda_class",
        "semantic",
        None,
        "Faction currently faces an internal schism, split, or factional threat.",
    ),
)


def run(conn: connection) -> None:
    """Apply slot-2 semantic vocabulary seed tags."""

    with conn.cursor() as cur:
        for tag, category, description in DURABLE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, FALSE,
                    NULL, NULL,
                    NULL, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, category, description),
            )
        for tag, category, clearance_kind, clear_on_json, description in EPHEMERAL_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, TRUE,
                    %s::entity_tag_clearance_kind,
                    'extend_expiry'::entity_tag_reapplication_policy,
                    %s::jsonb, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, category, clearance_kind, clear_on_json, description),
            )
        _assert_seeded_categories(cur)
    conn.commit()


def _assert_seeded_categories(cur: Any) -> None:
    expected = {tag: (category, False) for tag, category, _description in DURABLE_TAGS}
    expected.update(
        {
            tag: (category, True)
            for tag, category, _clearance, _clear_on, _description in EPHEMERAL_TAGS
        }
    )
    cur.execute(
        """
        SELECT tag, category, is_ephemeral
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected),),
    )
    actual = {
        tag: (category, is_ephemeral) for tag, category, is_ephemeral in cur.fetchall()
    }
    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(
        f"{tag}=category:{actual[tag][0]},ephemeral:{actual[tag][1]}"
        for tag in set(expected) & set(actual)
        if actual[tag] != expected[tag]
    )
    if missing or mismatched:
        message = "Orrery slot-2 semantic vocabulary seed mismatch"
        if missing:
            message += f"; missing={missing}"
        if mismatched:
            message += f"; mismatched={mismatched}"
        raise RuntimeError(message)
