---
status: canonical
sources:
  - nexus/runtime/logging_config.py
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0064: Story Text in Diagnostic Logs

**Kind:** decision
**Links:** #842, Loom sequence 43

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/842#issuecomment-6421996124.

> - **842-Q1, story text in diagnostic logs:** *DEBUG may contain the text* (`debug_may`). Explicitly enabled diagnostic logging at DEBUG may contain story and player text; INFO and every higher level redact it.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
