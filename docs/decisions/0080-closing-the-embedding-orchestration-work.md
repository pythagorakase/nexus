---
status: canonical
sources:
  - tests/test_memnon/test_results.py
  - scripts/qa_shift/mission_prompt.md
verified_commit: "b0e9cb77af52a22673113b4910d027cd189cf281"
---

# 0080: Closing the Embedding Orchestration Work

**Kind:** decision
**Links:** #848, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/848#issuecomment-6423111652.

> - **848-D1.** Should the fourth orchestration copy, `ContentProcessor._generate_chunk_embeddings`, be refactored onto `source_embeddings` under #848, or handed to #1091? Decision: `ContentProcessor._generate_chunk_embeddings` goes with #1091's deletion (built this wave). Basis: Map default. Reversal cost: None.
> - **848-D2.** Should the "`embed_character_experiences` has no production caller" follow-up from PR #999 still be scheduled? Decision: The `embed_character_experiences` follow-up is resolved by PR #1002 (`drain_experience_embeddings_sync`); nothing to schedule. Basis: Map evidence. Reversal cost: None.
> - **848-D3.** Is the caller-level byte-identity CI check that PR #999 listed under Known Limits required before closing? Decision: No caller-level byte-identity CI check; `tests/test_memnon/test_results.py` pins the builders. Basis: Map default. Reversal cost: None.
> - **848-D4.** May the coordinator write to save_04 to re-embed and re-stamp the twelve summaries, and is further forensics needed on why the damage is present again? Decision: The coordinator runs R1 (dry run, then `--execute` on save_04, then the re-check) at land time, after R1b merges, so a QA reseed cannot undo it. The 2026-10-26 dry run found 27 summary rows, 12 stamped without a vector (ids 1, 2, 3, 5, 7, 8, 11, 13, 14, 15, 17, 19). Basis: Owner-data doctrine; critique ordering. Reversal cost: None (additive).
> - **848-R1b.** Should the QA kit's seed-alignment step repair stamped-but-vectorless Retrograde summaries, so that a reseed of save_04 from the pre-#671 seed cannot bring the damage back? Decision: The QA kit's seed-alignment step (`scripts/qa_shift/mission_prompt.md` step 7 and the README Seeds section) runs `nexus retrograde-embed-history --slot N` dry run then `--execute` after `scripts/migrate.py --slot N` and before the gateway starts, and requires `nexus jobs --slot N` to print no `stamped_without_vectors` line, recording the counts in the shift report. Docs only. Basis: The 07-31 seed carries the #665 damage; the reseed on 08-21 undid the heal. Reversal cost: Docs.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
