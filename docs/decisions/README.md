---
status: canonical
sources:
  - tests/test_doc_front_matter.py
  - README.md
  - tests/generated_docs.py
verified_commit: "d295eef0928706cda3a9f7c5a8b4dc103929e1ed"
---

# Document Status and the Decision Ledger

GitHub issues and pull requests track active work. This directory holds what
must outlive them: durable rulings, the alternatives they rejected, parked work,
and the evidence that would reopen either. Documents elsewhere in the repository
declare whether they describe the current system through the front matter
defined here.

## Document Front Matter

A classified document begins with a YAML block, before its title:

```yaml
---
status: canonical
sources:
  - nexus/api/narrative.py
  - nexus/jobs/scheduler.py
verified_commit: "ed9531e3418f695b9e47b5c9e7fdc897ac4ecdcd"
---
```

| Key | Required | Contract |
|---|---|---|
| `status` | always | `canonical`, `historical`, or `superseded`. |
| `verified_commit` | always | The commit whose tree the document was last checked against: 7 to 40 lowercase hex characters, quoted so YAML keeps it a string. A commit cannot name itself, so this is usually the base of the change that edits the document. When it changes, it must name the merge base with `origin/main` or one of its ancestors, and descend from the value it replaces, so it survives a squash merge. |
| `sources` | when `canonical` | Repository-relative paths of the files that the document describes. Directories are not accepted. Every path must exist. Optional for the other statuses. |
| `superseded_by` | when `superseded` | The repository-relative path of the replacing document, which must list this document under `supersedes`. The replacement may itself be superseded later; links are never rewritten, and following them must reach a document that is not superseded. Not allowed with any other status. |
| `supersedes` | no | Documents this one replaces. Each must be `superseded` with `superseded_by` naming this document. |

No other keys are accepted.

### Status Values

- **canonical** — describes the current system. Any change to a listed
  source re-verifies the document and moves its `verified_commit` in the same
  pull request.
- **historical** — a record of retired or completed work: blueprints for
  modules that were never built, dated plans and checkpoints, and notes on
  configurations since replaced. Kept for provenance, never edited to track the
  current system, and labeled historical wherever `README.md` references it.
- **superseded** — replaced by the document named in `superseded_by`, whose
  own successor, if any, continues the chain. `README.md` never references it.

Documents without front matter are unclassified. Classify a document when you
verify it against its sources or retire it. Generated documents,
`docs/orrery_packages.md` and `docs/cli_reference.md`, carry no front matter;
their generators' tests check their freshness.

### Scope and Validation

`tests/test_doc_front_matter.py` checks every Markdown file at the repository
root and under `docs/`: the keys and values above, that every `sources` path
exists, that supersession links agree in both directions and every chain ends
at a document that is not superseded, and that every Markdown path `README.md`
references, including `./`-relative links, exists inside the repository, is not
superseded, and is labeled historical on its line when its status is
historical. It also fails when the branch's diff against its merge base with
`origin/main`, uncommitted and untracked files included, touches a source that
a document canonical at that merge base or now declares at either point, unless
the document's `verified_commit` changed. It fails rather than skips when that
history is missing: no git checkout at the repository root, a shallow clone, no
`origin/main`, or no merge base. It also checks every record in this directory:
its file name and title, the Kind and Links lines, the three sections in order,
and that the Records list below names each record once, in number order. It
also fails when a Markdown file in that scope has no front matter and is not
listed in `config/doc_classification_baseline.json`, when that baseline lists a
file that is classified, deleted or exempt, and when the baseline gains an
entry that its merge-base copy lacks; `docs/qa/`, `README.md`, `CLAUDE.md` and
the generated documents registered in `tests/generated_docs.py` are exempt.

## Decision and Parked-Work Records

Each record is one file, `docs/decisions/NNNN-short-slug.md`. `NNNN` is the
next unused four-digit number, and numbers are never reused. A record carries
the document front matter above: `canonical` while its ruling stands or its
work stays parked, `superseded` when a later record overturns it, and
`historical` once parked work is picked up or the governed code is gone. Its
`sources` are the paths the ruling governs.

```markdown
# NNNN: Title in Chicago Title Case

**Kind:** decision | parked
**Links:** #issue, PR #number, or Loom

## Ruling

The decision, or what is parked and why.

## Rejected Alternatives

- Each alternative considered, with the reason it lost.

## Reopening Criteria

- The observable evidence that would reopen the ruling or unpark the work.
```

Records hold rulings, not task lists; the linked issue or pull request keeps
execution state.

When the coordinator relays a loom ruling verbatim to an issue, the pull
request that lands work under that ruling, or a follow-up pull request, appends
a record here. The record quotes the relay comment and names the files the
ruling governs as its `sources`.

## Records

- [0001: The Cut](0001-the-cut.md)
- [0002: Disengagement in the Menu](0002-disengagement-in-the-menu.md)
- [0003: A Reading Contract](0003-a-reading-contract.md)
- [0004: The Narrative Lens](0004-the-narrative-lens.md)
- [0005: Passive Drift](0005-passive-drift.md)
- [0006: Who Owns the Choice](0006-who-owns-the-choice.md)
- [0007: Secrets With Authors](0007-secrets-with-authors.md)
- [0008: The Story Clock in Chrome](0008-the-story-clock-in-chrome.md)
- [0009: Dollars in the Ledger](0009-dollars-in-the-ledger.md)
- [0010: The Gaia Seat](0010-the-gaia-seat.md)
- [0011: The Reference Corpus](0011-the-reference-corpus.md)
- [0012: The Reveal](0012-the-reveal.md)
- [0013: Institutional Cadence](0013-institutional-cadence.md)
- [0014: Return Contract](0014-return-contract.md)
- [0015: Return Recaps](0015-return-recaps.md)
- [0016: Speculatively Mature Entities From Choice Text](0016-speculative-maturation.md)
- [0017: Enrich Sparse Entities in Additional Maturation Passes](0017-sparse-entity-enrichment.md)
- [0018: Separate Prose From Turn Structure](0018-killed-c003.md)
- [0019: Give Player-Visible Prose One Author](0019-killed-c014.md)
- [0020: Let Revelations Recast Earlier Scenes](0020-killed-c030.md)
- [0021: Let Night QA Recover Before Measuring](0021-killed-c063.md)
- [0022: Authorize Capabilities and Protect the Golden Master](0022-killed-c068.md)
- [0023: Put Episode Boundaries on World Time](0023-killed-c100.md)
- [0024: Unify Narrative Memory Documents and Embeddings](0024-killed-c102.md)
- [0025: Legacy New-Story Seed and Zone Columns](0025-legacy-new-story-seed-columns.md)
- [0026: Entity Tag Clear-on-Override Column](0026-entity-tag-clear-on-override.md)
- [0027: Narration Job Provider Columns](0027-narration-job-provider-columns.md)
- [0028: World Event Narration Link Column](0028-world-event-narration-link.md)
- [0029: Legacy Vector-Helper Functions](0029-legacy-vector-helper-functions.md)
- [0030: Relationship Drift](0030-relationship-drift.md)
- [0031: Time-Release Backstory](0031-time-release-backstory.md)
- [0032: Mood and Weather](0032-mood-and-weather.md)
- [0033: Updates Block Shape](0033-updates-block-shape.md)
- [0034: Conspiracy Channel](0034-conspiracy-channel.md)
- [0035: Narrative Memory Shape](0035-narrative-memory-shape.md)
- [0036: Scene Spine](0036-scene-spine.md)
- [0037: Seat Budgets](0037-seat-budgets.md)
- [0038: Token Headroom](0038-token-headroom.md)
- [0039: Boundary Catch-Up](0039-boundary-catch-up.md)
- [0040: Story Bundles](0040-story-bundles.md)
- [0041: Off-Screen Ledger](0041-off-screen-ledger.md)
- [0042: Durable Intentions](0042-durable-intentions.md)
- [0043: Routine Anchors](0043-routine-anchors.md)
- [0044: Mundane Texture](0044-mundane-texture.md)
- [0045: Gatherings](0045-gatherings.md)
- [0046: Colliding Itineraries](0046-colliding-itineraries.md)
- [0047: Missed Commitments](0047-missed-commitments.md)
- [0048: Region Genesis](0048-region-genesis.md)
- [0049: Faction Seeding](0049-faction-seeding.md)
- [0050: Continuous Book](0050-continuous-book.md)
- [0051: Time Lens](0051-time-lens.md)
- [0052: Story Map](0052-story-map.md)
- [0053: Resumable Genesis](0053-resumable-genesis.md)
- [0054: Responsive Shell](0054-responsive-shell.md)
- [0055: Weirdness Control](0055-weirdness-control.md)
- [0056: Background Activities](0056-background-activities.md)
- [0057: Stranger Encounters Without Place Sizes](0057-stranger-encounters-without-place-sizes.md)
- [0058: Map Points From Their Authors](0058-map-points-from-their-authors.md)
- [0059: Backups and Rollback Copies](0059-backups-and-rollback-copies.md)
- [0060: The Runtime Home Move](0060-the-runtime-home-move.md)
- [0061: Play and Operator Listeners](0061-play-and-operator-listeners.md)
- [0062: Merge Blocking and the Live Tier](0062-merge-blocking-and-the-live-tier.md)
- [0063: One Envelope for Every Command](0063-one-envelope-for-every-command.md)
- [0064: Story Text in Diagnostic Logs](0064-story-text-in-diagnostic-logs.md)
- [0065: The Legacy Drop Migration Number](0065-the-legacy-drop-migration-number.md)
- [0066: The Keyboard-Held Tooltip](0066-the-keyboard-held-tooltip.md)
- [0067: Seat Lists in a Popover](0067-seat-lists-in-a-popover.md)
- [0068: Incubator Column Comments](0068-incubator-column-comments.md)
- [0069: Log Redaction at the Call Site](0069-log-redaction-at-the-call-site.md)
- [0070: The Fable Structured-Output Probe](0070-the-fable-structured-output-probe.md)
- [0071: Embedding Weights and Legacy Vectors](0071-embedding-weights-and-legacy-vectors.md)
- [0072: Landing the Ratchet and Ledger Currency](0072-landing-the-ratchet-and-ledger-currency.md)
- [0073: The Envelope Migration Plan](0073-the-envelope-migration-plan.md)
- [0074: Pinned Tokenizer Revisions](0074-pinned-tokenizer-revisions.md)
- [0075: A Behavior-Preserving Reachability Index](0075-a-behavior-preserving-reachability-index.md)
- [0076: The Offline Merge Gate](0076-the-offline-merge-gate.md)
- [0077: Refusing Out-of-Range Chunk Slugs](0077-refusing-out-of-range-chunk-slugs.md)
- [0078: Retiring the Legacy File Ingest](0078-retiring-the-legacy-file-ingest.md)
- [0079: Listener Ports, Lanes and Origins](0079-listener-ports-lanes-and-origins.md)
- [0080: Closing the Embedding Orchestration Work](0080-closing-the-embedding-orchestration-work.md)
- [0081: Golden-Path Observation Assertions](0081-golden-path-observation-assertions.md)
- [0082: Extension Versions in the Genesis Artifact](0082-extension-versions-in-the-genesis-artifact.md)
- [0083: Retiring Old Scripts and Retired-Tag Gates](0083-retiring-old-scripts-and-retired-tag-gates.md)
