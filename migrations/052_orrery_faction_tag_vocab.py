"""Seed Orrery faction tag vocabulary anchors."""

from __future__ import annotations

import json
from typing import Any, Sequence

from psycopg2.extensions import connection


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "authoritarian",
        "ideology",
        "Faction legitimizes hierarchy, command, obedience, and coercive order.",
    ),
    (
        "egalitarian",
        "ideology",
        "Faction legitimizes equal standing, distributed rights, or anti-elite "
        "politics.",
    ),
    (
        "traditionalist",
        "ideology",
        "Faction legitimizes inherited custom, lineage, ritual, or precedent.",
    ),
    (
        "progressive",
        "ideology",
        "Faction legitimizes deliberate reform, novelty, or future-oriented change.",
    ),
    (
        "theocratic",
        "ideology",
        "Faction grounds authority in sacred law, divine mandate, or priesthood.",
    ),
    (
        "secularist",
        "ideology",
        "Faction grounds authority outside priestly or sacred institutions.",
    ),
    (
        "nationalist",
        "ideology",
        "Faction organizes around a people, homeland, nation, tribe, or civic "
        "identity.",
    ),
    (
        "cosmopolitan",
        "ideology",
        "Faction organizes around cross-border, cross-culture, or universalist "
        "belonging.",
    ),
    (
        "imperial",
        "ideology",
        "Faction legitimizes expansion, dominion, tributary hierarchy, or "
        "civilizing mission.",
    ),
    (
        "communalist",
        "ideology",
        "Faction prioritizes local commons, mutual obligation, or community survival.",
    ),
    (
        "mercantilist",
        "ideology",
        "Faction prioritizes trade advantage, market control, profit, or commerce.",
    ),
    (
        "technocratic",
        "ideology",
        "Faction legitimizes expert rule, optimization, planning, or technical "
        "competence.",
    ),
    (
        "revolutionary",
        "ideology",
        "Faction legitimizes overthrow of the present order and rupture with "
        "authority.",
    ),
    (
        "restorationist",
        "ideology",
        "Faction legitimizes return to a prior order, lost dynasty, or old law.",
    ),
    (
        "isolationist",
        "ideology",
        "Faction prioritizes boundary maintenance and protection from outside control.",
    ),
    (
        "capital",
        "resource_base",
        "Faction can mobilize money, credit, stored wealth, or financial leverage.",
    ),
    (
        "force",
        "resource_base",
        "Faction can mobilize fighters, guards, troops, weapons, or coercive capacity.",
    ),
    (
        "information",
        "resource_base",
        "Faction can mobilize intelligence, archives, surveillance, secrets, or "
        "analysis.",
    ),
    (
        "faith",
        "resource_base",
        "Faction can mobilize religious devotion, ritual authority, or sacred "
        "legitimacy.",
    ),
    (
        "industry",
        "resource_base",
        "Faction can mobilize workshops, factories, craft, or production capacity.",
    ),
    (
        "labor",
        "resource_base",
        "Faction can mobilize workers, volunteers, conscripts, members, or retainers.",
    ),
    (
        "territory",
        "resource_base",
        "Faction draws operational capacity from land or resource control.",
    ),
    (
        "patronage",
        "resource_base",
        "Faction can mobilize sponsors, donors, backers, parent bodies, or subsidies.",
    ),
    (
        "bureaucracy",
        "resource_base",
        "Faction can mobilize records, offices, permits, administrators, or procedure.",
    ),
    (
        "technology",
        "resource_base",
        "Faction can mobilize advanced tools, machines, infrastructure, or systems.",
    ),
    (
        "specialized_knowledge",
        "resource_base",
        "Faction can mobilize rare expertise, scholarship, lore, or trade secrets.",
    ),
    (
        "criminal_network",
        "resource_base",
        "Faction can mobilize smuggling, black markets, fences, or illicit logistics.",
    ),
    (
        "supply_lines",
        "resource_base",
        "Faction can mobilize logistics, transport, warehousing, or material "
        "throughput.",
    ),
    (
        "mobility",
        "resource_base",
        "Faction can mobilize ships, vehicles, mounts, portals, couriers, or roads.",
    ),
    (
        "state_recognized",
        "legitimacy",
        "Faction is formally recognized by the dominant legal or political order.",
    ),
    (
        "customary",
        "legitimacy",
        "Faction is locally accepted by tradition or community practice.",
    ),
    (
        "tolerated",
        "legitimacy",
        "Faction is known and allowed to operate without strong formal recognition.",
    ),
    (
        "shadow_legal",
        "legitimacy",
        "Faction is partly legal, deniable, gray-market, or protected by loopholes.",
    ),
    (
        "underground",
        "legitimacy",
        "Faction is hidden or unofficial; exposure changes its risk profile.",
    ),
    (
        "outlaw",
        "legitimacy",
        "Faction is known and proscribed; public association is dangerous or "
        "criminalized.",
    ),
    (
        "contested",
        "legitimacy",
        "Faction recognition is unstable or disputed by competing authorities.",
    ),
    (
        "overt",
        "operational_mode",
        "Faction acts openly under its own name; public footprint is normal.",
    ),
    (
        "covert",
        "operational_mode",
        "Faction acts through secrecy, fronts, cells, aliases, or deniable agents.",
    ),
    (
        "hybrid",
        "operational_mode",
        "Faction maintains both public and hidden operating surfaces.",
    ),
)

# (tag, category, clear_on_json, description)
EPHEMERAL_TAGS: Sequence[tuple[str, str, str, str]] = (
    (
        "dominant",
        "power_status",
        '{"description": "replace when strength or trajectory changes"}',
        "Faction sets terms locally; rivals react to it.",
    ),
    (
        "ascending",
        "power_status",
        '{"description": "replace when gains consolidate or reverse"}',
        "Faction is gaining power, territory, members, resources, or legitimacy.",
    ),
    (
        "stable",
        "power_status",
        '{"description": "replace when a major event changes faction trajectory"}',
        "Faction is operationally steady; neither surging nor collapsing.",
    ),
    (
        "pressured",
        "power_status",
        '{"description": "replace when pressure resolves or worsens"}',
        "Faction is under meaningful stress without yet losing the overall position.",
    ),
    (
        "declining",
        "power_status",
        '{"description": "replace when recovery, collapse, or restructure changes it"}',
        "Faction is losing ground, influence, cohesion, resources, or legitimacy.",
    ),
    (
        "fragile",
        "power_status",
        '{"description": "replace when recovery, collapse, or rescue changes it"}',
        "Faction can still act, but one shock could break its position.",
    ),
    (
        "collapsed",
        "power_status",
        '{"description": "clear or replace when it dissolves, refounds, or revives"}',
        "Faction is no longer coherent as an actor, though remnants may persist.",
    ),
    (
        "expand_control",
        "agenda",
        '{"description": "clear when expansion succeeds, fails, or is abandoned"}',
        "Faction is trying to acquire territory, influence, markets, offices, "
        "or reach.",
    ),
    (
        "consolidate_control",
        "agenda",
        '{"description": "clear when control consolidates, realigns, or fails"}',
        "Faction is trying to secure gains, normalize rule, or stabilize holdings.",
    ),
    (
        "infiltrate",
        "agenda",
        '{"description": "clear when infiltration succeeds, is exposed, or fails"}',
        "Faction is trying to place agents or influence inside a target.",
    ),
    (
        "seize_leadership",
        "agenda",
        '{"description": "clear when leadership changes or seizure fails"}',
        "Faction is trying to take control of a faction, office, throne, or command.",
    ),
    (
        "settle_succession",
        "agenda",
        '{"description": "clear when succession settles or deepens"}',
        "Faction is trying to resolve contested leadership or inheritance.",
    ),
    (
        "recover_losses",
        "agenda",
        '{"description": "clear when losses recover, settle, or are abandoned"}',
        "Faction is trying to retake lost assets, territory, status, members, "
        "or rights.",
    ),
    (
        "negotiate",
        "agenda",
        '{"description": "clear when agreement is reached or talks fail"}',
        "Faction is seeking settlement, alliance, treaty, contract, ransom, or "
        "accommodation.",
    ),
    (
        "mobilize",
        "agenda",
        '{"description": "clear when mobilization completes or stands down"}',
        "Faction is preparing forces, members, resources, or logistics for "
        "imminent action.",
    ),
    (
        "investigate",
        "agenda",
        '{"description": "clear when investigation resolves, blocks, or is abandoned"}',
        "Faction is trying to discover facts, identify actors, audit records, "
        "or locate causes.",
    ),
    (
        "recruit",
        "agenda",
        '{"description": "clear when recruitment completes, disrupts, or stops"}',
        "Faction is trying to grow membership, hire agents, convert, or enlist.",
    ),
    (
        "extract_resources",
        "agenda",
        '{"description": "clear when extraction completes, disrupts, or loses target"}',
        "Faction is trying to draw value from people, territory, infrastructure, "
        "or debt.",
    ),
    (
        "sabotage",
        "agenda",
        '{"description": "clear when sabotage completes, fails, or is exposed"}',
        "Faction is trying to disrupt a rival operation, infrastructure, "
        "reputation, or supply.",
    ),
    (
        "suppress_dissent",
        "agenda",
        '{"description": "clear when dissent is suppressed, fails, or settles"}',
        "Faction is trying to silence, coerce, appease, or eliminate internal "
        "opposition.",
    ),
    (
        "conceal_exposure",
        "agenda",
        '{"description": "clear when scandal is contained, exposed, or resolved"}',
        "Faction is trying to contain scandal, leak, investigation, identity, "
        "or evidence.",
    ),
    (
        "reform_internal",
        "agenda",
        '{"description": "clear when reform completes, fails, or is superseded"}',
        "Faction is trying to change doctrine, governance, membership rules, or "
        "methods.",
    ),
    (
        "secure_alliance",
        "agenda",
        '{"description": "clear when alliance brokers, fails, breaks, or stops"}',
        "Faction is trying to build or preserve alliance, patronage, clientage, "
        "or coalition.",
    ),
    (
        "enforce_claim",
        "agenda",
        '{"description": "clear when claim enforces, fails, or is abandoned"}',
        "Faction is trying to turn a claim into practical control or punish "
        "its violation.",
    ),
    (
        "protect_asset",
        "agenda",
        '{"description": "clear when asset secures, is lost, or guard ends"}',
        "Faction is trying to guard a person, place, object, secret, route, or "
        "institution.",
    ),
    (
        "retaliate",
        "agenda",
        '{"description": "clear when retaliation executes, truces, or stops"}',
        "Faction is trying to punish injury, betrayal, insult, attack, default, "
        "or trespass.",
    ),
)


def run(conn: connection) -> None:
    """Seed faction vocabulary tag rows idempotently."""

    with conn.cursor() as cur:
        _assert_no_cross_category_conflicts(cur)
        for tag, category, description in DURABLE_TAGS:
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

        for tag, category, clear_on_json, description in EPHEMERAL_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy, clear_on,
                    synonym_for, deprecated, description
                ) VALUES (
                    %s, %s, TRUE,
                    'semantic'::entity_tag_clearance_kind,
                    'replace'::entity_tag_reapplication_policy,
                    %s::jsonb,
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
                (tag, category, clear_on_json, description),
            )

        _assert_seeded_tags(cur)
    conn.commit()


def _assert_no_cross_category_conflicts(cur: Any) -> None:
    expected_categories = _expected_categories()
    cur.execute(
        """
        SELECT tag, category
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected_categories),),
    )
    conflicts = {
        tag: category
        for tag, category in cur.fetchall()
        if category != expected_categories[tag]
    }
    if conflicts:
        detail = ", ".join(
            f"{tag}={actual_category} (expected {expected_categories[tag]})"
            for tag, actual_category in conflicts.items()
        )
        raise RuntimeError(f"Faction tag vocabulary name collisions: {detail}")


def _assert_seeded_tags(cur: Any) -> None:
    expected = {
        tag: (category, False, None, None, None, False, description)
        for tag, category, description in DURABLE_TAGS
    }
    expected.update(
        {
            tag: (
                category,
                True,
                "semantic",
                "replace",
                _normalize_clear_on(clear_on_json),
                False,
                description,
            )
            for tag, category, clear_on_json, description in EPHEMERAL_TAGS
        }
    )
    cur.execute(
        """
        SELECT tag,
               category,
               is_ephemeral,
               clearance_kind::text,
               reapplication_policy::text,
               clear_on,
               deprecated,
               description
        FROM tags
        WHERE tag = ANY(%s)
        ORDER BY tag
        """,
        (list(expected),),
    )
    actual = {}
    for (
        tag,
        category,
        is_ephemeral,
        clearance_kind,
        reapplication_policy,
        clear_on,
        deprecated,
        description,
    ) in cur.fetchall():
        actual[tag] = (
            category,
            is_ephemeral,
            clearance_kind,
            reapplication_policy,
            _normalize_clear_on(clear_on),
            deprecated,
            description,
        )
    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(
        f"{tag}={actual[tag]}"
        for tag in set(expected) & set(actual)
        if actual[tag] != expected[tag]
    )
    if missing or mismatched:
        message = "Orrery faction vocabulary seed mismatch"
        if missing:
            message += f"; missing={missing}"
        if mismatched:
            message += f"; mismatched={mismatched}"
        raise RuntimeError(message)


def _expected_categories() -> dict[str, str]:
    return {tag: category for tag, category, *_rest in (*DURABLE_TAGS, *EPHEMERAL_TAGS)}


def _normalize_clear_on(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
