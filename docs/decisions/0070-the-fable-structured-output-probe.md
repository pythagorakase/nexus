---
status: canonical
sources:
  - nexus.toml
  - scripts/api_anthropic.py
verified_commit: "571f982b2fa375acd4b52c51c76c29f4663f7242"
---

# 0070: The Fable Structured-Output Probe

**Kind:** decision
**Links:** #845, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/845#issuecomment-6423081217.

> - **845-D1.** How many paid Fable turns, and what threshold, separate "flake gone" from "not yet seen"? Decision: The probe is 12 consecutive two-pass production turns on claude-fable-5-1. Zero "did not include JSON output" rejections, and zero prompted-transport empty-content rejections on the Gaia seat, is a null result that closes the issue. The bootstrap case is outside the close condition. Basis: Map default with the critique's bootstrap and Gaia amendments. Reversal cost: Run more turns.
> - **845-D2.** Which database does the probe play on? Decision: The probe plays on a disposable data clone of save_04 (`requires_corpus` marker, `NEXUS_RUN_CORPUS=1`). The clone is pinned to claude-fable-5-1 through `story_pin`. `NEXUS_SLOT` is set to the routed slot for the gateway child. The child gets the secret-store opt-out env that the golden path uses. Basis: Map default plus critique items 1, 2 and 9. Reversal cost: Test-only.
> - **845-D3.** Which Fable model ID does the probe test? Decision: claude-fable-5-1, the registry's only Fable entry. Basis: Registry. Reversal cost: Trivial.
> - **845-D4.** Does the "explicitly strict tool variant" become a permanent `anthropic_storyteller_transport` value? Decision: No strict-tool arm is built unless S3 reproduces the flake. The two-pass writer is hard-coded native, so a probe-only arm is not buildable as stated. Basis: Critique objection to D4. Reversal cost: S4 builds it if needed.
> - **845-D5.** Which transport arms run first? Decision: Only the shipped production path runs in S2 and S3. Basis: Map default. Reversal cost: S4.
> - **845-D6.** Does any result reopen the mixed-channel writer design that PR #562 closed? Decision: The mixed-channel writer design is not reopened within #845. Basis: PR #562. Reversal cost: New issue.
> - **845-D7.** Where are `stop_reason` and the content block types recorded? Decision: S1 is diagnostics only. `stop_reason` and the content block types are added to the exception text and to the existing "structured-output rejected" log line. The `ValueError` class and the repair loop keep their shape. Basis: Critique objection on S1. Reversal cost: Trivial.
> - **845-D8.** Does Fable become the default Skald after a null result? Decision: No default Skald change follows a null result. Basis: Map default. Reversal cost: nexus.toml.
> - **845-D9.** Who runs the paid S3 probe, and when? Decision: The coordinator runs S3 after S1 and S2 land, under ruling 43 on #816. S3 is the paid run on this Mac, with a cap of 30 Anthropic calls and about 12 two-pass turns. S4 is conditional. Basis: Owner-data and paid-tier doctrine. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
