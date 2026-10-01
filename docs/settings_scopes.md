# Settings Scopes

Design pending owner confirmation; issues #814 and #756.

`nexus.toml` holds defaults and developer tunables. Runtime writes to it raise an error. `GET /api/settings` serves defaults and registry metadata from the active config; its PATCH route is retired.

| Scope | Storage | API |
| --- | --- | --- |
| Story | Slot database, singleton `global_variables` row | `GET/PATCH /api/slot/{n}/settings` |
| Player | `[runtime].state_dir/preferences.toml` | `GET/PATCH /api/preferences` |
| Developer | Read-only `nexus.toml` | `GET /api/settings` |

Story fields are `skald_model` (existing `model` column), `gaia_model`, and `apex_context_window`. Migration 117 adds only the latter two nullable columns with comments. NULL Skald and context pins follow repository defaults; NULL Gaia follows the actual Skald selection, including a request override. Existing rows are not repinned. The old `/api/slot/{n}/model` routes are retired.

Player fields are `theme`, per-theme `fonts`, and `wizard_model`. First write materializes all three from repository defaults into an atomically replaced TOML file. Until then, reads use defaults without creating a file. A relative state directory resolves under the runtime home: the checkout by default (the gitignored `.nexus/runtime`), or `$NEXUS_HOME` when set. An absolute state directory is used as configured.

## The Active Configuration

One rule, in `nexus/runtime/home.py`, selects the `nexus.toml` every reader uses, independent of the working directory. With `NEXUS_HOME` set, the active config is `$NEXUS_HOME/nexus.toml`; `NEXUS_RUNTIME_CONFIG` (set by the supervisor on every service it spawns) or `nexus up --config` may also name it, but naming a different file is refused with a `RuntimeError`, so two active configurations cannot exist. Without `NEXUS_HOME`, `--config` wins, then `NEXUS_RUNTIME_CONFIG`, then the checkout's `nexus.toml`. The same rule anchors relative runtime directories (`[runtime].state_dir`, `[usage].usage_dir`) at the home root. See The Runtime Home in `docs/runtime.md` for the layout and the `nexus home plan` dry run.

## Resolution and Callers

`nexus/config/story_model.py::resolve_story_model` applies request override → slot pin → player preference (wizard only) → repository default. All selected models must exist in the registry before provider construction. Developer seats supply their existing configured model explicitly through the same resolver; this change does not move their tunables into player preferences.

- Writer, bootstrap, and regeneration resolve the story's Skald pin. `continue --model` is a request override and no longer repins the story.
- Gaia resolves its story pin; NULL follows the writer. Local-runtime management remains under Skald.
- Setup resolves the wizard preference when there is no operator pin or started setup, then records the chosen model in the slot row. Subsequent wizard chat, set design, trait derivation, and wizard Retrograde use that pin through the resolver.
- Native structured-output and Pydantic AI provider construction share the registry boundary. Experience rendering, runtime maturation, summaries, and correspondence compaction retain their configured developer model selections. Orrery narration currently consumes deterministic verdicts; it no longer constructs a narration provider.
- Story context settings are copied before budget calculation. An explicit story window outranks repository provider profiles and feeds writer/Gaia sizing and the Pass-2 fingerprint. Bootstrap and the baseline-stamping operator use the same projection. A change affects that story's fingerprint only.

`LogonUtility(story_settings=...)` and bootstrap's `story_settings` input accept explicit snapshots for already-resolved callers and offline tests. With no snapshot, production reads use the shared pool and propagate errors.

## Gaia Generation Profile

Gaia's model follows story resolution; its generation profile does not. The developer-scoped `[apex.gaia]` table holds Gaia's `reasoning_effort`, `max_output_tokens`, and reserve fields, and the writer keeps `[apex]`. A Gaia resolved to a model other than the writer's builds a fresh provider from `[apex.gaia]`; the slot-following clone of the writer's provider takes its effort and output allowance from `[apex.gaia]`. The shipped profile equals the writer's.

`[apex.gaia].reasoning_effort` reaches the OpenAI Responses and Anthropic transports only. Chat Completions routes (OpenAI-compatible `base_url` providers such as `local` and `openrouter`) never send the configured effort for either seat: the request carries the model's registry `request_params` effort (a `reasoning = { effort = "low" }` damping, for example), or none. The output allowance reaches every transport.

Settings load rejects a configured Gaia default (`apex.gaia_model`, else `apex.model`) whose registry entry lists `reasoning_effort` or `reasoning` in `unsupported_params`, or declares `reasoning_accounting = "none"`. Gaia seat resolution applies the same check to story pins and slot following. The TEST mock is exempt. The writer's `apex.reasoning_effort` has no equivalent check; this profile validates the Gaia seat only.

Every turn uses this one profile; workload-driven selection waits on real-entry-point A/B evidence (issue #758). `generation_attempt_manifests.config_sha256` hashes the full effective settings, `[apex.gaia]` included. Each usage-ledger event (`reasoning_effort`, `max_output_tokens`) and its `USAGE` log line (`effort=`, `max_output=`) record the generation profile sent: the exact request kwargs for provider calls, and the run's model settings for Pydantic AI aggregates. The log line shows `-` when nothing was sent.

## Retired Pins

A pin naming a removed registry ID is readable but fails resolution. No automatic clearing occurs. Use `nexus model --slot N --clear`, or PATCH the corresponding model field to NULL. `nexus model --slot N --set ID` assigns a registered Skald pin.

Migration 117 is applied to disposable databases during QA only. The coordinator applies fleet/template migrations at land time.

## Pass-2 Baseline Compatibility

Each accepted chunk stores a Pass-2 baseline (`lore_pass_baselines`): the
memory identities and token accounting of that turn's context, fingerprinted
against the `[memory]` and `[lore.token_budget]` settings in effect, with the
story's window pin applied. Schema 2 keeps the full `config_fingerprint`
unchanged for audit and schema-1 comparison and adds `config_snapshot` (every
fingerprinted value under its class) and `semantic_fingerprint` (a hash of the
semantic class only). Every field carries an explicit class in
`nexus/memory/baseline_compat.py`; an unclassified field fails at import and in
the test suite.

| Setting | Class | Why |
| --- | --- | --- |
| `lore.token_budget.apex_context_window` | budget | Each turn resolves the window, then recomputes `total_available` and the Phase-2 cap. |
| `lore.token_budget.provider_overrides` | budget | Per-provider reductions of the same window. |
| `lore.token_budget.system_prompt_tokens` | budget | Allocation hint read by the live budget calculation. |
| `lore.token_budget.prompt_overhead_tokens` | budget | Legacy allocation hint; nothing stored derives from it. |
| `memory.phase2_fraction` | budget | Multiplies the live window into the Phase-2 cap, exactly like a window change. |
| `memory.raw_search_k` | semantic | Pass-2 retrieval breadth: the candidate pool, not a token amount. |
| `memory.skip_simple_choices` | semantic | Whether Pass 2 runs at all for a bare choice. |
| `memory.pass2_budget_reserve` | semantic | Baked into the stored accounting (`reserved_for_pass2`, `reserve_shortfall`). |
| `memory.warm_slice_default` | semantic | Warm-slice expansion behavior. |
| `memory.max_sql_iterations` | semantic | Query iteration cap that shapes retrieval. |

The LORE retrieval breadth settings `lore.retrieval.max_deep_queries` and `lore.retrieval.deep_query_k`, and the historical-passage cap `lore.render_limits.historical_passages`, sit outside the fingerprinted tables. `deep_query_k` bounds the results MEMNON returns for each deep query before deduplication. Changing these settings does not change the Pass-2 configuration fingerprint or require a stored-baseline refresh.

On continuation:

- An equal full fingerprint proceeds.
- A schema-2 baseline whose semantic fingerprint still matches is rebased: its
  memory identities and prior accounting are kept, and the turn re-derives the
  remaining budget from live token counts, capped by the new Phase-2 budget. A
  `WARNING` names the database, the old and new window, every changed budget
  field, and what was kept.
- A semantic change fails and names each changed field with its stored and
  current values. Restore the previous values, or accept them for the story
  with the refresh below.
- A schema-1 baseline records no snapshot, so any mismatch fails as before and
  names the refresh.

A window change through `PATCH /api/slot/{n}/settings` is an explicit player
intervention. In the same transaction as the new pin, the accepted tail's
baseline is rewritten as schema 2 under the new window when it was
fingerprinted under the pre-change settings; a schema-1 tail is upgraded. A
tail fingerprinted under other settings is left unchanged for the next
continuation to rebase or refuse. Historical rows and provisional drafts are
not rewritten; a schema-2 draft staged under the old window is rebased when
the turn after its acceptance continues from it.

## Refreshing a Pass-2 Fingerprint

After a deliberate configuration change that the story may continue under
(such as removing an unused memory setting, or accepting a semantic change for
an existing story), run:

```sh
PYTHONPATH=$PWD python scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --slot N --write-locked-slot
# Disposable/reference database alternative:
PYTHONPATH=$PWD python scripts/stamp_lore_pass_baseline.py --refresh-fingerprint --dbname qa640_example
```

Run with turns stopped for that target. This explicit compatibility operation
uses the current settings projected through the target story's context-window
pin. For a locked target, `--write-locked-slot` overrides read-only policy only in
the maintenance session; leave the database locked throughout. It prints the old
and new hashes. A schema-1 tail keeps its schema and changes only
`config_fingerprint`; a schema-2 tail is re-fingerprinted and re-snapshotted.
Memory identities, accounting, budget, historical rows, and provisional drafts
remain unchanged. Missing or malformed baselines are errors; refresh never
stamps an empty replacement. Refreshing past a semantic change is an operator
decision that the story continues under the new retrieval semantics; budget-only
changes to a schema-2 tail need no refresh. The coordinator runs it for affected
saves at landing after deploying this change.

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

The recorded `removed_block_tokens` map attributes cached assembly estimates to
recent narrative, historical context, and recalled scenes, including removed
headings. `removed_tokens_total` sums that map; absent or empty legacy accounting
is unknown (`null` in replay JSON), while a complete three-key zero map records
zero. Candidate changes preserve these per-attempt snapshots. Retries repeat
assembly accounting rather than adding removals; do not sum them as new removals
or provider usage. `freed_tokens` remains candidate headroom, a separate quantity.
Kept block sums still reconcile to actual dispatch input.

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
