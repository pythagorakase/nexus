---
status: canonical
sources:
  - nexus/maintenance/new_story_setup.py
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0082: Extension Versions in the Genesis Artifact

**Kind:** decision
**Links:** #810, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/810#issuecomment-6423201171.

> - **810-S4a-ext.** How does the genesis artifact treat the PostgreSQL extension versions (postgis, vector)? Decision: the manifest records each extension's name AND the version observed when the artifact was generated; `genesis build` installs the server's default versions and fails loudly when an installed version differs from the manifest, unless the operator passes an explicit `--allow-extension-drift` flag, in which case the build receipt records the drift. No update of `NEXUS_template`'s extensions is part of this slice. Basis: the fail-loud doctrine (a silent version change is the defect the IDF analyzer key already guards against on the text side), the owner's standing rule against graceful fallbacks, and least change to the template. Reversal cost: one flag and one manifest field.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
