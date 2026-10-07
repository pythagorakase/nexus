---
status: canonical
sources:
  - nexus/config/story_model.py
verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
---

# 0010: The Gaia Seat

**Kind:** decision
**Links:** #859, #758, #759

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/859#issuecomment-5800955522.

> **Ruling (owner, 2026-09-23): resolved out of band.** The owner moved the seats through the settings card that PR #874 added. Working tree `nexus.toml` (uncommitted, written by the card): `gpt-6-astra` now carries `apex.model` and `wizard.default_model`; the `apex.gaia_model` use is removed, so Gaia follows the slot model (Skald). Still on the retired models and worth one follow-up under C078 (#814): `gpt-5.6-sol` carries `orrery.experiences.model` and `storyteller.correspondence.compaction_model`; `gpt-5.6-terra` carries `global.model.default_model`, `ir_eval.judgment.model`, and `orrery.retrograde.maturation.model_ref`. The Chimeric delegate is already Astra (skill and `~/.codex/config.toml` updated 2026-09-05).

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
