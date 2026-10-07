---
status: canonical
sources:
  - nexus/agents/logon/skald_wire.py
verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
---

# 0033: Updates Block Shape

**Kind:** decision
**Links:** #566, Loom sequence 8

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/566#issuecomment-5070275155.

> Updates block shape: per-kind-arrays, keep a single optional updates namespace containing four typed arrays, instead of adding four sibling keys at the wire root:
> ```json
> "updates": {
>   "characters": [],
>   "places": [],
>   "factions": [],
>   "relationships": []
> }
> ```
> Omit `updates` when empty; when present, require all four arrays and remove the now-redundant `kind` discriminator.
>
> Local payload profile: provider-profile
>
> Overall notes: (no value)

## Rejected Alternatives

- "adding four sibling keys at the wire root". No reason recorded.

## Reopening Criteria

- A later owner ruling on the linked issue.
