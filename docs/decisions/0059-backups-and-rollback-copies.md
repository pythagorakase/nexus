---
status: canonical
sources:
  - nexus/runtime/slot_operations.py
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0059: Backups and Rollback Copies

**Kind:** decision
**Links:** #823, Loom sequence 42

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/823#issuecomment-6156195936.

> - **823-Q3, backup before a destructive operation:** *Make the backup itself, then continue* (`auto_backup`). A destructive slot operation takes its own backup first and proceeds without asking.
> - **823-Q4, rollback copies:** *Keep the last N copies for each slot* with **N = 3** (`last_n`, `n = 3`).
> - **823-Q11, clearing a slot:** *Keep a hidden copy* (`keep_copy`).

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
