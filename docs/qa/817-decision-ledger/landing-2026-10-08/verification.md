# Decision Ledger Final Landing Verification

The final landing review ran on clean commit
`658f24fcb4188baa6496b07decc7dd19b90fb199`, after merging runtime main
`d70a1991210ce16aef5d6f9b57b0ec563ee1d164`. The following evidence commit adds
only this directory. No implementation correction was needed.

All 55 records and the decisions README now use that final main SHA. Compared
with ledger head `734d7b4d95a3d031090de25a78482e457d05cc71`, their only changes
are the 56 verification stamps and the five unquoted baseline `Source:` SHA
lines in 0025–0029. All quotation text, other body text, source lists, statuses,
and reciprocal 0030 → 0005 supersession links are preserved. The 43 original
files under the ledger QA directory and shared campaign evidence directory are
byte-identical. [Preservation proof](preservation.json) records these checks.

## Review Against Final Runtime Sources

No stale unquoted implementation or status claim was found. The existing
[integration review](../../resume-2026-10-08/review-ledger-integration.md)
continues to apply:

- Records 0006 and 0022 preserve choice ownership and the golden-master ruling;
  slot identity additions do not change those contracts.
- Records 0009, 0010, 0024, and 0034 preserve the token-only ledger, recorded
  seat ruling, rejection of canonical memory-store unification, and
  correspondence lifecycle. Receipt, TEST-provider, travel, and evaluation
  configuration changes introduce no contrary ruling. The dated refutation in
  0024 remains historical source text, not an assertion that all old runtime
  configuration options remain available.
- Record 0040 preserves Build/import-as-fork without claiming completed bundle
  import. Records 0041 and 0042 concern actor rank and foreground intentions;
  travel routing does not alter them. Record 0048 selects Natural Earth and
  required place-stub coordinates without claiming later region-genesis work
  is complete.
- Parked records 0025–0029 still describe unchanged schema-baseline entries and
  deferred manifests. No inspected change drops those objects or supplies an
  invented contract. Record 0030 remains superseded by 0005.

The final #816 seeder fixes use explicit singleton exceptions, parse help before
default configuration, and name the selected target in success output. They
contradict none of these rulings and do not change a declared ledger source.

The final #810 production file `scripts/regenerate_embeddings.py` at committed
head `1c418ad5e5db6a4e85ed6692b4c7660504006dd8` is byte-identical to reviewed
blob `cb9e181f179cbb8f476df1e7c441c13cd01581b5`, including in this landing
tree. Requested supported ANN prerequisites are checked before model loading,
lazy table creation, or vector deletion; resume/chunk entry points preserve the
refusal and the high-dimension exact-search exemption remains. The script is
not a declared ledger source. It does not unify canonical memory storage
(0024), define the six parked SQL helper contracts (0029), or alter story
initialization (0040). The schema baseline, deferred manifest, MEMNON database
and embedding helpers, and story initializer remain unchanged from the tested
integration in that lane. Its exception-baseline removal is unrelated to the
parked schema baseline. No quotation or source-list rewrite is warranted.

## Final Proof

Commands ran from this worktree with `PYTHONPATH=$PWD` and the shared
`/Users/pythagor/nexus/.venv/bin/python` as `$PY`, at `nice -n 15`. PostgreSQL,
live-model, slot, and gateway environment opt-ins were unset for pytest.

```text
PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/quote_audit.py $PWD
distinct objects fetched: 90 (45 comments, 45 issues)
all 55 records match (merge base d70a1991210ce16aef5d6f9b57b0ec563ee1d164)

PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/table_check.py $PWD
mismatches: 0

PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/source_sweep.py $PWD
tracked files cited but not in sources: 0

env -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES -u NEXUS_GATEWAY_PORT \
  -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY \
  -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 14.82s
```

Full outputs: [quote audit](quote-audit.txt), [table audit](table-check.txt),
[source sweep](source-sweep.txt), and [focused tests](focused.txt). The live
quote audit is a point-in-time comparison. The source sweep's five external
references (`~/.codex/config.toml`, `doctrine.md`, and
`coverage_critique.md`) are the previously documented untracked references;
they are not missing tracked source declarations. No owner configuration file
was read to resolve them.

[Static checks](static-checks.txt) passed: Black and flake8 for the validator
and three audit scripts, mypy for `tests/test_doc_front_matter.py`, and the
exception disposition/shrink-only baseline check. Normal applicable commit
hooks passed on the final merge; hooks also run for the evidence commit.

The ledger validator and audit programs are unchanged from the tested assembled
integration `f291dc792e4b071a4cc4940101f6c40871ea8b7b`. Its
[serial PostgreSQL gate](../../resume-2026-10-08/verification.md#serial-postgresql-full-gate)
passed with 6984 tests and 72 skips, with all three guard summaries clean. That
is assembled-integration evidence; no new standalone full gate is claimed here.
The earlier negative controls and all original audit artifacts remain intact.

This landing refresh changes documentation and evidence only. It performs no
owner database, secret, service, model, or fleet operation and makes no paid
provider call. The coordinator owns PR publication, merge, and fleet landing.

Codex — GPT-6
