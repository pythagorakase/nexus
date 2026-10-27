---
status: canonical
sources:
  - nexus.toml
  - docs/cli_reference.md
  - nexus/cli.py
  - nexus/cli_contract.py
verified_commit: "70a1ff95104eb89c4362993e7889021deef72723"
---

# 0073: The Envelope Migration Plan

**Kind:** decision
**Links:** #815, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/815#issuecomment-6423086585.

> - **815-D1.** Under the remote profile, which route do `up` and `status` probe? Decision: Remote up/status probe GET /health only (player plane, reports plane since PR #1147). Basis: Decision 815-Q5 and the non-widening rule. Reversal cost: Trivial.
> - **815-D2.** Does local or external `nexus status` with the gateway down change its exit code too? Decision: Local and external `status` keep exit 0 with the nested runtime error; only the remote profile changes. Basis: A stopped local runtime is a valid report. Reversal cost: Trivial.
> - **815-D3.** How does remote `up` classify a non-2xx or access-rejected probe answer? Decision: Remote `up` classifies through the S1 classifier: non-2xx is `api_error`; 401/403/unfollowed 3xx is `config_error`. Basis: PR #1060 contract. Reversal cost: Trivial.
> - **815-D4.** What is `data` for a migrated command whose handler returns `{success: true, ...}`? Decision: For a migrated command, `data` = the handler's result minus the `success` key; other keys unchanged. Basis: Least caller change. Reversal cost: None.
> - **815-D5.** How do report-style commands that fail by policy fit the envelope? Decision: A failing report-style command (`doctor`, `init`, `trait-audit --fail-on-remainders`) is the stderr failure envelope (code `domain_failure`, exit 1) with the full report passed verbatim as `partial`; a passing one is `{ok: true, data: report}`. Basis: Map default plus the critique's verbatim-partial amendment. Reversal cost: Trivial.
> - **815-D6.** Is the envelope migration one PR or several, and in what order? Decision: The envelope migration lands as four sequential PRs: S6a runtime and local-ledger family (this order, after S4), then S6b play/slot family, S6c database/local-file family, S6d finish (allow-list removed, parser-walking test, docs, S9 `nexus.toml` comment drift and the re-stamps). Basis: Reviewable size. Reversal cost: None.
> - **815-D7.** Does the generated `docs/cli_reference.md` gain a per-command JSON-shape column? Decision: `docs/cli_reference.md` gains no per-command JSON-shape column; each slice regenerates it. Basis: After S6d every command uses the envelope. Reversal cost: Trivial.
> - **815-D8.** Must #815 wait for #769 (spoiler gating, 815-R8) before it closes? Decision: #815 closes after S4, S6a-d and S9; spoiler gating (815-R8) is tracked solely on #769, superseding the 815-S2 order's "R8 stays open until #769 lands". Basis: Map default; #769 already names the dependency. Reversal cost: Reopen.
> - **815-D9.** Who reclassifies `clear`, `lock`, `unlock` and `model --set/--clear` from `http` to `operator_api`? Decision: #824's listener-split slice reclassifies `clear`, `lock`, `unlock` and `model --set/--clear` (built in parallel this wave). Basis: Decision 815-Q3. Reversal cost: None.
> - **815-D10.** Does #815 add an inspect family for queues? Decision: No queue inspect family; `nexus jobs --slot N --json` serves queues and moves to `{ok, data}` in S6c. Basis: Map default. Reversal cost: None.
> - **815-D11.** Does the `nexus.toml` comment drift deferred by S2 and S3 belong to #815? Decision: The `nexus.toml` comment drift deferred by S2/S3 belongs to #815 and lands with S6d. Basis: Critique. Reversal cost: None.
> - **815-D12.** What happens to callers the repository cannot update, such as the gitignored local `nexus-cli` skill? Decision: The coordinator updates the gitignored local `nexus-cli` skill's jq examples when S6b lands. Basis: Outside the repository. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
