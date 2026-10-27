---
status: canonical
sources:
  - ui/client/src/state-shades.test.ts
  - ui/client/src/components/nexus/LocalModelRows.tsx
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0066: The Keyboard-Held Tooltip

**Kind:** decision
**Links:** #1102, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1102#issuecomment-6423072099.

> - **1102-D1.** Which fix mechanism applies: a controlled Radix tooltip held open by keyboard focus-within, or one of the issue body's alternatives (the trash button as its own trigger, or the tooltip on a non-focusable element with `aria-describedby`)? Decision: a controlled tooltip, with `open = radixOpen || (keyboardFocusWithin && !escapeDismissed)` and the row as the single trigger. Basis: the 2026-10-14 issue comment. Reversal cost: revert to an uncontrolled tooltip.
> - **1102-D2.** Does any focus inside the row hold the tooltip open, including focus from a pointer click, or only keyboard-modality focus? Decision: keyboard modality only (`:focus-visible`, or no preceding pointerdown on the row). A pointerdown ref is cleared on focusout from the row or on any keydown. Pointer interactions keep Radix's behavior. Basis: the map default plus the critique's clearing rule. Reversal cost: trivial.
> - **1102-D3.** After Escape, does the tooltip stay dismissed while focus moves within the row, or reopen on the next internal focus? Decision: after Escape the tooltip stays dismissed until focus leaves the row. Basis: the map default. Reversal cost: trivial.
> - **1102-D4.** Does the natural-Tab trace replace the stationary-viewport precondition, or do both variants stay? Decision: replace the stationary-viewport precondition with natural Tab, assert that the auto-scroll happened, require 50/50/50, and record a red plant run. Basis: the remaining fix named in the issue comment. Reversal cost: test-only.
> - **1102-D5.** Does the README passage that differs from the 777-UI item-17 ordered text need separate coordinator confirmation? Decision: S1's rewritten README passage supersedes the 777-UI item-17 text. Basis: the map default. Reversal cost: docs only.
> - **1102-D6.** While keyboard focus holds one exceeds-RAM row's tooltip open, does hovering another tooltip trigger (the Radix broadcast close) close it? Decision: the keyboard hold wins over a Radix broadcast close. Radix's close only clears `radixOpen`. Basis: the map default. Reversal cost: trivial.
> - **1102-D7.** Is the browser-resolved state-surface receipt regenerated on this issue's branch? Decision: the receipt is not regenerated on this branch. `ui/client/src/state-shades.test.ts` fails as stale on the branch by design. The coordinator regenerates once on the wave's UI union before landing, as wave B did. Basis: several UI slices build in this wave, so one regeneration serves them all. Reversal cost: none.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
