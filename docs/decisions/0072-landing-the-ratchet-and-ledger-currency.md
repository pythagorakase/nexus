---
status: canonical
sources:
  - docs/decisions/README.md
  - tests/test_doc_front_matter.py
verified_commit: "b75f6241cf98aff251b100b776d50f3003c872cb"
---

# 0072: Landing the Ratchet and Ledger Currency

**Kind:** decision
**Links:** #817, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/817#issuecomment-6423083545.

> - **817-D1.** How do 817-S4 and 817-S5 land, given that both edit and re-stamp `docs/decisions/README.md`? Decision: S4 then S5 in one PR with ordered commits; `docs/decisions/README.md` re-stamped once at the end. Basis: the scan shows that both slices touch the README. Reversal cost: none.
> - **817-D2.** Which rulings do the new ledger records in 817-S5 cover? Decision: S5's new ledger records cover every loom ruling relayed verbatim since the backfill, including sequences 41, 42 and 43 and the coordinator decisions recorded on 2026-10-26. Basis: ledger currency. Reversal cost: docs only.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
