---
status: canonical
sources:
  - config/exception_disposition_baseline.json
  - scripts/extract_scene_numbers.py
verified_commit: "b0e9cb77af52a22673113b4910d027cd189cf281"
---

# 0078: Retiring the Legacy File Ingest

**Kind:** decision
**Links:** #1091, #1119, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1091#issuecomment-6423107274.

> - **1091-Q1.** Should MEMNON's file ingest be retired, or repaired onto the live `chunk_metadata` columns and made to raise? Decision: Retire MEMNON's file ingest outright (`ContentProcessor`, the MEMNON wrappers, the `process files` step command) and `scripts/import_narratives.py`. Basis: Dead on every current slot; 811-Q3/Q5 defaults recorded on #811 on 2026-10-26. Reversal cost: git revert.
> - **1119-Q2.** Should the seven legacy importers and metadata writers be retired, or have their handlers made to raise? Decision: Retire all seven legacy writers (`import_narratives` in 1091-S1; `simple_update`, `update_raw_text`, `extract_season_episode`, `estimate_time_delta`, `map_builder_legacy`, `process_characters` in 1119-S2) with the operator prompts only they consume. This supersedes Decision 810-Q4's "commands stay available" for these commands. The coordinator records the supersession on #810 at landing. Basis: Each names retired columns and turns failures into silent zeros. Reversal cost: git revert.
> - **1119-Q3.** How does each remaining swallowing handler get its `nexus-exception-disposition` marker or get removed? Decision: Handlers disappear by removal. `config/exception_disposition_baseline.json` shrinks accordingly. No new markers are added. Basis: The lint allows shrinking. Reversal cost: None.
> - **1091-Q2.** Should `[memnon.import]` be retired along with the ingest? Decision: `[memnon.import]` stays this wave, because `scripts/extract_scene_numbers.py` still reads it. It is retired under #811 once no reader remains. Basis: Least change. Reversal cost: Trivial.
> - **1091-Q3.** Should the PostgreSQL proof `test_content_processor_embedding_method_propagates_ensure_failure` be ported when `_generate_chunk_embeddings` is deleted? Decision: The test is deleted with the method, not ported. Basis: Map default. Reversal cost: None.
> - **1091-Q4.** Should #1091 and #1119 ship as one PR or two? Decision: One PR with two ordered commits (1091-S1 then 1119-S2). The PR says Closes #1091, Closes #1119. Basis: Coupled deletions. Reversal cost: None.
> - **1091-Q5.** Should `MEMNON._load_aliases` be deleted with the ingest? Decision: Keep `MEMNON._load_aliases` and its `load_aliases_from_db` import. Remove only the `load_aliases_func` argument tied to `ContentProcessor`. Basis: Critique: test-pinned and documented. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
