---
status: canonical
sources:
  - nexus/agents/orrery/weather.py
verified_commit: "d70a1991210ce16aef5d6f9b57b0ec563ee1d164"
---

# 0032: Mood and Weather

**Kind:** decision
**Links:** #480, Loom sequence 4

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035539341.

> ISSUE #480 — Mood and Weather
> Axis 1a · Weather Scope: Per-Place / Per-Region
> Notes: > 20/24 characters are placeless and 15/16 places lack zone and coordinates
> This is worth looking into as a separate issue. The whole point of me introducing a GIS system was to require everything to be *somewhere*.
> Axis 1b · Weather Vocabulary: Current Closed Enum
> Notes: Let's let Skald elaborate in prose. No need to add weight to the schema here.
> Axis 1c · Weather Evolution: W-1 · Derived Function of World Time
> Notes: Give Skald an option to override local (in-scene) weather for dramatic effect, if it feels like it.
> Axis 2 · Mood Model: M-B · Stored Tag (the Issue's Sketch)
> Axis 3 · Consumption: Branch-selection bias
> Notes: These *seem* mutually exclusive, so I'm curious why this isn't an `<input type="radio">`.
> Axis 4 · Coupling: Events Only — Weather Stays Physical

Source: https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035716638.

> ## Axis 3 Correction — Owner Clarification (2026-07-21)
>
> Follow-up to the seq-4 relay above. The owner confirms the Axis 3 checkbox group was read as single-select at ruling time, pushed that way by two copy defects in the brief (both accepted as lessons for future briefs):
>
> 1. The option label "Storyteller context **only**" — the "only" implies mutual exclusivity, contradicting the checkbox semantics. The word survived verbatim from the v1 single-select option list, where it was correct; converting an axis to multi-select requires re-copyediting its labels, not just swapping its input type.
> 2. The brief's "soft mechanics" vs. "hard mechanics" framing reads as opposed approaches rather than composable channels.
>
> With additive semantics understood, the owner's corrected selection is:
>
> - [x] Storyteller context
> - [x] Branch-selection bias
> - [x] Branch conditions (hard gates)
> - [ ] Bleed selection coloring
>
> **Axis 3 freezes as: consumption via storyteller context + branch-selection bias + branch conditions. Mood/weather does not color bleed selection.** For consumption purposes this comment supersedes the Axis 3 line of Arachne ruling seq 4; the stored ruling remains the immutable record of what was literally filed. All six #480 axes are now frozen.
>
> *Recorded from the owner's direct in-session clarification, 2026-07-21.*

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
