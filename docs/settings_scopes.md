# Settings Scopes

Design pending owner confirmation; issues #814 and #756.

`nexus.toml` holds defaults and developer tunables. Runtime writes to it raise an error. `GET /api/settings` serves defaults and registry metadata from the effective runtime config; its PATCH route is retired.

| Scope | Storage | API |
| --- | --- | --- |
| Story | Slot database, singleton `global_variables` row | `GET/PATCH /api/slot/{n}/settings` |
| Player | `[runtime].state_dir/preferences.toml` | `GET/PATCH /api/preferences` |
| Developer | Read-only `nexus.toml` | `GET /api/settings` |

Story fields are `skald_model` (existing `model` column), `gaia_model`, and `apex_context_window`. Migration 117 adds only the latter two nullable columns with comments. NULL Skald and context pins follow repository defaults; NULL Gaia follows the actual Skald selection, including a request override. Existing rows are not repinned. The old `/api/slot/{n}/model` routes are retired.

Player fields are `theme`, per-theme `fonts`, and `wizard_model`. First write materializes all three from repository defaults into an atomically replaced TOML file. Until then, reads use defaults without creating a file. The default state directory is still the gitignored `.nexus/runtime`; relocating runtime home outside the checkout is deferred. An absolute state directory stores preferences outside the checkout today.

## Resolution and Callers

`nexus/config/story_model.py::resolve_story_model` applies request override → slot pin → player preference (wizard only) → repository default. All selected models must exist in the registry before provider construction. Developer seats supply their existing configured model explicitly through the same resolver; this change does not move their tunables into player preferences.

- Writer, bootstrap, and regeneration resolve the story's Skald pin. `continue --model` is a request override and no longer repins the story.
- Gaia resolves its story pin; NULL follows the writer. Local-runtime management remains under Skald.
- Setup resolves the wizard preference when there is no operator pin or started setup, then records the chosen model in the slot row. Subsequent wizard chat, set design, trait derivation, and wizard Retrograde use that pin through the resolver.
- Native structured-output and Pydantic AI provider construction share the registry boundary. Experience rendering, runtime maturation, summaries, and correspondence compaction retain their configured developer model selections. Orrery narration currently consumes deterministic verdicts; it no longer constructs a narration provider.
- Story context settings are copied before budget calculation. An explicit story window outranks repository provider profiles and feeds writer/Gaia sizing and the Pass-2 fingerprint. Bootstrap and the baseline-stamping operator use the same projection. A change affects that story's fingerprint only.

`LogonUtility(story_settings=...)` and bootstrap's `story_settings` input accept explicit snapshots for already-resolved callers and offline tests. With no snapshot, production reads use the shared pool and propagate errors.

## Retired Pins

A pin naming a removed registry ID is readable but fails resolution. No automatic clearing occurs. Use `nexus model --slot N --clear`, or PATCH the corresponding model field to NULL. `nexus model --slot N --set ID` assigns a registered Skald pin.

Migration 117 is applied to disposable databases during QA only. The coordinator applies fleet/template migrations at land time.

## Refreshing a Pass-2 Fingerprint

After a deliberate configuration-shape change that leaves Pass-2 semantics
unchanged (such as removing an unused memory setting), run:

```sh
PYTHONPATH=$PWD python scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --slot N --write-locked-slot
# Disposable/reference database alternative:
PYTHONPATH=$PWD python scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --dbname qa640_example
```

Run with turns stopped for that target. This explicit compatibility operation
uses the current settings projected through the target story's context-window
pin. For a locked target, `--write-locked-slot` overrides read-only policy only in
the maintenance session; leave the database locked throughout. It prints the old
and new hashes and updates only `config_fingerprint` in
the accepted tail's existing baseline payload. Memory identities, accounting,
budget, historical rows, and provisional drafts remain unchanged. Missing or
malformed baselines are errors; refresh never stamps an empty replacement.
Do not use refresh to bypass an actual change in retrieval semantics. The
coordinator runs it for affected saves at landing after deploying this change.

## Replaying Recorded Prompt Windows

Every rendered generation attempt appends its exact input tokens, per-block
counts, and seat ceiling to the usage ledger (`windows-<day>.jsonl`; list them
with `nexus usage --run SESSION`). Before changing seat policy or a model's
declared limits, replay a run under the candidate configuration:

```sh
nexus window-replay --run SESSION --day 2026-09-26 --config candidate.toml
nexus window-replay --run SESSION --model MODEL_ID --window 90000 --json
```

`--config` names a complete copy of `nexus.toml` and is validated like any
configuration. The replay keeps the recorded token counts and recomputes only
the ceiling through the same seat arithmetic the trimming pass and the final
guard use; nothing is rendered, counted, priced, or sent to a provider. Each
attempt holds its recorded prompt spend (ceiling plus policy headroom) unless
`--window` replaces it. The candidate's window keys
(`lore.token_budget.apex_context_window` and its `provider_overrides`) are not
applied: when the candidate's configured window for an attempt's model differs
from the runtime config's, the replay stops with both values, and `--window`
is how to replay the new spend. `--model` replaces every attempt's model,
keeping the counts measured with the recorded model's tokenizer. Unregistered
models and allowances above a model's maximum fail exactly as they would at
runtime.

Per attempt, the report gives the ceiling delta, whether the recorded spend
was capped by the model's maximum input (a zero delta on a capped attempt can
hide capacity the candidate frees; pass `--window` to see it), the overflow
above the new ceiling, the recent-narrative, historical-context, and
recalled-scene tokens the trimming pass could drop, whether they cover the
overflow, and the tokens freed below the new ceiling. Feasibility is an upper
bound: the trimmable counts include section headings and the newest scene,
which is never dropped; the trimming pass drops memory from the writer and
Gaia seats jointly while the replay judges each seat alone; and it ignores the
registry's tokenizer safety margin (4,096 on the Anthropic, Kimi, and GLM
entries), which the trimming pass reserves and the final guard also subtracts
for the locally approximated Kimi and GLM counts.
