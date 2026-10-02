---
status: canonical
sources:
  - tests/test_doc_front_matter.py
  - README.md
verified_commit: "41783c1dfcb16ff94e31e26bf2723b597b97803b"
---

# Document Status and the Decision Ledger

GitHub issues and pull requests track active work. This directory holds what
must outlive them: durable rulings, the alternatives they rejected, parked work,
and the evidence that would reopen either. Documents elsewhere in the repository
declare whether they describe the current system through the front matter
defined here.

## Document Front Matter

A classified document begins with a YAML block, before its title:

```yaml
---
status: canonical
sources:
  - nexus/api/narrative.py
  - nexus/jobs/scheduler.py
verified_commit: "ed9531e3418f695b9e47b5c9e7fdc897ac4ecdcd"
---
```

| Key | Required | Contract |
|---|---|---|
| `status` | always | `canonical`, `historical`, or `superseded`. |
| `verified_commit` | always | The commit whose tree the document was last checked against: 7 to 40 lowercase hex characters, quoted so YAML keeps it a string. A commit cannot name itself, so this is usually the base of the change that edits the document. When it changes, it must name the merge base with `origin/main` or one of its ancestors, and descend from the value it replaces, so it survives a squash merge. |
| `sources` | when `canonical` | Repository-relative paths of the files that the document describes. Directories are not accepted. Every path must exist. Optional for the other statuses. |
| `superseded_by` | when `superseded` | The repository-relative path of the replacing document, which must list this document under `supersedes`. The replacement may itself be superseded later; links are never rewritten, and following them must reach a document that is not superseded. Not allowed with any other status. |
| `supersedes` | no | Documents this one replaces. Each must be `superseded` with `superseded_by` naming this document. |

No other keys are accepted.

### Status Values

- **canonical** — describes the current system. Any change to a listed
  source re-verifies the document and moves its `verified_commit` in the same
  pull request.
- **historical** — a record of retired or completed work: blueprints for
  modules that were never built, dated plans and checkpoints, and notes on
  configurations since replaced. Kept for provenance, never edited to track the
  current system, and labeled historical wherever `README.md` references it.
- **superseded** — replaced by the document named in `superseded_by`, whose
  own successor, if any, continues the chain. `README.md` never references it.

Documents without front matter are unclassified. Classify a document when you
verify it against its sources or retire it. Generated documents, such as
`docs/orrery_packages.md`, carry no front matter; their generators' tests check
their freshness.

### Scope and Validation

`tests/test_doc_front_matter.py` checks every Markdown file at the repository
root and under `docs/`: the keys and values above, that every `sources` path
exists, that supersession links agree in both directions and every chain ends
at a document that is not superseded, and that every Markdown path `README.md`
references, including `./`-relative links, exists inside the repository, is not
superseded, and is labeled historical on its line when its status is
historical. It also fails when the branch's diff against its merge base with
`origin/main`, uncommitted and untracked files included, touches a source that
a document canonical at that merge base or now declares at either point, unless
the document's `verified_commit` changed. It fails rather than skips when that
history is missing: no git checkout at the repository root, a shallow clone, no
`origin/main`, or no merge base.

## Decision and Parked-Work Records

Each record is one file, `docs/decisions/NNNN-short-slug.md`. `NNNN` is the
next unused four-digit number, and numbers are never reused. A record carries
the document front matter above: `canonical` while its ruling stands or its
work stays parked, `superseded` when a later record overturns it, and
`historical` once parked work is picked up or the governed code is gone. Its
`sources` are the paths the ruling governs.

```markdown
# NNNN: Title in Chicago Title Case

**Kind:** decision | parked
**Links:** #issue, PR #number, or Loom

## Ruling

The decision, or what is parked and why.

## Rejected Alternatives

- Each alternative considered, with the reason it lost.

## Reopening Criteria

- The observable evidence that would reopen the ruling or unpark the work.
```

Records hold rulings, not task lists; the linked issue or pull request keeps
execution state.

## Records

None yet.
