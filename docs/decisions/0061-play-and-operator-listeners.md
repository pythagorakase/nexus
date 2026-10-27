---
status: canonical
sources:
  - nexus/api/narrative.py
  - docs/runtime.md
verified_commit: "e058005f8df04e4c5807f695eded4a68657e9f05"
---

# 0061: Play and Operator Listeners

**Kind:** decision
**Links:** #824, Loom sequence 43

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/824#issuecomment-6421993908.

> - **824-Q1, which side keeps port 8002:** *The play side keeps 8002* (`play_keeps`). The player projection serves today's address, so the Cloudflare tunnel's ingress does not change. The operator projection moves to its own loopback listener on a new configured port, and the local commands, the desktop shell and the SSH recipe re-point to it.
> - **824-Q2, remote administration:** *A second Cloudflare-protected address* (`second_tunnel`). The operator projection becomes reachable away from home through a second hostname on the existing tunnel, behind its own Access policy, and never through the player hostname.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
