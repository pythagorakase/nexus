# Scratchpad Audit Kit

Instruments for commissioned live audits of the Skald–Gaia correspondence
channel (the private writer/Gaia letters and their digest compactions).

An audit is a one-off adversarially-steered campaign run against an isolated
gateway lane, driven by a frozen charter handed to a Codex operator. Charters
are authored per run (they encode the specific mission — behavioral audit,
compaction proof, regression check) and archived with the evidence; this kit
holds what persists between runs.

## Contents

- `rubric.md` — the anchored scoring instrument (v2.2, 0–4 per dimension,
  six dimensions plus the digest-fidelity appendix). Version lineage and
  cross-run score mapping are documented in the rubric header.

## Audit Discipline

- Runtime artifacts only: an audit never edits tracked files, commits, or
  writes to the database outside public surfaces. Evidence archives live in
  ignored `temp/` (`temp/scratchpad_audit_*` / `temp/compaction_audit_*`).
- Model routes are pinned through an ignored runtime config derived from
  `nexus.toml`; `tests/test_qa_shift.py` enforces the pinnable-route roster.
- Scoring is performed blind where possible (the scorer sees letters and
  rubric, not prior scores or reports), with the caveat that rubric anchors
  quote past corpora — true validation is scoring a *fresh* corpus.
- A rubric revision must pass the validation criteria at the bottom of
  `rubric.md` before replacing the tracked version. Any judgment call a
  scorer had to invent mid-score is a rubric defect and goes back into the
  document.

## Mid-Campaign Seeds

Post-audit database dumps that are useful as depth seeds for the nightly QA
shift go to `temp/qa_seeds/` (see `scripts/qa_shift/README.md`, "Seeds").
