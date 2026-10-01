# Existing-Ledger Envelope Measurement (#759 S2a)

Measured on 2026-10-01; ledger read began at `2026-10-01T09:02:24.388132+00:00`. Implementation and tests: `bba49a03dcf4b4d1f4e86740b876d7ceeae9f072`; rebased base: `16993687d7381955e0cc5f7ea0bbb59bf4b22764`. The report code is unchanged from the commit used for this evidence run; the final fixture-only edit preserves distinct sanitized source identifiers.

This is a read-only measurement of the selected historical ledgers. It adds no product behavior. The primary estimate-error population has **0 eligible attempts** because no projected estimate/reported pairs exist in the inspected saves. Concurrent calls cannot be measured: **0 measurable intervals**, with peak and overlap distribution **unknown**. The separate rendered-window comparison has **57 eligible pairs**.

## Binding Scope

The issue body’s “Scope After the Owner’s Ruling (2026-09-30, Arachne Sequence 38)” binds. The snapshot and all live comments were read before implementation. The owner’s and coordinator’s settled text is preserved:

> Disposition: Build (disp_759=build)

> Envelope behavior when headroom is short: Report only (q_759_policy=report)

> A: One attempt per critical seat

> Astra's OTHER: extend the existing window and usage ledgers into a timestamped, explicitly stateful, report-only demand projection with a configured expiry and no atomic admission

> C: every provider-backed call counts toward in-flight demand

> A: inside the in-flight generation telemetry, as an unlabeled cue with the figures on hover

Tokens only; Gaia follows the slot model. Retries are separate recorded attempts, with no speculative retry multiplier. No confirmation, blocking, provider substitution, omitted Gaia, Writer downgrade, account-pool claim, price, expiry tunable or signal change is introduced. The estimator, stateful projection and transient UI remain their assigned later slices.

## Reverified Current Behavior

| Evidence | Current Behavior |
| --- | --- |
| `nexus/telemetry/prompt_window.py:229-246` | PromptWindowRecord has attempt identity, model and rendered counts; it has no timestamp, dispatch state or output allowance. |
| `nexus/telemetry/usage.py:800-837`, `:63-70` | The recorder appends a window model to the UTC-day file; the reader keeps the last seat/attempt revision. Wire repair appends another row of the same attempt. |
| `nexus/agents/lore/logon_utility.py:2080-2129` | Manifest and window recording precede the final prompt-window guard and shared Gaia guard. An unmatched window proves neither dispatch nor a live provider call. |
| `nexus/telemetry/usage.py:95-131` | Usage records completion timestamps and nullable counts but no request-start timestamp. The measurement requires raw, explicit offset-bearing timestamps before Pydantic validation can supply defaults. |
| `nexus/telemetry/attempt_manifest.py:241-266`, `nexus/telemetry/usage.py:543-569` | Manifest counts record the request estimate and reported input; Anthropic reported input adds cache reads and creation. |
| `nexus/telemetry/turn_observation.py:111`, `:394-439` | PR #1067 is present: schema version 2 projects estimated_input_tokens and reported_input_tokens. This order consumes that projection and changes no telemetry module or choice-readiness behavior. |
| `migrations/124_attempt_manifests.sql:41-42`, `:64-65`; `nexus/telemetry/attempt_manifest.py:250-251` | Manifest created_at is insertion time and updated_at changes with measurements; neither is dispatch. |
| `nexus/telemetry/attempt_manifest.py:328-339`; `nexus/telemetry/turn_observation.py:573-604` | Background seats map to queues. Production attribution checks numeric run id, slot, queue seat, ledger day and enqueue time; a numeric id alone is not globally unique. |
| `nexus/telemetry/usage.py:144-156`, `:459-469`; `nexus.toml:1325-1333` | Alternate runtime configs share runtime-home ledger files. Configured provider allowances are readout only, not authoritative account headroom. |
| `scripts/qa_shift/prose_metrics.py:331-343`; `nexus/telemetry/attempt_manifest.py:346-354` | Read-only verification starts a transaction. inspect_turn must enter idle and owns a separate read-only, repeatable-read transaction. |
| `nexus/telemetry/turn_observation.py:321-331` | The observation emits the union of manifest, window and usage keys, so its attempts are not a date-bounded population. The new report applies ledger membership after derivation. |
| `config/reachability.toml` operator and sorted classification entry; `scripts/qa_shift/envelope_measure.py:52`, `:156`, `:318` | The operator captures/validates fixed prefixes, reads databases independently, derives production observations and filters membership. Both reachability obligations are registered. |

## Commands and Snapshot Boundaries

Every command ran from `/Users/pythagor/nexus/.claude/worktrees/759-envelope-measure`. The import check printed that worktree’s `nexus/__init__.py`. The evidence command below is an authorized read of owner ledgers/databases, separate from the disposable test gate. No provider, token counter, writer, migration or gateway startup is called by the measurement operator. Its SQL is SELECT-only; read-only and repeatable-read are enforced by the connection options before any table read and checked explicitly.

```bash
PY=/Users/pythagor/nexus/.venv/bin/python
SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
PYTHONPATH=$PWD NEXUS_TEST_PROVIDER_ONLY=1 $PY scripts/qa_shift/envelope_measure.py --usage-dir /Users/pythagor/nexus/.nexus/runtime/usage --from-day 2026-07-30 --through-day 2026-10-01 --slot-db 1=save_01 --slot-db 2=save_02 --slot-db 3=save_03 --slot-db 4=save_04 --slot-db 5=save_05 > "$SCRATCH/measurement.json"
```

Captured JSON SHA-256: `f37d61706c332b918f5ff2abe0747f7af895483f497af3353b97f897dd161a3f`. The script writes no file; shell redirection wrote this scratch artifact.

The snapshot captures each selected file length once, reads only that prefix, requires complete newline-terminated rows and records its digest. Missing days mean no file was present, not proof of zero calls. All usage events are retained in `coverage.event_inventory`; sources identify the file and line. Exact duplicate rows and multiple events per attempt are counted separately. No file mtime or line order is used as elapsed time.

Enumeration ends with rollback before inspection. Every enumerated session is inspected once; each verification transaction also ends before the inspection. Recorded `idle_before` and `idle_after` are true for every inspection. The inspection start/end bounds are wall-clock read boundaries, not provider timing. Verification snapshots precede inspections and are not claimed to be the inspection snapshots. Enumeration and each inspection are separate snapshots; intervening changes are possible. There is no report-wide atomic database snapshot.

| Slot | Database | Sessions | Manifests | Phases | Inspections | Database-Only Attempts |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | save_01 | 0 | 0 | 0 | 0 | 0 |
| 2 | save_02 | 0 | 0 | 0 | 0 | 0 |
| 3 | save_03 | 50 | 0 | 0 | 50 | 0 |
| 4 | save_04 | 56 | 0 | 0 | 56 | 0 |
| 5 | save_05 | 0 | 0 | 0 | 0 | 0 |

| Slot | Enumeration Start | Enumeration End | Inspection Read Bounds |
| --- | --- | --- | --- |
| 1 | 2026-10-01T09:02:24.632942+00:00 | 2026-10-01T09:02:24.644077+00:00 | none |
| 2 | 2026-10-01T09:02:24.666229+00:00 | 2026-10-01T09:02:24.680510+00:00 | none |
| 3 | 2026-10-01T09:02:24.706014+00:00 | 2026-10-01T09:02:24.715454+00:00 | 2026-10-01T09:02:24.715539+00:00 through 2026-10-01T09:02:24.746163+00:00 |
| 4 | 2026-10-01T09:02:24.768948+00:00 | 2026-10-01T09:02:24.778656+00:00 | 2026-10-01T09:02:24.778736+00:00 through 2026-10-01T09:02:24.812867+00:00 |
| 5 | 2026-10-01T09:02:24.853193+00:00 | 2026-10-01T09:02:24.901827+00:00 | none |

All five enumerations recorded `read_only=on`, `isolation=repeatable read`, the requested database name, and server port `5432`. No template database was opened by this report. The session, manifest, phase, file and row counts agree with the work order’s dated 2026-10-01 save/ledger counts.

## Numeric Results and Coverage Limits

| Measure | Count |
| --- | --- |
| usage_events | 815 |
| window_rows | 58 |
| distinct_windows | 57 |
| window_revisions_folded | 1 |
| attributed_attempts | 409 |
| attributed_usage_events | 560 |
| multiple_event_attempts | 18 |
| duplicate_usage_events | 0 |
| aggregate_events | 169 |
| missing_run_events | 111 |
| test_events | 20 |
| non_test_events | 795 |

| Unattributed Source and Reason | Rows |
| --- | --- |
| usage:missing_run | 111 |
| usage:unmatched_job | 144 |

The 255 unattributed usage events remain in coverage and concurrency limitations; they enter no attributed-attempt error denominator. The 144 numeric job events lack a matching recorded job in the inspected session inventory; their slot/seat alone does not prove an enqueue-relative job identity. All 57 latest windows have unambiguous slot attribution and a matching usage event in this snapshot. All 169 aggregate events reside in the 18 multiple-event attempts, so the exclusive error-exclusion reason is `multiple_events`; aggregate timing is counted separately in coverage. No duplicate usage row was found.

| Recorded Seat | Usage Events |
| --- | --- |
| correspondence_compaction | 22 |
| experience_renderer | 3 |
| gaia | 204 |
| orrery_narration | 31 |
| retrograde_expansion | 53 |
| retrograde_seed_candidates | 56 |
| retrograde_seed_selection | 51 |
| set_designer | 13 |
| skald_single_pass | 14 |
| skald_writer | 173 |
| trait_input_derivation | 26 |
| wizard | 169 |

| Recorded Provider | Usage Events |
| --- | --- |
| anthropic | 2 |
| openai | 793 |
| test | 20 |

This inventory includes recorded background, wizard and genesis/setup seats (`set_designer` and `trait_input_derivation`), including events with no windows or run ids. Calls absent from the ledgers cannot be reconstructed. “TEST” means recorded model `TEST` or provider `test` (case-insensitive provider); it does not claim every non-TEST event is owner play.

### Projected Estimate Versus Reported

| Population | Eligible | Excluded | Exclusion Reasons |
| --- | --- | --- | --- |
| signed_absolute | 0 | 409 | {"missing_counts": 391, "multiple_events": 18} |
| relative | 0 | 409 | {"missing_counts": 391, "multiple_events": 18} |

| Statistic | Value |
| --- | --- |
| mean signed error (tokens) | unknown |
| mean absolute error (tokens) | unknown |
| absolute error count | 0 |
| absolute error max | unknown |
| absolute error min | unknown |
| absolute error p50 | unknown |
| absolute error p95 | unknown |
| relative error count | 0 |
| relative error max | unknown |
| relative error min | unknown |
| relative error p50 | unknown |
| relative error p95 | unknown |

| Grouping | Value | Signed/Absolute Eligible | Signed/Absolute Excluded | Relative Eligible | Relative Excluded | Mean Signed | Mean Absolute | Exclusion Reasons (Signed; Relative) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | "TEST" | 0 | 8 | 0 | 8 | unknown | unknown | {"missing_counts": 6, "multiple_events": 2}; {"missing_counts": 6, "multiple_events": 2} |
| model | "gpt-5.6-sol" | 0 | 9 | 0 | 9 | unknown | unknown | {"missing_counts": 9}; {"missing_counts": 9} |
| model | "gpt-5.6-terra" | 0 | 391 | 0 | 391 | unknown | unknown | {"missing_counts": 376, "multiple_events": 15}; {"missing_counts": 376, "multiple_events": 15} |
| model | "gpt-6-astra" | 0 | 1 | 0 | 1 | unknown | unknown | {"multiple_events": 1}; {"multiple_events": 1} |
| provider | "openai" | 0 | 401 | 0 | 401 | unknown | unknown | {"missing_counts": 385, "multiple_events": 16}; {"missing_counts": 385, "multiple_events": 16} |
| provider | "test" | 0 | 8 | 0 | 8 | unknown | unknown | {"missing_counts": 6, "multiple_events": 2}; {"missing_counts": 6, "multiple_events": 2} |
| seat | "gaia" | 0 | 204 | 0 | 204 | unknown | unknown | {"missing_counts": 204}; {"missing_counts": 204} |
| seat | "skald_single_pass" | 0 | 14 | 0 | 14 | unknown | unknown | {"missing_counts": 14}; {"missing_counts": 14} |
| seat | "skald_writer" | 0 | 173 | 0 | 173 | unknown | unknown | {"missing_counts": 173}; {"missing_counts": 173} |
| seat | "wizard" | 0 | 18 | 0 | 18 | unknown | unknown | {"multiple_events": 18}; {"multiple_events": 18} |
| slot | 3 | 0 | 4 | 0 | 4 | unknown | unknown | {"missing_counts": 4}; {"missing_counts": 4} |
| slot | 4 | 0 | 297 | 0 | 297 | unknown | unknown | {"missing_counts": 282, "multiple_events": 15}; {"missing_counts": 282, "multiple_events": 15} |
| slot | 5 | 0 | 108 | 0 | 108 | unknown | unknown | {"missing_counts": 105, "multiple_events": 3}; {"missing_counts": 105, "multiple_events": 3} |
| transport | "pydantic_ai" | 0 | 18 | 0 | 18 | unknown | unknown | {"multiple_events": 18}; {"multiple_events": 18} |
| transport | "responses" | 0 | 391 | 0 | 391 | unknown | unknown | {"missing_counts": 391}; {"missing_counts": 391} |

### Rendered Window Versus Reported

| Population | Eligible | Excluded | Exclusion Reasons |
| --- | --- | --- | --- |
| signed_absolute | 57 | 352 | {"missing_counts": 334, "multiple_events": 18} |
| relative | 57 | 352 | {"missing_counts": 334, "multiple_events": 18} |

| Statistic | Value |
| --- | --- |
| mean signed error (tokens) | 547.8947368421053 |
| mean absolute error (tokens) | 547.8947368421053 |
| absolute error count | 57 |
| absolute error max | 17322 |
| absolute error min | 0 |
| absolute error p50 | 0 |
| absolute error p95 | 5686 |
| relative error count | 57 |
| relative error max | 17.322 |
| relative error min | 0.0 |
| relative error p50 | 0.0 |
| relative error p95 | 5.686 |

| Grouping | Value | Signed/Absolute Eligible | Signed/Absolute Excluded | Relative Eligible | Relative Excluded | Mean Signed | Mean Absolute | Exclusion Reasons (Signed; Relative) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| model | "TEST" | 3 | 5 | 3 | 5 | 10410.0 | 10410.0 | {"missing_counts": 3, "multiple_events": 2}; {"missing_counts": 3, "multiple_events": 2} |
| model | "gpt-5.6-sol" | 0 | 9 | 0 | 9 | unknown | unknown | {"missing_counts": 9}; {"missing_counts": 9} |
| model | "gpt-5.6-terra" | 54 | 337 | 54 | 337 | 0.0 | 0.0 | {"missing_counts": 322, "multiple_events": 15}; {"missing_counts": 322, "multiple_events": 15} |
| model | "gpt-6-astra" | 0 | 1 | 0 | 1 | unknown | unknown | {"multiple_events": 1}; {"multiple_events": 1} |
| provider | "openai" | 54 | 347 | 54 | 347 | 0.0 | 0.0 | {"missing_counts": 331, "multiple_events": 16}; {"missing_counts": 331, "multiple_events": 16} |
| provider | "test" | 3 | 5 | 3 | 5 | 10410.0 | 10410.0 | {"missing_counts": 3, "multiple_events": 2}; {"missing_counts": 3, "multiple_events": 2} |
| seat | "gaia" | 24 | 180 | 24 | 180 | 236.91666666666666 | 236.91666666666666 | {"missing_counts": 180}; {"missing_counts": 180} |
| seat | "skald_single_pass" | 9 | 5 | 9 | 5 | 1924.6666666666667 | 1924.6666666666667 | {"missing_counts": 5}; {"missing_counts": 5} |
| seat | "skald_writer" | 24 | 149 | 24 | 149 | 342.5833333333333 | 342.5833333333333 | {"missing_counts": 149}; {"missing_counts": 149} |
| seat | "wizard" | 0 | 18 | 0 | 18 | unknown | unknown | {"multiple_events": 18}; {"multiple_events": 18} |
| slot | 3 | 0 | 4 | 0 | 4 | unknown | unknown | {"missing_counts": 4}; {"missing_counts": 4} |
| slot | 4 | 57 | 240 | 57 | 240 | 547.8947368421053 | 547.8947368421053 | {"missing_counts": 225, "multiple_events": 15}; {"missing_counts": 225, "multiple_events": 15} |
| slot | 5 | 0 | 108 | 0 | 108 | unknown | unknown | {"missing_counts": 105, "multiple_events": 3}; {"missing_counts": 105, "multiple_events": 3} |
| transport | "pydantic_ai" | 0 | 18 | 0 | 18 | unknown | unknown | {"multiple_events": 18}; {"multiple_events": 18} |
| transport | "responses" | 57 | 334 | 57 | 334 | 547.8947368421053 | 547.8947368421053 | {"missing_counts": 334}; {"missing_counts": 334} |

The historical rendered-window sample comprises **3 TEST pairs** (mean signed and absolute difference **10,410 tokens**, absolute min/p50/p95/max **5,686 / 8,222 / 17,322 / 17,322**) and **54 non-TEST pairs** (all signed, absolute and relative differences **0**). The non-TEST pairs record `gpt-5.6-terra`; this is a historical model id, not a configured choice. The 57-pair rendered comparison does not substitute for local-estimate error.

Signed error is compared input minus reported input; relative error divides that signed difference by reported input. The primary comparison consumes only the version-2 observation’s manifest projection. The historical comparison uses the latest selected rendered window and one matching nonaggregate usage event, with run, slot, seat, attempt and model agreement. Anthropic Messages reported input requires input plus cache-read plus cache-creation counts; an absent required count is unknown. Missing counts never become zero. Reported zero remains eligible for signed/absolute errors and is excluded from relative errors only as `zero_reported`. Percentiles use nearest rank `ceil(p*n)`. Empty populations have count zero and unknown statistics. No NaN or infinity is emitted. The JSON also contains all group-specific percentiles.

### Concurrent Demand

| Measure | Value |
| --- | --- |
| aggregate_timing_events | 169 |
| ambiguous_identity_events | 424 |
| measurable_intervals | 0 |
| missing_completion_events | 0 |
| missing_start_events | 815 |
| overlap_distribution | unknown |
| peak_concurrent_calls | unknown |
| reason | Existing ledgers have no per-call dispatch timestamps. |
| windows_without_completion | 0 |

Existing records contain no explicit per-call dispatch timestamp. An unmatched window is never labeled in flight. Manifest creation, phase entry, job enqueue, file time, ticks and diegetic time are never substituted for dispatch. Aggregate responses have no individual internal-request timing. Missing start, missing completion, ambiguous identity and aggregate timing counts describe overlapping limitations and must not be added together. Missing completion events are zero because every accepted usage row has an explicit completion timestamp; the separate unmatched-window count is also zero in this snapshot.

Golden-path and QA traffic bias this ledger and do not establish the owner’s play demand. Slot 2’s diegetic time is contaminated evidence; this report uses only recorded operational telemetry. No allowance, pool boundary, safety margin or expiry value is recommended.

## Input Prefix Digests

Paths below are relative to `/Users/pythagor/nexus/.nexus/runtime/usage`; the JSON retains their absolute paths.

| File | Captured Bytes | SHA-256 |
| --- | --- | --- |
| usage-2026-07-30.jsonl | 86829 | 375c66ffcba76cbfb20fae4b6db3b54135d58ae3cf1f97097dc83e0d2dc15f1a |
| usage-2026-07-31.jsonl | 6608 | af9e3ccc1ba5ef177f60965cca94ef16d8be4b0a62d675ccdc988bc05b2dac08 |
| usage-2026-08-01.jsonl | 10549 | fd1a0ceec32a3ab666a80cf0d8b0ab76717076decb3dcf6810cb6292afbf8b14 |
| usage-2026-08-02.jsonl | 17281 | 2c53947ce224d5d5fed98132fbab5a68cb819d6c836b89aafc7ad7e7575c69a2 |
| usage-2026-08-03.jsonl | 2032 | 7f7d655102ec9bc2a6033e7b71da4df8c53740561cfeadc411167109f14cb8d4 |
| usage-2026-08-04.jsonl | 10031 | b017b0656ac4eb2ddf7178e04c1f7a6c8effe7f6879f3ea7012eee76e730aaa5 |
| usage-2026-08-05.jsonl | 5537 | d2085cbc854a10f2a27acfdb5a37a4dd6d653f0e86086cfc573c2d87a7b584c3 |
| usage-2026-08-06.jsonl | 14113 | 3eda5a8fd7f4d60225a57004c5c65ae83f0c4412afef7c12852b16a8d5730e0e |
| usage-2026-08-09.jsonl | 6546 | 8854a5f7f547a82b0880fa19e7c824273ef90ab5c82ba8de557ad3c46c77c618 |
| usage-2026-08-10.jsonl | 8093 | 7c7e7736f407638948f1698ed184b2d0f64a29cbf3a738c498dd29d4c869a6dc |
| usage-2026-08-12.jsonl | 35349 | 5727f3741acc99503fee974335dfecfd1ecf4ad2631cf5e28784d2cc4b7fd968 |
| usage-2026-08-13.jsonl | 9576 | 734ca3671411a09be6225d171c68efba35c4f66a21d40cbccb75feabe28d674f |
| usage-2026-08-14.jsonl | 19503 | 627fea8e47cc746215edc5ada28a1725ef56e3c9585c13db089a22a0bea2e107 |
| usage-2026-08-15.jsonl | 8999 | 0e4f18fe2c7386360c3d4bf628814c0e1d93e119c8049b14c5125a38f3388dd6 |
| usage-2026-08-19.jsonl | 10453 | dab3b30acb4017f64317867ab7510259694fe124ff335167d74f46504cdf0afb |
| usage-2026-08-20.jsonl | 1011 | ffcfe1f2977130cb41538df73ae50186dae53127faa2ed90b5cc6734a133172f |
| usage-2026-08-21.jsonl | 10445 | 3bc08296b0c1edb9e5ad337d9fbada88d7cbba6a11388642d0489b8d0f0ff8d9 |
| usage-2026-09-21.jsonl | 920 | f972bf70240009fd3f90f351dad09a8b383b8224240fc299fafa0df1724aed12 |
| usage-2026-09-23.jsonl | 13704 | 70ca1766e3f0c704a31c0258f8e314b33ec21d13f59fe4249c9bf2fcd4e40b8d |
| windows-2026-09-24.jsonl | 6542 | 810021eaf733c3a5c047200feff89d1900ba91fbc1ab6358f299747dd002a525 |
| usage-2026-09-24.jsonl | 18298 | 6cfce5cbce33cb6969981dd154ef9fadcf3eb58735a04a83096d7e412ac99030 |
| windows-2026-09-25.jsonl | 27128 | 96682615a492292d31210921904a4319b4aeb2cc6c52e4d32e3a0b360f5b5038 |
| usage-2026-09-25.jsonl | 47574 | 6c79187cfcfed34df12d6be668f57c8f135a4d5416443623fcc814d0e05516a9 |
| windows-2026-09-26.jsonl | 4623 | 7bca331e000b63ba722e081f31f79d539f66af1ac6da9d4ba7d99f434443091f |
| usage-2026-09-26.jsonl | 12494 | 5da490bb3ad700088cb9bd98c4e6dbc514141233bd2668dd5448fdfae6f3d481 |
| windows-2026-09-29.jsonl | 5063 | f89cc92634eaae4e92644271a92f843db0a650535e4be376149d8f204f8508be |
| usage-2026-09-29.jsonl | 21827 | 8c665c210cbc5df7ebc00c456b9b31d99fa48f6017ef833cc11d956a82b20db8 |
| windows-2026-09-30.jsonl | 5058 | 1dbd3b9121099912e15e346fb9e544854937ac1bf8d2dc48c9628457212bfea7 |
| usage-2026-09-30.jsonl | 12610 | 71b3adb9628b5476bb077834dcd21c2cf952175200a36169ba8b9d0b1bb98859 |
| windows-2026-10-01.jsonl | 7442 | 22555ade404b03a712485811be91cc1391d7a74112237ab1b1e6b30edb52bbed |
| usage-2026-10-01.jsonl | 13811 | b30162036003ff0cec3e3c043483e9a446edb25a7a07caf859ea35ab08c14bbd |

- Missing `usage` days (39): 2026-08-07 through 2026-08-08, 2026-08-11, 2026-08-16 through 2026-08-18, 2026-08-22 through 2026-09-20, 2026-09-22, 2026-09-27 through 2026-09-28.
- Missing `windows` days (58): 2026-07-30 through 2026-09-23, 2026-09-27 through 2026-09-28.

## Sanitized Offline Fixture Provenance

`tests/test_qa_shift.py` embeds the first row of each source below in recorder format, preserving counts and transport. The usage run identifier is consistently replaced with `envelope-wizard`; the distinct window generation-session identifier becomes `envelope-fixture`. The source rows are not asserted to correlate. Explicit edge variants assign a shared run, seat and TEST model, change dates/counts or create aggregate, missing, duplicate, conflicting and job-queue examples. No real reader, recorder, observation builder or connection is replaced with a mock. PostgreSQL proof seeds two sessions in `disposable_slot_database("qa640_759_measure")` using real manifest/usage recorders and proves the read connection rejects a write.

| Source Day | File | SHA-256 |
| --- | --- | --- |
| 2026-07-30 | usage-2026-07-30.jsonl | 375c66ffcba76cbfb20fae4b6db3b54135d58ae3cf1f97097dc83e0d2dc15f1a |
| 2026-09-24 | windows-2026-09-24.jsonl | 810021eaf733c3a5c047200feff89d1900ba91fbc1ab6358f299747dd002a525 |

## Verification

Commands below used `PYTHONPATH=$PWD`, `PYTHONUNBUFFERED=1` and `TMPDIR=$SCRATCH/tmp`. `$PY` and `$SCRATCH` are defined above. The scratch `run_gate.py` executes each listed command as a foreground child, captures its log, enforces a 570-second deadline and stops after 115 seconds with no new log output. Every run completed before either limit. The final runs remove inherited `PYTEST_ADDOPTS`; no suite or case was skipped to avoid a failure. The 481 and 749 skips are the offline suites’ declared environment markers; the PostgreSQL proof has no skips.

### Disposable PostgreSQL Proof

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_qa_shift.py tests/test_api/test_attempt_manifest_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_759_measure_*, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_778s4a_tests_* x6, qa640_800b_inspect_*, qa640_802_reported_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
217 passed, 9 warnings in 54.67s
```

### Offline Suite Outside API/Orrery

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2846 passed, 481 skipped, 8 warnings in 476.89s (0:07:56)
```

### Offline API/Orrery Suite

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1829 passed, 749 skipped, 7 warnings in 38.18s
```

### Reachability

```bash
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.50s
```

### Nested Pytest Harness Recheck

```bash
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py::test_review_injections_fail_the_gate_in_scratch_copy
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 5 warnings in 6.12s
```

The PostgreSQL audit’s `ReplicationConnection` caveat is the existing plugin limitation; the exercised normal psycopg2 connections are audited. Its fixture owns all listed disposable prefixes, including `qa885_transaction_writer_*`. The order’s new test opens only its `qa640_759_measure_*` clone.

### Earlier Runs and Wrapper Correction

The focused implementation check ran:
```bash
$PY -m pytest -q tests/test_qa_shift.py -k envelope --basetemp=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/pytest-focused
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
14 passed, 1 skipped, 56 deselected, 5 warnings in 0.40s
```

The first exact PostgreSQL proof command above also passed before rebase:
```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_759_measure_*, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_778s4a_tests_* x6, qa640_800b_inspect_*, qa640_802_reported_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
217 passed, 9 warnings in 50.15s
```

The first offline-core command was run before the base gained #1090’s additional tests. My wrapper exported `PYTEST_ADDOPTS=--basetemp=...`; a nested pytest whose working directory was inside that parent directory correctly rejected it. No repository test was changed to address this wrapper error. I removed the inherited option, kept `TMPDIR` in the authorized scratch directory, reran the failing test successfully, and reran the entire offline suite successfully on the rebased branch. Exact original failure:
```text
tests/test_prompt_lint.py::test_review_injections_fail_the_gate_in_scratch_copy
__main__.py: error: argument --basetemp: basetemp must not be empty, the current working directory or any parent directory of it (via PYTEST_ADDOPTS)
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_prompt_lint.py::test_review_injections_fail_the_gate_in_scratch_copy
1 failed, 2751 passed, 481 skipped, 8 warnings in 439.84s (0:07:19)
```

### Static Checks and Pre-existing Diagnostics

```bash
$PY -m black --check scripts/qa_shift/envelope_measure.py tests/test_qa_shift.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

```bash
$PY -m flake8 scripts/qa_shift/envelope_measure.py tests/test_qa_shift.py
$PY -m flake8 "$SCRATCH/baseline/tests/test_qa_shift.py"
```

Both flake8 invocations exit 0 with no output.

```bash
git show origin/main:tests/test_qa_shift.py > "$SCRATCH/baseline/tests/test_qa_shift.py"
$PY -m mypy --explicit-package-bases scripts/qa_shift/envelope_measure.py tests/test_qa_shift.py
$PY -m mypy --explicit-package-bases "$SCRATCH/baseline/tests/test_qa_shift.py"
```

Branch output (exit 1):
```text
tests/test_qa_shift.py:176: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1062: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1062: note: Possible overload variants:
tests/test_qa_shift.py:1062: note:     def int(str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1062: note:     def int(str | bytes | bytearray, /, base: SupportsIndex) -> int
Found 2 errors in 1 file (checked 2 source files)
```

Extracted main output (exit 1):
```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/baseline/tests/test_qa_shift.py:176: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/baseline/tests/test_qa_shift.py:1062: error: No overload variant of "int" matches argument type "object"  [call-overload]
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/baseline/tests/test_qa_shift.py:1062: note: Possible overload variants:
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/baseline/tests/test_qa_shift.py:1062: note:     def int(str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/759-S2a/baseline/tests/test_qa_shift.py:1062: note:     def int(str | bytes | bytearray, /, base: SupportsIndex) -> int
Found 2 errors in 1 file (checked 1 source file)
```

The same two diagnostics occur on untouched lines 176 and 1062. The new script and added test lines have no diagnostics. This satisfies the work order’s **no new diagnostics** gate; pre-existing debt was not fixed. The new script has no main counterpart. Black formatting was also applied during implementation with `$PY -m black scripts/qa_shift/envelope_measure.py tests/test_qa_shift.py`. Commit hooks passed.

## Coordinator Handoff

No new owner question and no open implementation question. Existing 759-Q1 and its allowance-source ruling remain outside this order. The coordinator posts these numbers and their missing-evidence limits on #759. No migration number or fleet application, owner gateway restart, or UI rebuild is needed: only the measurement operator, its tests, registration, README and this evidence document changed. No product, runtime configuration, telemetry, schema, prompt or client change is included. This PR is not merged.
