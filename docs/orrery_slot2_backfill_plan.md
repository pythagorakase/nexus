# Orrery Slot 2 Backfill Plan

**Status:** Phase 3 planning artifact for issue #326. This document is the
review contract before any mature Slot 2 vocabulary rewrite mutates data.

## Source Vocabulary

The backfill must read from the accepted vocabulary specs, not from ad hoc
runtime proposals:

- `docs/orrery_tag_vocabulary.md` for character, place, pair-tag, status, and
  genre vocabulary.
- `docs/orrery_state_vocabulary.md` for canonical character `state` anchors
  and clearance contracts.
- `docs/orrery_faction_vocabulary.md` for faction categories and legacy
  column/tag mapping.

Registry and substrate prerequisites:

- Migration 043 registers replacement place and faction categories and marks
  legacy cutover categories deprecated.
- Migration 052 seeds the closed faction tag bank.
- PR #346 / migration 054 seeds completed state and place anchors. Until that
  lands in the target slot, the place/state rewrite is planning-only.
- Character `role.function` remains a registry alignment decision: the design
  spec names `role.function`, but live migrations currently keep function tags
  under `role` and only split `role.fame` / `role.resources`. Do not run a
  destructive character rewrite until this is resolved by either a registry
  migration or an explicit doc correction.

## Slot 2 Preflight

Read-only checks run on 2026-05-28:

```bash
poetry run nexus --json faction-audit --slot 2
poetry run nexus faction-manifest --slot 2 --output temp/slot2_backfill/faction_manifest_phase3.json
```

Observed entity counts:

| Kind | Count |
|---|---:|
| character | 36 |
| faction | 9 |
| place | 78 |

Observed active legacy/rewrite surface:

| Surface | Active rows / operations | Reading |
|---|---:|---|
| `place_affordance` entity tags | 0 | No existing place tags to rewrite deterministically; place backfill must come from place prose/manual review. |
| faction manifest operations | 145 | All review-required; no ready writes should be applied without human review. |
| faction legacy tag rows | 56 | Covered by `nexus faction-audit` / `faction-manifest`. |
| `profession_lite` rows | 26 | Character function rewrite needed after `role` vs `role.function` decision. |
| `orrery_signal` rows | 1 | `under_active_pursuit` should become inbound `hunting` pair-tag or be dropped if already represented. |
| `orrery_state` rows | 50 | Mixed old semantic states; classify into canonical state, need/travel/work/intimacy substrate, pair-tags, or prose. |
| old `role` rows | 110 | Many remain useful, but target category is blocked by role registry alignment. |
| `role.fame` / `role.resources` rows | 0 | No live rows to rewrite; future compiler/backfill may add reviewed values. |

## Manifest Operation Classes

Every backfill manifest should classify operations into one of these classes:

| Operation class | Meaning | Apply eligibility |
|---|---|---|
| `insert_entity_tag` | Registered single-entity tag can be inserted on a known entity. | Eligible only when status is `ready` and no exclusive sibling conflict exists. |
| `review_entity_tag` | Candidate tag is plausible but source text or alias mapping needs review. | Not applied automatically. |
| `insert_pair_tag` | Registered pair-tag can be inserted with resolved endpoints. | Separate apply path; requires endpoint validation. |
| `resolve_pair_tag_target` | Source implies a relation but endpoint entity is unresolved. | Not applied automatically. |
| `preserve_prose` | Source belongs in summary/prose rather than tags. | No tag write. |
| `world_event_or_prose` | Source should become event history or prose. | No tag write in this slice. |
| `structured_remainder` | Source is package-relevant but lacks a clean target substrate. | No tag write; reviewed follow-up needed. |
| `drop_legacy_tag_after_review` | Legacy tag has no replacement and can be cleared after review. | Later destructive slice only. |

The manifest is not authorization to clear old rows or drop columns. It is a
review surface. Apply commands may insert reviewed ready rows, but destructive
cleanup remains a later data-rewrite migration scoped to Slot 2.

## Category Plans

### Factions

Current status: strongest implementation coverage.

Existing surfaces:

- `nexus faction-audit --slot N`
- `nexus faction-manifest --slot N --output PATH`
- `nexus faction-apply --slot N --manifest PATH [--execute]`

Slot 2 dry-run result: 145 operations, all review-required. This is expected
because faction columns are prose-heavy and many legacy values are aliases or
structured remainders rather than deterministic tag writes.

Next actions:

1. Review the generated faction manifest manually.
2. Promote only unambiguous operations to `ready`.
3. Run `nexus faction-apply --slot 2 --manifest PATH` as dry run.
4. Execute only ready `insert_entity_tag` rows.
5. Leave column drops, legacy tag clearing, pair-tag target resolution, prose
   preservation, and world-event extraction to later reviewed slices.

### Places

Current status: registry and resolver shim are ready or nearly ready, but Slot
2 has no active `place_affordance` rows to rewrite.

Implications:

- #292 Phase 2 is not a bulk rewrite of existing place tags in Slot 2.
- The place manifest should be a backfill/review manifest over place prose,
  names, summaries, references, and any existing location metadata.
- Deterministic operations are likely rare; most place rows should begin as
  `review_entity_tag` because `place_function`, `place_visibility`,
  `place_access`, `place_environment`, and `place_threat` are compositional.

Safe deterministic defaults:

- No row from absence alone. Do not tag all places `place_known` or
  `place_open` just because those are common defaults.
- `place_threat` should not be generated from stable descriptions unless the
  source names a current danger posture.
- `claims`, `operates_from`, `resides_at`, `can_access`, and `knows_location`
  belong in pair-tag manifests, not single-entity place tags.

Next actions:

1. Add a read-only `place-audit` / `place-manifest` surface, or fold places into
   a broader `vocabulary-audit` command.
2. Generate Slot 2 place candidates from place prose and existing references.
3. Review place candidates before any apply step.
4. Remove the `place_affordance` resolver shim only after migrated rows and
   predicate tests prove that package gates still match.

### Characters

Current status: largest unresolved planning surface.

Do not run a broad character apply until these are decided:

- `role` vs `role.function` registry target.
- Whether old prefixed bodyform tags such as `bodyform:android` become
  canonical aliases or are migrated to unprefixed anchors such as `inorganic`
  and `virtual`.
- Global tag-name collisions created by category-qualified design language.
  The live `tags` table keys by global tag string, not by `(category, tag)`.
  Known blockers include `disposition:traditionalist` colliding with faction
  `ideology:traditionalist`, and `role.function:hunter` colliding with the
  legacy `capacity:hunter` row. Resolve these with globally unique tag names,
  aliases, or category rewrites before inserting character rows.
- Which legacy `orrery_state` values move to canonical `state`, which move to
  dedicated need/travel/work/intimacy substrates, and which become prose.
- Which old `profession_lite` rows are tag renames, role-function folds, or
  pair-tag/prose remainders.

Initial classification:

| Legacy surface | Default classification |
|---|---|
| `profession_lite` | Rename/fold into function role after registry decision. |
| old `role` | Keep or migrate category, depending on `role.function` decision. |
| `orrery_signal:under_active_pursuit` | Convert to inbound `hunting` pair-tag, or drop if already represented. |
| `orrery_signal:debt_pulse_active` | Drop or structured remainder; Skald sovereignty model supersedes debt-pulse forcing. |
| `orrery_state:contacts_available` | Decompose to `contact:<kind>` pair-tags or relationship rows; never keep as single entity state. |
| `orrery_state:off_grid` / `ghostprint_active` | Likely concealment/prose/pair-tag review, not canonical `state` by default. |
| `orrery_state:seeking_identity` | Structured remainder or prose unless a package needs it. |
| `state` rows outside the canonical 14 | Review into canonical `state`, event history, prose, or package-specific follow-up. |

Next actions:

1. Resolve `role.function` registry alignment.
2. Resolve global character vocabulary collisions against the live
   single-string tag registry.
3. Seed any missing accepted character anchors and aliases.
4. Add a character manifest builder that reports keep/rename/drop/pair-tag/prose
   decisions without applying them.
5. Reconcile the existing Slot 2 reference taggings in
   `docs/orrery_tag_vocabulary.md` against the manifest output.

## Execution Order

1. Merge PR #346 so the state/place seed exists in target slots.
2. Resolve the character registry alignment blocker.
3. Resolve globally colliding character anchor names before seeding or applying
   character rows.
4. Generate three read-only manifests for Slot 2: faction, place, character.
5. Review manifests in that order: faction first because tooling exists, place
   second because there are no existing place rows to preserve, character last
   because it has the most category drift.
6. Apply ready non-destructive `insert_entity_tag` rows to Slot 2 only.
7. Re-run Orrery resolver/template tests and a Slot 2 dry run.
8. Only then clear legacy rows, drop obsolete faction columns, and remove
   resolver shims in separate migrations.
9. Refresh retrograde seed vocabulary/config after the registry-backed Slot 2
   rewrite is stable.

## Stop Conditions

Pause before mutation if any of these occur:

- A manifest operation needs to clear or overwrite an existing exclusive sibling
  row.
- A proposed tag is not registered or is registered under a deprecated category.
- A legacy row implies a pair-tag but the target entity cannot be resolved.
- A source value belongs in world events or prose rather than tags.
- Place/faction/character rewrites disagree about the same entity.
- Review finds a real design decision rather than a mechanical mapping.
