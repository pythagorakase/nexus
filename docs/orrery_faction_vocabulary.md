# Orrery Faction Vocabulary

**Status:** draft design spec for faction single-entity tag categories. Companion to `docs/orrery_tag_vocabulary.md`; migration 052 seeds the 65 tag anchors. Legacy Slot 2 faction tag rewrite, faction-table cleanup, and clearance-event collapse remain separate follow-up work.

---

## Scope and Boundaries

Faction tags describe what package logic needs to know about an organization, institution, movement, polity, guild, gang, church, cult, corporation, army, family house, informal scene, or other group-level actor.

The same three vocabulary tests from the main registry apply here:

- **Differential + gating:** the tag must change what a package can plausibly do with the faction.
- **Reskinning:** the tag must survive translation across eras and genres.
- **Granularity:** sibling tags must produce meaningfully different package behavior.

Faction vocabulary has a stronger decomposition burden than character vocabulary because group facts often look like single-entity properties when they are really relationships:

- Territory is `claims(faction -> place)`, not a faction tag.
- Bases are `operates_from(faction -> place)`, not a faction tag.
- Inter-faction obligations, hostility, protection, and hierarchy are pair-tags.
- A character or sub-faction's standing inside a faction is `status:<level>(subject -> faction)`.
- Past origin, founding myth, scandal history, and wars belong in `world_events` and prose, not durable tags.

---

## Category Overview

These six categories match the replacement categories registered by migration 043. This draft intentionally does **not** add a seventh generic faction `state` category.

| Category | Cardinality | Ephemerality | What It Answers |
|---|---|---|---|
| `ideology` | Multi-valued | Durable | What legitimizing worldview or doctrine guides the faction? |
| `resource_base` | Multi-valued | Durable | What durable sources of operational capacity does it draw on? |
| `legitimacy` | Exclusive | Durable | How does the dominant local order recognize or tolerate it? |
| `operational_mode` | Exclusive | Durable | Does it act openly, secretly, or both? |
| `power_status` | Exclusive | Ephemeral | What is its current strategic strength/trajectory? |
| `agenda` | Multi-valued | Ephemeral | What concrete campaign is it actively pursuing? |

**No generic faction `state` category.** Earlier examples such as `recently_dispossessed`, `leadership_disputed`, `under_investigation`, `negotiating`, and `mobilized` decompose into the categories above plus event history:

- `recently_dispossessed` -> loss event + changed `claims(...)` rows + likely `power_status:declining` or `fragile`
- `leadership_disputed` -> `agenda:settle_succession` and/or `agenda:seize_leadership`
- `under_investigation` -> event history plus `agenda:conceal_exposure`, `agenda:negotiate`, or no tag until a package reads it
- `negotiating` -> `agenda:negotiate`
- `mobilized` -> `agenda:mobilize`

If a passive faction condition later proves package-load-bearing and cannot decompose cleanly, it should be proposed as a named category with a clearance contract rather than smuggled into a catch-all `state`.

---

## Durable Identity Categories

### `ideology` (Multi-Valued, Durable)

The faction's legitimizing worldview: what it claims is right, necessary, sacred, efficient, natural, or worth organizing around. Ideology is not the same as current agenda; a `traditionalist` faction can pursue `agenda:reform_internal` when it believes reform preserves the tradition.

| Tag | Meaning / Package Reading |
|---|---|
| `authoritarian` | Legitimizes hierarchy, command, obedience, and coercive order. |
| `egalitarian` | Legitimizes equal standing, distributed rights, or anti-elite politics. |
| `traditionalist` | Legitimizes inherited custom, lineage, ritual, or precedent. |
| `progressive` | Legitimizes deliberate reform, novelty, or future-oriented social change. |
| `theocratic` | Grounds authority in sacred law, divine mandate, priesthood, or revelation. |
| `secularist` | Grounds authority outside priestly or sacred institutions. |
| `nationalist` | Organizes around a people, homeland, nation, tribe, or civic identity. |
| `cosmopolitan` | Organizes around cross-border, cross-culture, or universalist belonging. |
| `imperial` | Legitimizes expansion, dominion, tributary hierarchy, or civilizing mission. |
| `communalist` | Prioritizes local commons, mutual obligation, kin/community survival. |
| `mercantilist` | Prioritizes trade advantage, market control, profit, or commercial sovereignty. |
| `technocratic` | Legitimizes expert rule, optimization, planning, or technical competence. |
| `revolutionary` | Legitimizes overthrow of the present order and rupture with existing authority. |
| `restorationist` | Legitimizes return to a prior order, lost dynasty, old law, or remembered compact. |
| `isolationist` | Prioritizes boundary maintenance and protection from outside contamination/control. |

**Compositions are normal.** A faction can be `theocratic` + `authoritarian`; a trade league can be `mercantilist` + `cosmopolitan`; a rebel order can be `revolutionary` + `nationalist`.

**Dropped / folded candidates.**

- `populist`: rhetorical style more than durable worldview; usually composes from `egalitarian`, `nationalist`, `revolutionary`, and prose.
- `libertarian`: too modern-coded; split case-by-case into `egalitarian`, anti-state prose, or `mercantilist`.
- `fanatical`: intensity belongs in prose, `power_status`, agenda urgency, or event history.

### `resource_base` (Multi-Valued, Durable)

The durable sources of capacity the faction can draw on. This does not say what it owns in detail; it says what package branches can assume it can mobilize.

| Tag | Meaning / Package Reading |
|---|---|
| `capital` | Money, credit, stored wealth, liquidity, or financial leverage. |
| `force` | Fighters, guards, troops, enforcers, weapons, coercive capacity. |
| `information` | Intelligence, archives, surveillance, secrets, informants, analysis. |
| `faith` | Religious devotion, ritual authority, sacred legitimacy, pilgrim/donor networks. |
| `industry` | Workshops, factories, production capacity, craft infrastructure. |
| `labor` | Large pools of workers, volunteers, conscripts, members, or retainers. |
| `territory` | Land/resource control as capacity. Specific claims still live in `claims(...)`. |
| `patronage` | Sponsors, donors, noble backers, corporate parents, state subsidy. |
| `bureaucracy` | Records, offices, permits, administrators, procedural control. |
| `technology` | Advanced tools, machines, infrastructure, engineered systems. |
| `specialized_knowledge` | Rare expertise, scholarship, occult lore, trade secrets, or doctrine. |
| `criminal_network` | Smuggling, black markets, fences, protection rackets, illicit logistics. |
| `supply_lines` | Logistics, transport, warehousing, food/fuel/material throughput. |
| `mobility` | Ships, vehicles, mounts, portals, couriers, roads, or rapid movement capacity. |

**Boundary with `role.resources`.** `role.resources` is a character wealth tier. `resource_base` is a faction capacity source. A destitute prophet can lead a faction with `faith`; a wealthy noble can personally have `role.resources:wealthy` while their faction lacks `capital`.

**Boundary with pair-tags.** `resource_base:territory` means territorial control is a meaningful capacity source; actual control/contest is still represented by `claims(faction -> place)` rows.

### `legitimacy` (Exclusive, Durable)

The faction's recognition posture relative to the dominant local legal/social order. This category is exclusive because the runtime usually needs one default answer to "can this faction act in public without being treated as inherently illicit?"

| Tag | Meaning / Package Reading |
|---|---|
| `state_recognized` | Formally recognized by the dominant legal/political order. |
| `customary` | Not necessarily state-chartered, but locally accepted by tradition or community practice. |
| `tolerated` | Known and allowed to operate, but without strong formal recognition or social trust. |
| `shadow_legal` | Partly legal, deniable, gray-market, or protected by loopholes/corruption. |
| `underground` | Hidden or unofficial; exposure changes its risk profile. |
| `outlaw` | Known and proscribed; public association is dangerous or criminalized. |
| `contested` | Competing authorities disagree about its legitimacy; recognition is unstable. |

**Scope caveat.** Legitimacy is always a simplification of a scoped reality. If a faction is legal in one polity and outlawed in another, the baseline tag should describe the dominant story-local order; scoped exceptions belong in prose, pair-tags, or later audience-scoped legitimacy substrate if package pressure demands it.

### `operational_mode` (Exclusive, Durable)

How the faction normally operates. This is distinct from legitimacy: an `outlaw` faction can act overtly, and a `state_recognized` intelligence office can act covertly.

| Tag | Meaning / Package Reading |
|---|---|
| `overt` | Acts openly under its own name; public footprint is normal. |
| `covert` | Acts through secrecy, fronts, cells, aliases, or deniable agents. |
| `hybrid` | Maintains both public and hidden operating surfaces. |

**Rejected split:** `cellular`, `hierarchical`, `networked`, and `centralized` describe organization structure. They can become their own category only if package gates need that distinction; do not overload `operational_mode`.

---

## Ephemeral Strategic Categories

### `power_status` (Exclusive, Ephemeral)

The faction's current strategic strength and trajectory. This is a pressure/branching hint, not a precise power score. A new major event should usually replace the old row.

| Tag | Meaning / Package Reading |
|---|---|
| `dominant` | Sets terms locally; rivals react to it. |
| `ascending` | Gaining power, territory, members, resources, or legitimacy. |
| `stable` | Operationally steady; neither surging nor collapsing. |
| `pressured` | Under meaningful stress, but not yet losing the overall position. |
| `declining` | Losing ground, influence, cohesion, resources, or legitimacy. |
| `fragile` | Can still act, but one shock could break its position. |
| `collapsed` | No longer coherent as an actor, though remnants/history may persist. |

**Why exclusive despite nuance?** "Dominant but brittle" is a real story reading, but the tag should encode the strongest branch-relevant answer. Keep the nuance in prose/events unless packages start needing a second axis such as resilience.

### `agenda` (Multi-Valued, Ephemeral)

An active campaign the faction is currently pursuing. Agendas are verbs in noun clothing: they should imply possible Orrery packages. Do not tag every routine task; tag only campaigns a package might read.

| Tag | Meaning / Package Reading |
|---|---|
| `expand_control` | Acquire territory, influence, markets, offices, converts, or reach. |
| `consolidate_control` | Secure recent gains, normalize rule, bind members, stabilize holdings. |
| `infiltrate` | Place agents or influence inside a target group/place/system. |
| `seize_leadership` | Take control of a faction, office, throne, board, cell, or command. |
| `settle_succession` | Resolve contested leadership or inheritance. |
| `recover_losses` | Retake lost assets, territory, status, hostages, members, or rights. |
| `negotiate` | Seek settlement, alliance, treaty, contract, ransom, or accommodation. |
| `mobilize` | Prepare forces, members, resources, or logistics for imminent action. |
| `investigate` | Discover facts, identify actors, audit records, or locate hidden causes. |
| `recruit` | Grow membership, hire agents, convert believers, enlist workers/fighters. |
| `extract_resources` | Draw value from people, territory, infrastructure, debt, or captured assets. |
| `sabotage` | Disrupt a rival's operation, infrastructure, reputation, supply, or cohesion. |
| `suppress_dissent` | Silence, coerce, appease, or eliminate internal opposition. |
| `conceal_exposure` | Contain scandal, leak, investigation, compromised identity, or evidence. |
| `reform_internal` | Change doctrine, governance, membership rules, methods, or priorities. |
| `secure_alliance` | Build or preserve alliance, patronage, clientage, or coalition support. |
| `enforce_claim` | Turn a claim into practical control or punish violation of a claim. |
| `protect_asset` | Guard a person, place, object, secret, route, or institution. |
| `retaliate` | Punish injury, betrayal, insult, attack, default, or trespass. |

**Naming replacements.**

- `revanchist` -> `recover_losses`
- `coup` -> `seize_leadership`
- `succession` -> `settle_succession`
- `infiltration` -> `infiltrate`
- `expansion` -> `expand_control`
- `consolidation` -> `consolidate_control`

The replacement names are longer, but they are easier to guess without peeking and read more directly as package inputs.

---

## Clearance Contracts

Faction ephemerals need a clearance/replacement plan before they ship as seeded tags. The state vocabulary's rule applies here too: clearance belongs to the tag row's `clear_on`, not to a central event table. Event names below are design targets unless a migration already registers them.

Migration 052 seeds `power_status` and `agenda` rows with `clearance_kind='semantic'`, `reapplication_policy='replace'`, and per-row `clear_on.description` text so runtime bestowal can begin without duration overrides or unregistered event dependencies. A later clearance migration can promote specific rows to event clearance after the event names are collapsed and registered.

### `power_status`

`power_status` should usually be replaced rather than cleared to absence. A faction without an active power row is "unknown," not necessarily stable.

| Tag | Clears / Replaces On |
|---|---|
| `dominant` | major defeat, loss of recognition, successful rival expansion, leadership break |
| `ascending` | consolidation into `dominant`/`stable`, setback into `pressured`/`declining` |
| `stable` | any major event that changes trajectory |
| `pressured` | pressure resolved, defeat worsens to `declining`/`fragile`, recovery to `stable` |
| `declining` | recovery, collapse, or decisive restructuring |
| `fragile` | recovery/stabilization, collapse, or external rescue |
| `collapsed` | dissolution into history, refounding as a new faction, or revival event |

### `agenda`

Every agenda should name at least one success, failure, abandonment, or supersession event before migration. Suggested clearance event families:

| Agenda | Example Clearing Events |
|---|---|
| `expand_control` | `claim_established`, `expansion_abandoned`, `major_defeat` |
| `consolidate_control` | `control_consolidated`, `faction_realignment`, `major_defeat` |
| `infiltrate` | `infiltration_completed`, `infiltration_exposed`, `operation_abandoned` |
| `seize_leadership` | `leadership_changed`, `coup_defeated`, `faction_realignment` |
| `settle_succession` | `succession_settled`, `succession_crisis_deepened` |
| `recover_losses` | `loss_recovered`, `recovery_abandoned`, `settlement_reached` |
| `negotiate` | `agreement_reached`, `talks_failed`, `negotiation_abandoned` |
| `mobilize` | `mobilization_completed`, `stand_down_ordered`, `major_defeat` |
| `investigate` | `investigation_resolved`, `investigation_blocked`, `case_abandoned` |
| `recruit` | `recruitment_drive_completed`, `recruitment_disrupted` |
| `extract_resources` | `extraction_completed`, `route_disrupted`, `asset_lost` |
| `sabotage` | `sabotage_completed`, `sabotage_failed`, `operation_exposed` |
| `suppress_dissent` | `dissent_suppressed`, `crackdown_failed`, `settlement_reached` |
| `conceal_exposure` | `scandal_contained`, `exposed`, `investigation_resolved` |
| `reform_internal` | `reform_completed`, `reform_defeated`, `faction_realignment` |
| `secure_alliance` | `alliance_brokered`, `alliance_failed`, `alliance_broken` |
| `enforce_claim` | `claim_enforced`, `claim_abandoned`, `claim_lost` |
| `protect_asset` | `asset_secured`, `asset_lost`, `threat_removed` |
| `retaliate` | `retaliation_executed`, `truce_reached`, `retaliation_abandoned` |

This table is deliberately a clearance design, not a migration. A later migration should either register the event types it uses or collapse them onto already-registered event names.

---

## Legacy Mapping and Table Cleanup

### Category Mapping

| Legacy Category | Replacement |
|---|---|
| `ideology_axis` | `ideology` |
| `power_posture` | `power_status` |
| `legitimacy_status` | `legitimacy` |
| `operational_secrecy` | `operational_mode` |
| `resource_class` | `resource_base` |
| `hidden_agenda_class` | `agenda` |
| `state` (faction only, if any rows exist) | no tag replacement; decompose into `power_status`, `agenda`, pair-tags, event history, or prose |
| `history_class` | no tag replacement; migrate to `world_events` / prose |

The faction-only `state` row is a legacy draft category, not the canonical
character `state` category. A future implementation migration should either
verify that no `(entity_kind='faction', category='state')` rows exist in target
slots or mark the faction category deprecated with no replacement before the
backfill runs.

### Example Value Mapping

| Legacy / Sample Value | New Reading |
|---|---|
| `revanchist` | `agenda:recover_losses` |
| `infiltration` | `agenda:infiltrate` |
| `coup` | `agenda:seize_leadership` |
| `succession` | `agenda:settle_succession` |
| `expansion` | `agenda:expand_control` |
| `consolidation` | `agenda:consolidate_control` |
| `network` | `resource_base:criminal_network`, `resource_base:information`, or `resource_base:patronage` depending on actual usage |
| `state_recognized` | `legitimacy:state_recognized` |
| `underground` | `legitimacy:underground` or `operational_mode:covert` only if secrecy, not recognition, is the key fact |
| `hidden` / `secretive` | `operational_mode:covert` |

### Deterministic Seeding Rules

- Seed `resource_base:territory` when the faction has at least one active
  `claims(faction -> place)` row, or when legacy prose/column data explicitly
  names territorial control as a capacity source. Do not infer it merely from
  having a `primary_location` or `operates_from` base.
- Seed `operational_mode` from existing `operational_secrecy` tag rows when
  present. The `factions` table has no source column for this axis, so slots
  without legacy tags should leave `operational_mode` unset unless prose review
  supplies a clear mapping.

### `factions` Table Cleanup

Move to tags:

- `ideology` -> `ideology`
- `power_level` -> `power_status`
- `hidden_agenda` -> `agenda`
- `resources` -> `resource_base`

No direct table column feeds `operational_mode`; it comes from the legacy
`operational_secrecy` tag category or later prose/manual review.

Do not move to tags:

- `history` -> `world_events` / summary prose
- `current_activity` -> usually `agenda`; otherwise prose
- `territory` -> `claims(faction -> place)` and `operates_from(faction -> place)`

Keep as columns:

- `id`, `name`, `entity_id`
- `summary`
- `primary_location`
- `created_at`, `updated_at`, `extra_data`

Preflight command:

- `nexus faction-audit --slot N` performs a read-only dry run over the legacy
  faction columns, existing `claims` / `operates_from` pair-tags, and legacy
  faction tag categories. Review its JSON output before any destructive data
  rewrite or column-drop migration.
- `nexus faction-manifest --slot N --output PATH` folds the audit into a
  read-only migration manifest with stable operation IDs. It separates
  deterministic entity-tag inserts from review-required tag candidates,
  pair-tag target resolution, prose/world-event preservation, structured
  remainders, and no-replacement legacy tag drops. The manifest is a
  review/apply contract; it does not authorize destructive mutations by itself.
- `nexus faction-apply --slot N` validates the same manifest and reports which
  deterministic `insert_entity_tag` operations would write. Add `--manifest
  PATH --execute` to insert only the reviewed ready rows into `entity_tags` with
  `source_kind=system`. Review-required operations, pair-tags, prose
  preservation, structured remainders, legacy-tag drops, and existing
  exclusive-category conflicts are skipped rather than inferred. This still
  does not clear legacy columns or old tag rows.

Runtime write boundary:

- New faction creation and faction state updates should not write
  `ideology`, `history`, `current_activity`, `hidden_agenda`, `territory`,
  `power_level`, or `resources`. New prose goes in `summary` / `extra_data`
  when it is descriptive context; package-relevant facts go through
  `orrery_tags` or reviewed pair-tag/world-event paths.
- Migration 053 removes the `factions.power_level` default so omitted runtime
  inserts do not silently create fresh legacy `0.5` values.

---

## Mechanical Implications

1. **Registry categories.** Migration 043 registers the six categories used here, and migration 052 seeds the 65 canonical tag rows. The draft intentionally avoids adding faction `state`; any future seventh category needs a separate category-registration migration.
2. **Cardinality enforcement.** `legitimacy`, `operational_mode`, and `power_status` are exclusive design categories. Until the `tags.cardinality` column ships, application writers must clear sibling rows explicitly, as with current exclusive character categories.
3. **Slot 2 backfill.** Existing faction tags should be classified as keep/rename/drop/convert-to-pair-tag. Ambiguous `resource_class:network` rows need manual review because "network" may mean information, patronage, criminal logistics, or membership.
4. **Package gates.** Packages should prefer category-specific predicates when they care about the axis. A gate that cares whether a faction is public should read `operational_mode`, not `legitimacy`; a gate that cares whether public association is risky should read `legitimacy`.
5. **Status flavor.** Scope-bound `status:<level>(subject -> faction)` derives formal/informal flavor from the faction's `legitimacy` and `operational_mode`. Do not split `status:senior` into formal/informal variants.
6. **Retrograde.** Stage R1/R2 seed generation can use the durable categories freely. Ephemeral `power_status` and `agenda` should be generated sparingly and anchored to a recent or active `world_event`, not sprinkled as timeless backstory.

---

## Open Decisions

1. **Legitimacy scope.** If stories frequently need "legal here, outlaw there," single-entity `legitimacy` may need a scoped pair-tag layer. Do not build that until a package requires it.
2. **Organization structure category.** `centralized`, `cellular`, `networked`, and `hierarchical` are plausible but currently unadmitted. Add only if package branches read them differently from `operational_mode`.
3. **Power-status resilience.** If "dominant but brittle" becomes a package-relevant distinction, split resilience into its own axis rather than bloating `power_status`.
4. **Clearance event collapse.** The agenda clearance table intentionally over-names events for readability. A migration pass should collapse synonyms onto existing event types wherever possible.

---

## Count

Ideology 15 + resource_base 14 + legitimacy 7 + operational_mode 3 + power_status 7 + agenda 19 = **65 faction anchors**.
