---
status: canonical
sources:
  - nexus/api/choice_handling.py
  - nexus/api/slot_endpoints.py
verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"
---

# 0006: Who Owns the Choice

**Kind:** decision
**Links:** #855, #801, #773

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/855#issuecomment-5565439618.

> **Ruling (owner, 2026-09-07): Option B plus one rule.** The parent chunk keeps owning the player's input and selected choice, written at generation time. Definitions: regenerate = try again without the player altering their choice; undo = the player wants to recast the last choice. Added rule: undo clears the parent's choice fields (choice_text and the derived raw_text), and startup recovery clears any parent choice that has no accepted child. No ownership move to the session row. The rest of C064 (#801) proceeds as planned: Bleed offer bookkeeping behind acceptance, validation before a chunk id is allocated. C035 (#773) keeps the integer selection plus edited text as one continuation payload.

## Rejected Alternatives

- "the player's input and selected choice belong to the generation attempt until the child chunk is accepted". No reason recorded.

## Reopening Criteria

- A later owner ruling on the linked issue.
