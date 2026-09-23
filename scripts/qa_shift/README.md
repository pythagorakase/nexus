# NEXUS Adversarial QA Shift

This tracked utility turns the previous one-off `temp/qa_shift` experiment into
a repeatable native Codex Scheduled task. The operator remains Codex itself;
there is no nested `codex exec`, launchd plist, systemd unit, or six-hour shell
wrapper.

Run evidence still belongs in ignored `temp/qa_night_*` archives. The durable
policy, usage guard, configuration, and templates live here in version control.

## Schedule It in Codex

Create a recurring standalone task that uses the local project at
`/Users/pythagor/nexus`. A nightly 11:30 PM `America/Chicago` start leaves the
normal workday alone and avoids the OpenAI UTC-day boundary during the
configured one-hour shift.

Use this task prompt:

```text
Open /Users/pythagor/nexus/scripts/qa_shift/mission_prompt.md and execute the
NEXUS Night QA Shift exactly as written. Issue publication is explicitly
authorized.
```

The machine must be awake, the Codex app must be running, and the scheduled
task must have the shell, local-filesystem, network, PostgreSQL, Keychain, and
GitHub access needed by the mission. Run the prompt once manually before
enabling recurrence.

## Completion Policy

Defaults in `qa_shift.toml` deliberately combine independent bounds:

- at most five verified, published issues;
- three consecutive dry probe families, after at least five total families;
- a 60-minute wall clock; and
- a 10,000,000-token daily allowance with a 1,000,000-token reserve.

The issue count is a cap, not a quota. The dry-well rule lets a healthy build
finish without manufacturing bugs, while the token and time fences remain
backstops. A seeded run also owes an observed roster transition, one bounded
concurrency family, novelty against up to two completed prior runs when that
history exists, and classification of every current-run structured-output
rejection before it may end dry.

The 10M figure is operational configuration, not a billing entitlement
discovery mechanism. Reconfirm the organization’s current complimentary-token
enrollment and eligible model group before raising it or changing
`target_model`.

## Seeds

Shallow single-request probes stop finding bugs once the early-game surface
hardens; state-threshold defects (compaction, alias accumulation) only appear
deep into a campaign. Drop a checksummed mid-campaign `pg_dump -Fc` dump into
`temp/qa_seeds/` (ignored, conventionally preserved) and the shift seeds the
disposable slot from the newest one instead of a bare reset, then owes the
deep-state and coverage gates in `mission_prompt.md`.

A dry final state is only a seed candidate. Promotion requires a trustworthy
usage ledger, no unresolved anomaly, current migrations, zero active generation
leases, empty Orrery job queues, coherent measured counts, a final public load,
and a checksummed dump that restores successfully into a disposable verification
database. Write the `.partial`, promoted `.dump`, checksum, and adjacent manifest
under `temp/qa_seeds/`. The manifest records the source archive, commit,
schema/model metadata, exact chunk/exchange/digest counts, known-issue hotspots,
and sha256. Retain the previous seed; do not silently replace the only known-good
depth checkpoint. Prune stale seeds only when the schema or campaign shape they
capture stops being representative.

For novelty preflight, a prior archive counts as completed only when its
`shift_state.json` says `status: "finished"`. Read the newest two qualifying
archives, or every qualifying archive when fewer than two exist. Zero prior
archives is valid and contributes an empty coverage history.

## Usage Guard

Run the helper through Poetry:

```text
poetry run python scripts/qa_shift/qa_shift.py config
poetry run python scripts/qa_shift/qa_shift.py begin
poetry run python scripts/qa_shift/qa_shift.py check temp/qa_night_...
poetry run python scripts/qa_shift/qa_shift.py check temp/qa_night_... --expect-call
poetry run python scripts/qa_shift/qa_shift.py finish temp/qa_night_... --exit-condition dry_well
```

`begin` creates the archive, captures the UTC-day baseline, copies the report
and ledger templates, and generates an isolated runtime config. That config
pins both the default and Gaia OpenAI roles to the configured target model and
sets the slot default to the same model. It never edits `nexus.toml`.

The ledger is exact for API responses recorded by this NEXUS checkout; it is
not the OpenAI organization-wide usage meter. Concurrent NEXUS traffic is
conservatively included in the shift delta, while API calls made outside NEXUS
are invisible. Run the shift when no other API client is drawing on the same
allowance, or reduce the configured limit to leave room for that traffic.

Each `check` calls `nexus usage --json` and records:

- the OpenAI delta since the previous check;
- the provider-reported token fields for each new QA-slot API response;
- cumulative shift and UTC-day totals;
- the largest check-to-check delta;
- events and effective model routes for the QA slot;
- remaining room before the token fence; and
- elapsed wall time.

Exit code `0` means generation may continue. Exit code `2` means stop
generating and report. Exit code `1` means the guard itself could not establish
a trustworthy reading, which is also a stop. Checks are appended to
`usage_checks.jsonl`; `shift_state.json`, `usage_start.json`, and
`usage_end.json` provide the end-to-end tally. If UTC midnight interrupts a
shift, `finish` explicitly re-reads the archived quota day rather than mixing
the new day’s cumulative total with the old baseline.

The guard covers both provider-capable durable queues: Retrograde maturation
and experience rendering. Queued or leased work returns `pending` without
moving the usage watermark. `job_requeued:<queue>:<id>` stops the shift when a
re-queued job exceeds the configured normal lease count (a leased retry stays
pending until its call settles); inspect its
reported `last_error` before continuing.

Normal model-generating probes run one public command between checks. A bounded
concurrency probe may launch at most two public requests from one recorded shell
invocation, wait for both, and reconcile their complete request-group delta in
one post-check. Detached requests and process termination with an unaccounted
provider response remain outside the safe boundary.

The usage delta is also the authoritative rejection ledger. `finish` writes
`rejection_ledger.json` with every current-run QA-slot
`rejected_validation` attempt, exact rejected tokens, repair-tax percentage,
seat subtotals, and the `skald_writer` tripwire. Teardown enriches it with
validation classes from only the current gateway process's log slice. A
recovered retry still represents real cost and latency; a novel class must still
meet the normal repeatability standard before publication.

`finish` also writes `bleed_uptake.json` with the cumulative-counter deltas for
offered and exact-name-used resolutions plus the uptake rate between the
shift's start and finish snapshots.

The repair-tax percentage is unavailable when final OpenAI usage is unknown or
a rejection came from an unexpected provider, because those events do not share
a trustworthy OpenAI denominator. Preserve the attempts and token evidence, and
report the helper's explicit unavailability reasons instead of estimating.

## Safety Boundary

The configured lane is disposable slot 4 on port 8012. The mission prompt
forbids touching the normal port-8002 runtime, changing tracked source, or
filing anything weaker than a reproduced and deduplicated issue. A pre-shift
database dump is retained because the final QA state is intentionally left
available for diagnosis.

## Reference Corpora and Prose Metrics

[reference_corpora.toml](reference_corpora.toml) distinguishes `human_play`
(`save_01`, taste calibration), `codex_bakeoff` (the locked July regression
artifact), and `codex_qa` (`save_04`, historically contaminated adversarial QA).
Live-slot entries record an observation, not a permanent snapshot; their source
artifact SHA and restore date are explicitly not applicable. Each JSON baseline
also hashes the actual SELECT result, records current migration stamps, and
embeds its config and manifest entry. The dump itself is not committed.

```sh
PYTHONPATH=$PWD "$PY" scripts/qa_shift/prose_metrics.py --slot 1 --output human.json
PYTHONPATH=$PWD "$PY" scripts/qa_shift/prose_metrics.py --dbname ref_codex_bakeoff_2026_07 --output july.json
PYTHONPATH=$PWD "$PY" scripts/qa_shift/prose_metrics.py --slot 4 --from-chunk 20 --to-chunk 40
PYTHONPATH=$PWD "$PY" scripts/qa_shift/prose_metrics.py --compare human.json july.json
```

`$PY` is the environment's Python interpreter. JSON goes to stdout unless
`--output` is supplied; the readable table goes to stderr. Comparison prints
B minus A and rejects differing configs/schema versions. The tool accepts
`save_NN`, `qa640_*`, and `ref_*`, opens a repeatable-read transaction with
`default_transaction_read_only=on`, and issues SELECT statements only. It uses
the same synthetic-prologue exclusion as player-facing readers and orders by
chunk ID, preserving gaps. Bounds are inclusive chunk IDs. No slot is migrated.

All lexical lists, thresholds, and text-analysis patterns live in
`qa_shift.toml` under `[prose_metrics]`, validated by `ProseMetricsSettings`.
The [2026-09-23 baselines](baselines/2026-09-23/) use these definitions:

- Closers use the last nonempty narrative line after Markdown decoration is
  removed; question rate ends literally in `?`. The narrower rate matches
  `What do you ... ?`. Quotation marks after a question remain significant.
- Contraction ratio measures **negative** contractions (`n't`/`n’t`) divided by
  contractions plus configured expanded negations. It does not measure all
  apostrophes or confuse possessive `'s` with a contraction. Formal counts and
  `It is not X.` occurrences are also retained.
- Words are Unicode alphabetic tokens with internal apostrophes. Paragraphs
  split at blank lines; sentence segmentation is punctuation-based, so labels,
  fragments, abbreviations, and dialogue are not linguistic ground truth.
  Word-count SD is population SD. Motifs are case-folded 3–5-grams counted once
  per chunk, with every motif reaching K chunks reported (no hidden top-N cap).
- Modern choices come from `choice_object.presented`; `choice_text` is the
  selected player turn and is counted separately. First-verb mix is the first
  lexical token as a proxy for imperative verbs, not a part-of-speech model.
  Speech-act and place/time/company change shares are keyword heuristics, not
  claims about what the choice actually caused.
- `save_01` uses read-only `## Storyteller` / `## You` extraction. Observed
  storyteller-only, player-only, and trailing-space headings are supported;
  unknown or duplicate sections fail. Player-only chunks 686 and 1383 are
  reported explicitly and excluded from prose denominators. The final
  sequential decimal/keycap list is a **legacy menu heuristic**, with coverage
  reported separately; prose may itself contain numbered lists. Only option
  lines are recovered. Chunks without such a list have N/A menu statistics,
  never a fabricated zero-choice menu. Narrative measurements retain the full
  Storyteller section, including embedded lists/headings, unlike modern prose
  stored separately from choices. Cross-tier comparisons carry that limitation.
- Exactly one `setting` link identifies a primary place. Missing or multiple
  setting links break the streak and are counted, rather than picking an
  arbitrary place or carrying one forward. World-minute deltas use adjacent
  playable chunks with both timestamps present; missing pairs and negative
  deltas remain explicit.

To reconstruct the locked July reference, verify the manifest SHA against the
sidecar, `createdb ref_codex_bakeoff_2026_07`, restore with
`pg_restore --exit-on-error --no-owner --no-privileges`, then use
`scripts/migrate.py --dbname ref_codex_bakeoff_2026_07` and
`scripts/stamp_lore_pass_baseline.py --dbname ref_codex_bakeoff_2026_07` before
`ALTER DATABASE ref_codex_bakeoff_2026_07 SET default_transaction_read_only = on`.
Both mutation tools restrict `--dbname` to `qa640_*` or `ref_*`; this is separate
from their existing slot flags. Do not point replay-test write fixtures at the
locked reference. The September restoration reached 112 stamps through 114.
