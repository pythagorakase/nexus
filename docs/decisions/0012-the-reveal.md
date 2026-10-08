---
status: canonical
sources:
  - ui/client/src/components/nexus/NarrativePane.tsx
verified_commit: "d70a1991210ce16aef5d6f9b57b0ec563ee1d164"
---

# 0012: The Reveal

**Kind:** decision
**Links:** #861, #772

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/861#issuecomment-5565410350.

> **Ruling (owner, 2026-09-07): Option B.** Clean slate: the prose appears at once. Instant mode and the reduced-motion path only; no typewriter, no paragraph-by-paragraph reveal, no choices gated on completion. Some version of a reveal effect may return later, but not now. C034 (#772) is re-scoped to: remove the typewriter, render the parsed prose immediately, keep the follow-scroll and skip logic out.

## Rejected Alternatives

- "Approve the theatrical cadence of block-by-block reveal with choices gated on completion". No reason recorded.

## Reopening Criteria

- A later owner ruling on the linked issue.
