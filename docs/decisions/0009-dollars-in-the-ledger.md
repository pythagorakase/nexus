---
status: canonical
sources:
  - nexus/telemetry/usage.py
  - nexus.toml
  - nexus/cli.py
verified_commit: "54ee3dc1f811d1504d60bcdf0ecf3440c4e86397"
---

# 0009: Dollars in the Ledger

**Kind:** decision
**Links:** #858, #802, #756, #759

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/858#issuecomment-5800952750.

> **Ruling (owner, 2026-09-23): Option B.** The usage ledger stays in tokens. No price table in nexus.toml, no dollars column in `nexus usage`. The pool map (separate accounting per model pool) is not part of this ruling either way; propose it separately if a real pool boundary needs tracking.

## Rejected Alternatives

- "Restore list-price estimation". No reason recorded.

## Reopening Criteria

- A later owner ruling on the linked issue.
