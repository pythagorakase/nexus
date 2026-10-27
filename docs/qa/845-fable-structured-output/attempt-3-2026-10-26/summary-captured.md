# Attempt 3 Summary (captured from the probe's output; the raw files were lost)

pytest's basetemp rotation removed `pytest-677/fable_8450` before the coordinator copied it (other pytest runs on the machine advanced the counter past the three kept directories). These tables are the probe's `summary.md` and `turns.jsonl` as printed and read at 20:56 on 2026-10-26, verbatim where captured.

- Verdict: `incomplete`
- Stop reason: `turn_failed`
- Turns completed: 1 of 12 (two attempted)
- Worst case per turn (`worst`): 8
- Fable calls: 7 against `CALL_CAP` 30
- Excess over `CALL_CAP`: 0

## Turns

| Turn | Input | Exit | Success | Code | Session | Seconds |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | choice | 0 | True |  | 3bb3ac66-6271-4f2b-9567-4da086d1f36c | 187.309 |
| 2 | text | 1 |  | domain_failure | 5fd07ad8-ab3d-4d79-80e5-b300eff4f2c3 | 230.018 |

## Fable Attempts

| Turn | Seat | Attempt | Outcome | In | Out | Transport | Stop | Blocks | Exception | Class | Flake | ts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | skald_writer | 1 | accepted | 55713 | 2874 |  |  |  |  |  | False | 2026-10-27T01:50:50.380723Z |
| 1 | gaia | 1 | rejected_validation | 57581 | 4975 | prompted | end_turn | thinking,text | ModelRetry | validation | False | 2026-10-27T01:51:57.209427Z |
| 1 | gaia | 2 | accepted | 58325 | 2905 |  |  |  |  |  | False | 2026-10-27T01:52:37.502325Z |
| 2 | skald_writer | 1 | accepted | 64421 | 3034 |  |  |  |  |  | False | 2026-10-27T01:53:50.249779Z |
| 2 | gaia | 1 | rejected_validation | 65972 | 4034 | prompted | end_turn | thinking,text | ValidationError | validation | False | 2026-10-27T01:54:46.248554Z |
| 2 | gaia | 2 | rejected_validation | 66105 | 3783 | prompted | end_turn | thinking,text | ModelRetry | validation | False | 2026-10-27T01:55:40.681772Z |
| 2 | gaia | 3 | accepted | 66806 | 3422 |  |  |  |  |  | False | 2026-10-27T01:56:27.210050Z |

`turns.jsonl` as read:

```
{"index": 1, "input_kind": "choice", "exit_code": 0, "success": true, "code": null, "session_id": "3bb3ac66-6271-4f2b-9567-4da086d1f36c", "seconds": 187.309}
{"index": 2, "input_kind": "text", "exit_code": 1, "success": null, "code": "domain_failure", "session_id": "5fd07ad8-ab3d-4d79-80e5-b300eff4f2c3", "seconds": 230.018}
```
