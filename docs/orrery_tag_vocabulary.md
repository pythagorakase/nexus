# Orrery Tag Vocabulary

The closed-vocabulary registry for Orrery's tag system: entity-property tag categories (`bodyform`, `disposition`, `capacity`, `role`, `state`), multi-entity (relational) tag families, place + faction categories, and the trait_menu alignment layer. Companion to `docs/orrery_design_plan.md`.

Closed-vocabulary discipline: tags do not grow at runtime. Every candidate is filtered through three design tests (differential + gating, reskinning, granularity — see Architectural Foundations). The auditable invariant is **"tags must do work prose can't,"** not a fixed count.

---

## Architectural Foundations

### Three Structures, One Registry

| Structure | Application table | Carries | Example |
|---|---|---|---|
| **Single-entity tag** | `entity_tags` (existing) | Property of one entity | `bodyform:cybernetic` on Nyati |
| **Multi-entity tag** | `entity_pair_tags` (shipped — see PR #283) | Binary property of an ordered pair | `knows_location(Alex → Burrow)` |
| **Rich relationship** | `character_relationships` (existing) | Affective/social state with valence, history, sub-states | Alex/Emilia trust=high, valence=positive |

### Locked Vocabulary — No Runtime Growth

Skald applies from a closed registry. `skald_inline` remains the provenance marker for runtime bestowals of registered tags; the `auto_registered` source kind and runtime vocabulary-growth path are removed. Bestowal of an unknown tag name is a hard error, not an opportunity to auto-register.

**Rationale:** every successful tag system in adjacent design space (Bethesda Radiant AI, Dwarf Fortress) uses closed vocabularies. NEXUS's earlier "let Skald propose at runtime" gambit produced entropy without curation; the right discipline is pre-design.

**Implications:**
- Vocabulary must be comprehensive enough for cross-genre stories.
- **Universal scope:** tags are not genre-gated. `genre:*` tags exist as *informational* tags on the story slot, never gate other tags.
- Skald can introduce genre-bending plot beats freely (the secret-goblinization-of-the-population case).

### Skald Is Sovereign

Already shipped via PR #276 (issue #275). Skald's structured output can `defer` / `replace` / `void` any Orrery proposal at adjudication time. No `narrative_debt` flag — the canon-truth property is delegated entirely to Skald's authorial judgment.

**Counterweights:** careful prompting + path-of-least-resistance default (no adjudication = ratify-all). Skald's LLM positivity bias is the main risk; structural defaults mitigate it.

### Naming Discipline: "Guess Without Peeking"

A tag name that requires its description field to be understandable is wrong. Names must be self-documenting. Vague design-speak (`affordance`), hedge language (`profession_lite`), and operational jargon (`orrery_signal`) all fail this test and were renamed or dropped.

### Per-Category Cardinality

| Mode | Within one category | Example |
|---|---|---|
| **Exclusive** | One tag per entity (XOR) | `place_visibility:place_known` XOR `place_hidden` |
| **Multi-valued** | Many tags per entity | `place_function:commerce` AND `place_function:dwelling` |

**Default is multi-valued; exclusive is the exception.** The test for exclusivity: *"is there genuinely only one truth about this entity in this dimension?"* For visibility and access: yes. For bodyform / ideology / disposition / role / state / function: no — compositions are normal (half-cyborg elf is a feature, not a bug).

Cardinality is a property of the category-in-the-registry, not of individual tag definitions. Implementation: add a `cardinality` column to the `tags` registry (default `multi`), enforce at bestowal time.

**⏳ SCHEMA-PENDING:** the `cardinality` column does not yet exist on the `tags` registry (see Open Items #5). Until that migration lands, exclusive/multi distinctions throughout this doc are *design intent* only — not database-enforced. Bestowal-time exclusivity checks must be done in application code (for example, `apply_exclusive_tag_bestowal`) as an interim measure.

### Polymorphic Subjects/Objects

Multi-entity tags admit polymorphic endpoints (character | faction | place) where the relation makes sense across kinds. The `entities` super-table already polymorphizes; pair-tags ride on that. Examples: `can_access(character | faction → place)`, `obligation(character | faction → character | faction)`. Refusing polymorphism would force redundant vocabulary (`character_obligation`, `faction_obligation`, `cross_kind_obligation`).

### Compositional Truth over Baked-In Truth

Binary distinctions that are really cardinality questions are dissolved into the relation; counting reveals state. `claims` with one row = uncontested ownership; with multiple rows = disputed territory. No separate `owns` vocabulary needed. The pattern: **prefer compositional truth over baked-in truth.**

### Vocabulary Design Tests

Three tests filter candidate tags. Each catches a different failure mode; together they gate against the most common vocabulary mistakes. Apply in order — differential/gating first (should this be a tag at all?), then reskinning (is the concept era-neutral?), then granularity (does it add distinct value over its siblings?).

#### 1. Differential + Gating (Anti-Decoration)

A property earns a tag only if BOTH:

- *Differential:* it differs meaningfully across characters. If the tag would fire on most characters, it's an entity attribute, not a tag. Universal-with-variation identity attributes (pronouns, gender identity, biographical detail) go in entity metadata (columns or `extra_data`); historical events go in `world_events`; relational properties (sexual orientation) are compositionally inferred from `character_relationships`.
- *Gating:* at least one narrative or adjudication decision needs to read it to function. If prose already carries the information for Skald, the tag is decorative.

Examples: `bodyform:undead` fires on a small subset and gates package/affordance decisions → tag. `gender:female` fires on most characters and Skald reads pronouns from prose anyway → entity metadata. `disposition:cautious` fires differentially and gates Skald's plausible-action set → tag.

The pattern: **a tag must do work that prose and metadata can't already do.**

#### 2. Reskinning (Anti-Genre-Lock)

A candidate tag must survive translation across eras and genres without losing its meaning. This is the operational form of the universal-scope rule under Locked Vocabulary: tags are not genre-gated, so the vocabulary itself must be era-and-genre-neutral.

Examples: `warrior` reskins cleanly from Bronze Age to cyberpunk — passes. `hacker` is era-bound (modern/SF only) — fails; fold into `criminal` or `artisan`, both of which reskin. `clergy` reskins; `wizard` / `mage` does not (fantasy-bound), and decomposes by function into `scholar`, `healer`, `warrior`, etc.

Heuristic: imagine the candidate tag applied to characters in three eras you haven't designed for. If two of the three read awkwardly, the abstraction is too narrow.

#### 3. Granularity (Anti-Redundancy)

Does this anchor gate differently from its neighbors within the same category? If two candidate tags gate identically on character action, the distinction is decorative — keep one, fold the other to prose.

Examples: `goblin` and `kobold` gate identically on bodyform's functional axes (sustenance, vulnerability, longevity) — merge. `warrior` + `hitman` differ only in faction allegiance, which is captured by relationship structure per compositional truth — merge into `warrior`. `priest` and `monk` gate differently (one ceremonial/laity-interfacing, one cloistered/ascetic) — keep both.

Within bodyform, the **functional axes** (locomotion, sustenance, vulnerability, networkability, longevity, social legibility) serve as the granularity standard for whether two candidate tags are meaningfully distinct. Disposition uses its twelve axes the same way. Each category should articulate its own granularity standard.

#### Coverage Map

The three tests catch non-overlapping failure modes:

| Failure mode | Caught by |
|---|---|
| Decorative tag (`gender:female` fires on most characters) | Differential + gating |
| Genre-locked tag (`hacker`, `mage`, `programmer`) | Reskinning |
| Redundant tag (`hitman` next to `warrior`) | Granularity |

A candidate that passes all three earns its place in the registry.

---

## Character Categories

| Category      | Cardinality  | Ephemerality     | Notes                                 |
| ------------- | ------------ | ---------------- | ------------------------------------- |
| `bodyform`    | Multi-valued | Durable          | Hybrid lineages, layered augmentation |
| `capacity`    | Multi-valued | Durable (mostly) | Capabilities and affordances          |
| `disposition` | Multi-valued | Durable          | Stable behavioral patterns            |
| `role`        | Multi-valued | Durable          | Merged from role + profession_lite    |
| `state`       | Multi-valued | Ephemeral        | Merged from state + orrery_signal     |

### `bodyform`

#### Taxonomic Axes

These designations carry the most semantic meaning. Some distinctions will have mostly semantic value for Skald rather than package-gating, e.g., `human` vs `elf`.

**Lineage**: essential type of being you are
- `human`
- `elf`
- `dwarf`
- `orc`
- `goblinoid`
- `beastfolk`
- `animal`
- `dragon`
- `fey`
- `giant`
- `eldritch`
- `spirit`
- `inorganic`
- `alien`

**Conditions**: alter you fundamentally
- `undead`
- `lycanthrope`
- `enchanted`
- `awakened`
- `virtual`
- `extraplanar`
- `cybernetic`

**Note on `cybernetic`:** the condition requires surgical-grade integration — augmentation that needs medical intervention to remove. Removable wearable tech, however functionally indispensable, does not qualify. (Pete's cyber-goggles are accessory; Nyati's embedded circuit-lattice is `cybernetic`.)

**Note on `inorganic`:** covers any non-biological substrate — robotic chassis, AI server infrastructure, golem materials, the Grid hardware that hosts a digital ghost. The condition `virtual` further specifies software-resident consciousness within an inorganic substrate (e.g., Alina = `inorganic` + `virtual`; Lansky = `inorganic` + `virtual`). `animal` covers non-sapient living creatures (cats, dogs, beasts); for sapient anthropomorphic creatures use `beastfolk`.

#### Functional Axes

These are underlying qualities implied or denoted by our tags, which are likely to be what packages actually gate on:
- locomotion
- sustenance: biomatter, blood, souls, energy
- vulnerability: sunlight, silver, fire, cold iron
- networkability: hackable (with or without wireless), telepathic, hive mind
- longevity: mortal, immortal, notably longer/shorter than human
- social legibility: generally registers as "person" or not?

These qualities can be used as granularity standards to inform whether a tag distinction is useful. Longevity differs meaningfully between human and elf. Goblin and kobold probably don't need different tags.

#### Examples

**Composition**:
- werewolf = `human` + `lycanthrope`
- cyborg = `human` + `cybernetic`
- golem = `inorganic` + `enchanted`
- lich = `elf` + `undead` + `enchanted`
- Breton / half-elf = `human` + `elf`

**Dynamic** (from slot 2):
Alina (character ID 4) was a human; then became virtualized, and her body destroyed; then eventually became reembodied in an android chassis, though without being bound to it—like EDI in ME2. Thus,
1. `human`
2. loses `human` (?); gains `virtual`
3. gains `inorganic`; probably retains `virtual`?

#### Resolved Boundary Decisions

`alien`, `eldritch`, and `extraplanar` are deliberately different axes:

- `alien` is a lineage for beings whose ordinary biology / cognition is non-terrestrial or otherwise non-local enough that package affordances change. A human born on a Mars colony is still `human`; a Kryptonian-like person is `alien` unless a later lineage split earns its keep.
- `eldritch` is a lineage for beings whose nature is reality-strange, cognitively illegible, mythic, or non-rational in a way packages and Skald must handle differently. It is not merely "from elsewhere." Sam and the Bridge stress-test this use.
- `extraplanar` is a condition, not a lineage: the being's origin or metaphysical binding is elsewhere, but its essential bodyform is still read through another lineage (`human` + `extraplanar`, `spirit` + `extraplanar`, `fey` + `extraplanar`).

Subtype hierarchy is deferred by default. `undead` remains the only admitted undead condition; `vampire`, `lich`, `zombie`, and similar subtypes stay in prose plus composition (`undead` + `enchanted`, needs pressure, vulnerability prose, event history) until a package names a gate that must distinguish them. If that happens, add a deliberate registry migration using the same colon-subtype convention as `intoxicated:*`; do not improvise runtime sub-tags.

---

### `disposition`

#### The Twelve Axes

Disposition tags are organized along twelve single-word axes, each capturing one dimension of stable behavioral pattern that gates narrative choice. As with bodyform's functional axes, the axes are design-time discipline — the registry stores the flat `disposition` category, not the axis groupings. The axes exist so enumeration can be checked for completeness rather than left to chance.

| Axis | What it gates | Anchor tags |
|---|---|---|
| **Courage** | Risk-handling | `brave`, `cowardly`, `reckless`, `cautious` |
| **Aggression** | Default response to friction | `aggressive`, `peaceable`, `belligerent`, `gentle`, `fierce` |
| **Loyalty** | Commitment to persons/groups | `loyal`, `treacherous`, `trusting`, `suspicious` |
| **Compassion** | Response to others' suffering | `compassionate`, `callous`, `merciful`, `cruel`, `generous`, `miserly` |
| **Honesty** | Relationship with truth | `forthright`, `deceitful`, `honorable`, `manipulative` |
| **Lawfulness** | Posture toward institutional structure | `dutiful`, `independent`, `traditionalist`, `iconoclast`, `principled`, `expedient` |
| **Mutuality** | Reciprocity orientation in relations | `reciprocal`, `transactional`, `cooperative`, `exploitative` |
| **Drive** | Ambition and effort | `ambitious`, `complacent`, `industrious`, `indolent` |
| **Will** | Self-mastery over impulse, appetite, emotion, and commitment | `disciplined`, `impulsive`, `temperate`, `hedonistic`, `stoic`, `volatile`, `resolute`, `wavering` |
| **Pride** | Self-regard (valence + stability) | `humble`, `proud`, `arrogant`, `self-effacing`, `secure`, `insecure` |
| **Outlook** | Worldview / posture toward the future | `optimistic`, `cynical`, `idealistic`, `romantic`, `realistic`, `dispassionate` |
| **Sociability** | Source of social energy | `gregarious`, `solitary`, `reserved` |

The granularity test (see Vocabulary design tests in Architectural Foundations) applies axis by axis: if two candidate tags within an axis gate identically on character action, the distinction is decorative — keep one, fold the other to prose.

#### Cardinality

All twelve axes are multi-valued. Opposite-pair contradictions within an axis (e.g., `brave` + `cowardly`) are **not** system-enforced — characters develop contradictions, and a person who is `cautious` in one domain and `reckless` in another is a feature, not a bug. Skald is responsible for not generating nonsense; the registry is not.

#### Applicability

Disposition assumes person-level sapience. For non-person entities (animals, semi-aware artifacts, devices), some axes will be N/A and should simply not be tagged. Skald can read prose and metadata for what doesn't fit the vocabulary.

Worked examples (see Reference Taggings below):
- **Animal (Sullivan):** ~6 of 12 axes apply. Honesty, Lawfulness, Drive, Outlook generally N/A.
- **Semi-sapient device (Bridge):** ~4 of 12 axes apply.
- **Person-level entities** (most characters): all 12 axes apply.

#### Design Crosswalk

| Borrow | Source | What it contributed |
|---|---|---|
| Honesty axis as distinct from Compassion + Pride | HEXACO | Empirical case that honesty-humility captures variance Big Five misses |
| Opposed-pair virtues within each axis | Pendragon (KAP) | Within-axis structure: each axis has poles + middles |
| Aggression as its own axis | ChatClaude brainstorm | Default-friction-response, distinct from Courage |
| Lawfulness as its own axis | ChatClaude (rule-orientation) | Institutional posture, distinct from Loyalty |
| Mutuality as its own axis | DSM-5 LPFS (Relationships/Mutuality) | Reciprocity orientation, distinct from Compassion |
| Will as umbrella for self-mastery | RPG conventions | Single axis covering impulse + appetite + emotion + commitment |

Intentionally **not** imported:
- Big Five's neuroticism — emotional volatility belongs in `state`, not disposition (the disposition is the regulation capacity, captured by Will; the surge is a state)
- MBTI typology — wrong shape (disposition is composable, not categorical)
- LPFS dimensional 5-level gradation — wrong shape (tags, not impairment ratings)
- Pendragon's piety / chastity — religion-specific
- D&D `lawful` / `chaotic` literal tags — too alignment-loaded; Skald might import unwanted subtext

#### Resolved Stress-Test Notes

1. **`idealistic` Outlook anchor.** Kept. It did not fire in the initial six-character pass, but the wildcard round later exercised it across Sam, Black Kite, and the Bridge.
2. **`pessimistic` Outlook anchor.** Not admitted. Emilia and Pete can be read through `cynical`, `realistic`, `insecure`, and prose without adding a neighboring Outlook anchor that gates differently.
3. **Will anchor count.** Kept. Eight anchors held up across the twelve-character stress test: max-self-mastery (Alina), high-cluster (`disciplined` + `stoic` + `resolute`), moderate (`disciplined` alone), and opposite-pole (`impulsive` + `volatile` + `wavering`). No trim warranted.

### `role`

Three single-entity sub-categories — function, resources, fame — plus a fourth dimension carried by the multi-entity tag layer: scope-bound **status**. All durable.

This is a refactor of an earlier `function + authority + station` shape. Two design insights drove the change:

1. **Status is scope-bound, not single-entity.** Formal authority (rank-in-hierarchy) and informal social standing both depend on which audience is reading the character. A Major in the US Army is senior to BHO residents, nothing to the Jimmy Johns sandwich guy. The audience is part of the fact, not separate from it — so status is an *edge property* between a character and an audience-faction, captured via the multi-entity tag layer.
2. **Fame is a detection radius, not a social position.** Fame and station were conflated in the earlier design. Splitting them yields a single-entity unvalenced fame axis (ambient detection radius) plus scope-bound status for actual position.

**Registry-level note on cardinality.** Per the Per-Category Cardinality foundation, cardinality lives on the *category*, not the tag. Function is multi-valued, fame and resources are exclusive — three different cardinality values, so they cannot share one registry category. **At the registry level these are three distinct categories: `role.function`, `role.fame`, `role.resources`** (each carrying its own cardinality). The shared "role" prefix exists only for documentation grouping. The compiler writes literal `(category, tag)` pairs of the form `('role.function', 'warrior')`, `('role.fame', 'renowned')`, `('role.resources', 'wealthy')`. Bodyform's lineage/condition split is the same shape (separate registry categories `bodyform.lineage` and `bodyform.condition`) — benign there because they share cardinality, but the registry split is identical.

#### Function (Multi-Valued, Single-Entity)

- `advocate`
- `artisan`
- `artist`
- `caregiver`
- `clergy`
- `entertainer`
- `farmer`
- `functionary`
- `healer`
- `hunter`
- `investigator`
- `laborer`
- `leader`
- `merchant`
- `scholar`
- `sex_worker`
- `spy`
- `teacher`
- `technician`
- `thief`
- `warrior`

Multi-valued: characters wear multiple operational hats (Pete = `artisan` + `thief`; Nyati = `scholar` + `healer`). Tactical sub-archetypes of a function (a `warrior` who is a soldier vs. hitman vs. bodyguard) are *not* separate tags — that distinction is carried by faction relationships per the compositional-truth principle.

#### Resources (Exclusive, Single-Entity)

- `destitute`
- `poor`
- `comfortable`
- `wealthy`
- `magnate`

Economic capacity / wealth. Scope-independent — you are rich or poor in absolute terms. Maps to the trait_menu `Resources` trait. Exclusive: one current level per character. Default for typical characters is implicitly `comfortable` and may go untagged unless wealth is narratively load-bearing.

#### Fame (Exclusive, Single-Entity)

- `obscure` (default — absent unless narratively load-bearing)
- `known`
- `renowned`
- `legendary`

Ambient detection radius — effectively inverse stealth. **Unvalenced**: anchors describe how widely-known the character is, not whether the recognition is positive (beloved) or negative (notorious). Valence emerges from compositional intersection with other tags (`legendary` + `criminal` + `status:outcast(→ society)` = hunted celebrity; `legendary` + `healer` + `status:respected(→ community)` = venerated elder).

**Global, not scope-bound.** Fame radius applies to *all* observers — a `renowned` character is recognizable to passersby in any subculture. Subculture-only recognition is **not** fame; it compiles to `status:respected(char → subculture-faction)` instead. A Grid info-broker known only inside netrunner circles is `obscure` + `status:respected(→ Grid_underground)`, NOT `renowned` with a scope qualifier. The two concepts compose cleanly: `legendary` + `status:respected(→ Archivum)` reads as "globally legendary AND additionally elevated within the Archivum"; the fame tag never carries an audience.

Maps to the trait_menu `Fame` trait (renamed from `Reputation` for naming consistency). Exclusive: one current radius per character.

#### Status — Scope-Bound, Multi-Entity

Status is captured via the multi-entity tag layer rather than as a single-entity role sub-category — see the Multi-Entity Tags section below for the `status:<level>(char|faction → faction)` family.

The architectural insight: status — formal authority, informal social standing, rank within a hierarchy — is an **edge property** between a character and an audience-faction, not a single-entity property of the character. The formal vs. informal distinction is read off the scope-faction's own tags (its `legitimacy`, `operational_mode`), NOT off the status tag itself. A character can hold multiple scope-bound statuses simultaneously, each scoped to a different audience-faction.

This absorbs the old `authority` axis (rank-in-a-hierarchy is now `status:<level>(char → formal-institution-faction)`) and the position-within-society parts of the old `station` axis. The fame parts of the old `station` (e.g., the anchor `famous`) migrated to the new `fame` axis above. The negative-station anchors (`outcast`, `pariah`, `enslaved`) became scope-bound levels of status (`status:outcast(char → society)`, etc.).

Maps to the trait_menu `Status` trait (broadened from "formal institutional standing" to cover any scope-bound position — formal or informal; the wizard prompts for the scope-faction during compilation).

#### Applicability

Like disposition and capacity, role assumes social-actor-in-society. For animals, semi-sapient devices, and similar non-person entities, role tags will be N/A and should simply not be applied (Sullivan, Bridge, Black Kite).

---

### `capacity`

What this character can *actually do* when they try. Distinct from `role.function` (the *social slot* — what others recognize you as) and from `disposition` (what you *tend* to do): a `healer` role with no `medical` capacity is a quack; a `warrior` with no `martial` capacity is a poseur; a character with `medical` capacity but role `spy` is a soldier-medic operating undercover. The 90% case is that role and capacity agree; the 10% divergence is narratively interesting and deliberately preserved.

#### Anchors

Single flat category, multi-valued, durable. Organized below by domain for legibility; the registry stores anchors flat. **`(–)` marks a negative anchor** — apply only when the absence of the capability is *diagnostic* of the character (the rest of the time, absence is the default and goes untagged).

**Physical** (3 + 3 negative)

| Tag            | Meaning                                                                               |
| -------------- | ------------------------------------------------------------------------------------- |
| `strong`       | Exceptional strength; breaks things, wins brawls, carries heavy loads                 |
| `agile`        | Exceptional speed / coordination / dexterity                                          |
| `hardy`        | Exceptional stamina / resilience / recovery                                           |
| `frail` `(–)`  | Body is fragile; physical scenes resolve unfavorably without compensating composition |
| `clumsy` `(–)` | Poor coordination; drops things, fumbles fine motor work                              |
| `sickly` `(–)` | Persistent ill health; tires quickly, susceptible to harm and disease                 |

**Cognitive** (4 + 2 negative)

| Tag | Meaning |
|---|---|
| `educated` | Has acquired substantive knowledge of one or more domains (prose specifies which) |
| `perceptive` | Notices details, reads situations, picks up cues others miss |
| `resourceful` | Improvises, adapts, finds solutions where none are obvious |
| `tactician` | Multi-step strategic planning that anticipates opponents (military, political, criminal, corporate) |
| `unlettered` `(–)` | Illiterate or substantially uneducated; book-based scenes resolve unfavorably |
| `oblivious` `(–)` | Misses details others notice; observation-based scenes resolve unfavorably |

**Social** (4 + 1 negative)

| Tag | Meaning |
|---|---|
| `persuasive` | Sways through argument, evidence, reasoned appeal |
| `intimidating` | Projects threat; others yield through fear or imposing presence |
| `deceptive` | Constructs and maintains false fronts effectively |
| `empathic` | Reads emotional state; understands others' feelings |
| `inarticulate` `(–)` | Poor verbal expression; persuasion / negotiation scenes resolve unfavorably |

**Specialized skill** (7)

| Tag          | Meaning                                                                                                                                                                                 |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `martial`    | Combat-trained; uses era-appropriate weapons / unarmed techniques effectively                                                                                                           |
| `medical`    | Diagnoses and treats injury / illness (era-appropriate: herbalism, surgery, body-mod, magical mending)                                                                                  |
| `mechanical` | Builds / repairs / maintains intricate things (era-appropriate: clockwork, motors, cybernetics, magical artifacts)                                                                      |
| `stealthy`   | Moves unseen; bypasses physical or digital security (era-appropriate: thief, hacker, netrunner)                                                                                         |
| `arcane`     | Trained to manipulate magical / supernatural forces (genre-permitting). Distinct from bodyform's `enchanted` condition (the character has *learned* magic vs. *is* magical in essence). |
| `wild`       | Wilderness-savvy; tracks, forages, navigates untamed nature, reads weather                                                                                                              |
| `urban`      | Street-savvy; navigates dense populations, reads city undercurrents, knows the underclass                                                                                               |

#### Cardinality

Multi-valued. A character carries every capacity that fires on them; the character record never carries a numerical skill score. Magnitude in a domain ("how good a fighter") emerges from composition with adjacent capacities (a `martial` character is competent; `martial` + `tactician` + `strong` + `hardy` reads as a hardened veteran). Arithmetic over capacity tags happens only at the Orrery resolver layer, using package-author coefficients, off-screen — on-screen, Skald reads tags as narrative cues, not as inputs to dice.

Negative anchors are **not** strictly paired with their positive counterparts. Apply them when the absence is *diagnostic* of the character (the elderly scholar is `frail`; an average untrained civilian is simply un-tagged on physical capacities). The handful of negatives clusters on physical and sensory axes where most protagonists have baseline competence and explicit absence is unusual enough to be narratively load-bearing.

#### Applicability

Like disposition and role, capacity assumes person-level sapience for most anchors. Animals get a sparse subset (a cat is plausibly `agile`, `perceptive`, `stealthy`); semi-aware devices and artifacts mostly N/A.

The orthogonality to `role.function` is intentional: `role.function` captures the *social slot* (what others recognize you as), `capacity` captures the *actual skill*. The same character can carry `role.function:healer` + `capacity:medical` (a competent practitioner), `role.function:healer` without `capacity:medical` (a quack), or `capacity:medical` with a different `role.function` (a soldier-medic operating undercover). The 90% case has both fire together; the 10% divergence is narratively interesting and deliberately preserved.

#### Design Crosswalk

| Borrow | Source | What it contributed |
|---|---|---|
| Cross-cutting boolean trait list | Frosthaven road / city events | Validation that compositional booleans gate richer outcomes than skill scores do |
| Anchor names (`strong`, `agile`, `educated`, `resourceful`, `arcane`, `intimidating`, `persuasive`) | Frosthaven traits | Direct lift where the words were sharp and reskin-clean |
| `wild` + `urban` paired environmental affinity | Frosthaven `wild` extended with `urban` counterpart | Tag-level differentiation between e.g. subsistence poacher and skip tracer; both reskin across genres |
| Negative anchors (`frail`, `clumsy`, etc.) | Inverse-tag pattern adapted from disposition | Frosthaven only gates favorably from positive traits; NEXUS gates both ways, so absence-as-diagnostic earns explicit tags |

Intentionally **not** imported:

- A meta-tag for "general intelligence" (e.g. `analytical`) — fails the differential test (would fire on most protagonists). Magnitude in cognition emerges from composition of `educated` + `perceptive` + `resourceful` + (where strategic) `tactician`.
- Per-character bound (Frosthaven's three-traits-per-character limit) — NEXUS allows arbitrary multi-valued; the cross-genre breadth makes a fixed bound too restrictive.
- Levels-within-anchor (e.g. `martial:3` for "expert") — would constitute skill scores, which the project has explicitly avoided. Magnitude stays compositional.

#### Resolved Usage Notes

1. **`urban` in modern / cyberpunk slots.** Keep it, but apply it only when street-level, city-navigation competence is diagnostic. A character who merely lives in a city is not automatically `urban`; the off-grid hermit remains untagged, and the skip tracer / courier / fixer earns the tag.
2. **Negative anchors imply tristate gates.** Accepted. Negative anchors (`frail`, `clumsy`, etc.) make capacity gating three-state: positive-tag-fires, no-tag-fires (baseline), negative-tag-fires. Package authors must handle all three branches when the capacity matters. Do not silently collapse negative-absence to baseline-absence in package logic.

---

## Slot 2 Reference Taggings (6 Characters)

Derived 2026-05-19 from `characters`, `character_psychology`, and `backstory.md` for six core NEXUS characters. Serves as canonical reference for re-applying tags after the existing slot 2 vocabulary is dropped.

### Bodyform

| Character | Tags | Notes |
|---|---|---|
| Alina | `inorganic`, `virtual` | Lost `human` at virtualization; Athena-8 chassis is now essential type; consciousness software-resident |
| Alex | `human` | Open: the "cognitive mirror" predictive faculty — implant or training? If implant, add `cybernetic` |
| Emilia | `human` | Consciousness uploaded into gene-engineered organic host; substrate is biological. Echo Syndrome is `state`, not bodyform |
| Pete | `human` | Cyber-goggles are wearable accessory — fails the `cybernetic` integration test |
| Nyati | `human`, `cybernetic` | Subdermal circuit-lattice is true integration |
| Victor | `human` | Unaugmented |

### Disposition

| Axis | Alina | Alex | Emilia | Pete | Nyati | Victor |
|---|---|---|---|---|---|---|
| Courage | `cautious` | `brave`, `reckless` | `cautious` | `cautious` | `cautious` | `cautious` |
| Aggression | `peaceable` | `peaceable` | `peaceable` | `peaceable` | `fierce` | `aggressive` |
| Loyalty | `loyal`, `suspicious` | `loyal`, `suspicious` | `loyal`, `suspicious` | `loyal`, `suspicious` | `loyal`, `suspicious` | `loyal`, `treacherous`, `suspicious` |
| Compassion | `compassionate` | `compassionate` | `compassionate` | `compassionate` | `compassionate` | `callous` |
| Honesty | `honorable`, `manipulative` | `manipulative` | `honorable` | `honorable` | `honorable` | `manipulative`, `deceitful` |
| Lawfulness | `independent`, `principled` | `iconoclast`, `expedient` | `independent`, `principled` | `iconoclast`, `principled` | `independent`, `principled` | `expedient` |
| Mutuality | `reciprocal`, `cooperative` | `reciprocal`, `cooperative` | `reciprocal`, `cooperative` | `reciprocal`, `cooperative` | `reciprocal`, `cooperative` | `transactional`, `exploitative` |
| Drive | `industrious` | `ambitious` | `industrious` | `industrious` | `ambitious`, `industrious` | `ambitious`, `industrious` |
| Will | `disciplined`, `stoic`, `resolute`, `temperate` | `impulsive`, `volatile`, `wavering` | `disciplined`, `stoic`, `resolute` | `disciplined` | `disciplined`, `stoic`, `resolute` | `disciplined`, `stoic`, `resolute` |
| Pride | `humble`, `secure` | `proud`, `self-effacing`, `insecure` | `proud`, `self-effacing`, `insecure` | `humble`, `self-effacing`, `insecure` | `proud`, `self-effacing`, `insecure` | `arrogant`, `insecure` |
| Outlook | `realistic`, `dispassionate` | `optimistic`, `romantic` | `realistic` | `cynical` | `optimistic`, `realistic` | `cynical`, `dispassionate` |
| Sociability | `reserved` | `gregarious` | `reserved` | `solitary`, `reserved` | `reserved` | `reserved` |

### Capacity

| Character | Capacities |
|---|---|
| Alina | `educated`, `mechanical`, `perceptive` |
| Alex | `perceptive`, `persuasive`, `deceptive`, `stealthy`, `martial`, `resourceful`, `urban` |
| Emilia | `perceptive`, `martial`, `strong`, `hardy` |
| Pete | `mechanical`, `educated`, `stealthy`, `urban`, `resourceful` |
| Nyati | `educated`, `medical`, `tactician` |
| Victor | `tactician`, `persuasive`, `deceptive`, `intimidating`, `resourceful`, `urban` |

### Role (Single-Entity)

| Character | Function | Resources | Fame |
|---|---|---|---|
| Alina | `scholar`, `technician` | `comfortable` | `obscure` |
| Alex | `spy`, `leader` | `comfortable` | `renowned` |
| Emilia | `scholar` *(pre-transfer)* | `comfortable` | `obscure` |
| Pete | `artisan`, `technician` | `poor` | `renowned` *(within tech subcultures; Deadhand kernel)* |
| Nyati | `scholar`, `healer` | `comfortable` | `known` |
| Victor | `leader` | `magnate` | `renowned` *(publicly disgraced exec; widely known)* |

### Role (Scope-Bound Status, Multi-Entity)

| Character | Status rows |
|---|---|
| Alina | `status:outcast(→ Dynacorp)`, `status:respected(→ Ghost_crew)` |
| Alex | `status:pariah(→ Dynacorp)`, `status:respected(→ Ghost_crew)` |
| Emilia | `status:outcast(→ Dynacorp)`, `status:respected(→ Ghost_crew)` |
| Pete | `status:outcast(→ Dynacorp)`, `status:respected(→ Ghost_crew)`, `status:respected(→ tech_underground)` |
| Nyati | `status:pariah(→ Dynacorp)`, `status:respected(→ Ghost_crew)` |
| Victor | `status:pariah(→ Dynacorp)` *(formerly `status:executive(→ Dynacorp)` pre-disgrace; transition captured in `world_events`)* |

### Cluster Findings

- **Moral coalition visible without an alignment axis.** Five crew characters converge on Compassion (`compassionate`), Mutuality (`reciprocal`+`cooperative`), and Honesty (`honorable` for 4 of 5). Victor diverges on all three. Antagonism emerges from values divergence — vindicates the design choice to skip D&D-style alignment.
- **Insecurity baseline.** 5 of 6 characters carry `insecure`; only Alina is `secure` (notable: she literally edited her own affect modulation). The crew's competence-pride-with-fragile-self-worth is a thematic baseline of the cast.
- **Will spectrum fully exercised.** All 8 anchors used; range from Alex's opposite-pole cluster to Alina's 4-anchor maximum. Pete is the lone moderate case (`disciplined` alone).

### Wildcards / Edge Cases (6 Characters)

Diagnostic batch covering non-mainline characters and entity types that stress-test vocabulary boundaries. Derived 2026-05-19 from `characters` and `character_psychology` (Sullivan only had a psych row).

#### Bodyform

| Character | Tags | Notes |
|---|---|---|
| Sullivan (6) | `animal` | Tabby cat; surfaced the need for the `animal` lineage |
| Lansky (21) | `inorganic`, `virtual` | Fully digital consciousness, no embodied form. `human` dropped per Alina precedent — origin captured in `world_events` |
| Sam (22) | `eldritch` | Ancient biomechanical Archivum fragment; biomechanical body is prose detail, `eldritch` captures cognitive illegibility |
| The Bridge (50) | `eldritch` | Semi-sapient alien conduit; barely a "character" in the disposition sense — possibly belongs in a separate entity kind (schema-level open question) |
| Black Kite (53) | `inorganic`, `awakened` | Hybrid AI from spliced Nexus-06 + Alex-2 fragments; awakening from object to actor is exactly `awakened` |
| Cam (99) | `human` | Standard human NPC. ⚠️ `current_activity` field has anomalous data unrelated to Cam — flag for slot 2 data review, not a vocabulary issue |

#### Disposition (— = Axis N/A for This Entity)

| Axis | Sullivan | Lansky | Sam | Bridge | Black Kite | Cam |
|---|---|---|---|---|---|---|
| Courage | `cautious` | `cautious` | `cautious` | — | `brave` | `cautious` |
| Aggression | `peaceable` | `peaceable` | `peaceable` | `peaceable` | `peaceable` | `peaceable`, `gentle` |
| Loyalty | `loyal`, `suspicious` | `suspicious` | `loyal`, `suspicious` | — | `loyal`, `suspicious` | — |
| Compassion | `compassionate` | `callous` | `compassionate` | — | `compassionate` | `compassionate` |
| Honesty | — | `manipulative` | `honorable`, `manipulative` | — | `forthright` | `forthright` |
| Lawfulness | — | `independent` | `independent`, `principled` | — | `independent`, `iconoclast` | `dutiful` |
| Mutuality | `reciprocal` | `transactional` | `transactional`, `reciprocal` | `reciprocal` | `reciprocal`, `cooperative` | `transactional` |
| Drive | — | `industrious` | `industrious` | — | `industrious` | `industrious` |
| Will | `disciplined`, `stoic` | `disciplined`, `stoic` | `disciplined`, `stoic`, `resolute` | `disciplined` | `disciplined` | `disciplined` |
| Pride | `proud`, `secure` | `humble` | `humble`, `self-effacing`, `insecure` | — | `insecure` | `humble`, `self-effacing` |
| Outlook | — | `cynical`, `dispassionate` | `cynical`, `realistic`, `idealistic` | `idealistic` | `optimistic`, `idealistic` | `cynical`, `realistic` |
| Sociability | `reserved` | `solitary`, `reserved` | `solitary`, `reserved` | — | `reserved` | `reserved` |

#### Capacity (— = Capacity N/A for This Entity)

| Character | Capacities |
|---|---|
| Sullivan | `agile`, `perceptive`, `stealthy` |
| Lansky | `educated`, `deceptive`, `stealthy`, `mechanical` |
| Sam | `educated`, `arcane`, `perceptive` |
| The Bridge | — |
| Black Kite | `educated`, `perceptive` |
| Cam | `perceptive`, `resourceful`, `empathic`, `urban` |

#### Role (— = Sub-Category N/A for This Entity)

| Character | Function | Resources | Fame | Status (scope-bound) |
|---|---|---|---|---|
| Sullivan | — | — | — | — |
| Lansky | `spy`, `merchant` *(info-broker)* | `comfortable` *(Grid economy)* | `obscure` | `status:outcast(→ Dynacorp)`, `status:respected(→ Grid_underground)` |
| Sam | `teacher`, `scholar` | — | `obscure` | `status:outcast(→ Archivum)` *(banished or self-exiled — narrative ambiguity preserved)* |
| The Bridge | — | — | — | — |
| Black Kite | — *(still emerging)* | — | `obscure` | — *(Archivum has registered it as `Node-07`; may emerge as `status:respected(→ Archivum)` once integration completes)* |
| Cam | `functionary` | `poor` | `obscure` | `status:junior(→ Dynacorp_Retail)` |

#### Anchors First-Fired in Wildcard Round

- `idealistic` (Outlook): Sam, Black Kite, Bridge — earned its keep across multiple Archivum-mythos entities
- `forthright` (Honesty): Black Kite, Cam
- `dutiful` (Lawfulness): Cam (corporate good-citizen archetype)
- `gentle` (Aggression): Cam
- `secure` (Pride): Sullivan (joining Alina)

**All disposition anchors across all 12 axes have now fired at least once in the 12-character sample. The vocabulary is fully exercised; no anchor is decorative.**

#### Open Items Surfaced (Beyond Vocabulary)

- **Cam data anomaly:** `current_activity` field describes a different character/setting ("consciousness couture", "HALCYON THREADS stockroom"). Flag for slot 2 data review.
- **Bridge entity-kind question:** semi-sapient devices/artifacts may warrant a separate entity kind from `characters`. Schema-level decision, deferred.

---

## Place Categories

Place tags describe package-relevant facts about a location. They deliberately
avoid ownership, residence, factional control, and route topology: those are
multi-entity rows (`claims`, `resides_at`, `operates_from`) or travel substrate
facts. A place can be many things at once; the old `place_affordance` bucket was
too vague because it mixed function, geography, secrecy, permissions, and
danger into one axis.

**Registry-name constraint.** The live `tags` registry keys by global `tag`
string, not by `(category, tag)`. Place anchors therefore avoid bare common
words that already mean something elsewhere (`known` is `role.fame`, `medical`
is `capacity`, `contested` is `legitimacy`). The category still carries the
axis; the tag string stays globally unique.

| Category | Cardinality | Ephemerality | Anchors |
|---|---|---|---|
| `place_function` | Multi-valued | Durable | `commerce`, `dwelling`, `place_medical`, `transit`, `archive`, `fortification`, `haven`, `sacred`, `meeting`, `tomb`, `confinement`, `learning`, `craft`, `military`, `production`, `administration`, `water_source`, `entertainment` |
| `place_visibility` | Exclusive | Durable | `place_known`, `place_hidden` |
| `place_access` | Exclusive | Durable | `place_open`, `place_restricted` |
| `place_environment` | Multi-valued | Durable | `urban_dense`, `urban_sparse`, `rural`, `wilderness`, `subterranean`, `underwater`, `aerial`, `mountainous`, `forest`, `desert`, `polar`, `marshland`, `coastal` |
| `place_threat` | Exclusive | Ephemeral | `place_safe`, `place_contested`, `place_dangerous` |

### `place_function` (Multi-Valued, Durable)

The functional role a place serves. Multi-valued because real places stack
functions freely: a medieval tavern is `commerce` + `dwelling` + `meeting` +
`entertainment`; a monastery is `sacred` + `dwelling` + `learning`; the Burrow
safe-house is `dwelling` + `haven`.

| Tag | Meaning / Package Reading |
|---|---|
| `commerce` | Goods, services, markets, meals, rooms, brokerage, or ordinary buying/selling can happen here. |
| `dwelling` | Habitual or temporary shelter; supports sleep, domestic routines, private recovery, or household scenes. |
| `place_medical` | Care, triage, healing, diagnosis, surgery, apothecary work, body-mod, or magical treatment. |
| `transit` | Movement node or passage: street, road, station, port, stable, garage, tunnel, gate, airlock, or route junction. |
| `archive` | Records, memory, libraries, logs, vaults, databases, museums, or evidence repositories. |
| `fortification` | Defensible structure or prepared position; improves defense / resistance branches. |
| `haven` | Shelter that is discreet or safe enough for hiding, recovery, or pressure relief. Usually composes with `place_hidden` and/or `place_restricted`, but not always. Durable until an authored/event update changes the place's facts; a burned or discovered safe-house gets rewritten, not time-cleared. |
| `sacred` | Ritual, worship, taboo, blessing, curse, pilgrimage, memorial, or divine/social awe. |
| `meeting` | Plausible gathering or negotiation venue; neutral-ground readings emerge from claims/access/status, not a separate tag. |
| `tomb` | Burial, remembrance, grave-tending, ancestor contact, or the dangerous boundary between dead and living. |
| `confinement` | Prison, cell, cage, holding facility, quarantine, asylum, detention office, or magical containment. |
| `learning` | Instruction, study, apprenticeship, school, academy, dojo, lab seminar, or knowledge transfer. |
| `craft` | Small-scale making/repair: workshop, forge, studio, garage bench, occult circle, body-mod chair. |
| `military` | Barracks, command post, armory, drill yard, war room, police precinct, mercenary camp. |
| `production` | Large-scale extraction, agriculture, manufacturing, energy, food preparation, server farms, or industrial throughput. |
| `administration` | Bureaucratic, clerical, judicial, corporate, planning, permit, accounting, or institutional paperwork work. |
| `water_source` | Routine or urgent water access: fountain, well, pump, riverbank, cistern, oasis, hydration station. |
| `entertainment` | Performance, leisure, gaming, spectacle, drinking culture, sex-work venue, theatre, club, festival ground. |

**Boundary rule.** `commerce` says "transactions can happen here," not "food is
always available." `water_source` earns a separate anchor because thirst gates
read it differently from ordinary commerce. Likewise, `haven` is not a claim of
ownership or secrecy by itself; it is the place's practical shelter quality.

### `place_visibility` (Exclusive, Durable)

Whether the place's existence and location are generally discoverable.

| Tag | Meaning / Package Reading |
|---|---|
| `place_known` | Ordinary locals / relevant actors can learn or find it without special knowledge. Usually the default and may be omitted until cardinality enforcement exists. |
| `place_hidden` | Existence or route is concealed, secret, unmapped, warded, socially obscured, or otherwise unavailable to ordinary search. |

If `place_hidden`, use `knows_location(character -> place)` rows to specify who can
find it. Do not encode "known to Alex but hidden from Dynacorp" in the place
tag itself; the tag is the global posture, and the pair-tags carry exceptions.

### `place_access` (Exclusive, Durable)

Whether entry/use is ordinarily available.

| Tag | Meaning / Package Reading |
|---|---|
| `place_open` | A character can enter or use it without special permission, membership, cover, coercion, or key. |
| `place_restricted` | Entry/use requires permission, membership, disguise, key, bribe, invitation, clearance, taboo status, or force. |

If `place_restricted`, use `can_access(character|faction -> place)` rows for known
permissions. A faction-mediated access row lets ordinary members or agents
derive access by story context without writing one row per character.

### `place_environment` (Multi-Valued, Durable)

Physical or geographic environment. Multi-valued because geography composes:
Hong Kong is `urban_dense` + `coastal`; a castle in the Alps is `mountainous` +
`forest`; a flooded subway can be `subterranean` + `underwater` + `urban_dense`.

| Tag | Meaning / Package Reading |
|---|---|
| `urban_dense` | High-density built environment: crowds, infrastructure, surveillance, businesses, alleys, verticality. |
| `urban_sparse` | Built environment with lower density: suburbs, small towns, industrial outskirts, scattered services. |
| `rural` | Cultivated or settled countryside: farms, hamlets, estates, roads, fields. |
| `wilderness` | Uncultivated or minimally settled terrain; supports foraging, tracking, exposure, rough travel. |
| `subterranean` | Underground, buried, tunnelled, cavernous, basement, sewer, bunker, root-space. |
| `underwater` | Submerged or aquatic environment; gates breath, pressure, visibility, equipment. |
| `aerial` | Airborne, skyborne, floating, cliff-suspended, orbital-in-atmosphere, or otherwise height-dominant. |
| `mountainous` | Steep terrain, altitude, passes, cliffs, avalanches, thin air, defensible approaches. |
| `forest` | Dense tree/vegetation cover; gates concealment, travel, hunting, navigation. |
| `desert` | Arid exposure, water scarcity, heat/cold swings, sparse settlement. |
| `polar` | Extreme cold, ice, snow, seasonal darkness, survival pressure. |
| `marshland` | Wetlands, bog, swamp, reeds, unstable ground, insects, hidden channels. |
| `coastal` | Shore, port, tide, sea access, beach, cliffs, fisheries, flood risk. |

Do not create era-specific environmental tags (`spaceport`, `arcology`,
`wizard_tower`) unless the reskinned function or environment cannot be expressed
by composition. A spaceport is usually `transit` + `military` or `commerce` +
`urban_dense`; a wizard tower is `learning` + `archive` + `fortification` +
maybe `sacred`.

### `place_threat` (Exclusive, Ephemeral)

Current danger posture. Exclusive and ephemeral because threat shifts after
events; new major danger/safety events should replace the current row rather
than stack contradictory rows.

| Tag | Meaning / Package Reading |
|---|---|
| `place_safe` | Currently low-risk enough that rest, recovery, negotiation, or routine work can proceed without threat pressure. Not a permanent promise. |
| `place_contested` | Active dispute, occupation, tension, surveillance, siege, jurisdictional conflict, or factional pressure. |
| `place_dangerous` | Immediate or predictable harm: violence, monsters, disaster, toxic conditions, traps, hostile patrols, collapse risk. |

**Clearance / replacement.** `place_threat` should use semantic replacement
initially: `place_safe` becomes `place_dangerous` after an attack,
`place_contested` after a claim or occupation, `place_safe` again after a
settlement / cleanup / protection event.
Do not overbuild a bespoke event table before Slot 2 backfill reveals which
place-threat transitions actually recur.

### Legacy `place_affordance` Mapping

`place_affordance` is dropped as a category. Migration 043 marks it deprecated
and registers the replacement categories; the resolver shim reads old and new
rows until the data rewrite lands. Migration/backfill should use a reviewed
manifest rather than a one-size-fits-all mapping, but these defaults are safe
starting points:

**Seed prerequisite.** This mapping cannot be applied until a registry migration
seeds the target place anchors. `administration` and `water_source` are newly
introduced by this draft, and the rest of the replacement anchors also need
real `tags` rows because migration 043 registered only category names.

| Legacy / Sample Value | New Reading |
|---|---|
| `home` | `place_function:dwelling`; add `resides_at(character -> place)` for actual residents. |
| `lodgings` | `place_function:dwelling` + usually `commerce`; access depends on story. |
| `safe_house` | `place_function:dwelling` + `haven` + usually `place_visibility:place_hidden` and `place_access:place_restricted`. |
| `tavern` / `teahouse` / `cafe` / `restaurant` / `cookshop` | `place_function:commerce`; add `meeting`, `entertainment`, `dwelling`, or `water_source` only when the venue really supports that branch. |
| `market` | `place_function:commerce` + `meeting`; often `place_access:place_open`. |
| `public_water` | `place_function:water_source`; access/visibility as appropriate. |
| `wilderness` | `place_environment:wilderness`; add `water_source`, `forest`, `mountainous`, etc. only from prose. |
| `street` / `transit_hub` | `place_function:transit`; pair with `urban_dense`, `urban_sparse`, or other environment tags. |
| `the_roots` | `place_environment:subterranean` plus `place_function:transit`, `archive`, `dwelling`, or `production` depending on the specific Roots location. |
| `the_glow` | `place_environment:urban_dense`; usually `place_visibility:place_known`, often `place_access:place_open`. |
| `town_square` / `public_space` / `general_social_venue` / `neutral_ground` | `place_function:meeting`; neutrality emerges from claims/access/status rows, not a tag. |
| `intimate_social_venue` / `intimate_services_establishment` | `place_function:meeting` and/or `entertainment`; contracted access should use `contact:intimate` where package gates need a relationship edge. |
| `private_quarters` | `place_function:dwelling` + usually `place_access:place_restricted`. |
| `workplace` / `worksite` / `administrative_office` | `administration`, `production`, `craft`, `place_medical`, `military`, or another concrete function based on the actual work. |
| `place_of_remembrance` | `tomb` and/or `sacred`; use `meeting` only for public memorial sites. |

---

## Faction Categories

Companion: `docs/orrery_faction_vocabulary.md`. Migration 052 seeds the 65
faction tag anchors, and `nexus faction-apply --slot N --manifest PATH
[--execute]` covers the reviewed deterministic entity-tag rewrite slice.
Review-required Slot 2 values, faction table API cleanup, column drops, and
clearance-event collapse remain follow-up work.

Faction categories describe group-level actors: institutions, movements,
corporations, gangs, churches, polities, guilds, scenes, families, and other
organizations. The draft deliberately stays within the six categories registered
by migration 043 and does not add a generic faction `state` category; passive
faction conditions decompose into `power_status`, `agenda`, pair-tags, event
history, or prose.

| Category | Cardinality | Ephemerality | Seeded tags |
|---|---|---|---|
| `ideology` | Multi-valued | Durable | `authoritarian`, `egalitarian`, `traditionalist`, `progressive`, `theocratic`, `secularist`, `nationalist`, `cosmopolitan`, `imperial`, `communalist`, `mercantilist`, `technocratic`, `revolutionary`, `restorationist`, `isolationist` |
| `resource_base` | Multi-valued | Durable | `capital`, `force`, `information`, `faith`, `industry`, `labor`, `territory`, `patronage`, `bureaucracy`, `technology`, `specialized_knowledge`, `criminal_network`, `supply_lines`, `mobility` |
| `legitimacy` | Exclusive | Durable | `state_recognized`, `customary`, `tolerated`, `shadow_legal`, `underground`, `outlaw`, `contested` |
| `operational_mode` | Exclusive | Durable | `overt`, `covert`, `hybrid` |
| `power_status` | Exclusive | Ephemeral | `dominant`, `ascending`, `stable`, `pressured`, `declining`, `fragile`, `collapsed` |
| `agenda` | Multi-valued | Ephemeral | `expand_control`, `consolidate_control`, `infiltrate`, `seize_leadership`, `settle_succession`, `recover_losses`, `negotiate`, `mobilize`, `investigate`, `recruit`, `extract_resources`, `sabotage`, `suppress_dissent`, `conceal_exposure`, `reform_internal`, `secure_alliance`, `enforce_claim`, `protect_asset`, `retaliate` |

Legacy sample values rename for clarity: `revanchist` -> `recover_losses`,
`coup` -> `seize_leadership`, `succession` -> `settle_succession`,
`infiltration` -> `infiltrate`, `expansion` -> `expand_control`, and
`consolidation` -> `consolidate_control`.

### `factions` Table Cleanup (Future Data Migration Scope)

**Drop columns (move to tags):**
- `ideology` → tag category `ideology`
- `power_level` → tag category `power_status`
- `hidden_agenda` → tag category `agenda`
- `resources` → tag category `resource_base`

**Drop columns entirely:**
- `history` — narrative belongs in `world_events`
- `current_activity` — usually should become `agenda`; otherwise prose
- `territory` — should be multi-entity tag `claims(faction → place)`

**Keep columns:**
- `id`, `name`, `entity_id` (identity)
- `summary` (true narrative prose)
- `primary_location` (FK to places)
- `created_at`, `updated_at`, `extra_data`

---

## Story Slot / Genre Tags

Genre is informational metadata about the story slot. It can guide prompts,
Retrograde seeding, weirdness calibration, UI grouping, and package
interpretation, but it **does not gate vocabulary admission**. A fantasy slot
may contain cybernetics; a cyberpunk slot may reveal goblins. The closed
vocabulary remains universal.

The authoritative runtime source today is the new-story setting enum
(`nexus/api/new_story_schemas.py::Genre`) persisted as `setting_genre` and
`setting_secondary_genres`. If these are mirrored into the Orrery registry, use
a story-slot `genre` category with the same canonical values below; UI/prompt
surfaces may display them as `genre:<value>`.

**Registration status.** No current migration registers a story-slot `genre`
category in `tag_category_registry`, and the current `entity_kind` enum has no
story-slot kind. Treat registry mirroring as blocked on a dedicated substrate
migration; today these values remain setting-column metadata.

### `genre` (Multi-Valued, Durable, Story Slot)

Primary and secondary genres share one closed vocabulary. The primary genre is
the story's dominant contract; secondary genres are modifiers. The category is
multi-valued because blended stories are normal.

| Tag | Meaning / Reading |
|---|---|
| `fantasy` | Magic, mythic beings, secondary-world or folkloric possibility. |
| `scifi` | Speculative science / technology as a major story premise. Canonical value remains `scifi`, matching the existing enum; do not spell this `science_fiction` in registry rows. |
| `horror` | Fear, dread, violation, monstrosity, or survival under uncanny threat. |
| `mystery` | Discovery of hidden facts drives the central contract. |
| `historical` | Past era or alternate-history grounding is central to the setting contract. |
| `contemporary` | Present-day or near-present mundane baseline. |
| `postapocalyptic` | Social order after collapse, catastrophe, extinction pressure, or ruined infrastructure. |
| `cyberpunk` | High-tech / low-trust social order; identity, surveillance, augmentation, networks, corporations, or illicit tech scenes are central. |
| `steampunk` | Industrial-era speculative machinery, retrofuturism, alternate engineering, or gaslamp-technological romance. |
| `urban_fantasy` | Supernatural or mythic elements embedded in a modern / urban ordinary world. |
| `space_opera` | Large-scale interstellar adventure, politics, war, exploration, or mythic science-fiction scope. |
| `noir` | Cynical investigation, moral compromise, shadows, corruption, fatalism, or hardboiled social texture. |
| `thriller` | High-tension danger, pursuit pressure, conspiracy, countdowns, or suspense-forward pacing. |

**Alias discipline.** `postapoc` is an API/enum member name but the stored value
is `postapocalyptic`; `science_fiction` is a human synonym but the stored value
is `scifi`. Do not add aliases to the tag registry unless import/backfill code
needs to canonicalize legacy rows. `romance`, `western`, `cozy`, `grimdark`,
and similar candidates are not admitted until the setting enum and any
per-genre Retrograde config are updated together.

**Mechanical boundary.** Packages may read genre as context when ranking or
wording branches, but package predicates should not say "only fantasy can have
`arcane`" or "only scifi can have `cybernetic`." Genre selects expectations;
entity tags describe facts.

---

## Multi-Entity Tags

**Implementation-status legend** (applies to all multi-entity tag tables below + the trait alignment section):

- *(no marker)* — Seeded by the migration named in context (`042` for the original pair-tag set, `045` for trait-compiler additions/status/`claims` extension); runtime-ready.
- **⏳ DESIGN-TARGET** — Settled in this doc, but not yet fully represented by shipped schema/data/compiler behavior. Treat as design-target until the referenced issue or migration lands.

### Place-Bound (6)

| Tag | Subject | Object | Purpose |
|---|---|---|---|
| `knows_location` | character | place | Knowledge of the place's existence and how to find it |
| `can_access` | character \| faction | place | Permission to enter (direct individual or group-mediated) |
| `claims` | character \| faction | place | Territorial claim; contestation emerges from row cardinality. The character-side polymorphism was added by migration 045 so the registry can accept future `Domain` trait bestowals. |
| `resides_at` | character | place | Habitual residence (multi-residence supported) |
| `operates_from` | faction | place | Operational base (distinct from `claims`) |
| `originates_from` | character | place | Origin / hometown |

### Character / Faction Relations (6)

| Tag | Subject | Object | Purpose |
|---|---|---|---|
| `hunting` | character \| faction | character | Active intentional targeting; ephemeral. Confers narrow elevated detection sensitivity for the target (see issue #282). Migration 048 renames live `pursuing` rows to `hunting`, deprecates the old pair-tag, and retires the single-entity `under_active_pursuit` signal. *Reskinning rationale: "hunt" generalizes better than "pursue" across genres; the concept is not physical-chase-specific.* |
| `handles` | character | character | Operative-handler relationship; covert/operational |
| `obligation` | character \| faction | character \| faction | Debt / oath / loyalty; kind inferable from establishing event |
| `authority_over` | character \| faction | character \| faction | Interpersonal/positional power over a specific other entity. Distinct from scope-bound status (a king has `authority_over` a vassal directly; a senior officer in an institution holds `status:senior(→ faction)` against that institution's membership) |
| `protects` | character \| faction | character | Active protective relationship; durable |
| `mentors` | character | character | Teaching/training |

### Scope-Bound Status (1 Family — `status:<level>`)

| Tag family | Subject | Object | Purpose |
|---|---|---|---|
| `status:<level>` | character \| faction | faction | Scope-bound social/institutional position within the audience-faction. The level is encoded in the tag name via the existing colon convention (`status:senior`, `status:outcast`, etc.). Maps to trait_menu's `Status` trait. Seeded by migration 045. |

**Level vocabulary** (each registers as a distinct `pair_tags` row):

- *Hierarchy ranks*: `junior`, `senior`, `executive`, `sovereign`
- *Social positions*: `respected`, `elite`
- *Negative positions*: `outcast`, `pariah`, `enslaved`

**`commoner` is the untagged default.** Ordinary citizens of a faction — no elevated rank, no informal recognition above baseline, not negatively positioned — carry *no* `status:<level>` row scoped to that faction. The compiler should NOT synthesize a `status:commoner` row for ordinary NPCs; the absence-of-row IS the commoner reading. This matches the same default-absent pattern as `role.fame:obscure` and `role.resources:comfortable`.

**Level vocabulary is closed.** Status follows the same closed-vocabulary discipline as every other category in this registry. Genre-specific status-level additions (`status:apprentice`, `status:guildmaster`, `status:exiled`, etc.) require deliberate registry additions via migration; they are NOT added at runtime via Skald proposals or other auto-registration paths. The runtime `new_tag_proposals` path that previously allowed such growth was removed in #293. The `LEGACY_ORRERY_PROPOSAL_KEY` constant remains — not as historical residue, but as an **active strip-filter** at `nexus/api/new_story_schemas.py:27` that silently discards any `new_tag_proposals` key submitted by legacy callers. Dead as a growth mechanism; still live as a sanitization guard — do not remove without first removing the strip-filter. When a new status level is warranted for a story or genre, the path is: register it in a migration, then it becomes available for bestowal.

**Formal vs. informal** is read off the scope-faction's own tags (its `legitimacy`, `operational_mode`), NOT the status tag itself. `status:senior(char → US_Army)` reads as formal military rank; `status:senior(char → village_elders)` reads as informal community elevation. Same level anchor, different flavor by composition.

Status-family reads and writes go through `nexus.agents.orrery.status_family` / `apply_status_pair_tag_bestowal` rather than ad-hoc string parsing in individual packages. Within a single `(subject, scope_faction)` edge, status is exclusive: bestowing a new `status:<level>` clears sibling `status:*` rows for that same edge.

### Trait-Compiler Relationship Pair Tags

Migration 045 registered the first trait-compiler relationship tags. Migration 047 deprecates the bare `contact` pair-tag for new gates and registers the kind-qualified contact family.

**Important per #303**: these tags' existence in the registry does NOT mean the compiler instantiates them automatically at trait selection. Per the functional-vs-affective principle (Pair Tags vs. `character_relationships` Source-of-Truth Rule below), affective traits (Allies, Contacts, Enemies) compile primarily to `character_relationships` rows. The pair-tags below exist for *future* package gates that may need a binary mechanical edge; the compiler adds them per-package, not by default at trait selection time.

| Tag | Subject | Object | Purpose |
|---|---|---|---|
| `ally` | character | character | Will actively help when it matters; takes risks for the other |
| `contact:lodging` | character | character | Contact can provide lodging, shelter, or safe-house access |
| `contact:social` | character | character | Contact can provide ordinary social connection, favors, messages, or indirect channels |
| `contact:intimate` | character | character | Contact can provide contracted-intimacy access where the setting supports it |
| `hostile_to` | character \| faction | character \| faction | Active opposition; willing to expend energy thwarting the other. **Durable** — captures simmering enmity (the Enemies trait is a durable character feature, not an acute episode). Distinct from `hunting` (which is *ephemeral, purposeful, acute* targeted pursuit). A character can be `hostile_to` someone without currently `hunting` them; conversely a hunt may fire without antecedent hostility. |

All cardinalities multi-valued. Polymorphic subjects/objects collapse what would otherwise be ~30 separate tags.

The bare `contact` pair-tag was registered by migration 045 but is deprecated by migration 047. Use `contact:<kind>` for package gates; generic contact flavor belongs in `character_relationships`.

### Pair Tags vs. `character_relationships` — Source-of-Truth Rule

The `ally`, `contact:<kind>`, and `hostile_to` tags (and their future siblings) sit alongside the existing `character_relationships` table. Both layers can describe what looks like "the same" relationship — but they answer different questions and must not drift.

- **`pair_tag`** = typed mechanical edge that packages gate on. Binary: exists or it doesn't, plus the tag name. Cheap to query; deterministic. Example: a HIDE package gating on "does the acting character have any `hunting(other → self)` edges?"
- **`character_relationships`** = affective / historical / valence layer that Skald and social-logic read. Multi-state; evolves continuously over time; carries trust, valence, history, sub-states. Example: Skald composing prose that reflects "Alex and Emilia were close, then there was a falling-out, then a partial reconciliation."

**Functional-vs-affective compiler principle (decided 2026-05-23 per issue #303; applies uniformly across all affective traits).** Affective traits — ally, contact, patron, dependents, enemies, and any future trait describing a graded interpersonal bond — compile primarily to a `character_relationships` row capturing the affective bond. Pair-tags are added **selectively**, only where a specific package needs to gate on the edge. The compiler does **not** pre-provision pair-tags "just because the trait was selected"; each pair-tag is justified by a specific package that gates on it. When in doubt, write only the relationship row and add pair-tags reactively when a package implementation requires them. See the trait→tag mapping table below for per-trait application.

The compiler writes both layers within a single transaction *when both are warranted*. Reconciliation invariants:

- Every `ally` / `contact:<kind>` / `hostile_to` pair tag MUST have a corresponding `character_relationships` row (these tags carry intrinsic affective content)
- The converse does NOT hold uniformly — a `character_relationships` row need not have a parallel pair-tag unless a package needs the gate

Drift between paired rows is a bug. Issue #291 codified the rule and added the reconciliation surface in `nexus/api/trait_compiler.py::reconcile_trait_relationship_pair_tags`.

---

## trait_menu ↔ Tag-Vocabulary Alignment

The player-facing trait system (`docs/trait_menu.md`) is the wizard's entry point during character creation. Each character chooses 3 traits from the optional list, plus 1 required wildcard. The compiler implemented for new-story bootstrap is intentionally narrower than the full design target: every selected trait returns a structured `TraitCompileResult`, and unsupported or under-specified traits become explicit `prose_only_remainders` rather than silent mechanical loss.

Compiler surfaces:

- **Final bootstrap apply:** `nexus/api/new_story_db_mapper.py` calls `apply_character_trait_compilation()` after protagonist insertion and persists the result to `characters.extra_data.trait_compile_result` plus `assets.new_story_creator.trait_compile_result`.
- **Dry-run audit:** `nexus trait-audit --slot N` reads the wizard cache, runs `compile_character_traits(..., dry_run=True)`, and reports applied writes vs. prose-only remainders. `--fail-on-remainders` is available for testing loops; normal wizard/UI flow does not add a confirmation screen.

| trait_menu trait | Current compiler behavior | Design target / notes |
|---|---|---|
| `Status` | Writes `status:<level>(char → faction)` when `TraitCompileInputs.status` provides a scope faction and closed level. Missing/unknown scope or level becomes a structured remainder. | Scope-faction can be formal or informal; flavor is read from the faction's own tags. |
| `Fame` / legacy `Reputation` | Writes `role.fame:<level>` when typed input supplies `obscure`, `known`, `renowned`, or `legendary`. Legacy `reputation` input aliases to `fame`. | Rename landed in migration 045; `reputation` remains accepted as a compatibility alias. |
| `Resources` | Writes `role.resources:<level>` when typed input supplies `destitute`, `poor`, `comfortable`, `wealthy`, or `magnate`. | `comfortable` is the default/ordinary tier; absence of typed input is reported, not guessed. |
| `Allies` | Writes `character_relationships` rows from structured targets. No pair-tag by default; optional `apply_pair_tag=True` writes `ally(char → char)` in the same transaction. | Per #303, affective relationship row first; pair-tag only when a package gate needs the binary edge. |
| `Contacts` | Writes `character_relationships` rows from structured targets. No pair-tag by default; optional `apply_pair_tag=True` requires `contact_kind` (`lodging`, `social`, or `intimate`) or an explicit `contact:<kind>` pair-tag. | The bare `contact` pair-tag is deprecated as a package gate. Needs templates consume `has_contact_of_kind(...)` predicates. |
| `Enemies` | Writes `character_relationships` rows from structured targets. Optional `apply_pair_tag=True` can write `hostile_to`; target-to-protagonist direction is supported. | Acute targeting remains the `hunting` pair-tag track, not default `hostile_to`. |
| `Domain` | Current MVP returns a prose-only remainder. | Target design: create/identify a place entity and write `claims(char → place)`; registry polymorphism is ready, compiler input/schema is not. |
| `Patron` | Current MVP returns a prose-only remainder. | Target design: one `character_relationships` row for the patron-client bond; package-specific pair-tags later as needed. This preserves the #305 resolution: patron is not decomposed into a default OR/AND bundle of mentor, sponsor, protector, and authority edges. |
| `Dependents` | Current MVP returns a prose-only remainder. | Target design: `protects(char → dependent)` plus affective relationship row; no default `authority_over`/`obligation` edge. |
| `Obligations` | Current MVP returns a prose-only remainder. | Target design: `obligation(char → target)` when a structured target exists. |
| `Wildcard` | Outside the current selected-trait compiler loop. The wizard persists prose in `characters.extra_data.wildcard`, and any Skald-bestowed `orrery_tags` apply through the ordinary tag bestowal surface. | Future wildcard decomposition may only use registered vocabulary. It cannot mint tags; novel mechanics remain prose/`extra_data` until a compiler surface exists. There is no planned `items` table; inanimate artifacts stay prose/`extra_data` unless/until project scope changes. |

**Migration 045 landed the trait-compiler substrate portion**: `role.resources`, `role.fame`, the status pair-tag family, `ally`, `contact`, `hostile_to`, the `claims` subject-kind extension, the `assets.traits` `reputation` → `fame` rename, and the `trait_compile_result` cache column. **Migration 047 refines contacts** by deprecating bare `contact`, adding `contact:lodging` / `contact:social` / `contact:intimate`, and deprecating the old single-entity contact flags. The compiler code owns only the current MVP rows above; the table is deliberately split so future docs do not confuse registry readiness with compiler readiness.

---

## Dropped / Rejected Vocabulary

| Dropped | Reason |
|---|---|
| `access_granted_to` | Folded into `can_access` via polymorphic subject |
| `bound_to` + `owes` | Merged into `obligation` |
| `controls` | Too vague — Skald-confusion attractor |
| `orrery_state` (category) | System-bookkeeping moves to dedicated tables |
| `place_affordance` (category) | Decomposed into function / visibility / access / environment / threat. Migration 043 marks the category deprecated and registers replacement categories; legacy tag rows remain readable through the resolver shim until data rewrite. |
| `profession_lite` (category) | Merged into `role`. Migration 043 marks the category deprecated; legacy tag rows remain live until rewritten. |
| `orrery_signal` (category) | Merged into `state`. Migration 043 marks the category deprecated; legacy tag rows remain live until rewritten. |
| `defensive_position` (place_function value) | Renamed to `fortification`; `haven` added |
| Vocabulary Growth Contract | Replaced by locked-vocabulary discipline |

---

## Open Items

1. **Character category implementation.** `bodyform`, `disposition`, `capacity`, the role split (`role.function`, `role.resources`, `role.fame`, scope-bound `status`), and the companion `state` vocabulary are now drafted. Remaining work is implementation-specific: seed any still-missing tags and keep compiler support aligned with typed inputs.
2. **Place category implementation.** Values are drafted here. Migration 043 registers the replacement categories, but follow-up work still needs to seed the new place anchors, migrate/deprecate legacy `place_affordance` rows, and remove the resolver shim after backfill.
3. **Faction category implementation.** Drafted in `docs/orrery_faction_vocabulary.md`; migration 052 seeds the closed 65-anchor tag vocabulary. Remaining work: Slot 2 mapping, faction-table cleanup, and clearance-event collapse.
4. **Story/genre implementation.** Values are drafted here from the existing `Genre` enum. The runtime currently stores them on new-story setting columns; a story-slot entity/category mirror is optional future substrate, blocked on an entity-kind/category-registration migration and not a blocker for current packages.
5. **Clearance vocabulary for ephemerals.** State clearance events are enumerated in `docs/orrery_state_vocabulary.md`. Faction `agenda` / `power_status`, `place_threat`, and any future ephemeral pair-tags still need event-collapse passes before event-cleared registry rows replace today's semantic-clearance defaults.
6. **Cardinality column on `tags` registry.** Migration to add `cardinality enum('exclusive', 'multi')`.
7. **`entity_pair_tags` substrate** — mostly landed. PR #283 shipped the migration (`042_orrery_entity_pair_tags.py`), the `pair_tags` registry, the `entity_pair_tags` table, and the writer functions (`apply_pair_tag_bestowal`, `clear_pair_tag`). PR #284 shipped the DB-level predicates (`pair_tag_exists`, `lookup_pair_tag_subjects`, `lookup_pair_tag_objects`). PR #285 shipped WorldState hydration + Condition-shape predicates (`has_pair_tag` over hydrated state). Migration 048 adds the `hunting` rename plus `has_inbound_pair_tag(...)` template gates; future work is now limited to any additional pair-tag-derived binding composers demanded by package implementations.
8. **Audit pass on existing slot 2 vocabulary.** Per-tag classification: keep (in new categories), rename, drop, or convert to multi-entity tag.
9. **Template rewrite.** `NEXUS_template` schema/seed updates downstream of vocabulary lock-in.
10. **Slot 2 backfill data plan.** Re-apply settled tags to existing slot 2 entities; this is ready to plan against the completed vocabulary draft and remains tracked by issue #326.

---

## Related Artifacts

- `docs/trait_menu.md` — player-facing trait selection system; alignment documented above.
- `docs/orrery_design_plan.md` — broader Orrery system design.
- `docs/orrery_state_vocabulary.md` — authoritative spec for the `state` category; kept separate from this registry overview because it carries clearance contracts, substrate debts, and state-specific migration notes.
- `docs/orrery_faction_vocabulary.md` — draft spec for faction tag categories, legacy category mapping, seeded anchors, and faction table cleanup implications.
- `nexus/api/new_story_schemas.py::Genre` — current runtime source of truth for the story genre values mirrored in the Story Slot / Genre Tags section.
- `nexus/agents/orrery/resolver.py::LOCATION_CLASS_TAG_CATEGORIES` — cutover shim that hydrates legacy `place_affordance` plus the replacement place categories into `WorldState.location_classes` until the data rewrite removes the old rows.
- `migrations/043_orrery_category_refactor_phase1.py` — registers the place and faction replacement category names and records the legacy-to-replacement mappings.
- `migrations/042_orrery_entity_pair_tags.py` — source-of-truth for seeded multi-entity tags (registry rows in `pair_tags`).
- `migrations/045_trait_compiler_substrate.py` — trait-compiler registry additions, `claims` subject-kind extension, `reputation` → `fame` data update, and audit cache column.
- `migrations/047_kind_qualified_contact_pair_tags.py` — `contact:<kind>` registry additions plus deprecation of `contacts_available`, `intimate_services_contact`, and bare `contact`.
- `migrations/048_orrery_hunting_pair_tag.py` — `pursuing` → `hunting` pair-tag rename plus deprecation of `under_active_pursuit`.
- `migrations/052_orrery_faction_tag_vocab.py` — seeds the 65 faction tag anchors across `ideology`, `resource_base`, `legitimacy`, `operational_mode`, `power_status`, and `agenda`.
- `migrations/053_retire_faction_legacy_write_defaults.py` — drops the legacy `factions.power_level` default so new runtime inserts do not create fresh obsolete faction strength values.
- Issue #275 / PR #276 — Skald sovereignty (adjudication) model. *Merged.*
- Issue #282 — Package self-awareness architectural pattern (three-stage gating: entry → branch → outcome; `hunting` tags confer targeted detection sensitivity). *Open.*
- PR #283 — `entity_pair_tags` substrate (migration 042 + writer functions). *Merged.*
- PR #284 — DB-level multi-entity tag predicates (`pair_tag_exists`, inbound/outbound subject lookups). *Merged.*
- Issue #290 / PR #323 — structured trait-compiler audit and opt-in `nexus trait-audit` CLI. *Merged.*
- Issue #291 — pair-tag-vs-`character_relationships` reconciliation. *Closed.*
- Issue #317 — Replace `contacts_available` overload with kind-qualified contact pair-tag predicates. *Closed.*
- Issue #318 — Replace `under_active_pursuit` ephemeral with inbound `hunting` pair-tag predicate. *Implemented.*

### Implementation Contracts (Open)

These are the downstream mechanical pre-requisites surfaced during the design-doc review. Each is tracked as its own issue so substrate work can be sequenced independently of further doc edits.

- Issue #292 — Place/faction tag subcategory refactor + resolver adapter for `in_location_class()` gates.
