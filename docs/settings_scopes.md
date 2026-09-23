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
