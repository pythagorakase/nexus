---
status: canonical
sources:
  - nexus/agents/orrery/templates.py
  - scripts/apply_slot2_semantic_tags.py
  - nexus/config/loader.py
  - CLAUDE.md
  - scripts/api_openai.py
  - scripts/api_anthropic.py
  - nexus/maintenance/new_story_setup.py
  - nexus/runtime/slot_operations.py
  - scripts/rebuild_memory_idf.py
  - scripts/replay_state.py
  - tests/test_schema_ownership.py
verified_commit: "55ab85a4468f0a46b5cbe7b0daacf66d8a890709"
---

# 0083: Retiring Old Scripts and Retired-Tag Gates

**Kind:** decision
**Links:** #811, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/811#issuecomment-6423208720.

> - **811-Q2.** What happens to the ten active tags in retired categories on save_03 (4 rows) and save_04 (6 rows)? Decision: Report only. The ten active retired-category tags on save_03 and save_04 stay in place; `nexus tags audit` keeps listing them; no operator verb (811-Q14) is built. Basis: Owner story data; least change; reversible later by the Q14 verb. Reversal cost: Build the verb later.
> - **811-Q3.** Where does the unique old material in scripts/ and ir_eval/ go, meaning the 78 pending-ruling:811-Q3 paths plus the ignored logs? Decision: Before any deletion, the coordinator copies every path the deletion slices remove, plus every untracked or ignored file under scripts/ and ir_eval/ (logs, local databases, context files), to ~/nexus-archive/811-2026-10/ with a MANIFEST (path, size, last commit, sha256). Then the tracked paths are deleted from HEAD with Git history as the record. Basis: Loses nothing; keeps the checkout clean. Reversal cost: Restore from the archive or git.
> - **811-Q5.** Is the ir_eval V1 runner, broken since June, deleted, repaired onto typed settings, or kept unchanged as historical? Decision: Retire ir_eval V1: delete the 38 pending-ruling:811-Q5 paths, the loader's .json branch and the CLAUDE.md sentence about legacy .json paths, after the Q3 archive copy. Basis: Broken since June; #813's direction; git history remains. Reversal cost: git revert.
> - **811-Q8.** Are the off-screen NPC behaviors gated only on retired-category tags (for example cultivate_informant at templates.py:1313) rewired, restored, removed or left as they are? Decision: Rewire the Orrery gate literals that name retired-category tags to live tags in the registry's replacement categories; negated gates are remapped the same way, never dropped (templates.py:2633-2636 documents the design). Basis: The owner's standing dynamism goal: behaviors that can never fire are defects. Reversal cost: Edit the literals.
> - **811-Q8b.** What is the per-literal mapping from retired tags to live role.function and state tags, including the negated informant_handler gate at :2643? Decision: The coordinator drafts the per-literal mapping table from the tag descriptions and records it on #811 before 811-S5 is frozen (next round). Basis: Prompt-adjacent vocabulary is the coordinator's pen. Reversal cost: Edit the table.
> - **811-Q15.** Where do the relocated provider shims land, and do the scripts/ wrappers stay? Decision: The provider shims move unchanged to nexus/providers/api_openai.py and nexus/providers/api_anthropic.py; the scripts/ wrappers keep __main__ and re-export. Basis: Decision 811-Q4 and 811-Q11. Reversal cost: Trivial.
> - **811-Q16.** Do the new runtime imports of scripts.rebuild_memory_idf (nexus/maintenance/new_story_setup.py:757) and scripts.replay_state (nexus/runtime/slot_operations.py:365) move into nexus/? Decision: The two runtime imports from scripts/ that appeared after S1 (rebuild_memory_idf, and the second the map names) move under nexus/maintenance/ with thin wrappers, plus a guard test that nexus/ never imports scripts. Basis: Decision 811-Q6 precedent. Reversal cost: Trivial.
> - **811-Q17.** Does the held class keep the name `pending-ruling:811-Q1` now that the retention ruling is settled? Decision: The held class is renamed retained:811-Q1 with the 2026-07-17 retention ruling as its reason. Basis: Accurate classification. Reversal cost: Trivial.
> - **811-Q18.** Does apply_slot2_semantic_tags.py skip and count a deprecated-category candidate, or fail? Decision: apply_slot2_semantic_tags.py fails loudly before any insert on a deprecated-category candidate, routed through apply_tag_bestowal (the 2026-10-01 direction), not a copied message. Basis: Fail-loud doctrine; the critique. Reversal cost: Trivial.
> - **811-Q19.** Are the 33 `dead` paths deleted, given that they include scripts/edi, which wraps a client outside the repository? Decision: The 33 dead paths are deleted after the Q3 archive copy, with their test loaders (tests/test_schema_ownership.py) updated in the same slice. Basis: Dead code; #1119 points the same way. Reversal cost: git revert.
> - **811-Q20.** Does #811 need a submit-time place-tag check in the set designer, as deferred by PR #1063? Decision: No submit-time place-tag check in the set designer; the transition writer is the boundary gate. Basis: Map default. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
