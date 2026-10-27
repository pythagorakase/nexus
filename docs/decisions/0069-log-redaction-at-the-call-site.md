---
status: canonical
sources:
  - nexus/api/native_structured_output.py
  - nexus/api/wizard_chat.py
  - scripts/api_openai.py
  - scripts/api_anthropic.py
  - scripts/api_openrouter.py
verified_commit: "70a1ff95104eb89c4362993e7889021deef72723"
---

# 0069: Log Redaction at the Call Site

**Kind:** decision
**Links:** #842, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/842#issuecomment-6423079832.

> - **842-D1.** How is ruling 43 ("INFO and above redact") implemented: by moving text to DEBUG at each call site, or by a logging filter that masks message bodies? Decision: call-site demotion. Story and player text moves to `logger.debug`, and a metadata-only line stays at the original level. No masking filter. Basis: ruling 43 (DEBUG may contain the text). Reversal cost: trivial.
> - **842-D2.** May ERROR and WARNING sites keep a short capped excerpt of the text? Decision: no. ERROR and WARNING log ids, lengths and exception classes. Any excerpt goes on a paired DEBUG line. The exception is where the structured-output privacy contract (`nexus/api/native_structured_output.py:282-296`) already forbids payload text; those sites stay as they are. Basis: the critique's objection to the paired DEBUG excerpt in D2 and D4. Reversal cost: trivial.
> - **842-D3.** What counts as story and player text for the redaction sweep? Decision: free text counts. That means player input, author's notes and directives, storyteller and model output, retrieval query text derived from them, story titles and wizard choice texts. Basis: critique item 5. Reversal cost: trivial.
> - **842-D4.** Must exception messages that may echo payload, such as `str(e)` of a Pydantic ValidationError or a provider error, be scrubbed at INFO and above? Decision: no generic scrubber. Sites that format payload-bearing exceptions (`nexus/api/wizard_chat.py:906` and the others the critique names) log the exception class and a length at INFO or above, and log `str(e)` at DEBUG. Basis: the critique. Reversal cost: trivial.
> - **842-D5.** How is the redaction enforced so new sites do not regress? Decision: an AST test covers `nexus/` and also `scripts/api_openai.py`, `scripts/api_anthropic.py` and `scripts/api_openrouter.py`. It rejects INFO-or-higher logger calls whose arguments reference a declared list of story-text names. An explicit allowlist of metadata-only uses, such as presence flags like `" [with note]"`, settles false positives in advance. Basis: critique items 2 and 4. Reversal cost: delete the test.
> - **842-D6.** Should the QA kit's isolated gateway run at DEBUG to keep the query text that INFO lines carried before? Decision: no change to the QA kit's isolated configs. A probe that needs the text sets `level = "DEBUG"` in its own config. Basis: the map's default. Reversal cost: trivial.
> - **842-D7.** Is a separate log path tunable still owed, as sketch item 1 named it? Decision: no. `[runtime.logs]` and the runtime home own the path. Basis: already landed. Reversal cost: none.
> - **842-D8.** Do the dated QA probes' in-process gateways (`card_identity_probe`, `long_absence_probe`) need the shared dictConfig before #842 closes? Decision: yes. They use the shared dictConfig, as slice 842-S7. Basis: sketch item 2. Reversal cost: trivial.
> - **842-D9.** Are the CLI-only FileHandlers of standalone `main()` scripts part of #842? Decision: no. They are out of #842's scope. Basis: they are not runtime services. Reversal cost: none.
> - **842-D10.** Does the cause of the `/api/local-models/status` HTTP 500 storm belong to #842? Decision: no. Rotation bounds the disk. A reproduction goes to a new issue. Basis: the map's default. Reversal cost: none.
> - **842-D11.** How does 842-S6 fix `_stop_pid`? Decision: 842-S6 uses `log_capture.process_running`, which reaps an exited child, in place of `_pid_alive` in `_stop_pid`. Basis: the map's default. Reversal cost: trivial.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
