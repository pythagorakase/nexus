---
status: canonical
sources:
  - nexus/memory/correspondence.py
  - nexus.toml
  - prompts/storyteller_writer_pass.md
  - prompts/storyteller_gaia.md
  - prompts/correspondence_compaction.md
verified_commit: "4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8"
---

# 0034: Conspiracy Channel

**Kind:** decision
**Links:** #617, Loom sequence 9

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113803006.

> **Channel shape:** dm-letters. "I think an auto-compaction feature is the answer to the lifecycle. But give it a trailing distance. The last `n` letters are always presented uncompressed. Let `n` be a configurable variable. Could try starting with 5?"
>
> **How plans end:** (no option selected) "Let the compaction do the culling. Some well-laid plans will become irrelevant or inappropriate to the direction the story has taken, or moot, or simply impossible to enact. Let's try folding a judgment call into the compaction call: In the act of extracting old plans from a backlog of letters and structuring them into a summary, mark which ones appear live/viable vs stale, expired, no longer applicable, etc."
>
> **First page:** empty. "Let's frame the goal like this: The two personas, when correctly invoked, will *want* to conspire. Refine both prompts to this end."

Source: https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113867184.

> ## Ruling Amendment (owner, 2026-07-29)
>
> The trailing window is a **hysteresis range**, not a fixed length:
>
> - **Floor** (default 5): the number of uncompressed letters that survive a compaction.
> - **Ceiling** (default 10): the trigger — when appending the current turn's letters would exceed it, everything older than the floor compacts into the digest first.
>
> Rationale: a fixed window forces a compaction call every turn (each turn deposits two letters — writer + Gaia reply). The range amortizes compaction to roughly every 2–3 turns and gives each compaction a meatier span to judge, which suits the compaction-does-the-culling lifecycle.
>
> Implementation notes riding with this:
> - Compaction boundaries align to **exchange pairs** — a turn's writer letter and Gaia reply compact together or not at all.
> - The compaction call runs **off the hot path** (its own utility call after turn completion), leaving both seat wire schemas untouched.
> - Both knobs live in `nexus.toml`.

Source: https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113874777.

> ## Units Correction (owner, 2026-07-29)
>
> The hysteresis range is measured in **turns (exchange pairs), not individual letters**: floor 5 = the last 5 turns' correspondence (10 letters) survives compaction; ceiling 10 = compaction triggers before an 11th turn's exchange would be appended. Exchange-pair atomicity is therefore inherent to the unit, not a separate rule. Compaction cadence: roughly every 5 turns at defaults.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
