# Orrery Needs

Design rationale for the physiological and interpersonal need packages: **SLEEP, EAT, DRINK, SOCIALIZE, INTIMACY**. Implementation lives in `nexus/agents/orrery/needs.py` and migrations 028, 029, 032. The mechanical catalog (priorities, branches, magnitudes, scene-pressure stubs) is `docs/orrery_packages.md`. This doc captures the architectural rationale the catalog doesn't carry.

Companion to `docs/orrery_design_plan.md`. Promoted from drafting work in `temp/orrery/` after implementation landed in PRs #233 and #243.

---

## Core Principle

**The substrate models conditions and accumulating pressure. The storyteller authors consequence.**

Orrery does not resolve what happens "in the bar" when Pete goes to socialize. It models that Pete's socialize debt was high, the threshold was met, a gate condition fired, and a branch was chosen — at which point control passes to Skald. The simulation accumulates pressure; the storyteller decides the shape of release.

This principle has direct implementation consequences worth knowing before tweaking:

- **`PresentActorPolicy.STORYTELLER_PRESSURE`** injects severity tags into Skald's prompt rather than resolving on-screen needs as if they were off-screen ticks. The on-screen actor's needs are storyteller material, not resolver material. The resolver excludes present actors before actor-only templates are evaluated; a separate prompt formatter surfaces the severity state to Skald.
- **INTIMACY is single-slot.** There is no binding-composer pairing the acting character with a partner; the partner emerges (or doesn't) in storyteller prose. Computing "viable intimate partner" at the binding composer would be both technically uncomfortable (the closest thing to compatibility scoring NEXUS would have) and architecturally unnecessary.
- **The maintenance pass computes debt accrual** from elapsed time since `last_evaluated_at`, but the *narrative effect* of that debt is the storyteller's call. A character with `intimacy_starved_3_severe` doesn't have to act on it; the tag is prompt material.

This is also what distinguishes NEXUS from Dwarf Fortress on this axis. DF generates compelling stories about emergent relationships because it runs the full compatibility-scoring/pairing/family-formation simulation; it also generates absurdity (the cat that triggers a tantrum spiral, the dwarf who marries his cousin out of proximity-driven affection scores), and the player tolerates it. NEXUS has different goals — characters need plausible interior lives the narrator can draw on, not autonomous pairing.

---

## The Pete Worked Example

The canonical illustration of what this architecture does and does not do. Each phase shows what the substrate would record and what the storyteller would author. When a future maintainer wonders "should the simulation just pair Pete with someone in the bar?", the answer is in Phase 4.

**Phase 1 — Hermit life (pre-recruitment).** Pete carries tags `extroversion_low`, `libido_moderate`, `closeted`, plus a `preferences.partner_pattern` field describing strong same-sex preference with occasional opposite-sex receptivity. The SOCIALIZE counter increments very slowly (low extroversion → high threshold), so weeks of isolation accumulate only mild severity. The INTIMACY counter increments normally, but the `closeted` suppressor closes its gate completely. The body wants; the simulation registers the want; no resolution attempts to satisfy. The storyteller has all this data as context for Pete's prose appearances — the grumpy hermit has substrate justification beyond just personality.

**Phase 2 — Submarine confinement.** Forced co-presence with the party largely meets the SOCIALIZE need (low-extroversion characters need less and what they get is more than enough). INTIMACY continues climbing; the gate stays suppressed. The submarine offers no `preference_compatible_setting`, so even if `closeted` lifted tomorrow, the binding composer couldn't find a viable target. Pete's grumpiness compounds. The storyteller sees the accumulated pressure (high `intimacy_starved` severity, long-tenure `closeted` tag, no satisfying contact) and uses it for character beats. Pete being "notably grumpy" has substrate provenance.

**Phase 3 — Preferences clarify narratively.** The storyteller authors the moment where Pete's preferences become legible. The database gets updated; perhaps a more specific `partner_pattern` is recorded, or the closeted tag gets a more specific subtype. *This is the simulation's data getting richer through narrative authoring* — the canonical pattern for character development in NEXUS.

**Phase 4 — Shore leave intervention.** The player plots a bar-hopping path through a setting flagged as preference-compatible. Pete is now in `in_location_class("intimate_social_venue")` with an appropriate setting tag. His `intimacy_starved_3_severe` makes the gate's pressure clause pass. **But the gate still fails**, because `closeted` is an active suppressor. What changes is that the storyteller, present in the on-screen scene, can now author the suppressor's lifting as a scene outcome — the player has created the conditions where that authoring makes narrative sense. The simulation provides the conditions; the storyteller writes the resolution. The closeted tag clears as authored narrative consequence, not simulation outcome.

**Phase 5 — Aftermath.** Closeted is gone (durable narrative consequence). The INTIMACY counter is reset (authored). Pete's emotional state is updated. For future ticks, his gate is open, the binding composer can find viable matches when he's in appropriate settings, and the simulation routes him to satisfying behavior at appropriate frequency.

**What the substrate did:** tracked accumulating pressure, recorded suppression, made the data legible to the player and the storyteller.

**What the substrate did *not* do:** pair Pete with anyone, make him come out, compute compatibility scores, generate consequences from the encounter.

---

## Data Model

### `character_need_states` Table

Per-character per-need state keyed by `(character_entity_id, need_type)`. `need_type` is a Postgres enum:

```sql
CREATE TYPE character_need_type AS ENUM (
    'sleep', 'hunger', 'thirst', 'socialize', 'intimacy'
);

CREATE TABLE character_need_states (
    character_entity_id bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    need_type           character_need_type NOT NULL,
    debt_score          numeric(8, 2) NOT NULL DEFAULT 0,
    last_evaluated_at   timestamptz NOT NULL,
    last_fulfilled_at   timestamptz,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (character_entity_id, need_type)
);
```

**Bodyform immunity is row-presence, not NULL.** A character that doesn't track a need (an android with no sleep need; an asexual character with no intimacy track) simply has no row for it. This is cleaner than nullable columns whose semantics every query has to remember.

**Storage is hybrid: timestamp ground truth + debt counter.** The `debt_score` is intentional state, not a disposable cache. Each maintenance pass:

1. Computes elapsed world-time since `last_evaluated_at`
2. Accrues debt exactly once for that interval
3. Stamps `last_evaluated_at = current_world_time`

A skipped tick gets caught up on the next pass; a retried tick doesn't double-count. The paired timestamp is what prevents drift; the counter is what enables the maintenance pass to make decisions without re-deriving every time.

**`debt_score` is hours-equivalent**, not necessarily literal wall-clock hours. For hunger and thirst, default fulfillment rules can discharge it to zero in ordinary cases. For sleep, the same plumbing supports lower discharge rates in austere conditions, partial discharge from a nap, and Sunhelm-style quality modifiers.

### Fulfillment Effects

Fulfillment branches do not write `character.sleep_debt = 0` directly. They emit a typed fulfillment effect (e.g., `need.fulfilled = {"type": "sleep", "quality": "rough", "duration_hours": 6}`) that the commit/maintenance helper translates into:

- Debt reduction (full or partial per the quality + duration)
- `last_fulfilled_at` timestamp update
- Severity-tag clearance for the affected track
- Optional ephemeral application (`well_rested`, `recently_fed`, `recently_drunk`) that serves as a "don't immediately re-trigger" guard for the next maintenance pass

This keeps the state-delta contract explicit instead of opening the door to arbitrary character-column writes.

---

## The Graduated Severity Pattern

Severity tags follow a uniform, self-explanatory, alphabetically-self-sorting convention. The level number does double duty as both the human-readable severity indicator and the input parameter for the threshold predicates.

```
sleep_deprived_1_mild        ↔  has_severity_tag_at_or_above("sleep_deprived", 1)
sleep_deprived_2_moderate    ↔  has_severity_tag_at_or_above("sleep_deprived", 2)
sleep_deprived_3_severe      ↔  has_severity_tag_at_or_above("sleep_deprived", 3)
sleep_deprived_4_critical    ↔  has_severity_tag_at_or_above("sleep_deprived", 4)
```

Same shape for `hungry_*`, `thirsty_*`, `under_socialized_*`, `intimacy_starved_*`.

**Tags are mutually exclusive within a track.** A character is at exactly one level of `sleep_deprived` at any time (or none, if not deprived). The maintenance pass reads `debt_score`, computes the appropriate tier, applies the one correct tag, and removes any other tag from the same track.

### Threshold Tables (Illustrative)

Tune against actual play; these are the seed values.

```
sleep_debt   → 0-15h none, 16-29h mild, 30-47h moderate, 48-71h severe, 72+h critical
hunger_debt  → 0-7h  none, 8-15h mild,  16-29h moderate, 30-47h severe, 48+h  critical
thirst_debt  → 0-3h  none, 4-7h  mild,  8-15h moderate,  16-23h severe, 24+h  critical
```

Thirst ramps fastest because it should — water deprivation kills faster than starvation in any realistic biology. SOCIALIZE and INTIMACY thresholds are modulated by per-character tags (`extroversion_*`, `libido_*`) — see Modulator Tags below.

### Substrate Predicates

```python
has_severity_tag(prefix: str, slot: Slot) -> Predicate
    # True if any severity tag with the given prefix is present

has_severity_tag_at_or_above(prefix: str, level: int, slot: Slot) -> Predicate
    # True if the tag's numeric segment >= the threshold
```

Both are cheap — string operations only, no joins. The tag IS the cached form for fast gate predicates; gates ask "do you have `sleep_deprived_3_severe`?" rather than "how many hours of debt do you have?"

---

## The Stimulant Gate-Suppression Pattern

A generalizable architectural pattern worth naming. The `cns_stimulated` ephemeral (or any future analog: `pain_suppressed`, `fatigue_masked`, `hunger_inhibited`) does **not** alter the underlying `debt_score`. The counter continues to track actual physiological state. What the ephemeral does is appear in the SLEEP template's gate as `NOT(has_ephemeral("cns_stimulated"))`, suppressing the gate while the chemical is active.

**The crash falls out naturally.** When `cns_stimulated` expires, the gate opens, the accumulated `sleep_debt` is potentially severe, and the next-eligible tick fires SLEEP at high magnitude. That's the chemical-crash modeled as a single mechanical fact: the suppressor lifted; what was being deferred now demands attention. No special-case logic, no separate crash template — just the deferred state catching up.

**The pattern generalizes.** Any "push through the body's protest" mechanic — combat stims that mask wounding, performance enhancers that defer exhaustion, magical bindings that suspend hunger — follows the same shape: an ephemeral that suppresses a need-template's gate, expiring naturally, letting the deferred consequence land. Worth keeping this in mind whenever a new template wants to model a temporary override; the suppressor pattern is usually the right shape over carve-out logic.

The same pattern applies to INTIMACY suppressors (`closeted`, `vow_of_celibacy`, etc.) — counter continues, gate closes, lifting is a discrete narrative event. See Intimacy Suppressors below.

---

## The Five Needs

Mechanical details (gates, branch conditions, magnitudes, scene-pressure stubs) live in `docs/orrery_packages.md`. This section is the orientation layer.

Home/work routines are now driven by `character_routine_anchors` rather than by place-class inference. The needs packages read the actor's current place and pair-tags (`resides_at`, place functions, travel state), while `ROUTINE_COMMUTE` handles movement between scheduled anchors. In practice this means a normal citizen can commute home before EAT/SLEEP fire, while a character with `nomadic`, `none`, or `works_from_home` policy does not get forced into a generic 9-5 loop.

### SLEEP (priority 25)

The architecturally most significant of the basic-needs templates. Sleep is the substrate's most reliable source of small narrative texture — most ticks where it fires produce no prose, but the cumulative record of *where* a character has been sleeping is one of the densest queryable signals about their life situation.

- **Gate**: in local sleep window AND not `well_rested`, OR `has_severity_tag("sleep_deprived")` at any level. Plus `NOT(has_ephemeral("cns_stimulated"))` and `NOT(has_inbound_pair_tag("hunting", Slot.ACTOR))`.
- **Sleep schedules are tag-based**: `sleep_schedule:diurnal`, `sleep_schedule:nocturnal`, `sleep_schedule:nightshift`, `sleep_schedule:siesta`, `sleep_schedule:polyphasic`. Tag picks a profile; the profile (defined in `nexus.toml`) holds the actual windows. Tagless characters use the global default.
- **Sleep location is a mood lever.** The `slept_rough` tag applied by rough-sleep and collapse branches is the DF-inspired mood signal — downstream templates and the narrator can read "this character has been sleeping poorly." Several consecutive `slept_rough` ticks give a character a different emotional register than waking from their own bed.
- **Branches** discriminate by location and severity: collapse-into-sleep (severe-deprivation), at home with partner, at home alone, lodgings/safe-house, sleep rough.

### EAT (priority 22)

Architectural sibling to SLEEP. Same severity-tag gate pattern, location-discriminated branches, plus the preferences mechanic that turns routine meals into a steady source of small character-specific beats.

- **Gate**: in local mealtime window OR `has_severity_tag("hungry")`. Plus `NOT(has_ephemeral("recently_fed"))`.
- **Mealtime patterns** are per-character JSON (`characters.mealtime_pattern`) supporting cultural variation: standard three-meal, siesta, multi-small-meal, fasting practices.
- **Preferences** integration: each branch emits a `preferences_evaluated` context (`household_meal`, `wild_meal`, `rations_meal`, etc.). The promote discriminator and narrator both read this plus the character's `preferences` JSON — preference-clash or preference-delight can affect magnitude and shape prose.
- **Branches**: ravenous (severe-hunger), family meal, eat at home alone, eat at workplace, public dining, forage/hunt (gated by capacity tags), travel rations, opportunistic.

### DRINK (priority 24)

Slightly higher priority than EAT because thirst ramps faster. Structurally simpler — fewer branches, faster cooldown, more uniformly low magnitudes because routine hydration is rarely narratively interesting on its own.

- **Gate**: `has_severity_tag("thirsty")` OR routine (no time window — humans drink throughout the day). Plus `NOT(has_ephemeral("recently_drunk"))`. Routine thirst yields to an otherwise-due home/public meal unless thirst is severe; the dinner package gets to carry the ordinary "food and drink together" beat, while dehydration still interrupts.
- **Why not merged with EAT?** Different ramping curves, different cultural rhythms (water all day vs. meals at mealtimes), different fulfillment-affordances. Reuse belongs in primitives and maintenance helpers; merging would create one template with awkwardly disjoint branches.
- **Branches**: desperate-drink (severe-thirst), drink socially in public room, public/wild water source, routine drinking.

### SOCIALIZE (priority 18)

Routine-trigger gate plus pressure gate. The routine clause (`count_co_located(1) AND NOT(recently_socialized)`) means SOCIALIZE can fire just because someone is around — capturing the organic case where company is present and the character engages. Without it, SOCIALIZE only fires when severity-pressure builds, which misses the "Pete is on the submarine and the party is right there" pattern.

- **Gate**: `has_severity_tag("under_socialized")` OR (co-located AND not recently socialized). Plus `NOT(has_inbound_pair_tag("hunting", Slot.ACTOR))` and `NOT(has_ephemeral("grieving"))` (MOURN_LOSS owns that space).
- **Threshold mapping is per-character** via `extroversion_*` tags — see Modulator Tags.
- **Parasocial branch** (reading, listening to a recording, watching a serial) uses partial decrement (`socialize_debt_delta: -0.4`) rather than full reset — captures "takes the edge off" without fully discharging.
- **Branches**: seek-after-critical-isolation, engage with present company, go where people are (tavern/square/market), reach out to a contact, parasocial.

**Social hydration policy.** SOCIALIZE should satisfy ordinary loneliness without
forcing every implied acquaintance into the database. Branch selection uses four
layers, in order: real co-located NPCs when present; explicit `contact:social`
edges when the actor has one; public or semi-public place affordances where
off-book people can satisfy the need without a concrete character row; and
parasocial media/ritual contact as a partial fallback. Off-book people are lazily
hydrated into entities only when Skald attends to them, the interaction repeats,
or another package needs a concrete target. This keeps the routine social loop
useful while preserving the broader dehydrated-entity principle used for implied
spouses, families, coworkers, neighbors, and casual friends.

### INTIMACY (priority 16)

The most sensitive in the catalog. Single-slot template (ACTOR only); branches that involve a partner read partner identity from the actor's relationship data. **No binding-composer pairing** — see Core Principle above.

- **Gate**: `has_severity_tag("intimacy_starved")` AND `NOT(has_any_intimacy_suppressor())` AND not in a blocking state (recent satisfaction, inbound `hunting`, wounded, `grieving`).
- **Modulator**: `libido_*` tags shift thresholds; `libido_absent` means the counter is ignored at hydration and the gate never fires.
- **Branches** include partner-present (full reset), preference-compatible-setting (partial decrement — going is partial fulfillment; what happens at the venue is storyteller territory), contracted intimacy (gated on absence of vows), solo (partial decrement), let-the-want-stay (counter unchanged; chronic-deferral becomes narratively visible over many ticks).
- **`partnered_exclusively`** is a semi-suppressor — gate stays open, but routes exclusively to partnered branches. Modeled as an extra gate clause on non-partner branches rather than a suppressor proper.

---

## Modulator Tags

Per-character durable tags applied at character creation, stable through the simulation. They modulate how fast the relevant counter ramps and at what value each severity tag triggers — without changing the underlying accrual rate.

### Extroversion (Modulates SOCIALIZE Threshold Mapping)

| Tag | Semantic | Threshold mapping |
|---|---|---|
| `extroversion_low` | Hermit-tendency; needs less social contact | Severity triggers at ~2× default debt values |
| `extroversion_moderate` | Default; most characters | Default mapping |
| `extroversion_high` | Strongly needs frequent contact | Severity triggers at ~0.5× default debt values |

An `extroversion_low` character can go weeks before reaching `under_socialized_2_moderate`; an `extroversion_high` character reaches the same severity in days. Counter accrues at the same rate; threshold mapping is per-character.

### Libido (Modulates INTIMACY Threshold Mapping)

| Tag | Semantic | Threshold mapping |
|---|---|---|
| `libido_absent` | Asexual or equivalent; need does not apply | Counter ignored at hydration; severity never applies |
| `libido_low` | Present but easily satisfied; long intervals | Severity triggers at ~2× default debt values |
| `libido_moderate` | Default | Default mapping |
| `libido_high` | Strong need; shorter tolerance | Severity triggers at ~0.6× default debt values |

`libido_absent` is the cleanest immunity pattern — maintenance pass skips severity computation entirely. Unlike `bodyform.lineage:inorganic` (categorical embodiment), `libido_absent` is about orientation/identity and can apply to fully embodied characters.

---

## Intimacy Suppressor Vocabulary

Each suppressor closes the INTIMACY gate while present; counter continues to increment regardless. Listed with narrative-valence notes because each has a distinct prose register the narrator should honor.

| Tag | Kind | Clearance | Narrative valence |
|---|---|---|---|
| `closeted` | Durable | Authored narrative consequence | Internal conflict between identity and circumstance; the body wants but the situation forbids; lifting is a significant character beat |
| `vow_of_celibacy` | Durable | Authored narrative consequence | Principled abstention; lifting is a major identity shift |
| `religiously_abstinent` | Durable or ephemeral | Cyclical or authored (Lent, Ramadan, vow-periods) | Cultural/spiritual practice; lifting may be routine and not load-bearing narratively |
| `recently_traumatized_intimate` | Ephemeral | Authored narrative consequence | Body's recoil; lifting requires deliberate narrative care |
| `focus_committed` | Ephemeral | Authored when the project/mission resolves | Voluntary deferral; lifting is just "the work is done now" |
| `partnered_exclusively` | Durable | Narrative consequence (relationship change) | Not a true suppressor — gate doesn't *close*, it routes exclusively to partnered branches |

A `has_any_intimacy_suppressor()` predicate checks the actor for any tag in this controlled list. The list lives as a module constant; adding new suppressors is one place, not scattered across templates.

**Note on grief.** The earlier `grieving_recent_partner` (partner-loss-specific INTIMACY suppressor) has been collapsed into the canonical `grieving` state (see Resolved Decisions below). General `grieving` blocks INTIMACY by reading through the same suppressor list once added. If the partner-loss-specific nuance turns out to be load-bearing in play, `grieving_recent_partner` can be re-distinguished as a child state of `grieving`.

---

## Bodyform Immunity

Single namespace, applied at character-creation time and never removed by the simulation. Immunity belongs in hydration / maintenance (skip these characters at the maintenance pass), not in per-template gate clauses.

| Tag | Immunity scope |
|---|---|
| `bodyform.lineage:inorganic` | Typically all basic needs; legacy `bodyform:android` / `bodyform:construct` proposals canonicalize here |
| `bodyform.condition:undead` | Setting-specific — some variants null all needs, some redefine |
| `bodyform.condition:virtual` | All embodied needs (basic + intimacy); legacy `bodyform:non_corporeal` / `digital_mind` proposals canonicalize here |
| reviewed prose / future modifier | Biologically immortal characters track all needs but may have attenuated curves; no canonical `bodyform:biologically_immortal` alias is automatic |

Setting-specific supernaturals (fae, golems, intelligent undead variants, AI uplifts) get their bodyform tags seeded in setting-specific migrations. The bodyform tags remain durable identity facts; they should not be consulted repeatedly by every basic-needs branch — the maintenance pass simply doesn't create rows for immune needs.

**Implementation status.** Migration 057 installs `orrery_sync_character_need_states()`, rewires the character initializer through that helper, and adds an `entity_tags` trigger so bodyform/modulator changes prune or restore need rows. The resolver also filters stale inapplicable rows at hydration time, so pre-migration or queued data cannot make `inorganic` / `virtual` characters fire ordinary SLEEP / EAT / DRINK packages. `virtual` also suppresses INTIMACY row hydration; SOCIALIZE remains available because disembodied minds can still need company.

---

## DF Heritage and Where NEXUS Diverges

The basic-needs and interpersonal-needs work is architecturally indebted to Dwarf Fortress, both directly (the Sunhelm mod for Skyrim took the same inspiration) and via the broader simulation-as-narrative-engine tradition.

**Borrowed directly:**

- **Graduated severity** — DF's mild → severe → critical thirst progression with associated mood effects
- **Location-as-mood-lever** — where a character sleeps / eats matters; cumulative `slept_rough` produces real character state
- **Preference-driven small beats** — eating their favorite food is a small positive event; eating something they hate is a small negative one; the cumulative effect shapes mood
- **Suppressor-via-tag pattern** — temporary blocks on a need-template's gate that let pressure accumulate during the block
- **Dehydrated-entity pattern for implied others** — `married` + `parent_minor_children` tags imply a household without requiring those entities to exist as rows until narrative attention promotes them

**Deliberately not borrowed:**

- **Full mood/stress/tantrum cascade** — DF runs needs → mood → stress → behavior modification → tantrum spiral autonomously. NEXUS keeps the substrate honest about conditions but leaves the cascade to the narrator at prose-time, drawing on whatever preference / severity data the simulation recorded.
- **Compatibility scoring and autonomous pairing** — DF computes intimate compatibility and forms relationships emergently. NEXUS does not. Significant relationships form through narrative authoring; the substrate records the conditions that make those relationships plausible.
- **Stochastic-pregnancy chaos** and related emergent absurdities — NEXUS prefers narrative coherence over emergent surprise on these axes.

The architecture is **DF-inspired but narrator-led**. The substrate ensures characters have plausible interior lives the narrator can draw on; the narrator decides what those lives mean at any given moment.

---

## Resolved Decisions (Tracking Implementation)

These were surfaced as inconsistencies in `orrery_needs.md` during a follow-up review; decisions made via interview on 2026-05-23. This section records the settled policy and the implementation status.

### R1. `under_active_pursuit` → Inbound `hunting` Pair-Tag

**Category error.** `under_active_pursuit` was a single-entity ephemeral but the concept ("someone is hunting me") is inherently relational — it is an inbound pair-tag from a hunter. Migration 048 renames live `pursuing` pair-tag rows to `hunting`, deprecates the legacy single-entity signal, and the templates gate on `NOT(has_inbound_pair_tag("hunting", Slot.ACTOR))`.

### R2. Grief Vocabulary — Collapsed to Canonical `grieving`

Three names were live for the same concept: `bereaved` (gate-blocker in SOCIALIZE / INTIMACY), `grieving_recent_partner` (INTIMACY suppressor, partner-specific), and an implicit general `grieving` state that the templates assumed but never declared. **Resolved**: canonicalize on `grieving` as the single general-bereavement state. `bereaved` and `grieving_recent_partner` get aliased to `grieving` via the `CANONICAL_TAGS` mechanism. The INTIMACY suppressor fires on canonical `grieving`. Caveat: if play reveals that the partner-loss-specific intimacy recoil is meaningfully different from general grief in this context, `grieving_recent_partner` can be re-distinguished later as a child state.

### R3. `contacts_available` → Derive from `contact` Pair-Tag with Kind Qualifier

The single-entity `contacts_available` tag was overloaded across three templates with three meanings (SLEEP: lodging-providing; SOCIALIZE: reach-out target; INTIMACY: contracted-intimacy access). **Resolved**: drop the overloaded tag. Per-gate predicates filter the actor's outbound `contact:<kind>(char → other_char)` data by relationship kind — `has_contact_of_kind('lodging')` / `'social'` / `'intimate'`. The trait compiler's Contacts MVP writes `character_relationships` rows by default; optional pair-tag writes now require a kind-qualified `contact:<kind>` edge, not the deprecated bare `contact` pair-tag. The old public-mobility affordance is preserved narrowly through `contact:social`; lodging and intimate contacts do not imply general public-flow movement.

### R4. Affective Severity — Hybrid (Graduated Where Packages Gate; Flat Otherwise)

The needs work shipped with a uniform graduated `_N` convention (mild / moderate / severe / critical) because every basic need has a package that gates on severity. For the *affective* cluster (states like fear, anger, longing, curiosity, etc. — the ChatClaude-drafted `state` category), **most affective states stay flat / binary** (purely `STORYTELLER_PRESSURE`; Skald reads them as prompt context). A small subset uses the graduated `_N` convention because a specific package gates on the level — initial example: `grieving_1_mild` through `grieving_4_critical` for MOURN_LOSS branch selection. **Each graduation is a justified choice, not a default.** The principle preserves the graduated machinery's value where it earns its keep without imposing four-level granularity on every emotion.

---

## Open Questions

These were surfaced during design and remain unresolved as of the implementation landing. They should each be filed as issues for explicit tracking rather than buried here.

### 1. DRINK Gate Threshold

The DRINK gate's pressure clause uses `has_severity_tag("thirsty")` — fires at any level. But the mild severity threshold is at debt = 4.0, and DRINK has been observed firing at debt = 2 in earlier reviews. The mismatch between "any severity tag" and the actual debt threshold needs reconciliation: either the gate should explicitly use `has_severity_tag_at_or_above("thirsty", 1)` (matching mild explicitly), or the threshold should drop, or the routine-hydration clause should carry the sub-mild range.

### 2. SOCIALIZE in Confined Settings (the Submarine Problem)

A character in extended close-quarters confinement with the same small group: do they still accumulate socialization debt? At what rate? Three models proposed; none chosen:

- **Co-presence-saturates**: any time the actor is co-located with one or more other characters, the counter stops incrementing. Pete on the submarine never builds SOCIALIZE pressure.
- **Familiarity-discounts**: extended co-presence with the same characters discounts the increment over time. Pete builds *some* pressure on the submarine but less than he would alone.
- **Variety-required**: socialization needs novelty; same-people-same-place ticks contribute partial fulfillment but pressure still builds. Pete on the submarine builds SOCIALIZE pressure despite the company.

### 3. SOCIALIZE vs. the Contact Quartet

The contact quartet (`WARN_ALLY`, `CHECK_ON_DEPENDENT`, `REACH_OUT_TO_KIN`, `CONSULT_RIVAL`) and SOCIALIZE both exist. Two integration models proposed; current implementation uses separation-with-shared-events but the alternative remains open:

- **Separation with shared events** (current): contact templates emit `contact_made` events alongside their relationship-specific events. SOCIALIZE's maintenance pass reads `contact_made` events and decrements its counter accordingly.
- **Absorption into SOCIALIZE**: relationship-maintenance contact (`REACH_OUT_TO_KIN`, casual `CHECK_ON_DEPENDENT`) gets reshaped as SOCIALIZE branches with relationship-type-specific gates; urgent contact templates (`WARN_ALLY`, threat-driven `CHECK_ON_DEPENDENT`, `CONSULT_RIVAL`) stay separate.

Decision depends on whether the current catalog feels redundant in practice or whether the social-vs-informational split pays off.

### 4. Logging Depth for Routine Need Ticks

The basic-needs templates fire for every character every game-day, producing potentially thousands of resolutions per session. The current implementation uses a hybrid policy (severe / unusual / promoted-to-narration always log; routine maintenance updates need state and tags without a `world_events` row) — but the branch-level `log_policy` field is not formalized in the doc and routine ticks may still be logging more than intended. Audit needed.

### 5. ~~`contacts_available` Ambiguity~~ — Resolved

See R3 above. Decision: derive from `contact:<kind>` data with a relationship-kind qualifier.

### 6. Setting-Tag Vocabulary for `in_preference_compatible_setting`

The `in_preference_compatible_setting` predicate matches the actor's `partner_pattern` text against a controlled vocabulary of setting tags carried by places. Starter set was proposed but never formalized: `mixed_oriented`, `same_sex_oriented_male`, `same_sex_oriented_female`, `gender_inclusive`, `family_oriented`, `intimate_social_venue`, `general_social_venue`. Needs registration as a category in the tag vocabulary doc, or storage in a `places.setting_tags` column.

### 7. CONNECT as a Deferred Possibility

The architecture intentionally does not include a CONNECT template. Deep emotional bonds, the development of trust, the slow growth of friendship are storyteller territory. If patterns emerge where the narrator wants substrate data to confirm "have these two been growing closer over the last twenty chunks," CONNECT can be added later as a third graduated-need template. Flag this as something to revisit if the substrate-plus-storyteller model doesn't capture deep-bond-development cleanly in practice.

---

## Related Artifacts

- **`docs/orrery_packages.md`** — canonical mechanical catalog (priorities, branches, magnitudes, scene-pressure stubs). Regenerated by pre-commit hook.
- **`docs/orrery_design_plan.md`** — the broader Orrery system design.
- **`docs/orrery_tag_vocabulary.md`** — registry-level vocabulary for tag categories.
- **`nexus/agents/orrery/needs.py`** — implementation of the maintenance pass, severity tier computation, fulfillment effect handlers.
- **`nexus/agents/orrery/templates.py`** — package templates for SLEEP, EAT, DRINK, SOCIALIZE, INTIMACY.
- **Migrations**:
  - **028** — Sunhelm basic-needs (SLEEP, EAT, DRINK) schema + vocabulary seeding
  - **029** — Sunhelm need-state initialization trigger
  - **032** — Interpersonal needs (SOCIALIZE, INTIMACY) schema + vocabulary seeding
- **Issues / PRs**:
  - **#233** — Sunhelm basic-needs implementation
  - **#243** — Interpersonal needs implementation
  - **#318** — inbound `hunting` pair-tag migration for pursuit-like blockers
- **Drafting record (gitignored)**: `temp/orrery/sunhelm_update_draft.md`, `temp/orrery/orrery_interpersonal_update_draft.md` — full design conversation including multi-model input per open question. Useful for understanding *why* a particular decision was made; not authoritative for *what* shipped (this doc is).
