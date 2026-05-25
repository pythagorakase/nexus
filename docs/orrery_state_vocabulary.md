# Orrery `state` Category — Vocabulary

**Status:** authoritative spec for the `state` category — four clusters (physical, affective, pharmacologic, circumstantial). Companion to `orrery_tag_vocabulary.md` (settled substrate) and `orrery_needs.md` (needs subsystem boundary). Clearance contracts are named inline per anchor. Resolved decisions and migration debts are tracked toward the bottom; remaining open decisions follow.

---

## Scope and Boundaries

`state` is the **only ephemeral character category** — durable categories (bodyform, disposition, capacity, role) answer *what a character is*; `state` answers *what is currently true that wasn't always and won't always be*.

**Membership test (temporal, not semantic):** a state is a character condition that came from a describable event and ends at a describable event — or, for the pharmacologic cluster, at a describable *time*. If you cannot name what clears it, it is not a state: it is a durable tag, a need, or prose.

**Explicitly out of scope — owned by the needs subsystem.** Hunger, thirst, sleep, socialization, and intimacy are *not* `state` tags. They live in `character_need_states` with their own graduated-severity vocabulary (`sleep_deprived_N_label`, `hungry_N_label`, etc.), their own maintenance pass, and their own clearance-by-re-derivation. The needs-owned ephemerals (`well_rested`, `recently_fed`, `recently_drunk`, `slept_rough`) and modulators (`extroversion_*`, `libido_*`) are likewise not general `state` vocabulary. Anything physiological-clock-driven belongs there, not here.

**Dropped during prior passes, not revisited here:** `exhausted` (folds into the sleep need's severity track), `armored` (equipment — items table, not state), `elated` (fails the gating test — no package reads acute joy).

---

## The Degree Question (binary presence vs graduated severity)

The "no numbers" discipline that governs durable categories (`martial:3` was correctly refused) is **not** universal. The needs subsystem proves graduated numeric severity is the right pattern *when a gate thresholds on degree* — `sleep_deprived_3_severe` earns its integer because a branch fires only `has_severity_tag_at_or_above("sleep_deprived", 3)`, and the integer sorts cheaply as a string op.

**Per-anchor test:** is this state a **gate input** or **storyteller-pressure prompt material**?

- **Gate input** (a branch fires only above some severity) → adopt the needs convention: graduated `anchor_N_label` tags, mutually exclusive within track, reusing `has_severity_tag_at_or_above`. Do **not** invent a parallel numbering scheme.
- **Pressure material** (surfaced to Skald via `PresentActorPolicy.STORYTELLER_PRESSURE`; Skald reads degree from prose) → binary presence. The tag fires or it doesn't; "how much" is prose.

Most affective states are pressure material → binary. `wounded`/`sick` are the candidates that *might* gate on severity; flagged as open decisions below.

---

## Cardinality and the unique-index reality

`state` is **multi-valued** — a character is plausibly `wounded` + `afraid` + `intoxicated:stimulant` at once — and contradictions are not system-enforced (trust Skald, as with disposition).

One hard substrate fact constrains this: `ix_entity_tags_current` is `UNIQUE (entity_id, tag_id) WHERE cleared_at IS NULL`, so **any single `tag_id` is singular** — only one open row per tag per entity. Implications:

- Distinct tags coexist freely (different `tag_id`s): `intoxicated:stimulant` + `intoxicated:depressant` is fine.
- A re-apply of the **same** tag is policy-dispatched by the application writer: most tags keep idempotent `new_row` behavior, duration-bearing tags can `extend_expiry`, and refresh-style tags can `replace` the active row.
- Graduated-severity tracks are mutually exclusive within track by construction (one tier tag at a time), which the needs maintenance pass already enforces by clearing sibling tiers on re-tier.

---

## Cluster 1 — Physical Condition

The body's current condition. The most package-load-bearing cluster, and the one with the cleanest event clearances.

| State | Meaning | Clears on | Clearance kind | Degree |
|---|---|---|---|---|
| `wounded` | Injured; physical scenes resolve unfavorably, travel impeded | `tended` / `healed` event | event | **decision** — binary, or graduated if a collapse / seek-treatment branch gates on severity |
| `sick` | Illness / disease | `recovered` / `cured` event; mild cases may also time-decay | event (primary) | **decision** — as `wounded` |
| `restrained` | Physically bound, pinned, immobilized — cannot move freely *this scene* | `freed` / `escaped` event | event | binary |

**Rationale.** `wounded` and `sick` are the two anchors where graduated severity is genuinely plausible, because a "collapse from blood loss" or "seek medical attention" branch would threshold on degree exactly as the needs branches do. The difference from needs: there is no clock computing the tier — wounding is event-driven, so the tier (if adopted) is assigned by the establishing event, not re-derived each pass. That is admissible under the degree test (the integer is still a gate input), but it means the maintenance pass does not own these tiers — so re-tiering on a *second* wounding event must clear the prior tier explicitly. If no package actually gates on wound severity, keep them binary and let prose carry degree. **This is the call to make before these ship.**

`restrained` vs `imprisoned` (below): `restrained` is the immediate physical fact (tied up, pinned, this scene); `imprisoned` is the sustained condition across chunks. They gate similarly but clear on different events, so both are kept.

---

## Cluster 2 — Affective Condition

The current emotional reading — the transient counterpart to disposition. The state-vs-disposition boundary runs straight through here: the **participle / transient form is the state**, the **trait adjective is the disposition** (`enraged`/`volatile`, `afraid`/`cowardly`, `despairing`/`cynical`). This is the neuroticism-exile rule from the disposition crosswalk, generalized.

| State | Meaning | Clears on | Clearance kind | Degree |
|---|---|---|---|---|
| `enraged` | Acute anger overriding normal judgment | `vengeance_taken` / target-confronted event, or time-decay | event or time | binary (pressure material) |
| `afraid` | Acute fear; flight-biased | `threat_removed` event, or time-decay | event or time | binary (pressure material) |
| `grieving` | Acute grief / loss | time-decay (primary) + authored moment of moving on | time + authored | binary (pressure material) |
| `despairing` | Hopelessness; withdrawal-biased | `circumstance_reversed` event, or time-decay | event or time | binary (pressure material) |

**Rationale.** These are primarily `STORYTELLER_PRESSURE` material: surfaced to Skald, who narrates the register and intensity. Hence binary by default — nothing thresholds on a stored fear-integer. **The open fork** (below): if a specific package gates on affective severity — a `MOURN_LOSS` branch keyed to grief depth, a panic / flee package keyed to fear level — *those specific anchors* inherit the graduated convention. Until a package demands it, they stay flat.

**`despairing` is wellbeing-adjacent.** Any package or prompt reading it should be written for narrative care, not mechanical consequence. Resist enumerating finer distress shades; `despairing` covers the gating need and finer gradations belong in prose.

**Clearance reality.** `enraged` / `afraid` / `despairing` all have a plausible clearing event, so they work on today's substrate (`clear_entity_tag` + `tag_clearance_log.triggering_event_id`, confirmed in PR #315). `grieving` is the genuine time-decay case — grief fades without a triggering event — so it depends on the expiry sweeper (#328). Ship it with an event-clearance fallback (the existing `mourning_completed` event type, registered for the `MOURN_LOSS` package) until the sweeper lands; an over-lingering grief tag is a tolerable failure.

---

## Cluster 3 — Pharmacologic Condition

Replaces the vague `intoxicated` with one tag per **pharmacological class**, using the colon-subtype convention (`bodyform:cyborg`, `place_function:market`). The classes gate differently, so the split passes granularity where the vague tag failed.

| State | Meaning / primary gate effect | Clears on | Clearance kind | Degree |
|---|---|---|---|---|
| `intoxicated:stimulant` | Wired / activated; **suppresses the SLEEP gate** (absorbs `cns_stimulated`) | time (sweeper) | time | binary |
| `intoxicated:depressant` | Sedated / impaired; physical + cognitive scenes resolve unfavorably | time (sweeper) | time | binary |
| `intoxicated:hallucinogen` | Perceptual distortion; degrades witness-reliability | time (sweeper) | time | binary |
| `intoxicated:dissociative` | Detachment / depersonalization | time (sweeper) | time | binary |

**Kinetics model — duration at application, sweeper-cleared.** Every dose carries a duration set **at application** (default per class, overridable by the establishing event / Skald when the substance warrants it — espresso vs combat-drug). Clearance is by elapsed world-time, via the **expiry sweeper** (#328), *not* by any event — so these are the one cluster that names a **duration**, not a clearing event type. The clearance-event enumeration below intentionally does not include any `metabolized` type; it doesn't exist.

**Polypharmacy.** Multi-valued: different classes are distinct `tag_id`s and coexist (`intoxicated:stimulant` + `intoxicated:depressant` is a specific, recognizable state, and the suppression/impairment effects compose). Same-class re-dose is *not* a second row — the unique index forbids it — so the writer must **extend the open row's expiry** on conflict. Migration 049 provides the `entity_tags.expires_at_world_time` column plus writer dispatch on the existing `tags.reapplication_policy` enum (`new_row` / `extend_expiry` / `replace`). The remaining runtime prerequisite is the expiry sweeper (#328).

**On the kinetics framing.** Additive-timer is a *narrative-modeling convenience*, not pharmacological accuracy — only ethanol is genuinely zero-order at narrative-relevant doses; stimulants, opioids, hallucinogens, and dissociatives are first-order in reality. We favor legibility (more dose = lasts longer, in a way the writer can reason about) over verisimilitude. A per-class `expires_at` cap is a one-line knob if runaway re-dosing ever matters; probably unnecessary for narrative purposes.

**Predicates:** `has_tag("intoxicated:stimulant")` for the specific gate. For "under any influence," explicit enumeration via the existing `has_any_tag("intoxicated:stimulant", "intoxicated:depressant", "intoxicated:hallucinogen", "intoxicated:dissociative")` works today and is fine for a four-class cluster. A general colon-prefix predicate (e.g. `has_tag_with_prefix(prefix, separator=":")`) does not currently exist — `has_severity_tag(prefix)` matches `{prefix}_` with underscore, not colon — and would need to be added separately if frequent enough to warrant.

**`cns_stimulated` migration:** alias to `intoxicated:stimulant` via `CANONICAL_TAGS` (mechanism confirmed by PR #315's alias-resolution test). The SLEEP gate's `NOT(has_ephemeral("cns_stimulated"))` becomes `NOT(has_tag("intoxicated:stimulant"))`. This unifies the suppressor vocabulary with the general intoxication vocabulary instead of maintaining two parallel notions of "wired."

---

## Cluster 4 — Circumstantial / Positional Condition

These passed the membership test in earlier passes but belong to none of the first three clusters cleanly — they are about the character's *situation and how they are perceived*, not body / affect / chemistry. They form a fourth micro-cluster rather than folding into Physical: `imprisoned` is sustained situational constraint, while `concealed` and `disguised` are perception-facing states.

| State | Meaning | Clears on | Clearance kind | Degree |
|---|---|---|---|---|
| `imprisoned` | Held captive; sustained constraint on freedom of action across chunks | `released` / `escaped` event | event | binary |
| `concealed` | Currently unseen / in hiding; suppresses detection (temporary inverse of `fame`) | `revealed` / `discovered` event | event | binary |
| `disguised` | Seen but misidentified; suppresses recognition specifically | `unmasked` / `exposed` event | event | binary |

**Rationale.** `concealed` defeats *detection* (not seen at all); `disguised` defeats *recognition* (seen, read as someone else) — an evasion package and an infiltration package gate on different ones, so both are kept. `imprisoned` is the character's own freedom-of-action condition (the captor, if it matters, is a separate pair-tag). The social-cluster casualties from earlier (`fugitive`, `under_suspicion`, `disgraced`, `outlawed`) stay dropped — they decomposed cleanly into `hunting(X → char)` pair-tags, `concealed`, and scope-bound `status` levels.

**Scope rule.** `concealed` and `disguised` are single-entity states by default: global obscurity / misidentification is the common case and keeps the write surface cheap. Do not fan these out to every possible perceiver. When a package needs scoped perception ("hidden from Dynacorp but not from the town guard"), add a targeted pair-tag overlay rather than replacing the base state. Prefer separate overlay names for detection vs recognition if/when this substrate lands; do not overload one vague `evading` relation for both.

---

## Clearance Event-Type Vocabulary

**Where clearance config lives.** Per-tag-template fields declare *which* event types clear *this* state — clearance is a property of the state, not of the event. The runtime mechanism is `_clear_event_tags_sync` / `_clear_event_tags_async` (`nexus/agents/orrery/events.py:3030+`), which queries `t.clear_on -> 'event_types' ? <event_type>` against the `tags` table's `clear_on` JSONB column. Adding a new event type doesn't require enumerating every state it could clear; each tag template declares its own clearance contract. The event registry below lists *names referenced from the state side*; whether each currently exists in the `event_types` table is independent of whether any state has actually wired it up. A state whose clearance config names a nonexistent event type does not no-op — it applies and **never clears, silently** — so the event vocabulary cannot lag the state vocabulary.

The table marks each row's registry status against the live `event_types` table. Migration 050 registers the new rows required by this draft.

| Clearing event type(s) | Registry status | Clears |
|---|---|---|
| `tended_wound`, `wound_healed` | **existing** | `wounded` |
| `recovered_from_illness`, `cured` | **existing** | `sick` |
| `captivity_ended` | **existing** | `restrained` (release variant), `imprisoned` |
| `escaped` | **existing** | `restrained`, `imprisoned` (escape variant — distinct from `captivity_ended` because the actor's agency matters narratively) |
| `revealed`, `discovered` | **existing** | `concealed` |
| `unmasked`, `exposed` | **existing** | `disguised` |
| `threat_removed` | **existing** | `afraid` |
| `retaliation_executed` | **existing** | `enraged` (vengeance variant — uses the existing retaliation event-type from the contact/hostility cluster) |
| `confrontation_resolved` | **existing** | `enraged` (alternate path — confronted-and-de-escalated without retaliation) |
| `circumstance_reversed` | **existing** | `despairing` |
| `mourning_completed` | **existing** | `grieving` (authored fallback — the sweeper handles the primary time-decay path) |
| *(none — time-cleared via sweeper)* | sweeper #328 | `grieving` (primary), all `intoxicated:*` |

Several alignments with existing vocab dropped synonymous proposals: `tended`/`healed` collapse to the existing `tended_wound` + `wound_healed` pair; `released` collapses to `captivity_ended`; `vengeance_taken` collapses to `retaliation_executed`. The remaining new-registrations are anchors that don't currently have an event-type partner in the live registry.

**Substrate gap on `clearance_kind`.** The per-cluster tables above use `time` and `time + authored` in the Clearance kind column. The live `entity_tag_clearance_kind` enum only has `{event, semantic, authored}` (migration 023) — no `time` value. Adding `time` is implicitly bundled with the sweeper work in #328; without it, migrations for time-cleared tags will fail with a cast error. The enum extension should land before any tag template references `'time'::entity_tag_clearance_kind`.

---

## Migration Debts

1. **`under_active_pursuit` → inbound `hunting` pair-tag — resolved.** Migration 048 renames live `pursuing` pair-tag rows to `hunting`, deprecates the legacy single-entity signal, and templates now gate on `has_inbound_pair_tag("hunting", ...)`. This closes the category-error state debt; remaining `hunting` behavior belongs to package self-awareness (#282), not the `state` vocabulary.
2. **Grief vocabulary — resolved.** PR #320 collapsed three competing names (`bereaved`, `grieving_recent_partner`, the earlier-proposed `grieving`) to the canonical `grieving`. The INTIMACY suppressor row for `grieving_recent_partner` was removed; general `grieving` covers it. This doc adopts that resolution; no further work required.
3. **`cns_stimulated` → `intoxicated:stimulant` alias.** Alias via `CANONICAL_TAGS` + SLEEP-gate rewrite, as in Cluster 3. Implementation surface: `nexus/agents/orrery/tag_constants.py` (add alias) and `nexus/agents/orrery/templates.py:2298` (rewrite the gate predicate). This remains a small follow-up once the pharmacologic tags themselves are ready to ship.
4. **`contacts_available` overload — resolved.** PR #327 (migration 047) shipped the kind-qualified `contact:<lodging|social|intimate>` pair-tag family, replacing the overloaded `contacts_available` ephemeral and closing #317. Not a `state` issue — noted only for cross-reference; the substrate fix applies cleanly to needs templates per `orrery_needs.md` R3.
5. **`entity_tags` substrate enrichment for additive-timer pharmacologics — resolved.** Migration 049 adds `entity_tags.expires_at_world_time` and the expiring-row index, and `_insert_entity_tag` now dispatches `new_row` / `extend_expiry` / `replace` from each tag's existing `reapplication_policy` field.
   
   The remaining sibling is **#328** (sweeper). The pharmacologic cluster still needs the sweeper before `intoxicated:*` becomes a fully working time-cleared state family.

---

## Resolved Decisions from OQ #5-#8

5. **Circumstantial placement.** `imprisoned`, `concealed`, and `disguised` form Cluster 4 — Circumstantial / Positional Condition. They do not fold into Physical, and `imprisoned` is not split away from the perception-facing pair; the shared trait is "current situation that constrains action or perception."
6. **`concealed` / `disguised` scope.** Keep as single-entity states for the global/common case. Add targeted pair-tag overlays only when a package needs scoped perception against a specific faction, character, or audience. If that overlay becomes real substrate, use distinct relation names for hidden-from vs misidentified-by rather than one vague catch-all.
7. **Template ownership.** The doc adopts an ownership marker concept, but names it `derivation_owner` rather than `owned_by_subsystem`. It should distinguish who may derive or re-tier a tag track (`needs`, `event`, `sweeper`, `skald` / `authored`), so future maintenance passes do not accidentally mutate event-assigned tracks such as possible `wounded_N` tiers. This can start as template metadata and only needs a registry column once runtime code consumes it.
8. **Maintenance provenance.** Add `maintenance` to `entity_tag_source_kind` when a maintenance pass first writes general `state` tags. Engine-tick applications are auditably different from resolver/template/event writes, and `system` is too broad for debugging state drift.

---

## Remaining Open Decisions

1. **Affective gate-vs-pressure fork.** Does any package gate on affective *severity* (e.g., `MOURN_LOSS` on grief depth, panic/flee on fear level)? If yes, those anchors adopt graduated `_N_label`; if all affective states are pure `STORYTELLER_PRESSURE`, the whole cluster stays binary. **Determines whether the affective cluster reuses the needs severity machinery.**
2. **`wounded` / `sick` degree.** Binary, or graduated? Hinges on whether a collapse / seek-treatment branch thresholds on severity.
3. **`hallucinogen` vs `dissociative` split.** Keep separate only if a dissociative's detachment beat gates or prompts differently from a hallucinogen's perceptual distortion. Name the divergence before committing the split, or merge.
4. **`intoxicated:opioid` as a fifth class?** Pharmacologically a depressant, but a distinct analgesia-plus-sedation profile. Same gating test, stated actively: **name the gate or prompt that reads `:opioid` differently from `:depressant`, or merge.** A reviewer who can name one admits the class; a reviewer who can't, merges.

---

## Count

Physical 3 (`wounded`, `sick`, `restrained`) · Affective 4 (`enraged`, `afraid`, `grieving`, `despairing`) · Pharmacologic 4 (`intoxicated:stimulant` / `:depressant` / `:hallucinogen` / `:dissociative`) · Circumstantial 3 (`imprisoned`, `concealed`, `disguised`) = **14 anchors**, +1 if `intoxicated:opioid` is admitted. Deliberately lean — the name-the-clearance rule did the culling, and the near-total dissolution of the old social cluster is the clearest sign the test is doing real work.
