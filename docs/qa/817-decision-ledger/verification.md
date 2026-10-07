# 817-S3 Verification: Decision-Ledger Backfill

Branch `claude/817-decision-ledger`, merge base with `origin/main`
`b0da93eaedb4d1661af50742440e7988c7e48185`. Every record and the ledger
README carry that merge base as `verified_commit`.

## 819-S3 Merge Check

819-S3 (#1109, `e0966c6d`) landed before this branch was cut, so rows
0025-0029 were written from `config/schema_docs_baseline.json` at the merge base.

```text
$ git grep -n "Legacy Columns Without Evidence" origin/main -- docs/dead_retrieval_subtraction.md
origin/main:docs/dead_retrieval_subtraction.md:182:## Legacy Columns Without Evidence
e0966c6d Route the legacy schema-docs baseline debt into #813's manifest (#819 S3) (#1109)
e0966c6d is an ancestor of origin/main
```

## Quote Audit

`docs/qa/817-decision-ledger/quote_audit.py` fetches every cited comment and
issue fresh with `gh api repos/pythagorakase/nexus/issues/comments/<ID>` and
`gh api repos/pythagorakase/nexus/issues/<N>`, and reads the raw Markdown from
the JSON `.body` (the same text as `-q .body`, without the newline `gh` appends).
It does not import the generator. For each record it:

- parses every block that follows a `Source: <URL>.` line and a blank line;
- recomputes the expected block from the fetched text: the whole comment body;
  for a relay, the first maximal run of `^>( |$)` lines after the first line
  containing `verbatim` (case-insensitive), or lines 3-10 of 5817898265 (the
  #737 fence); the `## Risks` paragraph of #837 and #839; the
  `**Amendment / carry-forward:**`, `**Summary:**` and `REFUTED` verdict lines of
  the #849 section; the 819-Q1 `Decision:` line, the `<key>: <reason>` lines of
  `config/schema_docs_baseline.json` and the #819 Summary sentence;
- strips `^> ?` from each quoted line (the #737 fence is compared as it is) and
  asserts equality, not containment, with the whole expected text (for a relay
  block, the run with its own `> ` removed), and also asserts that the quoted
  lines equal the expected lines under the quoting rule byte for byte;
- checks the source URL and section of each block, the block count, that every
  inline quotation in Rejected Alternatives and Reopening Criteria occurs
  verbatim in the linked issue or cited comments, and that a relay record has
  one bullet per "not chosen" occurrence (0033 and 0044 take the order's
  wording).

Run: `PYTHONPATH=$PWD $PY docs/qa/817-decision-ledger/quote_audit.py $PWD`

```text
| Record | Sources | Blocks | Inline quotes | Result |
|---|---|---|---|---|
| 0001 | https://github.com/pythagorakase/nexus/issues/850#issuecomment-5556777011 | 1 | 2 | MATCH |
| 0002 | https://github.com/pythagorakase/nexus/issues/851#issuecomment-5556777557 | 1 | 1 | MATCH |
| 0003 | https://github.com/pythagorakase/nexus/issues/852#issuecomment-5556778630 | 1 | 2 | MATCH |
| 0004 | https://github.com/pythagorakase/nexus/issues/853#issuecomment-5565300043 | 1 | 1 | MATCH |
| 0005 | https://github.com/pythagorakase/nexus/issues/854#issuecomment-5565301694 | 1 | 2 | MATCH |
| 0006 | https://github.com/pythagorakase/nexus/issues/855#issuecomment-5565439618 | 1 | 1 | MATCH |
| 0007 | https://github.com/pythagorakase/nexus/issues/856#issuecomment-5800949507 | 1 | 1 | MATCH |
| 0008 | https://github.com/pythagorakase/nexus/issues/857#issuecomment-5800951144 | 1 | 1 | MATCH |
| 0009 | https://github.com/pythagorakase/nexus/issues/858#issuecomment-5800952750 | 1 | 1 | MATCH |
| 0010 | https://github.com/pythagorakase/nexus/issues/859#issuecomment-5800955522 | 1 | 0 | MATCH |
| 0011 | https://github.com/pythagorakase/nexus/issues/860#issuecomment-5565414838 | 1 | 0 | MATCH |
| 0012 | https://github.com/pythagorakase/nexus/issues/861#issuecomment-5565410350 | 1 | 1 | MATCH |
| 0013 | https://github.com/pythagorakase/nexus/issues/786#issuecomment-5915495413 | 1 | 1 | MATCH |
| 0014 | https://github.com/pythagorakase/nexus/issues/792#issuecomment-5915496685 | 1 | 1 | MATCH |
| 0015 | https://github.com/pythagorakase/nexus/issues/832#issuecomment-5915670598 | 1 | 1 | MATCH |
| 0016 | https://github.com/pythagorakase/nexus/issues/837 | 1 | 1 | MATCH |
| 0017 | https://github.com/pythagorakase/nexus/issues/839 | 1 | 1 | MATCH |
| 0018 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0019 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0020 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0021 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0022 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0023 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0024 | https://github.com/pythagorakase/nexus/issues/849 | 4 | 0 | MATCH |
| 0025 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | 3 | 0 | MATCH |
| 0026 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | 3 | 0 | MATCH |
| 0027 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | 3 | 0 | MATCH |
| 0028 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | 3 | 0 | MATCH |
| 0029 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | 3 | 0 | MATCH |
| 0030 | https://github.com/pythagorakase/nexus/issues/476#issuecomment-5035538982 | 1 | 0 | MATCH |
| 0031 | https://github.com/pythagorakase/nexus/issues/479#issuecomment-5035539149 | 1 | 0 | MATCH |
| 0032 | https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035539341, https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035716638 | 2 | 0 | MATCH |
| 0033 | https://github.com/pythagorakase/nexus/issues/566#issuecomment-5070275155 | 1 | 1 | MATCH |
| 0034 | https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113803006, https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113867184, https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113874777 | 3 | 0 | MATCH |
| 0035 | https://github.com/pythagorakase/nexus/issues/737#issuecomment-5817898265 | 1 | 0 | MATCH |
| 0036 | https://github.com/pythagorakase/nexus/issues/750#issuecomment-5915474062 | 1 | 0 | MATCH |
| 0037 | https://github.com/pythagorakase/nexus/issues/756#issuecomment-5915474827 | 1 | 1 | MATCH |
| 0038 | https://github.com/pythagorakase/nexus/issues/759#issuecomment-5915475165 | 1 | 1 | MATCH |
| 0039 | https://github.com/pythagorakase/nexus/issues/780#issuecomment-5915474444 | 1 | 1 | MATCH |
| 0040 | https://github.com/pythagorakase/nexus/issues/822#issuecomment-5915475477 | 1 | 1 | MATCH |
| 0041 | https://github.com/pythagorakase/nexus/issues/781#issuecomment-5915494108 | 1 | 1 | MATCH |
| 0042 | https://github.com/pythagorakase/nexus/issues/782#issuecomment-5915494408 | 1 | 1 | MATCH |
| 0043 | https://github.com/pythagorakase/nexus/issues/783#issuecomment-5915494698 | 1 | 0 | MATCH |
| 0044 | https://github.com/pythagorakase/nexus/issues/784#issuecomment-5915495072 | 1 | 1 | MATCH |
| 0045 | https://github.com/pythagorakase/nexus/issues/787#issuecomment-5915495765 | 1 | 0 | MATCH |
| 0046 | https://github.com/pythagorakase/nexus/issues/788#issuecomment-5915496016 | 1 | 1 | MATCH |
| 0047 | https://github.com/pythagorakase/nexus/issues/789#issuecomment-5915496362 | 1 | 0 | MATCH |
| 0048 | https://github.com/pythagorakase/nexus/issues/840#issuecomment-5915497021 | 1 | 2 | MATCH |
| 0049 | https://github.com/pythagorakase/nexus/issues/841#issuecomment-5915497315 | 1 | 2 | MATCH |
| 0050 | https://github.com/pythagorakase/nexus/issues/767#issuecomment-5915668877 | 1 | 0 | MATCH |
| 0051 | https://github.com/pythagorakase/nexus/issues/768#issuecomment-5915669173 | 1 | 1 | MATCH |
| 0052 | https://github.com/pythagorakase/nexus/issues/770#issuecomment-5915669468 | 1 | 1 | MATCH |
| 0053 | https://github.com/pythagorakase/nexus/issues/776#issuecomment-5915669789 | 1 | 1 | MATCH |
| 0054 | https://github.com/pythagorakase/nexus/issues/777#issuecomment-5915670142 | 1 | 1 | MATCH |
| 0055 | https://github.com/pythagorakase/nexus/issues/838#issuecomment-5915671010 | 1 | 1 | MATCH |

Fetch commands:
gh api repos/pythagorakase/nexus/issues/476
gh api repos/pythagorakase/nexus/issues/479
gh api repos/pythagorakase/nexus/issues/480
gh api repos/pythagorakase/nexus/issues/566
gh api repos/pythagorakase/nexus/issues/617
gh api repos/pythagorakase/nexus/issues/737
gh api repos/pythagorakase/nexus/issues/750
gh api repos/pythagorakase/nexus/issues/756
gh api repos/pythagorakase/nexus/issues/759
gh api repos/pythagorakase/nexus/issues/767
gh api repos/pythagorakase/nexus/issues/768
gh api repos/pythagorakase/nexus/issues/770
gh api repos/pythagorakase/nexus/issues/776
gh api repos/pythagorakase/nexus/issues/777
gh api repos/pythagorakase/nexus/issues/780
gh api repos/pythagorakase/nexus/issues/781
gh api repos/pythagorakase/nexus/issues/782
gh api repos/pythagorakase/nexus/issues/783
gh api repos/pythagorakase/nexus/issues/784
gh api repos/pythagorakase/nexus/issues/786
gh api repos/pythagorakase/nexus/issues/787
gh api repos/pythagorakase/nexus/issues/788
gh api repos/pythagorakase/nexus/issues/789
gh api repos/pythagorakase/nexus/issues/792
gh api repos/pythagorakase/nexus/issues/819
gh api repos/pythagorakase/nexus/issues/822
gh api repos/pythagorakase/nexus/issues/832
gh api repos/pythagorakase/nexus/issues/837
gh api repos/pythagorakase/nexus/issues/838
gh api repos/pythagorakase/nexus/issues/839
gh api repos/pythagorakase/nexus/issues/840
gh api repos/pythagorakase/nexus/issues/841
gh api repos/pythagorakase/nexus/issues/849
gh api repos/pythagorakase/nexus/issues/850
gh api repos/pythagorakase/nexus/issues/851
gh api repos/pythagorakase/nexus/issues/852
gh api repos/pythagorakase/nexus/issues/853
gh api repos/pythagorakase/nexus/issues/854
gh api repos/pythagorakase/nexus/issues/855
gh api repos/pythagorakase/nexus/issues/856
gh api repos/pythagorakase/nexus/issues/857
gh api repos/pythagorakase/nexus/issues/858
gh api repos/pythagorakase/nexus/issues/859
gh api repos/pythagorakase/nexus/issues/860
gh api repos/pythagorakase/nexus/issues/861
gh api repos/pythagorakase/nexus/issues/comments/5035538982
gh api repos/pythagorakase/nexus/issues/comments/5035539149
gh api repos/pythagorakase/nexus/issues/comments/5035539341
gh api repos/pythagorakase/nexus/issues/comments/5035716638
gh api repos/pythagorakase/nexus/issues/comments/5070275155
gh api repos/pythagorakase/nexus/issues/comments/5113803006
gh api repos/pythagorakase/nexus/issues/comments/5113867184
gh api repos/pythagorakase/nexus/issues/comments/5113874777
gh api repos/pythagorakase/nexus/issues/comments/5556777011
gh api repos/pythagorakase/nexus/issues/comments/5556777557
gh api repos/pythagorakase/nexus/issues/comments/5556778630
gh api repos/pythagorakase/nexus/issues/comments/5565300043
gh api repos/pythagorakase/nexus/issues/comments/5565301694
gh api repos/pythagorakase/nexus/issues/comments/5565410350
gh api repos/pythagorakase/nexus/issues/comments/5565414838
gh api repos/pythagorakase/nexus/issues/comments/5565439618
gh api repos/pythagorakase/nexus/issues/comments/5800949507
gh api repos/pythagorakase/nexus/issues/comments/5800951144
gh api repos/pythagorakase/nexus/issues/comments/5800952750
gh api repos/pythagorakase/nexus/issues/comments/5800955522
gh api repos/pythagorakase/nexus/issues/comments/5817898265
gh api repos/pythagorakase/nexus/issues/comments/5915474062
gh api repos/pythagorakase/nexus/issues/comments/5915474444
gh api repos/pythagorakase/nexus/issues/comments/5915474827
gh api repos/pythagorakase/nexus/issues/comments/5915475165
gh api repos/pythagorakase/nexus/issues/comments/5915475477
gh api repos/pythagorakase/nexus/issues/comments/5915494108
gh api repos/pythagorakase/nexus/issues/comments/5915494408
gh api repos/pythagorakase/nexus/issues/comments/5915494698
gh api repos/pythagorakase/nexus/issues/comments/5915495072
gh api repos/pythagorakase/nexus/issues/comments/5915495413
gh api repos/pythagorakase/nexus/issues/comments/5915495765
gh api repos/pythagorakase/nexus/issues/comments/5915496016
gh api repos/pythagorakase/nexus/issues/comments/5915496362
gh api repos/pythagorakase/nexus/issues/comments/5915496685
gh api repos/pythagorakase/nexus/issues/comments/5915497021
gh api repos/pythagorakase/nexus/issues/comments/5915497315
gh api repos/pythagorakase/nexus/issues/comments/5915668877
gh api repos/pythagorakase/nexus/issues/comments/5915669173
gh api repos/pythagorakase/nexus/issues/comments/5915669468
gh api repos/pythagorakase/nexus/issues/comments/5915669789
gh api repos/pythagorakase/nexus/issues/comments/5915670142
gh api repos/pythagorakase/nexus/issues/comments/5915670598
gh api repos/pythagorakase/nexus/issues/comments/5915671010
gh api repos/pythagorakase/nexus/issues/comments/5915950416

all 55 records match (merge base b0da93eaedb4d1661af50742440e7988c7e48185)
```

Negative control: changing one word inside the 0034 quote of comment
5113874777 and one word of the 0053 not-chosen bullet makes the audit fail
(both edits reverted):

```text
FAILURES:
0034: block from https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113874777 differs
0053: inline quotation not in source: 'The option not chosen reran from a fresh start.'
```

## Red Run

Three scratch plants on the committed tree, reverted with `git checkout` and never committed: `## Reopening Criteria` removed from
0001, the 0055 Records line removed, and 0055's `**Kind:** decision` changed to
`**Kind:** parked`.

```diff
diff --git a/docs/decisions/0001-the-cut.md b/docs/decisions/0001-the-cut.md
index d6158fc5..5a5166e6 100644
--- a/docs/decisions/0001-the-cut.md
+++ b/docs/decisions/0001-the-cut.md
@@ -20,6 +20,5 @@ Source: https://github.com/pythagorakase/nexus/issues/850#issuecomment-555677701
 
 - "must cuts stay player-initiated". Reason: "The cut is a craft move Skald owns; thresholds still only raise attention."
 
-## Reopening Criteria
 
 - A later owner ruling on the linked issue.
diff --git a/docs/decisions/0055-weirdness-control.md b/docs/decisions/0055-weirdness-control.md
index e0e0c619..cf37d659 100644
--- a/docs/decisions/0055-weirdness-control.md
+++ b/docs/decisions/0055-weirdness-control.md
@@ -7,7 +7,7 @@ verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
 
 # 0055: Weirdness Control
 
-**Kind:** decision
+**Kind:** parked
 **Links:** #838, Loom sequence 40
 
 ## Ruling
diff --git a/docs/decisions/README.md b/docs/decisions/README.md
index 32e07fd1..bd3cfde2 100644
--- a/docs/decisions/README.md
+++ b/docs/decisions/README.md
@@ -159,4 +159,3 @@ execution state.
 - [0052: Story Map](0052-story-map.md)
 - [0053: Resumable Genesis](0053-resumable-genesis.md)
 - [0054: Responsive Shell](0054-responsive-shell.md)
-- [0055: Weirdness Control](0055-weirdness-control.md)
```

`PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py -k decision_ledger --tb=short`:

```text
=================================== FAILURES ===================================
________________ test_decision_ledger_follows_the_record_format ________________
tests/test_doc_front_matter.py:799: in test_decision_ledger_follows_the_record_format
    assert ledger_errors(ROOT, paths, classification.documents) == []
E   assert ["docs/decisi...control.md)'"] == []
E     
E     Left contains 2 more items, first extra item: "docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']"
E     Use -v to get more diff
_____________________ test_decision_ledger_backfill_holds ______________________
tests/test_doc_front_matter.py:822: in test_decision_ledger_backfill_holds
    assert declared == DECISION_LEDGER
E   AssertionError: assert {'0001': ('de...onical'), ...} == {'0001': ('de...onical'), ...}
E     
E     Omitting 54 identical items, use -vv to show
E     Differing items:
E     {'0055': ('parked', 838, 'canonical')} != {'0055': ('decision', 838, 'canonical')}
E     Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_decision_ledger_follows_the_record_format
FAILED tests/test_doc_front_matter.py::test_decision_ledger_backfill_holds - ...
2 failed, 62 deselected in 0.63s
```

The format test's full error list on the planted tree (the assertion output
above truncates it):

```text
docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']
docs/decisions/README.md: the Records list lacks '- [0055: Weirdness Control](0055-weirdness-control.md)'
```

## Test Tails

All runs with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.
No PostgreSQL proof is owed: no code path that opens a database changes.

`$PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
118 passed, 5 warnings in 19.54s
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2986 passed, 562 skipped, 8 warnings in 643.95s (0:10:43)
```

`$PY -m pytest -q tests/test_api tests/test_orrery`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1848 passed, 1369 skipped, 7 warnings in 60.06s (0:01:00)
```

## Static Checks

```text
$ $PY -m black --check tests/test_doc_front_matter.py docs/qa/817-decision-ledger/quote_audit.py
All done! 2 files would be left unchanged.
$ $PY -m flake8 tests/test_doc_front_matter.py docs/qa/817-decision-ledger/quote_audit.py
(no output, exit 0; origin/main's tests/test_doc_front_matter.py: no output, exit 0)
$ $PY -m mypy --explicit-package-bases tests/test_doc_front_matter.py
Success: no issues found in 1 source file
(origin/main's copy: Success: no issues found in 1 source file)
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```
