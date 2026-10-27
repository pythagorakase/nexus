---
status: canonical
sources:
  - ui/client/src/state-surfaces.resolved.json
  - ui/client/src/components/nexus/SettingsPane.tsx
verified_commit: "70a1ff95104eb89c4362993e7889021deef72723"
---

# 0067: Seat Lists in a Popover

**Kind:** decision
**Links:** #821, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/821#issuecomment-6423073509.

> - **821-Q1.** How does a phone or tablet user reach the list of seats that need a key, which today appears only in a hover title? Decision: Touch disclosure of the seat list is a tap-opened shadcn Popover (checked against ui.shadcn.com first), with no new label. Basis: Visual minimalism; the decision-page question was never answered and is 'decide' grade. Reversal cost: Trivial.
> - **821-D2.** Is the non-macOS keyring case, where a broken keyring backend reads as a missing key, fixed on this issue? Decision: The KeyringLib non-macOS follow-up stays deferred and folds into #803's guest-host work. Basis: Scan default. Reversal cost: None.
> - **821-D3.** Does the 821-S2 branch regenerate the state-surface receipt (`ui/client/src/state-surfaces.resolved.json`)? Decision: The state-surface receipt is not regenerated on this branch (stale by design; the coordinator regenerates once on the wave's UI union). Basis: One regeneration per wave. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
