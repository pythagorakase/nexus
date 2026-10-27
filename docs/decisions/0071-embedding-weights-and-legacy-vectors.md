---
status: canonical
sources:
  - nexus.toml
verified_commit: "55ab85a4468f0a46b5cbe7b0daacf66d8a890709"
---

# 0071: Embedding Weights and Legacy Vectors

**Kind:** decision
**Links:** #812, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/812#issuecomment-6423082662.

> - **812-D1.** What does the last slice, 812-S4b, change in runtime config? Decision: 812-S4b takes `weight` out of runtime config and moves ensemble orchestration and weighting into `ir_eval` (Decision 812-Q4a). It deletes the unreachable `[ir_eval.embedding_candidates.bge-small-custom]` entry, and it keeps `is_active` as the single-active marker. Basis: Scan defaults. Reversal cost: git revert.
> - **812-Q4b.** Should the vectors from retired embedding models (about 94 MB each in save_01 and save_02) be kept, archived and dropped, or partly dropped? Decision: Legacy vectors on save_01 and save_02 stay as they are; the inventory records them. Basis: Least change; owner data. Reversal cost: A later drop migration.
> - **812-Q9.** What happens to the roughly 28 GB of model folders on disk that the app does not use? Decision: The unreferenced model folders (about 28 GB) are #820's under ruling 42 820-Q10: they are deleted at the #820 move. Basis: Ruling 42. Reversal cost: Recorded on #820.
> - **812-S7.** Does #812 still need a slice to anchor model artifacts under the runtime home? Decision: Retired: relative-path anchoring landed in PR #1125. Basis: Scan. Reversal cost: None.
> - **812-Q12.** Does 812-S4b migrate the legacy `ir_eval` V1 readers of `is_active`? Decision: The `ir_eval` V1 readers of `is_active` are left alone by S4b; #811's S4b deletes V1 (811-Q5 default, recorded 2026-10-26). Basis: 811-Q5 default. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
