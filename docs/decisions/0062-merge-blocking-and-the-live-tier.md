---
status: canonical
sources:
  - tests/test_golden_path_live.py
verified_commit: "b0e9cb77af52a22673113b4910d027cd189cf281"
---

# 0062: Merge Blocking and the Live Tier

**Kind:** decision
**Links:** #816, Loom sequence 43

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/816#issuecomment-6421994645.

> - **816-Q1, failing offline tests:** *Block merges and direct pushes to main* (`block_all`), with the owner's note: "I don't know. Choose for me." The coordinator's choice under that note keeps the selected option: the offline test workflow becomes a required status check for pull requests into `main`, and branch protection refuses direct pushes. The agents' landing path (squash merges through pull requests) does not change. Reversal cost: one branch-protection edit.
> - **816-Q2, the paid live-provider tier:** *Only on this Mac* (`mac_only`). The live-provider tier never runs in the cloud, and no provider key is stored as a GitHub secret. The per-run spend cap was left blank; the coordinator sets it in the slice order from the measured cost of the standing release gate (`tests/test_golden_path_live.py`) and records the number here when the slice lands.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
