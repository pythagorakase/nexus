---
status: canonical
sources:
  - nexus/runtime/home.py
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0060: The Runtime Home Move

**Kind:** decision
**Links:** #820, Loom sequence 42

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/820#issuecomment-6156196220.

> - **820-Q2, the old files after the move:** *The originals are deleted after verification* (`delete`).
> - **820-Q9, configuration updates after the move:** *Automatic* (`automatic`).
> - **820-Q10, model folders in the move:** *Move only the folders a setting names* (`move_used`). Owner's note: "For the models that aren't named anywhere, we can probably delete them. I'm willing to wait and see if anything breaks without them."
> - **820-Q11, uploaded images on a wipe:** *Delete them with the slot* (`delete`).

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
