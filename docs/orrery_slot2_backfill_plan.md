# Orrery Slot 2 Backfill Plan

**Status:** post-apply checkpoint for issue #326. This document records the
review contract, the 2026-05-29 Slot 2 entity-tag rewrite, and the remaining
cleanup surfaces after legacy active tags were retired.

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
- Hard prerequisite gate: migration 054 must be applied to the target slot
  before any place or state apply step.
- Migration 055 resolves the durable-character registry target: it keeps
  `tags.tag` globally keyed, registers `bodyform.lineage`,
  `bodyform.condition`, and `role.function`, seeds accepted durable character
  anchors, stores character lawfulness as `tradition_bound`, and moves the
  `hunter` tag definition to `role.function`.
- Local Slot 2 was brought current through migration 055 on 2026-05-28 for
  review-manifest generation. Reviewed rows were promoted and applied on
  2026-05-29.

## Slot 2 Preflight

Read-only checks run on 2026-05-28 before applying migrations 047-055:

```bash
poetry run nexus --json faction-audit --slot 2
poetry run nexus faction-manifest --slot 2 --output temp/slot2_backfill/faction_manifest_phase3.json
poetry run nexus place-manifest --slot 2 --output temp/slot2_backfill/place_manifest_phase5.json
poetry run nexus character-manifest --slot 2 --output temp/slot2_backfill/character_manifest_phase4_post055.json
```

Post-migration checkpoint run on 2026-05-28:

```bash
poetry run python scripts/migrate.py --slot 2
poetry run python scripts/migrate.py --slot 2 --dry-run
poetry run nexus --json faction-manifest --slot 2 --output temp/slot2_backfill/faction_manifest_phase4_post055.json
poetry run nexus --json character-manifest --slot 2 --output temp/slot2_backfill/character_manifest_phase4_post055.json
poetry run nexus --json faction-apply --slot 2 --manifest temp/slot2_backfill/faction_manifest_phase4_post055.json
poetry run nexus --json character-apply --slot 2
poetry run nexus --json place-apply --slot 2
poetry run nexus backfill-review-packet --slot 2 \
  --faction-manifest temp/slot2_backfill/faction_manifest_phase4_post055.json \
  --character-manifest temp/slot2_backfill/character_manifest_phase4_post055.json \
  --place-manifest temp/slot2_backfill/place_manifest_phase5.json \
  --output temp/slot2_backfill/review_packet_phase6.md
```

Observed entity counts:

| Kind | Count |
|---|---:|
| character | 36 |
| faction | 9 |
| place | 78 |

Pre-apply active legacy/rewrite surface:

| Surface | Active rows / operations | Reading |
|---|---:|---|
| `place_affordance` entity tags | 0 | No existing place tags to rewrite deterministically; place backfill must come from place prose/manual review. |
| place manifest operations | 889 | All review-required; all target tags registered; generated from place type plus bounded prose/metadata keyword evidence. |
| faction manifest operations | 145 | All review-required; no ready writes should be applied without human review. |
| faction legacy tag rows | 56 | Covered by `nexus faction-audit` / `faction-manifest`. |
| character manifest operations | 188 | All review-required; 15 candidate renames and 118 missing target-tag operations remain review items. |
| `profession_lite` rows | 26 | Character function rewrite needed into `role.function`; migration 055 resolves the target category but does not rewrite rows. |
| `orrery_signal` rows | 1 | `under_active_pursuit` should become inbound `hunting` pair-tag or be dropped if already represented. |
| `orrery_state` rows | 50 | Mixed old semantic states; classify into canonical state, need/travel/work/intimacy substrate, pair-tags, or prose. |
| old `role` rows | 92 | Many remain useful; accepted function anchors now target `role.function`, while noncanonical legacy role rows need review. |
| `role.fame` / `role.resources` rows | 0 | No live rows to rewrite; future compiler/backfill may add reviewed values. |

Post-migration manifest results:

| Manifest | Operations | Ready | Review-required | Notes |
|---|---:|---:|---:|---|
| faction | 145 | 0 | 145 | `faction-apply` dry-run skipped all rows as review-required and would insert 0 tags. |
| character | 188 | 0 | 188 | 15 candidate renames resolve to registered target tags; 118 operations still lack registered target tags and need review/prose/pair-tag handling. `character-apply` dry-run skipped all rows and would insert 0 tags. |
| place | 889 | 0 | 889 | All target tags are registered; `place-apply` dry-run skipped all rows and would insert 0 tags. |

Review packet result:

| Queue | Operations | Reading |
|---|---:|---|
| registered single-entity candidates | 980 | Narrowest non-destructive review surface; still not apply-ready until the reviewer promotes individual rows. |
| missing target tags | 118 | Requires vocabulary, prose, or pair-tag decisions. |
| pair target resolution | 36 | Requires endpoint decisions before any pair-tag apply path. |
| prose/event rows | 36 | Outside `entity_tags`; preserve or convert through a later prose/world-event slice. |
| structured remainders | 50 | Requires a substrate decision before mutation. |
| drop-after-review rows | 2 | Destructive; later reviewed cleanup only. |

Slot 2 apply checkpoint on 2026-05-29:

| Surface | Result |
|---|---:|
| old active entity-tag rows retired (`cleared_at` set) | 397 |
| replacement active entity tags inserted | 917 |
| active character tags | 11 |
| active faction tags | 67 |
| active place tags | 839 |
| duplicate ready operations skipped | 13 |
| exclusive place-category conflicts withheld | 50 |
| active deprecated / legacy category rows after apply | 0 |

The withheld conflicts are non-destructive review leftovers, not resolver
blockers: `place_visibility` (21), `place_access` (18), and `place_threat` (11).

Registry spot-checks:

- The current Slot 2 `tags` table had no `traditionalist` row before migration
  055. The resolved character anchor is `tradition_bound`; faction ideology
  keeps `traditionalist`.
- The current Slot 2 `hunter` row was category `capacity` before migration 055.
  The accepted capacity vocabulary no longer retains `hunter`; migration 055
  moves the tag definition to `role.function` without clearing entity rows.

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

The generated manifest is not authorization by itself to clear old rows or drop
columns. It is a review surface. For Slot 2, the user explicitly authorized the
2026-05-29 rewrite after reviewing the packet; the apply step inserted reviewed
single-entity rows and retired old active `entity_tags` rows by setting
`cleared_at`. Column drops, pair-tags, prose edits, and world-event extraction
remain separate reviewed slices.

Reviewed apply commands now exist for all single-entity manifest families:

- `nexus faction-apply --slot N --manifest PATH [--execute]`
- `nexus character-apply --slot N --manifest PATH [--execute]`
- `nexus place-apply --slot N --manifest PATH [--execute]`

`--execute` always requires a reviewed manifest file. Without `--execute`, the
commands run read-only and may rebuild the live manifest when no manifest path
is supplied. The shared character/place apply path consumes only operations that
have been manually promoted to `status=ready` with `review_required=false`; it
will not write pair-tags, edit prose, drop columns, or make schema changes.

## Category Plans

### Factions

Current status: strongest implementation coverage. Slot 2 has post-migration
manifest coverage and reviewed faction entity tags applied.

Existing surfaces:

- `nexus faction-audit --slot N`
- `nexus faction-manifest --slot N --output PATH`
- `nexus faction-apply --slot N --manifest PATH [--execute]`
- `nexus backfill-review-packet --slot N ...`

Pre-review dry-run result: 145 operations, all review-required. This was
expected because faction columns are prose-heavy and many legacy values are
aliases or structured remainders rather than deterministic tag writes. After
review promotion, Slot 2 now has 67 active faction tags and no active deprecated
or legacy category rows.

Next actions:

1. Keep pair-tag target resolution, prose preservation, and world-event
   extraction as later reviewed slices.
2. Handle faction-table API cleanup and column drops separately once callers no
   longer depend on obsolete columns.

### Places

Current status: reviewed Slot 2 place tags are applied. Slot 2 had no active
`place_affordance` rows to rewrite, so place tags came from the reviewed prose /
metadata manifest rather than deterministic legacy-row remaps.

Existing surface:

- `nexus place-manifest --slot N --output PATH`
- `nexus place-apply --slot N --manifest PATH [--execute]`
- `nexus backfill-review-packet --slot N ...`

Pre-review dry-run result: 889 operations across 78 places, all review-required.
Every target tag was registered. After review promotion, Slot 2 now has 839
active place tags. The apply path withheld 50 exclusive conflicts for later
review rather than overwriting sibling rows. The manifest scans place type plus
bounded keyword evidence from name, summary, history, `current_status`, secrets,
and `extra_data`. Keywords use word/phrase boundary matching so review
candidates do not come from substring accidents such as `port` inside
`Department` or `crypt` inside `encrypted`.

Implications:

- #292 Phase 2 was not a bulk rewrite of existing place tags in Slot 2.
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

1. Review withheld exclusive conflicts if a later package needs those exact
   axes.
2. Keep place pair-tags (`claims`, `operates_from`, `resides_at`, `can_access`,
   `knows_location`) in a separate apply path.

### Characters

Current status: the largest review surface, but reviewed Slot 2 single-entity
character tags are applied. The manifest runs against the final durable-character
registry, and ready-row apply coverage exists for future reviewed inserts.

Existing surfaces:

- `nexus character-manifest --slot N --output PATH`
- `nexus character-apply --slot N --manifest PATH [--execute]`
- `nexus backfill-review-packet --slot N ...`

The 2026-05-29 rewrite only applied reviewed single-entity rows. These surfaces
remain intentionally outside that apply:

- Legacy `role` / `profession_lite` rows that do not match an accepted
  `role.function` anchor.
- Ambiguous bodyform history rows such as `uploaded_consciousness` and
  `bodyform:biologically_immortal`; deterministic legacy proposals canonicalize
  through `CANONICAL_TAGS`, but these history-bearing rows need review.
- Which legacy `orrery_state` values move to canonical `state`, which move to
  dedicated need/travel/work/intimacy substrates, and which become prose.
- Which old `profession_lite` rows are tag renames, role-function folds, or
  pair-tag/prose remainders.

Initial classification:

| Legacy surface | Default classification |
|---|---|
| `profession_lite` | Rename/fold into `role.function`, or prose/pair-tag remainder when no accepted function anchor fits. |
| old `role` | Accepted anchors migrate to `role.function`; noncanonical legacy role rows remain review items. |
| `orrery_signal:under_active_pursuit` | Convert to inbound `hunting` pair-tag, or drop if already represented. |
| `orrery_signal:debt_pulse_active` | Drop or structured remainder; Skald sovereignty model supersedes debt-pulse forcing. |
| `orrery_state:contacts_available` | Decompose to `contact:<kind>` pair-tags or relationship rows; never keep as single entity state. |
| `orrery_state:off_grid` / `ghostprint_active` | Likely concealment/prose/pair-tag review, not canonical `state` by default. |
| `orrery_state:seeking_identity` | Structured remainder or prose unless a package needs it. |
| `state` rows outside the canonical 14 | Review into canonical `state`, event history, prose, or package-specific follow-up. |

Next actions:

1. Reconcile prose/pair-tag/remainder queues only when a package or compiler
   needs them.
2. Revisit the Slot 2 reference taggings in `docs/orrery_tag_vocabulary.md`
   after the full vocabulary bank stabilizes.

## Execution Order

Do not begin any apply step until migrations 054 and 055 have been applied to
the target slot. Slot 2 satisfies that prerequisite as of the 2026-05-28
checkpoint.

1. Apply migration 054 so the state/place seed exists in target slots. **Done
   locally for Slot 2.**
2. Apply migration 055 so the durable character seed and collision resolutions
   exist in target slots. **Done locally for Slot 2.**
3. Generate three read-only manifests for Slot 2: faction, place, character.
   **Done.**
4. Generate a read-only review packet from the three manifests. **Done.**
5. Review manifests in that order: faction first because tooling exists, place
   second because there are no existing place rows to preserve, character last
   because it has the most category drift. Use the review packet queues to find
   narrow registered single-entity candidates before pair/prose/remainder work.
   **Done for the applied single-entity slice.**
6. Apply ready non-destructive entity-tag rows to Slot 2 only. **Apply
   complete for reviewed single-entity rows: 917 active replacement tags.**
7. Re-run Orrery resolver/template tests and a Slot 2 dry run. **Done on
   2026-05-29: targeted Orrery tests passed; dry runs at chunks 100 and 1428
   produced concrete resolutions without Skald/API calls.**
8. Only then clear legacy rows, drop obsolete faction columns, and remove
   resolver shims in separate migrations. **Active legacy rows were cleared and
   the `place_affordance` resolver shim was removed. Faction column cleanup
   remains.**
9. Refresh retrograde seed vocabulary/config after the registry-backed Slot 2
   rewrite is stable. **The seed vocabulary now exposes `place_classes` rather
   than `place_affordances`.**

## Stop Conditions

Pause before mutation if any of these occur:

- A manifest operation needs to clear or overwrite an existing exclusive sibling
  row.
- A proposed tag is not registered or is registered under a deprecated category.
- A legacy row implies a pair-tag but the target entity cannot be resolved.
- A source value belongs in world events or prose rather than tags.
- Place/faction/character rewrites disagree about the same entity.
- Review finds a real design decision rather than a mechanical mapping.
