---
status: canonical
sources:
  - migrations/141_genesis_run_ledger.sql
  - nexus/api/conversations.py
verified_commit: "d70a1991210ce16aef5d6f9b57b0ec563ee1d164"
---

# 0053: Resumable Genesis

**Kind:** decision
**Links:** #776, Loom sequence 40

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/776#issuecomment-5915669789.

> **#776 Resumable genesis**
> - Disposition: Build (disp_776=build)
> - Failure recovery target: Resumable (q_776_target=resumable)
> - Incomplete wizards on OpenAI threads: Discard them (q_776_legacy=discard)

## Rejected Alternatives

- "The option not chosen reran from a clean start." No reason recorded.

## Reopening Criteria

- A later owner ruling on the linked issue.
