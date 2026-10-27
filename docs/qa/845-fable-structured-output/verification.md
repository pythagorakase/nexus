# 845-S3: The Paid Fable Two-Pass Probe (Coordinator Run, 2026-10-26)

Branch `claude/845-s3-probe` from main `d295eef0`. Lane 8014. Environment: `NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_845_PROBE=1 NEXUS_GATEWAY_PORT=8014`, with `NEXUS_RUNTIME_CONFIG`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. `CALL_CAP` is the committed 30.

## Preparation (two clone-only deletes, commits 0b58260e and 77fa8883)

- The qa640_845 data clone inherits save_04's nine queued `character_experience_jobs`; the gateway's drain would run them as paid OpenAI calls outside `CALL_CAP`. The probe deletes them on the clone before the gateway starts.
- save_04 holds one provisional incubator draft (session `5470b738…`, 2026-08-21) whose applied tags include `debt_pulse_active`, which `tag_category_registry` now deprecates for characters (#811). The gateway auto-approves and commits that draft on the next `continue`, and the commit refuses it with HTTP 500 before any model call (attempt 2 below). The probe deletes the draft on the clone only; save_04 is untouched. Recorded on #811: slot 4's own next turn hits the same error until the allowlist lands.

## Attempts

| Attempt | Result | Fable calls | Cause |
| --- | --- | --- | --- |
| 1 | skipped | 0 | `NEXUS_RUN_LIVE_LLM=1` was not set (the live marker's opt-in) |
| 2 | turn 1 failed, `api_error` | 0 | the inherited draft's `debt_pulse_active` tag refused at commit (above) |
| 3 | turn 1 completed, turn 2 `domain_failure` | 7 | after Gaia's accepted attempt 3, `ValueError: Cannot exit non-present character 'Kessa Brin' (id=0)` in `nexus.lore.logon`; the turn is lost after acceptance (#1173) |

Attempt 3's evidence is in `attempt-3-2026-10-26/`: `summary-captured.md` (the probe's summary and turn records as captured from its output) and `gateway-excerpt.txt` (the rejection, usage and error lines). The raw files were lost to pytest's basetemp rotation before they were copied; the next run passes `--basetemp` under the coordinator's scratchpad so the directory survives.

## What Attempt 3 Showed

- Verdict `incomplete`, stop reason `turn_failed`, one turn completed and a second attempted, 7 Fable calls against the cap of 30, no excess.
- Turn 1: `skald_writer` accepted (in 55,713 / out 2,874); `gaia` attempt 1 rejected by closed-registry validation (`ModelRetry`, transport `prompted`, stop `end_turn`, blocks `thinking,text`), attempt 2 accepted.
- Turn 2: `skald_writer` accepted; `gaia` attempt 1 rejected with `ValidationError`: `Invalid JSON: control character (\u0000-\u001F) found while parsing a string at line 2 column 0 (json_invalid)` (transport `prompted`, stop `end_turn`, blocks `thinking,text`, 4,034 output tokens); attempt 2 `ModelRetry` (closed-registry validation); attempt 3 accepted (in 66,806 / out 3,422); then the presence-exit `ValueError` ended the turn.
- No rejection of the #845 class (`did not include JSON output`): the `Flake` column is `False` on every row. The one structured-output defect seen is the control character inside a JSON string, repaired by the loop.

## Status

S3 is not complete: a `null` verdict needs twelve turns. The run stopped on a defect outside #845 (the presence-exit refusal after wire acceptance, #1173); S3 reruns after that fix lands, with the cap reset to 30. 845-S4 is not triggered by this evidence.
