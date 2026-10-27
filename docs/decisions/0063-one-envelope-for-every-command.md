---
status: canonical
sources:
  - nexus/cli.py
  - nexus/cli_contract.py
verified_commit: "571f982b2fa375acd4b52c51c76c29f4663f7242"
---

# 0063: One Envelope for Every Command

**Kind:** decision
**Links:** #815, Loom sequence 43

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/815#issuecomment-6421995432.

> - **815-Q1, scripts during the JSON transition:** *Move every command* (`migrate_all`). Existing scripts may require coordinated updates: every command moves to the one `{ok, data}` envelope, and the scripts and QA-kit callers that parse CLI output are updated in the same change that moves the command they call.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
