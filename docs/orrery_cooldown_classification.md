# Orrery Cooldown Classification and Calibration

Date: 2026-10-01. Refs #778; frozen order 778-S4a (778-R8).
Measurement implementation: `1d59a5a4` on `origin/main` `36ec0b26`.
The reports were captured before that rebase using exactly the same script,
templates, shared fixture, and added tests (byte equality verified afterward).
The original `748f1e6d` implementation patch is retained exactly as `08961673`
after the required rebase; it was neither squashed nor amended.

## Doctrine and Scope

778-Q1 binds verbatim: **D. Refractories to hours, staggering stays on ticks**.
Its basis binds verbatim: **The two-clocks ruling draws the line; hour values
are nexus.toml tunables calibrated on the reference corpus (778-S4a).**
778-Q6 binds verbatim: **C. Per named gate**.

Diegetic cooldowns belong on the world clock. Ordering, replay, exposure
fairness, habituation, and narration cadence retain ticks. These clock rules
are settled. Each individual classification and each measured equivalent below
is an analytical proposal; this slice adopts no hour policy and changes no
product behavior. Slot 2 is excluded as contaminated evidence.

There are 64 occurrences: 44 `since_last_event_at_least`, six
`count_recent_events_at_least`, one `knows_recent_event`, and 13 `recent_event`.
The runtime traversal and independent AST census agree on the arguments and
source locations. Gate names preserve the package/branch scope, each compound
child index (including NOT and OR), and `root` for a bare predicate. Equal
predicates are not deduplicated.

The six proposed `turn-cadenced` gates are `train/package_gate/3`,
`run_errands/package_gate/2`, `stroll/package_gate/1`, `upkeep/package_gate/1`,
`recreate/package_gate/2`, and `mourn_loss/package_gate/2`. The mundane checks
follow the anti-monoculture comment at `templates.py:3806`. The grief-completion
interpretation explicitly follows the pacing comment at `templates.py:1564`;
it does not classify every mourning check as cadence. The other 58 occurrences
are proposed `diegetic`: refractory, accumulation, or event-recency checks.
Event recency is not narration cadence. A package check and branch check keep
separate gate names even when their `(template, event)` pair is identical.

## Current Behavior and Source Evidence

Paths abbreviated as `templates.py`, `substrate.py`, and `resolver.py` below
are under `nexus/agents/orrery/`. These source positions were verified against
the measured checkout, not taken as current merely from the mapper snapshot.

- `templates.py:236` begins the hide refractory checks. The relocation
  inventory includes the nested windows at `templates.py:4372` and `:4382`.
- `substrate.py:2398` treats absent matching history as an expired cooldown;
  `:2400` compares chunk ticks. Recent-event cutoffs use ticks at `:2257` and
  `:2435`; `:2420` explains the hydration-window limitation.
- `resolver.py:2849` computes the lower chunk-ID bound and `:2865` filters
  event history by chunk ID. `nexus.toml:336` sets a 30-chunk window.
  `EventRecord` at `substrate.py:319` has a tick and no occurrence-time field.
- `templates.py:720` explains actor-global refractories; `:1305` explains
  actor-target cooldowns; `:3806` explains mundane staggering; `:1564`
  explains back-to-back grief-completion pacing. These purposes stay distinct.
- `migrations/023_orrery_schema.py:734` sums durations over all layers, using
  input at `:738` without a layer filter. `migrations/118_world_clock_identity.sql:2`
  preserves those trigger semantics and `:19` identifies the canonical stored
  end-of-chunk clock. This is historical behavior retained by the reference.
- Migration 140 is already fleet-wide per the coordinator. Its primary-layer
  filter is `migrations/140_world_clock_primary_layer.sql:117`; its current
  clock comments are at `:159` and `:162`. The measured save_04 clone is at 140.
  The reference remains at 114 and is never upgraded here.
- `scripts/qa_shift/prose_metrics.py:327` provides the read-only pattern;
  `:341` refuses an unprotected transaction. The new helper additionally
  verifies isolation and database identity and preserves ambient PGOPTIONS.
- `migrations/023_orrery_schema.py:558` and `:559` define the stored resolution
  tick and package identifier used for counts; no resolver or provider runs.
- `scripts/qa_shift/reference_corpora.toml:18` identifies the restored reference;
  `:24`, `:26`, and `:27` record level 114, 111 chunks, and its read-only status.
  `docs/reachability.md:89` requires sorted, unique path classification; this
  operator has both the operator root and its classification registration.

## Measurement and Formulas

The script uses `nexus.database.connection_kwargs`, appending read-only and
repeatable-read options after ambient PGOPTIONS so protection wins. Before any
corpus SELECT it verifies `current_database()`, `transaction_read_only = on`,
and `transaction_isolation = repeatable read`. All six script-issued SQL
statements are SELECTs. Target validation rejects save_02 and unapproved names
before connecting. Logging is configured only on the CLI path.

Primary rows are `chunk_metadata WHERE world_layer = 'primary' ORDER BY chunk_id`.
No `narrative_view.world_time`, recording timestamp, or `now()` is substituted.
For adjacent primary rows i and i+1:

- `gap_i = chunk_id_(i+1) - chunk_id_i > 0`.
- `hours_i = (stored_world_time_(i+1) - stored_world_time_i) / one hour >= 0`.
- `rate_i = hours_i / gap_i`.
- Weighted hours/tick = `sum(hours_i) / sum(gap_i)`.
- Median hours/tick = `median(rate_i)` (including zero deltas).
- Each gate's reference-cadence equivalents = its tick value multiplied by
  the weighted rate and the median rate, respectively. These are not policy values.

The ordinary mean and median of pair hours are also reported. Primary count,
NULL-duration count, and duration sum exclude all non-primary rows. The stored
clock span and pair deltas preserve any intervening non-primary duration
already embedded by the old all-layer trigger. We never subtract that
contribution or reconstruct a primary-only clock. NULL primary clocks, reversed
clocks, non-positive gaps, and fewer than two primary rows fail loudly.

## Mapper Baselines and Measured Results

| Quantity | Mapper Baseline | Reference Measurement | save_04 Clone Measurement |
| --- | --- | --- | --- |
| Migration level / stamp count | 114 / not supplied | 114 / 112 | 140 / 137 |
| All narrative chunks | 111 | 111 | 46 |
| Primary metadata rows | 110 | 110 | 45 |
| Primary duration sum | 14:37:00 | 14:37:00 | 03:25:00 |
| Stored primary clock span | not supplied | 14:37:00 | 03:25:00 |
| Median adjacent primary interval | 00:06:00 | 00:06:00 | 00:04:00 |
| Adjacent pairs / total tick gaps | not supplied | 109 / 141 | 44 / 47 |
| NULL primary durations / zero pair deltas | not supplied | 4 / 4 | 0 / 0 |
| Weighted hours per tick | not supplied | 0.10366430260047281 | 0.0726950354609929 |
| Median pair hours per tick | not supplied | 0.1 | 0.06666666666666667 |
| Stored resolution rows / distinct ticks | 448 / 85 | 448 / 85 | 103 / 26 |
| Resolution rows without primary metadata | not supplied | 0 | 0 |
| Unknown historical package identifiers | not supplied | none | none |

Every supplied mapper baseline is reproduced; there is no unexplained baseline
difference. The 111 total chunks versus 110 primary rows have different
populations: a supplemental read-only SELECT found the one non-primary row,
retrograde chunk 1 with zero duration. The first primary row, chunk 6, also
has zero duration. Thus this reference's primary duration sum equals its
stored-clock span even though the inherited trigger semantics allow all-layer
contamination. No non-primary duration has been subtracted. The new weighted
rate differs from the six-minute median because it divides total pair time by
141 actual chunk-ID ticks rather than treating 109 pairs as single ticks.
Migration level is the maximum version, not a count of migration stamps.
The clone is a different story snapshot and schema generation, not a mapper
baseline revision, so its shorter span and lower counts are not discrepancies.

## Limitations and Handoff

The reference inherits all-layer clock contamination semantics at migration
114. Its zero-duration retrograde row does not erase that methodological
limitation. The equivalents require remeasurement after the primary-layer
trigger repair in 778-S1b reaches the reference; this order neither upgrades
nor unlocks it. The save_04 clone already has migration 140's primary-only
clocks. It is a TEST-pinned fixture snapshot, not an untouched historical
reference and not an hour-policy recommendation. Live save_04 was read only by
pg_dump; fixture pinning, migration, and cleanup affected only the disposable
clone. The clone was dropped and catalog verification found no remaining
`qa640_778s4a_*` databases.

Stored resolution counts are not predicate evaluations, counterfactual
firings, or actor-specific cooldown evidence. Current packages with no rows
remain visible; unknown historical identifiers have a separate list. No paid
calls occurred. No gateway was started.

This document is calibration evidence, not a replacement for authoritative
PostgreSQL clock comments. S4b owns named hour policies; S4c owns predicate and
template conversion; hydration, chronology, Backstage, and other #778 slices
remain out of scope. Landing: **no migration, no restart, no UI rebuild**.
The coordinator posts the report on #778. There are no open coordinator
questions; Q1 and Q6 are not reopened.

## Complete Reports and Proposed Gate Tables

The following are the full CLI reports, retaining every field and the complete
sorted gate and firing tables. Each gate row includes its source evidence,
proposed class, purpose, scopes, and both measured equivalents. Machine field
names in the raw CLI tables are preserved verbatim.

## Reference Report

```sh
PYTHONPATH=$PWD $PY scripts/qa_shift/cooldown_calibration.py --dbname ref_codex_bakeoff_2026_07 --format markdown
```

# Cooldown Calibration

## header

| Field | Value |
| --- | --- |
| database | "ref_codex_bakeoff_2026_07" |
| migration_count | 112 |
| migration_level | "114" |
| transaction_read_only | "on" |
| transaction_isolation | "repeatable read" |
| total_chunks | 111 |
| classification_status | "Analytical proposals under settled Q1; no policy adopted." |
| clock_basis | "Inherited all-layer clock contamination: stored primary clocks retain intervening non-primary durations." |
| limitation | "Reference stays at migration 114 with inherited all-layer contamination; its reference-cadence equivalents retain that contamination. Slots are already repaired (migration 140). Reference equivalents require remeasurement after the primary-layer trigger repair in 778-S1b reaches that corpus. Never reconstruct or subtract from stored clocks. Primary-only duration sums differ conceptually from stored-clock span and cadence. Equivalents are measurements, not hour policy values." |
| firing_basis | "Stored resolution counts, not predicate evaluations or counterfactual firings; no actor-specific inference." |

## cadence

| Field | Value |
| --- | --- |
| first_clock_utc | "2042-08-17T22:13:00+00:00" |
| last_clock_utc | "2042-08-18T12:50:00+00:00" |
| primary_chunks | 110 |
| primary_duration_hours | 14.616666666666667 |
| null_primary_durations | 4 |
| world_clock_span_hours | 14.616666666666667 |
| adjacent_pairs | 109 |
| total_tick_gaps | 141 |
| zero_deltas | 4 |
| mean_pair_hours | 0.13409785932721713 |
| median_pair_hours | 0.1 |
| weighted_hours_per_tick | 0.10366430260047281 |
| median_pair_hours_per_tick | 0.1 |

## pairs

| from_chunk | to_chunk | tick_gap | world_hours | hours_per_tick |
| --- | --- | --- | --- | --- |
| 6 | 7 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 7 | 8 | 1 | 0.05 | 0.05 |
| 8 | 13 | 5 | 0.03333333333333333 | 0.006666666666666666 |
| 13 | 16 | 3 | 0.05 | 0.016666666666666666 |
| 16 | 21 | 5 | 0.06666666666666667 | 0.013333333333333332 |
| 21 | 22 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 22 | 23 | 1 | 0.05 | 0.05 |
| 23 | 24 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 24 | 25 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 25 | 26 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 26 | 27 | 1 | 0.05 | 0.05 |
| 27 | 28 | 1 | 0.1 | 0.1 |
| 28 | 29 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 29 | 30 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 30 | 31 | 1 | 0.1 | 0.1 |
| 31 | 32 | 1 | 0.016666666666666666 | 0.016666666666666666 |
| 32 | 33 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 33 | 34 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 34 | 35 | 1 | 0.1 | 0.1 |
| 35 | 36 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 36 | 37 | 1 | 0.05 | 0.05 |
| 37 | 38 | 1 | 2.0 | 2.0 |
| 38 | 39 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 39 | 40 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 40 | 41 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 41 | 42 | 1 | 0.3 | 0.3 |
| 42 | 43 | 1 | 0.1 | 0.1 |
| 43 | 47 | 4 | 0.2 | 0.05 |
| 47 | 48 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 48 | 49 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 49 | 50 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 50 | 51 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 51 | 55 | 4 | 0.06666666666666667 | 0.016666666666666666 |
| 55 | 56 | 1 | 0.23333333333333334 | 0.23333333333333334 |
| 56 | 57 | 1 | 0.2833333333333333 | 0.2833333333333333 |
| 57 | 58 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 58 | 59 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 59 | 60 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 60 | 61 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 61 | 62 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 62 | 63 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 63 | 64 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 64 | 65 | 1 | 0.05 | 0.05 |
| 65 | 66 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 66 | 67 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 67 | 68 | 1 | 0.0 | 0.0 |
| 68 | 69 | 1 | 0.0 | 0.0 |
| 69 | 70 | 1 | 0.0 | 0.0 |
| 70 | 75 | 5 | 0.0 | 0.0 |
| 75 | 78 | 3 | 0.36666666666666664 | 0.12222222222222222 |
| 78 | 79 | 1 | 0.23333333333333334 | 0.23333333333333334 |
| 79 | 80 | 1 | 0.3 | 0.3 |
| 80 | 81 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 81 | 82 | 1 | 0.3 | 0.3 |
| 82 | 83 | 1 | 0.3 | 0.3 |
| 83 | 84 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 84 | 85 | 1 | 0.05 | 0.05 |
| 85 | 86 | 1 | 0.016666666666666666 | 0.016666666666666666 |
| 86 | 87 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 87 | 88 | 1 | 0.1 | 0.1 |
| 88 | 89 | 1 | 0.05 | 0.05 |
| 89 | 90 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 90 | 91 | 1 | 0.05 | 0.05 |
| 91 | 92 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 92 | 93 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 93 | 94 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 94 | 99 | 5 | 0.1 | 0.02 |
| 99 | 100 | 1 | 0.3 | 0.3 |
| 100 | 101 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 101 | 102 | 1 | 0.05 | 0.05 |
| 102 | 103 | 1 | 0.1 | 0.1 |
| 103 | 104 | 1 | 0.1 | 0.1 |
| 104 | 105 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 105 | 106 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 106 | 107 | 1 | 0.23333333333333334 | 0.23333333333333334 |
| 107 | 108 | 1 | 0.3 | 0.3 |
| 108 | 109 | 1 | 0.3 | 0.3 |
| 109 | 114 | 5 | 0.13333333333333333 | 0.026666666666666665 |
| 114 | 115 | 1 | 0.36666666666666664 | 0.36666666666666664 |
| 115 | 116 | 1 | 0.15 | 0.15 |
| 116 | 117 | 1 | 0.1 | 0.1 |
| 117 | 118 | 1 | 0.3 | 0.3 |
| 118 | 119 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 119 | 120 | 1 | 0.18333333333333332 | 0.18333333333333332 |
| 120 | 121 | 1 | 0.05 | 0.05 |
| 121 | 122 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 122 | 123 | 1 | 0.05 | 0.05 |
| 123 | 124 | 1 | 0.23333333333333334 | 0.23333333333333334 |
| 124 | 125 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 125 | 126 | 1 | 0.1 | 0.1 |
| 126 | 127 | 1 | 0.1 | 0.1 |
| 127 | 128 | 1 | 0.18333333333333332 | 0.18333333333333332 |
| 128 | 129 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 129 | 130 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 130 | 131 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 131 | 132 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 132 | 133 | 1 | 0.18333333333333332 | 0.18333333333333332 |
| 133 | 134 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 134 | 137 | 3 | 0.1 | 0.03333333333333333 |
| 137 | 138 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 138 | 139 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 139 | 140 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 140 | 141 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 141 | 142 | 1 | 0.23333333333333334 | 0.23333333333333334 |
| 142 | 143 | 1 | 0.05 | 0.05 |
| 143 | 144 | 1 | 0.05 | 0.05 |
| 144 | 145 | 1 | 0.1 | 0.1 |
| 145 | 146 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 146 | 147 | 1 | 0.05 | 0.05 |

## gates

| gate_name | template_id | scope | branch_label | predicate | event_type | tick_parameter | ticks | minimum_count | actor_scope | target_scope | knower_scope | changed_fields_any_of | source_line | classification | purpose | evidence | weighted_equivalent_hours | median_equivalent_hours |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| "act_on_intel/package_gate/0" | "act_on_intel" | "package_gate" | null | "count_recent_events_at_least" | "surveillance_performed" | "within_ticks" | 25 | 3 | "actor" | "target" | null | [] | 1215 | "diegetic" | "Accumulate surveillance_performed occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:1215" | 2.59160756501182 | 2.5 |
| "act_on_intel/package_gate/1" | "act_on_intel" | "package_gate" | null | "since_last_event_at_least" | "intel_acted_on" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 1221 | "diegetic" | "Refractory period for actor-target intel_acted_on recurrence." | "nexus/agents/orrery/templates.py:1221" | 1.2439716312056737 | 1.2000000000000002 |
| "check_on_dependent/branches[0].conditions/1" | "check_on_dependent" | "branches[0].conditions" | "Drop by in person when the moment allows" | "since_last_event_at_least" | "welfare_check" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 2663 | "diegetic" | "Refractory period for actor-target welfare_check recurrence." | "nexus/agents/orrery/templates.py:2663" | 0.6219858156028368 | 0.6000000000000001 |
| "check_on_dependent/package_gate/2" | "check_on_dependent" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 2649 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2649" | 1.2439716312056737 | 1.2000000000000002 |
| "check_on_dependent/package_gate/3" | "check_on_dependent" | "package_gate" | null | "since_last_event_at_least" | "welfare_check" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 2652 | "diegetic" | "Refractory period for actor-target welfare_check recurrence." | "nexus/agents/orrery/templates.py:2652" | 1.2439716312056737 | 1.2000000000000002 |
| "consult_rival/package_gate/1/0" | "consult_rival" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 10 | null | null | null | null | [] | 2873 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2873" | 1.0366430260047281 | 1.0 |
| "consult_rival/package_gate/1/1" | "consult_rival" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 10 | null | null | null | null | [] | 2874 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2874" | 1.0366430260047281 | 1.0 |
| "consult_rival/package_gate/1/2" | "consult_rival" | "package_gate" | null | "recent_event" | "faction_realignment" | "within_ticks" | 15 | null | null | null | null | [] | 2875 | "diegetic" | "Event-recency window for faction_realignment under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2875" | 1.554964539007092 | 1.5 |
| "consult_rival/package_gate/2" | "consult_rival" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 20 | null | "actor" | "target" | null | [] | 2877 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2877" | 2.0732860520094563 | 2.0 |
| "consult_rival/package_gate/3" | "consult_rival" | "package_gate" | null | "since_last_event_at_least" | "rival_consulted" | "minimum_ticks" | 20 | null | "actor" | "target" | null | [] | 2880 | "diegetic" | "Refractory period for actor-target rival_consulted recurrence." | "nexus/agents/orrery/templates.py:2880" | 2.0732860520094563 | 2.0 |
| "cultivate_informant/branches[0].conditions/2" | "cultivate_informant" | "branches[0].conditions" | "Press for material intel when trust is sufficient" | "since_last_event_at_least" | "intel_acquired" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1337 | "diegetic" | "Refractory period for actor-target intel_acquired recurrence." | "nexus/agents/orrery/templates.py:1337" | 0.6219858156028368 | 0.6000000000000001 |
| "cultivate_informant/package_gate/2" | "cultivate_informant" | "package_gate" | null | "since_last_event_at_least" | "informant_contact" | "minimum_ticks" | 4 | null | "actor" | "target" | null | [] | 1317 | "diegetic" | "Refractory period for actor-target informant_contact recurrence." | "nexus/agents/orrery/templates.py:1317" | 0.41465721040189124 | 0.4 |
| "cultivate_informant/package_gate/3" | "cultivate_informant" | "package_gate" | null | "since_last_event_at_least" | "intel_acquired" | "minimum_ticks" | 4 | null | "actor" | "target" | null | [] | 1322 | "diegetic" | "Refractory period for actor-target intel_acquired recurrence." | "nexus/agents/orrery/templates.py:1322" | 0.41465721040189124 | 0.4 |
| "evade_pursuers/package_gate/0/1" | "evade_pursuers" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 5 | null | null | "actor" | null | [] | 134 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:134" | 0.5183215130023641 | 0.5 |
| "extract_vengeance/branches[0].conditions/2" | "extract_vengeance" | "branches[0].conditions" | "Let the hunt go cold" | "since_last_event_at_least" | "hunt_declared" | "minimum_ticks" | 18 | null | "actor" | "target" | null | [] | 754 | "diegetic" | "Refractory period for actor-target hunt_declared recurrence." | "nexus/agents/orrery/templates.py:754" | 1.8659574468085105 | 1.8 |
| "extract_vengeance/package_gate/2" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "retaliation_attempted" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 734 | "diegetic" | "Refractory period for actor-global retaliation_attempted recurrence." | "nexus/agents/orrery/templates.py:734" | 0.8293144208037825 | 0.8 |
| "extract_vengeance/package_gate/3" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "retaliation_executed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 735 | "diegetic" | "Refractory period for actor-global retaliation_executed recurrence." | "nexus/agents/orrery/templates.py:735" | 0.8293144208037825 | 0.8 |
| "extract_vengeance/package_gate/4" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "hunt_declared" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 736 | "diegetic" | "Refractory period for actor-global hunt_declared recurrence." | "nexus/agents/orrery/templates.py:736" | 0.8293144208037825 | 0.8 |
| "extract_vengeance/package_gate/5" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "hunt_called_off" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 737 | "diegetic" | "Refractory period for actor-global hunt_called_off recurrence." | "nexus/agents/orrery/templates.py:737" | 0.8293144208037825 | 0.8 |
| "hide/branches[5].conditions/1" | "hide" | "branches[5].conditions" | "Run a counter-surveillance sweep" | "recent_event" | "compliance_alert" | "within_ticks" | 8 | null | null | "actor" | null | [] | 366 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:366" | 0.8293144208037825 | 0.8 |
| "hide/package_gate/4" | "hide" | "package_gate" | null | "since_last_event_at_least" | "hideout_maintained" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 236 | "diegetic" | "Refractory period for actor-global hideout_maintained recurrence." | "nexus/agents/orrery/templates.py:236" | 0.6219858156028368 | 0.6000000000000001 |
| "hide/package_gate/5" | "hide" | "package_gate" | null | "since_last_event_at_least" | "signal_exposure_reduced" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 237 | "diegetic" | "Refractory period for actor-global signal_exposure_reduced recurrence." | "nexus/agents/orrery/templates.py:237" | 0.6219858156028368 | 0.6000000000000001 |
| "hide/package_gate/6" | "hide" | "package_gate" | null | "since_last_event_at_least" | "counter_surveillance_sweep" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 238 | "diegetic" | "Refractory period for actor-global counter_surveillance_sweep recurrence." | "nexus/agents/orrery/templates.py:238" | 0.6219858156028368 | 0.6000000000000001 |
| "honor_debt/package_gate/1" | "honor_debt" | "package_gate" | null | "recent_event" | "encoded_message" | "within_ticks" | 3 | null | null | "actor" | null | [] | 437 | "diegetic" | "Event-recency window for encoded_message under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:437" | 0.3109929078014184 | 0.30000000000000004 |
| "intimacy/package_gate/2" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_fulfilled" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3655 | "diegetic" | "Refractory period for actor-global intimacy_fulfilled recurrence." | "nexus/agents/orrery/templates.py:3655" | 0.8293144208037825 | 0.8 |
| "intimacy/package_gate/3" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_pursued" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3656 | "diegetic" | "Refractory period for actor-global intimacy_pursued recurrence." | "nexus/agents/orrery/templates.py:3656" | 0.8293144208037825 | 0.8 |
| "intimacy/package_gate/4" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_partial" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3657 | "diegetic" | "Refractory period for actor-global intimacy_partial recurrence." | "nexus/agents/orrery/templates.py:3657" | 0.8293144208037825 | 0.8 |
| "intimacy/package_gate/5" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_deferred" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3658 | "diegetic" | "Refractory period for actor-global intimacy_deferred recurrence." | "nexus/agents/orrery/templates.py:3658" | 0.8293144208037825 | 0.8 |
| "keep_vigil/package_gate/3" | "keep_vigil" | "package_gate" | null | "since_last_event_at_least" | "vigil_held" | "minimum_ticks" | 2 | null | "actor" | null | null | [] | 1708 | "diegetic" | "Refractory period for actor-global vigil_held recurrence." | "nexus/agents/orrery/templates.py:1708" | 0.20732860520094562 | 0.2 |
| "maintain_cover/package_gate/6" | "maintain_cover" | "package_gate" | null | "since_last_event_at_least" | "maintain_cover" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 581 | "diegetic" | "Refractory period for actor-global maintain_cover recurrence." | "nexus/agents/orrery/templates.py:581" | 0.6219858156028368 | 0.6000000000000001 |
| "mourn_loss/branches[0].conditions/root" | "mourn_loss" | "branches[0].conditions" | "Lay the grief down" | "count_recent_events_at_least" | "mourning_act" | "within_ticks" | 30 | 4 | "actor" | null | null | [] | 1584 | "diegetic" | "Accumulate mourning_act occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:1584" | 3.109929078014184 | 3.0 |
| "mourn_loss/package_gate/1" | "mourn_loss" | "package_gate" | null | "since_last_event_at_least" | "mourning_act" | "minimum_ticks" | 3 | null | "actor" | null | null | [] | 1569 | "diegetic" | "Refractory period for actor-global mourning_act recurrence." | "nexus/agents/orrery/templates.py:1569" | 0.3109929078014184 | 0.30000000000000004 |
| "mourn_loss/package_gate/2" | "mourn_loss" | "package_gate" | null | "since_last_event_at_least" | "mourning_completed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 1570 | "turn-cadenced" | "Proposed grief-completion pacing, based explicitly on the pacing comment." | "nexus/agents/orrery/templates.py:1570; nexus/agents/orrery/templates.py:1564" | 0.8293144208037825 | 0.8 |
| "protect_kin/package_gate/1/2" | "protect_kin" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 4 | null | null | "target" | null | [] | 912 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:912" | 0.41465721040189124 | 0.4 |
| "reach_out/branches[0].conditions/3" | "reach_out" | "branches[0].conditions" | "Find the moment for a real face-to-face conversation" | "since_last_event_at_least" | "kin_visit" | "minimum_ticks" | 5 | null | "actor" | "target" | null | [] | 2759 | "diegetic" | "Refractory period for actor-target kin_visit recurrence." | "nexus/agents/orrery/templates.py:2759" | 0.5183215130023641 | 0.5 |
| "reach_out/package_gate/2" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2740 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2740" | 0.8293144208037825 | 0.8 |
| "reach_out/package_gate/3" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "kin_visit" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2743 | "diegetic" | "Refractory period for actor-target kin_visit recurrence." | "nexus/agents/orrery/templates.py:2743" | 0.8293144208037825 | 0.8 |
| "reach_out/package_gate/4" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "contact_deferred" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2746 | "diegetic" | "Refractory period for actor-target contact_deferred recurrence." | "nexus/agents/orrery/templates.py:2746" | 0.8293144208037825 | 0.8 |
| "recreate/package_gate/2" | "recreate" | "package_gate" | null | "since_last_event_at_least" | "recreation_taken" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 4218 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4218; nexus/agents/orrery/templates.py:3806" | 0.6219858156028368 | 0.6000000000000001 |
| "run_errands/package_gate/2" | "run_errands" | "package_gate" | null | "since_last_event_at_least" | "errands_run" | "minimum_ticks" | 9 | null | "actor" | null | null | [] | 3950 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:3950; nexus/agents/orrery/templates.py:3806" | 0.9329787234042553 | 0.9 |
| "socialize/package_gate/1" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "socialized" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3392 | "diegetic" | "Refractory period for actor-global socialized recurrence." | "nexus/agents/orrery/templates.py:3392" | 0.41465721040189124 | 0.4 |
| "socialize/package_gate/2" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "socialized_alone" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3393 | "diegetic" | "Refractory period for actor-global socialized_alone recurrence." | "nexus/agents/orrery/templates.py:3393" | 0.41465721040189124 | 0.4 |
| "socialize/package_gate/3" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "social_travel_departed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3394 | "diegetic" | "Refractory period for actor-global social_travel_departed recurrence." | "nexus/agents/orrery/templates.py:3394" | 0.41465721040189124 | 0.4 |
| "start_relocation_plan/package_gate/5/0" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "upkeep_done" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4372 | "diegetic" | "Accumulate upkeep_done occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4372" | 3.109929078014184 | 3.0 |
| "start_relocation_plan/package_gate/5/1" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "errands_run" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4373 | "diegetic" | "Accumulate errands_run occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4373" | 3.109929078014184 | 3.0 |
| "start_relocation_plan/package_gate/5/2" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "recreation_taken" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4374 | "diegetic" | "Accumulate recreation_taken occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4374" | 3.109929078014184 | 3.0 |
| "start_relocation_plan/package_gate/5/3" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "work_performed" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4377 | "diegetic" | "Accumulate work_performed occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4377" | 3.109929078014184 | 3.0 |
| "start_relocation_plan/package_gate/6/0" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "travel_delayed" | "within_ticks" | 12 | null | "actor" | null | null | [] | 4382 | "diegetic" | "Event-recency window for travel_delayed under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4382" | 1.2439716312056737 | 1.2000000000000002 |
| "start_relocation_plan/package_gate/6/1" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "contact_deferred" | "within_ticks" | 12 | null | "actor" | null | null | [] | 4383 | "diegetic" | "Event-recency window for contact_deferred under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4383" | 1.2439716312056737 | 1.2000000000000002 |
| "start_relocation_plan/package_gate/6/2" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 12 | null | null | "actor" | null | [] | 4384 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4384" | 1.2439716312056737 | 1.2000000000000002 |
| "start_relocation_plan/package_gate/6/3" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "retaliation_attempted" | "within_ticks" | 12 | null | null | "actor" | null | [] | 4385 | "diegetic" | "Event-recency window for retaliation_attempted under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4385" | 1.2439716312056737 | 1.2000000000000002 |
| "stroll/package_gate/1" | "stroll" | "package_gate" | null | "since_last_event_at_least" | "stroll_taken" | "minimum_ticks" | 5 | null | "actor" | null | null | [] | 4034 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4034; nexus/agents/orrery/templates.py:3806" | 0.5183215130023641 | 0.5 |
| "surveil/package_gate/10" | "surveil" | "package_gate" | null | "since_last_event_at_least" | "surveillance_performed" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1054 | "diegetic" | "Refractory period for actor-target surveillance_performed recurrence." | "nexus/agents/orrery/templates.py:1054" | 0.6219858156028368 | 0.6000000000000001 |
| "surveil/package_gate/11" | "surveil" | "package_gate" | null | "since_last_event_at_least" | "intel_reviewed" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1057 | "diegetic" | "Refractory period for actor-target intel_reviewed recurrence." | "nexus/agents/orrery/templates.py:1057" | 0.6219858156028368 | 0.6000000000000001 |
| "surveil/package_gate/9/7" | "surveil" | "package_gate" | null | "knows_recent_event" | "threat_issued" | "within_ticks" | 8 | null | null | "target" | "actor" | [] | 1050 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:1050" | 0.8293144208037825 | 0.8 |
| "tend_craft/package_gate/1" | "tend_craft" | "package_gate" | null | "since_last_event_at_least" | "craft_tended" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2311 | "diegetic" | "Refractory period for actor-global craft_tended recurrence." | "nexus/agents/orrery/templates.py:2311" | 0.41465721040189124 | 0.4 |
| "tend_wounded/package_gate/4" | "tend_wounded" | "package_gate" | null | "since_last_event_at_least" | "tended_wound" | "minimum_ticks" | 2 | null | "actor" | "target" | null | [] | 1460 | "diegetic" | "Refractory period for actor-target tended_wound recurrence." | "nexus/agents/orrery/templates.py:1460" | 0.20732860520094562 | 0.2 |
| "tend_wounded/package_gate/5" | "tend_wounded" | "package_gate" | null | "since_last_event_at_least" | "wound_healed" | "minimum_ticks" | 2 | null | "actor" | "target" | null | [] | 1463 | "diegetic" | "Refractory period for actor-target wound_healed recurrence." | "nexus/agents/orrery/templates.py:1463" | 0.20732860520094562 | 0.2 |
| "train/package_gate/3" | "train" | "package_gate" | null | "since_last_event_at_least" | "training_performed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3852 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:3852; nexus/agents/orrery/templates.py:3806" | 0.8293144208037825 | 0.8 |
| "upkeep/package_gate/1" | "upkeep" | "package_gate" | null | "since_last_event_at_least" | "upkeep_done" | "minimum_ticks" | 7 | null | "actor" | null | null | [] | 4121 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4121; nexus/agents/orrery/templates.py:3806" | 0.7256501182033097 | 0.7000000000000001 |
| "warn_ally/package_gate/1/0" | "warn_ally" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 3 | null | null | "target" | null | [] | 2530 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2530" | 0.3109929078014184 | 0.30000000000000004 |
| "warn_ally/package_gate/1/1" | "warn_ally" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 3 | null | null | "target" | null | [] | 2535 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2535" | 0.3109929078014184 | 0.30000000000000004 |
| "work/package_gate/2" | "work" | "package_gate" | null | "since_last_event_at_least" | "work_performed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2119 | "diegetic" | "Refractory period for actor-global work_performed recurrence." | "nexus/agents/orrery/templates.py:2119" | 0.41465721040189124 | 0.4 |
| "work/package_gate/3" | "work" | "package_gate" | null | "since_last_event_at_least" | "household_work_performed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2120 | "diegetic" | "Refractory period for actor-global household_work_performed recurrence." | "nexus/agents/orrery/templates.py:2120" | 0.41465721040189124 | 0.4 |

## firings

| Field | Value |
| --- | --- |
| rows | 448 |
| ticks | 85 |
| rows_without_primary_metadata | 0 |

## current_packages

| template_id | rows | ticks |
| --- | --- | --- |
| "act_on_intel" | 21 | 7 |
| "advance_build_venture" | 0 | 0 |
| "advance_court_patron" | 0 | 0 |
| "advance_court_patron_faction" | 0 | 0 |
| "advance_pursue_romance" | 0 | 0 |
| "advance_recruit_ally" | 0 | 0 |
| "advance_relocation_plan" | 0 | 0 |
| "advance_seek_redemption" | 0 | 0 |
| "check_on_dependent" | 3 | 3 |
| "consult_rival" | 13 | 5 |
| "cultivate_informant" | 0 | 0 |
| "drink" | 40 | 23 |
| "eat" | 17 | 12 |
| "evade_pursuers" | 0 | 0 |
| "extract_vengeance" | 0 | 0 |
| "hide" | 24 | 21 |
| "honor_debt" | 0 | 0 |
| "intimacy" | 1 | 1 |
| "keep_vigil" | 0 | 0 |
| "maintain_cover" | 0 | 0 |
| "make_acquaintance" | 0 | 0 |
| "mourn_loss" | 0 | 0 |
| "protect_kin" | 0 | 0 |
| "reach_out" | 1 | 1 |
| "recreate" | 38 | 27 |
| "routine_commute" | 0 | 0 |
| "run_errands" | 28 | 12 |
| "sleep" | 6 | 6 |
| "socialize" | 1 | 1 |
| "start_build_venture" | 0 | 0 |
| "start_court_patron" | 0 | 0 |
| "start_court_patron_faction" | 0 | 0 |
| "start_pursue_romance" | 0 | 0 |
| "start_recruit_ally" | 0 | 0 |
| "start_relocation_plan" | 0 | 0 |
| "start_seek_redemption" | 0 | 0 |
| "stroll" | 81 | 45 |
| "surveil" | 61 | 21 |
| "tend_craft" | 15 | 14 |
| "tend_wounded" | 0 | 0 |
| "train" | 9 | 7 |
| "travel" | 0 | 0 |
| "uncover_past" | 0 | 0 |
| "upkeep" | 74 | 44 |
| "warn_ally" | 0 | 0 |
| "work" | 15 | 15 |

## unknown_historical_packages

[]

Exit status: `0`.

## save_04 Clone Report

```sh
PYTHONPATH=$PWD $PY - <<'PY'
import sys
from tests.pg_fixtures import disposable_slot_database
from scripts.qa_shift.cooldown_calibration import main
with disposable_slot_database("qa640_778s4a_evidence", source_db="save_04", include_data=True) as dbname:
    sys.argv = ["cooldown_calibration", "--dbname", dbname, "--format", "markdown"]
    main()
PY
```

# Cooldown Calibration

## header

| Field | Value |
| --- | --- |
| database | "qa640_778s4a_evidence_ab7f13d8c793" |
| migration_count | 137 |
| migration_level | "140" |
| transaction_read_only | "on" |
| transaction_isolation | "repeatable read" |
| total_chunks | 46 |
| classification_status | "Analytical proposals under settled Q1; no policy adopted." |
| clock_basis | "Post-140 primary-only stored clocks; slots already repaired by migration 140." |
| limitation | "Reference stays at migration 114 with inherited all-layer contamination; its reference-cadence equivalents retain that contamination. Slots are already repaired (migration 140). Reference equivalents require remeasurement after the primary-layer trigger repair in 778-S1b reaches that corpus. Never reconstruct or subtract from stored clocks. Primary-only duration sums differ conceptually from stored-clock span and cadence. Equivalents are measurements, not hour policy values." |
| firing_basis | "Stored resolution counts, not predicate evaluations or counterfactual firings; no actor-specific inference." |

## cadence

| Field | Value |
| --- | --- |
| first_clock_utc | "2189-10-17T19:12:00+00:00" |
| last_clock_utc | "2189-10-17T22:37:00+00:00" |
| primary_chunks | 45 |
| primary_duration_hours | 3.4166666666666665 |
| null_primary_durations | 0 |
| world_clock_span_hours | 3.4166666666666665 |
| adjacent_pairs | 44 |
| total_tick_gaps | 47 |
| zero_deltas | 0 |
| mean_pair_hours | 0.07765151515151515 |
| median_pair_hours | 0.06666666666666667 |
| weighted_hours_per_tick | 0.0726950354609929 |
| median_pair_hours_per_tick | 0.06666666666666667 |

## pairs

| from_chunk | to_chunk | tick_gap | world_hours | hours_per_tick |
| --- | --- | --- | --- | --- |
| 2 | 4 | 2 | 0.05 | 0.025 |
| 4 | 5 | 1 | 0.05 | 0.05 |
| 5 | 6 | 1 | 0.05 | 0.05 |
| 6 | 7 | 1 | 0.03333333333333333 | 0.03333333333333333 |
| 7 | 8 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 8 | 9 | 1 | 0.03333333333333333 | 0.03333333333333333 |
| 9 | 10 | 1 | 0.05 | 0.05 |
| 10 | 11 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 11 | 12 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 12 | 13 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 13 | 14 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 14 | 15 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 15 | 16 | 1 | 0.03333333333333333 | 0.03333333333333333 |
| 16 | 17 | 1 | 0.05 | 0.05 |
| 17 | 18 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 18 | 19 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 19 | 20 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 20 | 21 | 1 | 0.15 | 0.15 |
| 21 | 22 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 22 | 24 | 2 | 0.06666666666666667 | 0.03333333333333333 |
| 24 | 25 | 1 | 0.05 | 0.05 |
| 25 | 26 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 26 | 27 | 1 | 0.03333333333333333 | 0.03333333333333333 |
| 27 | 28 | 1 | 0.03333333333333333 | 0.03333333333333333 |
| 28 | 30 | 2 | 0.1 | 0.05 |
| 30 | 31 | 1 | 0.05 | 0.05 |
| 31 | 32 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 32 | 33 | 1 | 0.1 | 0.1 |
| 33 | 34 | 1 | 0.08333333333333333 | 0.08333333333333333 |
| 34 | 35 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 35 | 36 | 1 | 0.1 | 0.1 |
| 36 | 37 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 37 | 38 | 1 | 0.13333333333333333 | 0.13333333333333333 |
| 38 | 39 | 1 | 0.11666666666666667 | 0.11666666666666667 |
| 39 | 40 | 1 | 0.1 | 0.1 |
| 40 | 41 | 1 | 0.06666666666666667 | 0.06666666666666667 |
| 41 | 42 | 1 | 0.1 | 0.1 |
| 42 | 43 | 1 | 0.05 | 0.05 |
| 43 | 44 | 1 | 0.05 | 0.05 |
| 44 | 45 | 1 | 0.1 | 0.1 |
| 45 | 46 | 1 | 0.16666666666666666 | 0.16666666666666666 |
| 46 | 47 | 1 | 0.05 | 0.05 |
| 47 | 48 | 1 | 0.05 | 0.05 |
| 48 | 49 | 1 | 0.13333333333333333 | 0.13333333333333333 |

## gates

| gate_name | template_id | scope | branch_label | predicate | event_type | tick_parameter | ticks | minimum_count | actor_scope | target_scope | knower_scope | changed_fields_any_of | source_line | classification | purpose | evidence | weighted_equivalent_hours | median_equivalent_hours |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| "act_on_intel/package_gate/0" | "act_on_intel" | "package_gate" | null | "count_recent_events_at_least" | "surveillance_performed" | "within_ticks" | 25 | 3 | "actor" | "target" | null | [] | 1215 | "diegetic" | "Accumulate surveillance_performed occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:1215" | 1.8173758865248226 | 1.6666666666666667 |
| "act_on_intel/package_gate/1" | "act_on_intel" | "package_gate" | null | "since_last_event_at_least" | "intel_acted_on" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 1221 | "diegetic" | "Refractory period for actor-target intel_acted_on recurrence." | "nexus/agents/orrery/templates.py:1221" | 0.8723404255319148 | 0.8 |
| "check_on_dependent/branches[0].conditions/1" | "check_on_dependent" | "branches[0].conditions" | "Drop by in person when the moment allows" | "since_last_event_at_least" | "welfare_check" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 2663 | "diegetic" | "Refractory period for actor-target welfare_check recurrence." | "nexus/agents/orrery/templates.py:2663" | 0.4361702127659574 | 0.4 |
| "check_on_dependent/package_gate/2" | "check_on_dependent" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 2649 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2649" | 0.8723404255319148 | 0.8 |
| "check_on_dependent/package_gate/3" | "check_on_dependent" | "package_gate" | null | "since_last_event_at_least" | "welfare_check" | "minimum_ticks" | 12 | null | "actor" | "target" | null | [] | 2652 | "diegetic" | "Refractory period for actor-target welfare_check recurrence." | "nexus/agents/orrery/templates.py:2652" | 0.8723404255319148 | 0.8 |
| "consult_rival/package_gate/1/0" | "consult_rival" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 10 | null | null | null | null | [] | 2873 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2873" | 0.726950354609929 | 0.6666666666666666 |
| "consult_rival/package_gate/1/1" | "consult_rival" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 10 | null | null | null | null | [] | 2874 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2874" | 0.726950354609929 | 0.6666666666666666 |
| "consult_rival/package_gate/1/2" | "consult_rival" | "package_gate" | null | "recent_event" | "faction_realignment" | "within_ticks" | 15 | null | null | null | null | [] | 2875 | "diegetic" | "Event-recency window for faction_realignment under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2875" | 1.0904255319148934 | 1.0 |
| "consult_rival/package_gate/2" | "consult_rival" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 20 | null | "actor" | "target" | null | [] | 2877 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2877" | 1.453900709219858 | 1.3333333333333333 |
| "consult_rival/package_gate/3" | "consult_rival" | "package_gate" | null | "since_last_event_at_least" | "rival_consulted" | "minimum_ticks" | 20 | null | "actor" | "target" | null | [] | 2880 | "diegetic" | "Refractory period for actor-target rival_consulted recurrence." | "nexus/agents/orrery/templates.py:2880" | 1.453900709219858 | 1.3333333333333333 |
| "cultivate_informant/branches[0].conditions/2" | "cultivate_informant" | "branches[0].conditions" | "Press for material intel when trust is sufficient" | "since_last_event_at_least" | "intel_acquired" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1337 | "diegetic" | "Refractory period for actor-target intel_acquired recurrence." | "nexus/agents/orrery/templates.py:1337" | 0.4361702127659574 | 0.4 |
| "cultivate_informant/package_gate/2" | "cultivate_informant" | "package_gate" | null | "since_last_event_at_least" | "informant_contact" | "minimum_ticks" | 4 | null | "actor" | "target" | null | [] | 1317 | "diegetic" | "Refractory period for actor-target informant_contact recurrence." | "nexus/agents/orrery/templates.py:1317" | 0.2907801418439716 | 0.26666666666666666 |
| "cultivate_informant/package_gate/3" | "cultivate_informant" | "package_gate" | null | "since_last_event_at_least" | "intel_acquired" | "minimum_ticks" | 4 | null | "actor" | "target" | null | [] | 1322 | "diegetic" | "Refractory period for actor-target intel_acquired recurrence." | "nexus/agents/orrery/templates.py:1322" | 0.2907801418439716 | 0.26666666666666666 |
| "evade_pursuers/package_gate/0/1" | "evade_pursuers" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 5 | null | null | "actor" | null | [] | 134 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:134" | 0.3634751773049645 | 0.3333333333333333 |
| "extract_vengeance/branches[0].conditions/2" | "extract_vengeance" | "branches[0].conditions" | "Let the hunt go cold" | "since_last_event_at_least" | "hunt_declared" | "minimum_ticks" | 18 | null | "actor" | "target" | null | [] | 754 | "diegetic" | "Refractory period for actor-target hunt_declared recurrence." | "nexus/agents/orrery/templates.py:754" | 1.3085106382978722 | 1.2 |
| "extract_vengeance/package_gate/2" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "retaliation_attempted" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 734 | "diegetic" | "Refractory period for actor-global retaliation_attempted recurrence." | "nexus/agents/orrery/templates.py:734" | 0.5815602836879432 | 0.5333333333333333 |
| "extract_vengeance/package_gate/3" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "retaliation_executed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 735 | "diegetic" | "Refractory period for actor-global retaliation_executed recurrence." | "nexus/agents/orrery/templates.py:735" | 0.5815602836879432 | 0.5333333333333333 |
| "extract_vengeance/package_gate/4" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "hunt_declared" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 736 | "diegetic" | "Refractory period for actor-global hunt_declared recurrence." | "nexus/agents/orrery/templates.py:736" | 0.5815602836879432 | 0.5333333333333333 |
| "extract_vengeance/package_gate/5" | "extract_vengeance" | "package_gate" | null | "since_last_event_at_least" | "hunt_called_off" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 737 | "diegetic" | "Refractory period for actor-global hunt_called_off recurrence." | "nexus/agents/orrery/templates.py:737" | 0.5815602836879432 | 0.5333333333333333 |
| "hide/branches[5].conditions/1" | "hide" | "branches[5].conditions" | "Run a counter-surveillance sweep" | "recent_event" | "compliance_alert" | "within_ticks" | 8 | null | null | "actor" | null | [] | 366 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:366" | 0.5815602836879432 | 0.5333333333333333 |
| "hide/package_gate/4" | "hide" | "package_gate" | null | "since_last_event_at_least" | "hideout_maintained" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 236 | "diegetic" | "Refractory period for actor-global hideout_maintained recurrence." | "nexus/agents/orrery/templates.py:236" | 0.4361702127659574 | 0.4 |
| "hide/package_gate/5" | "hide" | "package_gate" | null | "since_last_event_at_least" | "signal_exposure_reduced" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 237 | "diegetic" | "Refractory period for actor-global signal_exposure_reduced recurrence." | "nexus/agents/orrery/templates.py:237" | 0.4361702127659574 | 0.4 |
| "hide/package_gate/6" | "hide" | "package_gate" | null | "since_last_event_at_least" | "counter_surveillance_sweep" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 238 | "diegetic" | "Refractory period for actor-global counter_surveillance_sweep recurrence." | "nexus/agents/orrery/templates.py:238" | 0.4361702127659574 | 0.4 |
| "honor_debt/package_gate/1" | "honor_debt" | "package_gate" | null | "recent_event" | "encoded_message" | "within_ticks" | 3 | null | null | "actor" | null | [] | 437 | "diegetic" | "Event-recency window for encoded_message under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:437" | 0.2180851063829787 | 0.2 |
| "intimacy/package_gate/2" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_fulfilled" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3655 | "diegetic" | "Refractory period for actor-global intimacy_fulfilled recurrence." | "nexus/agents/orrery/templates.py:3655" | 0.5815602836879432 | 0.5333333333333333 |
| "intimacy/package_gate/3" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_pursued" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3656 | "diegetic" | "Refractory period for actor-global intimacy_pursued recurrence." | "nexus/agents/orrery/templates.py:3656" | 0.5815602836879432 | 0.5333333333333333 |
| "intimacy/package_gate/4" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_partial" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3657 | "diegetic" | "Refractory period for actor-global intimacy_partial recurrence." | "nexus/agents/orrery/templates.py:3657" | 0.5815602836879432 | 0.5333333333333333 |
| "intimacy/package_gate/5" | "intimacy" | "package_gate" | null | "since_last_event_at_least" | "intimacy_deferred" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3658 | "diegetic" | "Refractory period for actor-global intimacy_deferred recurrence." | "nexus/agents/orrery/templates.py:3658" | 0.5815602836879432 | 0.5333333333333333 |
| "keep_vigil/package_gate/3" | "keep_vigil" | "package_gate" | null | "since_last_event_at_least" | "vigil_held" | "minimum_ticks" | 2 | null | "actor" | null | null | [] | 1708 | "diegetic" | "Refractory period for actor-global vigil_held recurrence." | "nexus/agents/orrery/templates.py:1708" | 0.1453900709219858 | 0.13333333333333333 |
| "maintain_cover/package_gate/6" | "maintain_cover" | "package_gate" | null | "since_last_event_at_least" | "maintain_cover" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 581 | "diegetic" | "Refractory period for actor-global maintain_cover recurrence." | "nexus/agents/orrery/templates.py:581" | 0.4361702127659574 | 0.4 |
| "mourn_loss/branches[0].conditions/root" | "mourn_loss" | "branches[0].conditions" | "Lay the grief down" | "count_recent_events_at_least" | "mourning_act" | "within_ticks" | 30 | 4 | "actor" | null | null | [] | 1584 | "diegetic" | "Accumulate mourning_act occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:1584" | 2.180851063829787 | 2.0 |
| "mourn_loss/package_gate/1" | "mourn_loss" | "package_gate" | null | "since_last_event_at_least" | "mourning_act" | "minimum_ticks" | 3 | null | "actor" | null | null | [] | 1569 | "diegetic" | "Refractory period for actor-global mourning_act recurrence." | "nexus/agents/orrery/templates.py:1569" | 0.2180851063829787 | 0.2 |
| "mourn_loss/package_gate/2" | "mourn_loss" | "package_gate" | null | "since_last_event_at_least" | "mourning_completed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 1570 | "turn-cadenced" | "Proposed grief-completion pacing, based explicitly on the pacing comment." | "nexus/agents/orrery/templates.py:1570; nexus/agents/orrery/templates.py:1564" | 0.5815602836879432 | 0.5333333333333333 |
| "protect_kin/package_gate/1/2" | "protect_kin" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 4 | null | null | "target" | null | [] | 912 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:912" | 0.2907801418439716 | 0.26666666666666666 |
| "reach_out/branches[0].conditions/3" | "reach_out" | "branches[0].conditions" | "Find the moment for a real face-to-face conversation" | "since_last_event_at_least" | "kin_visit" | "minimum_ticks" | 5 | null | "actor" | "target" | null | [] | 2759 | "diegetic" | "Refractory period for actor-target kin_visit recurrence." | "nexus/agents/orrery/templates.py:2759" | 0.3634751773049645 | 0.3333333333333333 |
| "reach_out/package_gate/2" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "contact_made" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2740 | "diegetic" | "Refractory period for actor-target contact_made recurrence." | "nexus/agents/orrery/templates.py:2740" | 0.5815602836879432 | 0.5333333333333333 |
| "reach_out/package_gate/3" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "kin_visit" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2743 | "diegetic" | "Refractory period for actor-target kin_visit recurrence." | "nexus/agents/orrery/templates.py:2743" | 0.5815602836879432 | 0.5333333333333333 |
| "reach_out/package_gate/4" | "reach_out" | "package_gate" | null | "since_last_event_at_least" | "contact_deferred" | "minimum_ticks" | 8 | null | "actor" | "target" | null | [] | 2746 | "diegetic" | "Refractory period for actor-target contact_deferred recurrence." | "nexus/agents/orrery/templates.py:2746" | 0.5815602836879432 | 0.5333333333333333 |
| "recreate/package_gate/2" | "recreate" | "package_gate" | null | "since_last_event_at_least" | "recreation_taken" | "minimum_ticks" | 6 | null | "actor" | null | null | [] | 4218 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4218; nexus/agents/orrery/templates.py:3806" | 0.4361702127659574 | 0.4 |
| "run_errands/package_gate/2" | "run_errands" | "package_gate" | null | "since_last_event_at_least" | "errands_run" | "minimum_ticks" | 9 | null | "actor" | null | null | [] | 3950 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:3950; nexus/agents/orrery/templates.py:3806" | 0.6542553191489361 | 0.6 |
| "socialize/package_gate/1" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "socialized" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3392 | "diegetic" | "Refractory period for actor-global socialized recurrence." | "nexus/agents/orrery/templates.py:3392" | 0.2907801418439716 | 0.26666666666666666 |
| "socialize/package_gate/2" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "socialized_alone" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3393 | "diegetic" | "Refractory period for actor-global socialized_alone recurrence." | "nexus/agents/orrery/templates.py:3393" | 0.2907801418439716 | 0.26666666666666666 |
| "socialize/package_gate/3" | "socialize" | "package_gate" | null | "since_last_event_at_least" | "social_travel_departed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 3394 | "diegetic" | "Refractory period for actor-global social_travel_departed recurrence." | "nexus/agents/orrery/templates.py:3394" | 0.2907801418439716 | 0.26666666666666666 |
| "start_relocation_plan/package_gate/5/0" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "upkeep_done" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4372 | "diegetic" | "Accumulate upkeep_done occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4372" | 2.180851063829787 | 2.0 |
| "start_relocation_plan/package_gate/5/1" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "errands_run" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4373 | "diegetic" | "Accumulate errands_run occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4373" | 2.180851063829787 | 2.0 |
| "start_relocation_plan/package_gate/5/2" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "recreation_taken" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4374 | "diegetic" | "Accumulate recreation_taken occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4374" | 2.180851063829787 | 2.0 |
| "start_relocation_plan/package_gate/5/3" | "start_relocation_plan" | "package_gate" | null | "count_recent_events_at_least" | "work_performed" | "within_ticks" | 30 | 2 | "actor" | null | null | [] | 4377 | "diegetic" | "Accumulate work_performed occurrences inside a bounded world-time window." | "nexus/agents/orrery/templates.py:4377" | 2.180851063829787 | 2.0 |
| "start_relocation_plan/package_gate/6/0" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "travel_delayed" | "within_ticks" | 12 | null | "actor" | null | null | [] | 4382 | "diegetic" | "Event-recency window for travel_delayed under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4382" | 0.8723404255319148 | 0.8 |
| "start_relocation_plan/package_gate/6/1" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "contact_deferred" | "within_ticks" | 12 | null | "actor" | null | null | [] | 4383 | "diegetic" | "Event-recency window for contact_deferred under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4383" | 0.8723404255319148 | 0.8 |
| "start_relocation_plan/package_gate/6/2" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 12 | null | null | "actor" | null | [] | 4384 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4384" | 0.8723404255319148 | 0.8 |
| "start_relocation_plan/package_gate/6/3" | "start_relocation_plan" | "package_gate" | null | "recent_event" | "retaliation_attempted" | "within_ticks" | 12 | null | null | "actor" | null | [] | 4385 | "diegetic" | "Event-recency window for retaliation_attempted under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:4385" | 0.8723404255319148 | 0.8 |
| "stroll/package_gate/1" | "stroll" | "package_gate" | null | "since_last_event_at_least" | "stroll_taken" | "minimum_ticks" | 5 | null | "actor" | null | null | [] | 4034 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4034; nexus/agents/orrery/templates.py:3806" | 0.3634751773049645 | 0.3333333333333333 |
| "surveil/package_gate/10" | "surveil" | "package_gate" | null | "since_last_event_at_least" | "surveillance_performed" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1054 | "diegetic" | "Refractory period for actor-target surveillance_performed recurrence." | "nexus/agents/orrery/templates.py:1054" | 0.4361702127659574 | 0.4 |
| "surveil/package_gate/11" | "surveil" | "package_gate" | null | "since_last_event_at_least" | "intel_reviewed" | "minimum_ticks" | 6 | null | "actor" | "target" | null | [] | 1057 | "diegetic" | "Refractory period for actor-target intel_reviewed recurrence." | "nexus/agents/orrery/templates.py:1057" | 0.4361702127659574 | 0.4 |
| "surveil/package_gate/9/7" | "surveil" | "package_gate" | null | "knows_recent_event" | "threat_issued" | "within_ticks" | 8 | null | null | "target" | "actor" | [] | 1050 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:1050" | 0.5815602836879432 | 0.5333333333333333 |
| "tend_craft/package_gate/1" | "tend_craft" | "package_gate" | null | "since_last_event_at_least" | "craft_tended" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2311 | "diegetic" | "Refractory period for actor-global craft_tended recurrence." | "nexus/agents/orrery/templates.py:2311" | 0.2907801418439716 | 0.26666666666666666 |
| "tend_wounded/package_gate/4" | "tend_wounded" | "package_gate" | null | "since_last_event_at_least" | "tended_wound" | "minimum_ticks" | 2 | null | "actor" | "target" | null | [] | 1460 | "diegetic" | "Refractory period for actor-target tended_wound recurrence." | "nexus/agents/orrery/templates.py:1460" | 0.1453900709219858 | 0.13333333333333333 |
| "tend_wounded/package_gate/5" | "tend_wounded" | "package_gate" | null | "since_last_event_at_least" | "wound_healed" | "minimum_ticks" | 2 | null | "actor" | "target" | null | [] | 1463 | "diegetic" | "Refractory period for actor-target wound_healed recurrence." | "nexus/agents/orrery/templates.py:1463" | 0.1453900709219858 | 0.13333333333333333 |
| "train/package_gate/3" | "train" | "package_gate" | null | "since_last_event_at_least" | "training_performed" | "minimum_ticks" | 8 | null | "actor" | null | null | [] | 3852 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:3852; nexus/agents/orrery/templates.py:3806" | 0.5815602836879432 | 0.5333333333333333 |
| "upkeep/package_gate/1" | "upkeep" | "package_gate" | null | "since_last_event_at_least" | "upkeep_done" | "minimum_ticks" | 7 | null | "actor" | null | null | [] | 4121 | "turn-cadenced" | "Stagger mundane actions to preserve varied narration." | "nexus/agents/orrery/templates.py:4121; nexus/agents/orrery/templates.py:3806" | 0.5088652482269503 | 0.4666666666666667 |
| "warn_ally/package_gate/1/0" | "warn_ally" | "package_gate" | null | "recent_event" | "threat_issued" | "within_ticks" | 3 | null | null | "target" | null | [] | 2530 | "diegetic" | "Event-recency window for threat_issued under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2530" | 0.2180851063829787 | 0.2 |
| "warn_ally/package_gate/1/1" | "warn_ally" | "package_gate" | null | "recent_event" | "compliance_alert" | "within_ticks" | 3 | null | null | "target" | null | [] | 2535 | "diegetic" | "Event-recency window for compliance_alert under enclosing Boolean conditions." | "nexus/agents/orrery/templates.py:2535" | 0.2180851063829787 | 0.2 |
| "work/package_gate/2" | "work" | "package_gate" | null | "since_last_event_at_least" | "work_performed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2119 | "diegetic" | "Refractory period for actor-global work_performed recurrence." | "nexus/agents/orrery/templates.py:2119" | 0.2907801418439716 | 0.26666666666666666 |
| "work/package_gate/3" | "work" | "package_gate" | null | "since_last_event_at_least" | "household_work_performed" | "minimum_ticks" | 4 | null | "actor" | null | null | [] | 2120 | "diegetic" | "Refractory period for actor-global household_work_performed recurrence." | "nexus/agents/orrery/templates.py:2120" | 0.2907801418439716 | 0.26666666666666666 |

## firings

| Field | Value |
| --- | --- |
| rows | 103 |
| ticks | 26 |
| rows_without_primary_metadata | 0 |

## current_packages

| template_id | rows | ticks |
| --- | --- | --- |
| "act_on_intel" | 0 | 0 |
| "advance_build_venture" | 0 | 0 |
| "advance_court_patron" | 0 | 0 |
| "advance_court_patron_faction" | 0 | 0 |
| "advance_pursue_romance" | 0 | 0 |
| "advance_recruit_ally" | 0 | 0 |
| "advance_relocation_plan" | 0 | 0 |
| "advance_seek_redemption" | 0 | 0 |
| "check_on_dependent" | 2 | 2 |
| "consult_rival" | 0 | 0 |
| "cultivate_informant" | 0 | 0 |
| "drink" | 6 | 3 |
| "eat" | 0 | 0 |
| "evade_pursuers" | 0 | 0 |
| "extract_vengeance" | 0 | 0 |
| "hide" | 1 | 1 |
| "honor_debt" | 0 | 0 |
| "intimacy" | 0 | 0 |
| "keep_vigil" | 0 | 0 |
| "maintain_cover" | 0 | 0 |
| "make_acquaintance" | 7 | 5 |
| "mourn_loss" | 0 | 0 |
| "protect_kin" | 0 | 0 |
| "reach_out" | 0 | 0 |
| "recreate" | 23 | 14 |
| "routine_commute" | 0 | 0 |
| "run_errands" | 0 | 0 |
| "sleep" | 0 | 0 |
| "socialize" | 0 | 0 |
| "start_build_venture" | 0 | 0 |
| "start_court_patron" | 0 | 0 |
| "start_court_patron_faction" | 0 | 0 |
| "start_pursue_romance" | 0 | 0 |
| "start_recruit_ally" | 0 | 0 |
| "start_relocation_plan" | 0 | 0 |
| "start_seek_redemption" | 0 | 0 |
| "stroll" | 31 | 19 |
| "surveil" | 6 | 4 |
| "tend_craft" | 0 | 0 |
| "tend_wounded" | 0 | 0 |
| "train" | 0 | 0 |
| "travel" | 0 | 0 |
| "uncover_past" | 0 | 0 |
| "upkeep" | 27 | 18 |
| "warn_ally" | 0 | 0 |
| "work" | 0 | 0 |

## unknown_historical_packages

[]

Exit status: `0`; fixture cleanup completed.

Implemented by Codex (GPT-6 Astra).
