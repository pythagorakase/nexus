# Work Order 817-S3: Required Changes

The "Required Changes" section of work order 817-S3, copied byte for byte from
the coordinator's order file (which lives under the gitignored `temp/`), so that
`table_check.py` can run from the branch alone. It holds the record table and
the fixed text of Required Changes 3 that the check parses.

## Required Changes

1. **Fifty-five records.** Create `docs/decisions/NNNN-<slug>.md` for each row below, and no other file in that directory. `c<ID>` means `https://github.com/pythagorakase/nexus/issues/<first Links issue>#issuecomment-<ID>`; fetch each with `gh api repos/pythagorakase/nexus/issues/comments/<ID> -q .body`. Every listed source exists at `364fef4b`.

| NNNN | Slug | Title | Kind | Links | Ruling Text | Sources |
|---|---|---|---|---|---|---|
| 0001 | the-cut | The Cut | decision | #850, #750 | c5556777011 | prompts/storyteller_core.md |
| 0002 | disengagement-in-the-menu | Disengagement in the Menu | decision | #851, #746, #748 | c5556777557 | prompts/storyteller_core.md |
| 0003 | a-reading-contract | A Reading Contract | decision | #852, #774 | c5556778630 | prompts/storyteller_core.md |
| 0004 | the-narrative-lens | The Narrative Lens | decision | #853, #743, #744, #870 | c5565300043 | prompts/storyteller_core.md |
| 0005 | passive-drift | Passive Drift | decision | #854, #790 | c5565301694 | nexus/agents/orrery/drift.py |
| 0006 | who-owns-the-choice | Who Owns the Choice | decision | #855, #801, #773 | c5565439618 | nexus/api/choice_handling.py, nexus/api/slot_endpoints.py |
| 0007 | secrets-with-authors | Secrets With Authors | decision | #856, #796 | c5800949507 | nexus/agents/orrery/epistemics.py, nexus/agents/orrery/retrograde_expansion.py |
| 0008 | the-story-clock-in-chrome | The Story Clock in Chrome | decision | #857, #771 | c5800951144 | ui/client/src/components/nexus/TopBar.tsx, ui/client/src/components/nexus/Intertitle.tsx |
| 0009 | dollars-in-the-ledger | Dollars in the Ledger | decision | #858, #802, #756, #759 | c5800952750 | nexus/telemetry/usage.py |
| 0010 | the-gaia-seat | The Gaia Seat | decision | #859, #758, #759 | c5800955522 | nexus/config/story_model.py |
| 0011 | the-reference-corpus | The Reference Corpus | decision | #860, #765, #751, #746, #747, #749 | c5565414838 | scripts/qa_shift/reference_corpora.toml |
| 0012 | the-reveal | The Reveal | decision | #861, #772 | c5565410350 | ui/client/src/components/nexus/NarrativePane.tsx |
| 0013 | institutional-cadence | Institutional Cadence | parked | #786, Loom sequence 39 | c5915495413 | docs/orrery_faction_vocabulary.md |
| 0014 | return-contract | Return Contract | parked | #792, Loom sequence 39 | c5915496685 | nexus/agents/orrery/bleed.py |
| 0015 | return-recaps | Return Recaps | parked | #832, PR #1006, Loom sequence 40 | c5915670598 | nexus/api/return_recap.py |
| 0016 | speculative-maturation | Speculatively Mature Entities From Choice Text | parked | #837 | #837 body | nexus/agents/orrery/retrograde_maturation.py, docs/orrery_retrograde_spec.md |
| 0017 | sparse-entity-enrichment | Enrich Sparse Entities in Additional Maturation Passes | parked | #839 | #839 body | nexus/agents/orrery/retrograde_maturation.py, docs/orrery_retrograde_spec.md |
| 0018 | killed-c003 | Separate Prose From Turn Structure | decision | #849 | `## C003` | nexus/agents/logon/skald_wire.py |
| 0019 | killed-c014 | Give Player-Visible Prose One Author | decision | #849 | `## C014` | nexus/agents/orrery/worker.py, nexus/agents/orrery/bleed.py |
| 0020 | killed-c030 | Let Revelations Recast Earlier Scenes | decision | #849 | `## C030` | nexus/agents/orrery/epistemics.py, nexus/api/reader_endpoints.py |
| 0021 | killed-c063 | Let Night QA Recover Before Measuring | decision | #849 | `## C063` | scripts/qa_shift/qa_shift.py, scripts/qa_shift/mission_prompt.md |
| 0022 | killed-c068 | Authorize Capabilities and Protect the Golden Master | decision | #849 | `## C068` | nexus/api/runtime_status.py, nexus/api/slot_endpoints.py |
| 0023 | killed-c100 | Put Episode Boundaries on World Time | decision | #849 | `## C100` | nexus/api/summary_triggers.py, nexus/api/db_converters.py |
| 0024 | killed-c102 | Unify Narrative Memory Documents and Embeddings | decision | #849 | `## C102` | nexus/agents/memnon/utils/embedding_tables.py |
| 0025 | legacy-new-story-seed-columns | Legacy New-Story Seed and Zone Columns | parked | #819, #813 | baseline `:2-6` | config/schema_docs_baseline.json, migrations/007_normalize_new_story_creator.sql, nexus/api/new_story_cache.py |
| 0026 | entity-tag-clear-on-override | Entity Tag Clear-on-Override Column | parked | #819, #813 | baseline `:7` | config/schema_docs_baseline.json, migrations/023_orrery_schema.py |
| 0027 | narration-job-provider-columns | Narration Job Provider Columns | parked | #819, #813 | baseline `:8-9` | config/schema_docs_baseline.json, migrations/023_orrery_schema.py |
| 0028 | world-event-narration-link | World Event Narration Link Column | parked | #819, #813 | baseline `:10` | config/schema_docs_baseline.json, migrations/023_orrery_schema.py |
| 0029 | legacy-vector-helper-functions | Legacy Vector-Helper Functions | parked | #819, #813, #812 | baseline `:11-16` | config/schema_docs_baseline.json |
| 0030 | relationship-drift | Relationship Drift | decision | #476, Loom sequence 2 | c5035538982 | nexus/agents/orrery/drift.py |
| 0031 | time-release-backstory | Time-Release Backstory | decision | #479, Loom sequence 3 | c5035539149 | nexus/agents/orrery/reveal.py, nexus/agents/orrery/epistemics.py |
| 0032 | mood-and-weather | Mood and Weather | decision | #480, Loom sequence 4 | c5035539341, c5035716638 | nexus/agents/orrery/weather.py |
| 0033 | updates-block-shape | Updates Block Shape | decision | #566, Loom sequence 8 | c5070275155 | nexus/agents/logon/skald_wire.py |
| 0034 | conspiracy-channel | Conspiracy Channel | decision | #617, Loom sequence 9 | c5113803006, c5113867184, c5113874777 | nexus/memory/correspondence.py |
| 0035 | narrative-memory-shape | Narrative Memory Shape | decision | #737, #793, Loom sequence 37 | c5817898265 | nexus/agents/lore/utils/entity_queries.py |
| 0036 | scene-spine | Scene Spine | decision | #750, Loom sequence 38 | c5915474062 | nexus/agents/logon/skald_wire.py |
| 0037 | seat-budgets | Seat Budgets | decision | #756, Loom sequence 38 | c5915474827 | nexus/agents/lore/utils/token_budget.py |
| 0038 | token-headroom | Token Headroom | decision | #759, Loom sequence 38 | c5915475165 | nexus/telemetry/usage.py |
| 0039 | boundary-catch-up | Boundary Catch-Up | decision | #780, Loom sequence 38 | c5915474444 | nexus/agents/orrery/boundaries.py |
| 0040 | story-bundles | Story Bundles | decision | #822, Loom sequence 38 | c5915475477 | scripts/new_story_setup.py |
| 0041 | off-screen-ledger | Off-Screen Ledger | decision | #781, Loom sequence 39 | c5915494108 | nexus/agents/orrery/events.py |
| 0042 | durable-intentions | Durable Intentions | decision | #782, Loom sequence 39 | c5915494408 | nexus/agents/orrery/substrate.py, migrations/087_seek_redemption_projects.sql |
| 0043 | routine-anchors | Routine Anchors | decision | #783, Loom sequence 39 | c5915494698 | migrations/056_orrery_routine_anchors.py |
| 0044 | mundane-texture | Mundane Texture | decision | #784, Loom sequence 39 | c5915495072 | nexus/agents/orrery/worker.py |
| 0045 | gatherings | Gatherings | decision | #787, Loom sequence 39 | c5915495765 | migrations/105_interaction_threads.sql, nexus/agents/orrery/ambient.py |
| 0046 | colliding-itineraries | Colliding Itineraries | decision | #788, Loom sequence 39 | c5915496016 | nexus/agents/orrery/ambient.py, migrations/056_orrery_routine_anchors.py |
| 0047 | missed-commitments | Missed Commitments | decision | #789, Loom sequence 39 | c5915496362 | migrations/105_interaction_threads.sql, nexus/agents/orrery/ambient.py |
| 0048 | region-genesis | Region Genesis | decision | #840, Loom sequence 39 | c5915497021 | nexus/api/new_story_db_mapper.py, ui/client/src/lib/world-outline.ts |
| 0049 | faction-seeding | Faction Seeding | decision | #841, Loom sequence 39 | c5915497315 | nexus/api/trait_compiler.py |
| 0050 | continuous-book | Continuous Book | decision | #767, Loom sequence 40 | c5915668877 | ui/client/src/components/nexus/NarrativePane.tsx, nexus/api/reader_endpoints.py |
| 0051 | time-lens | Time Lens | decision | #768, Loom sequence 40 | c5915669173 | ui/client/src/components/nexus/NexusLayout.tsx |
| 0052 | story-map | Story Map | decision | #770, Loom sequence 40 | c5915669468 | ui/client/src/components/nexus/MapPane.tsx |
| 0053 | resumable-genesis | Resumable Genesis | decision | #776, Loom sequence 40 | c5915669789 | migrations/141_genesis_run_ledger.sql, nexus/api/conversations.py |
| 0054 | responsive-shell | Responsive Shell | decision | #777, Loom sequence 40 | c5915670142 | ui/client/src/components/nexus/nexus-layout.css |
| 0055 | weirdness-control | Weirdness Control | decision | #838, Loom sequence 40 | c5915671010 | nexus/agents/orrery/retrograde_maturation.py |

2. **Front matter.** `status:` as set at the end of this item; `sources:` exactly the row's list, in that order; `verified_commit:` the quoted full SHA of `git merge-base origin/main HEAD` taken after your last merge of `origin/main`. Decision 817-Q7: "A parked record stays canonical. Its sources name the baseline file and any migration or genesis source that really governs the object." Rows 0025-0029 apply it: migration 007 and `nexus/api/new_story_cache.py` (its five NULL writers) govern the seed columns; migration 023 creates the other four columns (`:508`, `:582`, `:624-625`); no migration or genesis source defines the six functions (migration 001 is a no-op baseline), so 0029 names the baseline alone. No record is `historical`. Record 0005 (Decision 5, #854, 2026-09-07: "remove passive drift ... No accrual table.") overturns the accrual axis of the seq 2 ruling in 0030 ("Axis 3 ... 3B — World-Time-Rated Accrual"), and the contract (`docs/decisions/README.md:77-79`) makes such a record `superseded`. So 0030 has `status: superseded` and `superseded_by: docs/decisions/0005-passive-drift.md`, and 0005 adds `supersedes:` with the single entry `docs/decisions/0030-relationship-drift.md` after `verified_commit`. The existing validator checks both directions. Every other record is `canonical`.
3. **Body.** Exactly one blank line follows the closing `---`; then `# NNNN: Title`, blank, `**Kind:** <kind>`, `**Links:** <links>` (the row's text), then the three sections in the template's order with no other `##` heading. Paraphrase drift is this slice's risk: no record restates a ruling in new words. Each quoted block is preceded by one line `Source: <URL>.`, then a blank line, and is copied byte for byte. A source line that already starts with `>` is kept as it is. Any other source line gets the prefix `> `, and a blank source line becomes a bare `>`. The #737 fenced `text` block stays fenced and unprefixed.
   - **Ruling.** Rows 0001-0012: the whole comment body as a `> ` block. Rows 0013-0015 and 0030-0055: the relay's verbatim block, then each further listed comment's whole body as a `> ` block. The verbatim block is the first maximal run of lines matching `^>( |$)` after the first line or heading that contains `verbatim` (case-insensitive), skipping blank lines before the run. It includes bare `>` lines. For #737 it is the fenced block (lines 3-10 of 5817898265). Two relays have the marker only in their `##` heading: for 0033 the block is lines 3-16 of 5070275155, and for 0034 it is lines 3-7 of 5113803006. Rows 0016-0017: `Parked. The 2026-09-04 brainstorm placed this proposal in its Parked grouping.`, then the issue's `## Risks` paragraph as a `> ` block. Rows 0018-0024: `Not adopted. The three-angle verification of the 2026-09-04 brainstorm killed this cluster; #849 records it.`, then the section's `**Amendment / carry-forward:**` paragraph as a `> ` block. Rows 0025-0029: `Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.`, then decision 819-Q1's `Decision:` line from #819's "Decisions Recorded" comment as a `> ` block, then a separate block with its own line `Source: config/schema_docs_baseline.json at <merge base SHA>.` and one `> ` line per listed key, `<key>: <reason>`, copied from the file after your last merge of `origin/main`. Put a non-quote line between the two blocks so that they do not merge into one blockquote.
   - **Rejected Alternatives.** Rows 0001-0012 take these exact bullets. Each quotes the option not taken from the decision issue's `## Question`, then the reason from the ruling comment when the ruling states one. The `## Options` sections say only "Framed neutrally in the question" and add nothing.
     - 0001: `- "must cuts stay player-initiated". Reason: "The cut is a craft move Skald owns; thresholds still only raise attention."`
     - 0002: `- "should the menu stay inside the scene". No reason recorded.`
     - 0003: `- "Should the player be able to set story-level tendencies for prose density, decision granularity, and scene tempo". Reason: "A player-set reading contract would be too much choice burden to solicit."`
     - 0004: `- "Should each story carry an explicit, persisted lens (viewpoint, tense, psychic distance, narrator presence, register) distinct from the setting artifact". No reason recorded.`
     - 0005: `- "keep only accrued, scene-grounded drift that flushes at a material threshold or rung crossing". Reason: "Co-presence does not automatically engender fondness."`
     - 0006: `- "the player's input and selected choice belong to the generation attempt until the child chunk is accepted". No reason recorded.`
     - 0007: `- "must secrets only ever emerge from play". No reason recorded.`
     - 0008: `- "keep the clock in the intertitle only". No reason recorded.`
     - 0009: `- "Restore list-price estimation". No reason recorded.` (The ruling leaves the pool map undecided. It stays in the Ruling quote and is not a rejected option.)
     - 0010 and 0011: `- None recorded in the public relay.` (#859 was resolved out of band and takes neither Question option. The #860 ruling keeps parts of both options.)
     - 0012: `- "Approve the theatrical cadence of block-by-block reveal with choices gated on completion". No reason recorded.`

     Rows 0013-0015 and 0030-0055: one bullet per relay sentence that says "not chosen", in its words, ending with the reason quoted when the sentence states one, else `No reason recorded.` Two relays name the losing option in other words. 0033: `- "adding four sibling keys at the wire root". No reason recorded.` (from the verbatim block). 0044: `- "not to replace them with one new three-way class". No reason recorded.` (from the "What is settled." bullet of 5915495072). Rows 0018-0024: the section's `**Summary:**` paragraph, followed by each `REFUTED` verdict line quoted. Where the cited text names no alternative (including 0016-0017), use the single bullet `- None recorded in the public relay.` Rows 0025-0029: the single bullet `- A comment without reader or writer evidence.` followed by #819's Summary sentence "Ambiguous semantics must route to the decision ledger rather than receiving invented documentation." quoted.
   - **Reopening Criteria.** Rows 0013-0015: the last sentence of the relay's "State of this issue." bullet, quoted. Row 0016: the #837 Verifier Amendments sentence beginning "Add per-stage timing", quoted. Row 0017: the #839 sentence beginning "Require confirmation", quoted. Rows 0018-0024: `- New evidence that answers each REFUTED verdict quoted above.` Rows 0025-0029: `- A reader or writer that establishes the contract, or a migration that drops the object.` Row 0030: `- A later owner ruling that overturns record 0005.` Every other row: `- A later owner ruling on the linked issue.`
4. **The Records list.** Replace `None yet.` (`docs/decisions/README.md:106`) with one line per record in number order, exactly `- [NNNN: Title](NNNN-slug.md)`. At the end of the `### Scope and Validation` paragraph (after `... or no merge base.`, `:71`), append: `It also checks every record in this directory: its file name and title, the Kind and Links lines, the three sections in order, and that the Records list below names each record once, in number order.` Change nothing else. `tests/test_doc_front_matter.py` is this README's declared source, so move its `verified_commit` to the same merge base.

No UI element changes, so no shadcn/ui check applies. No prompt text changes.
