# 817-S3 Verification: Decision-Ledger Backfill

Branch `claude/817-decision-ledger`, merge base with `origin/main`
`b0da93eaedb4d1661af50742440e7988c7e48185`. Every record and the ledger
README carry that merge base as `verified_commit`.

## Resumed on 2026-10-07

The resume addendum to the order was dispatched at 22:58 CDT. The branch
already held three commits, `git status --short` was empty, and PR #1115 was
open at `5830781b`. `origin/main` was still `b0da93ea`, so no merge was owed.

| Commit | Items Covered | Left Unfinished |
|---|---|---|
| `39375159` | Required Changes 1-4: the 55 records, front matter (0030 superseded by 0005), bodies, the README Records list, the Scope and Validation sentence and the README stamp | Nothing |
| `aa42ebc5` | Tests: `ledger_errors`, `DECISION_LEDGER`, the format, backfill, rejection and valid-ledger tests | Nothing |
| `5830781b` | Proof: quote audit, red run, test tails, static checks | This "Resumed" table |
| `b77b59a8` | This "Resumed" table and a fresh audit run | Nothing |
| `4c9ebb83` | Review fixes: the Links-position cases, the audit's Fetch column and docstrings, `table_check.py` | This file's fix-pass evidence (next commit) |
| `e371d45c` | This file's evidence for the `4c9ebb83` fix pass | Nothing |
| `f7b73277` | Second review fixes: the committed order copy and `table_check.py` default, the audit's strip on both sides and its stray-quote check | This file's evidence (next commit) |
| `6df5115a` | This file's evidence for the `f7b73277` fix pass | Nothing |
| `b8c656b6` | Third review fixes: the sources the coordinator's ruling adds to 0009, 0019 and 0023, and the sweep's additions to 0010, 0020, 0024, 0025-0029 and 0034; `table_check.py` appends them | The sweep script (next commit) and this file's evidence |
| `d338db76` | `source_sweep.py` (the sweep, rerunnable); `table_check.py` types the joined sources list | This file's evidence (next commit) |
| (next commit) | This file's evidence for `b8c656b6` and `d338db76`, except the offline-suite tails | The offline-suite tails (the commit after) |
| (last commit) | The offline-suite tails, run on the commit before it | Nothing |

The resume first rechecked the records against the order's table with an
unrecorded scratch script. The review fix pass below replaced that recheck with
the committed `table_check.py`, whose command and full output are under "Order
Table and Fixed-Text Check". Fresh runs at `b77b59a8`:

```text
$ PYTHONPATH=$PWD $PY docs/qa/817-decision-ledger/quote_audit.py $PWD
all 55 records match (merge base b0da93eaedb4d1661af50742440e7988c7e48185)
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
118 passed, 5 warnings in 17.83s
```

The offline suites were not rerun on resume (the one-minute load was 23). The
third review fix pass superseded those tails with runs at a named commit; see
"Offline Suites" under "Test Tails". The quote audit is a point-in-time proof;
an edit to a cited comment after this run makes it stale.

## Review Fixes on 2026-10-07

A fix pass applied the confirmed review findings on PR #1115 in `4c9ebb83`.
Every tail in this file marked `4c9ebb83` ran on that commit, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset and `origin/main`
still at the merge base `b0da93ea` (no merge owed).

- `tests/test_doc_front_matter.py`: two more rejection cases assert the Links
  message, one with a blank line that moves `**Links:**` off its place and one
  with no Links line. A mutation that loosens the positional check
  (`RECORD_LINKS.fullmatch(body[4])`) to "any line matches" fails the first
  case (tail below, reverted). The second case covers a missing line, which the
  loosened check still rejects.
- `quote_audit.py`: a Fetch column lists the `gh api` commands each record
  reads, and its four helper functions have docstrings. It fetches 45 distinct
  comments (the 819-Q1 comment 5915950416 included) and 45 issues.
- `table_check.py` (new): the order-table and fixed-text check, committed with
  its command, output and a negative control below.
- The red run is repeated with `-vv` and a direct `ledger_errors` print.

Mutation check (`4c9ebb83` with this one-line change, reverted):

```text
-    links = RECORD_LINKS.fullmatch(body[4]) if len(body) > 4 else None
+    links = next(filter(None, map(RECORD_LINKS.fullmatch, body)), None)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py -k ledger --tb=line
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_ledger_rejects_format_violations[files10-a non-empty '**Links:**' line must follow the Kind]
1 failed, 23 passed, 42 deselected, 5 warnings in 0.58s
```

## Second Review Fixes on 2026-10-07

A second fix pass applied five confirmed review findings in `f7b73277`. Every
tail in this file marked `f7b73277` ran on that commit, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. `git fetch`
showed `origin/main` still at the merge base `b0da93ea`, so no merge was owed
and the stamps stay valid.

- `table_check.py` read the record table and the fixed text from the
  coordinator's order file under the gitignored `temp/`. The order's "Required
  Changes" section is now committed byte for byte as
  `docs/qa/817-decision-ledger/order_817_S3.md` and is the script's default
  input. A run without the worktree argument exits with a usage message:

  ```text
  $ PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/table_check.py
  usage: python table_check.py <worktree> [<work order .md>]
  exit 1
  ```

- `quote_audit.py` compared a whole comment's stripped quote with the fetched
  lines left unstripped, so a source line that already starts with `>` would
  report DIFFER. It now strips `^> ?` from `forward(<fetched lines>)` for every
  block kind and keeps the byte check `flines == forward(elines)`. No cited
  comment holds such a line today, so the audit output is unchanged. A scratch
  check (`817-S3-resume/strip_demo.py` in the session scratchpad) runs both
  comparisons on a synthetic comment that holds one:

  ```text
  $ PYTHONPATH=$PWD $PY <scratch>/817-S3-resume/strip_demo.py
  quoted lines: ['> Ruling text.', '> an already quoted line', '>', '> Last line.']
  old (e371d45c): False
  new: True
  ```

- `quote_audit.py` ignored a `>` run without a `Source:` line. `record_blocks`
  now records every line it collects and fails the record when a line that
  starts with `>` or a fence line lies outside every collected block. Because
  the audit fails on such a line, `table_check.py`, which leaves quoted lines to
  the audit, cannot pass a record with an unsourced quote either. Negative
  control: a paraphrased `>` line planted at the top of 0001's Rejected
  Alternatives (reverted with `git checkout -- docs/decisions`). The audit at
  `f7b73277` fails it; the audit at `e371d45c` (copied to the scratchpad) passes
  it:

  ```diff
  @@ -18,6 +18,8 @@ Source: https://github.com/pythagorakase/nexus/issues/850#issuecomment-555677701
   
   ## Rejected Alternatives
   
  +> The cut belongs to Skald, not the player.
  +
   - "must cuts stay player-initiated". Reason: "The cut is a craft move Skald owns; thresholds still only raise attention."
  ```

  ```text
  $ PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/quote_audit.py $PWD
  [... the 0001 row ends | 0 | 2 | DIFFER |; the other 54 rows read MATCH ...]
  FAILURES:
  0001: quoted or fenced lines without a Source line: [21]
  0001: 0 blocks, expected 1
  $ PYTHONPATH=$PWD nice -n 15 $PY <scratch>/817-S3-resume/quote_audit_e371d45c.py $PWD
  [...]
  all 55 records match (merge base b0da93eaedb4d1661af50742440e7988c7e48185)
  ```

- The 819-S3 merge check below now records the command for each line.
- The focused test set is rerun with `nice -n 15` (Test Tails below).

## Third Review Fixes on 2026-10-07

Astra (Codex GPT-6) reviewed `6df5115a` and returned four P2 findings. The
coordinator accepted all four and ruled: a record's `sources:` list names every
file its ruling governs or its reasoning depends on, not only the files that
implement it. `b8c656b6` applies the ruling to the front matter only, and
`d338db76` commits the sweep script. No ruling text changes, every existing
source stays first, and every `verified_commit` stays the merge base
`b0da93ea`, where the added files hold what the records cite (below).

The three records the review named:

| Record | Added Sources | Where the Record Cites Them |
|---|---|---|
| 0009 | `nexus.toml`, `nexus/cli.py` | Ruling: "No price table in nexus.toml, no dollars column in `nexus usage`"; the `usage` command is defined in `nexus/cli.py` (`:5144`, `:5929` at `b0da93ea`) |
| 0019 | `ui/client/src/components/nexus/NarrativePane.tsx`, `nexus/agents/lore/logon_utility.py` | REFUTED A cites `NarrativePane.tsx:250-255`; REFUTED B cites `logon_utility.py:2457-2476` (the one tracked file of that name) |
| 0023 | `prompts/storyteller_core.md` | REFUTED B cites `prompts/storyteller_core.md:171` |

The sweep of the other 52 records, under the same rule. The committed
`docs/qa/817-decision-ledger/source_sweep.py` lists every file a record's body
names that its sources omit: a tracked path, a bare file name with tracked
matches, or an untracked path with a file extension. On the records at
`6df5115a` it found the three rows above and these candidates, each cited as the
basis of its record's ruling or refutation, so each joins the sources:

| Record | Added Sources | Where the Record Cites Them |
|---|---|---|
| 0010 | `nexus.toml` | Ruling: the seat moves are recorded as the `nexus.toml` roster `uses` (`apex.model`, `wizard.default_model`, the removed `apex.gaia_model`) |
| 0020 | `migrations/091_backstory_secrets.sql` | REFUTED B cites `migrations/091_backstory_secrets.sql:9-41` |
| 0024 | `nexus.toml`, `docs/orrery_retrograde_spec.md`, `docs/orrery_design_plan.md` | REFUTED B cites `nexus.toml:852-924`; REFUTED C cites `docs/orrery_retrograde_spec.md:157-160,191` and `docs/orrery_design_plan.md:425-427` |
| 0025, 0026, 0027, 0028 | `docs/dead_retrieval_subtraction.md` | Ruling: the quoted 819-Q1 decision routes the entries into "#813's manifest (`docs/dead_retrieval_subtraction.md`)", and each quoted baseline reason names its section there |
| 0029 | `docs/dead_retrieval_subtraction.md`, `nexus/agents/memnon/utils/db_access.py` | The same routing; the quoted `hybrid_search` reasons rest on `nexus/agents/memnon/utils/db_access.py:581` |
| 0034 | `nexus.toml` | Ruling amendment: "Both knobs live in `nexus.toml`." |

Not added, with the reason:

- `doctrine.md` (0018, 0022, 0023) and `coverage_critique.md` (0023): working
  files of the 2026-09-04 brainstorm under the gitignored `temp/` of the main
  checkout (`.gitignore:45: /temp/`), not repository files, so no source can
  name them.
- `~/.codex/config.toml` (0010): outside the repository.
- Artifacts a record names without a file: the "pacing brief" (0001) and the
  "style diet" (0002) have no tracked file of that name (their guidance lives
  in `prompts/storyteller_core.md`, already a source of both); "both prompts"
  (0034) names no file; `SkaldWriterWire` (0018), `BleedCandidate.to_prompt_dict`
  (0019) and `begin_shift` (0021) live in files that are already sources;
  `save_04` (0020, 0024), `choice_text` and `raw_text` (0006) are database
  objects, and `memory_embeddings_2560d` (0024) is a proposed table.

The line numbers in the #849 verdicts are those of the 2026-09-04 tree; at
`b0da93ea` the cited content is still present at other lines (for example
"Episode boundaries complete arcs." at `prompts/storyteller_core.md:161`, and
`execute_hybrid_search` delegating at `nexus/agents/memnon/utils/db_access.py:416`).
The records quote the verdicts and do not restate the line numbers.

```text
$ PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/source_sweep.py $PWD   # on d338db76
0010-the-gaia-seat.md
    UNTRACKED:~/.codex/config.toml (body lines 11)
0018-killed-c003.md
    UNTRACKED:doctrine.md (body lines 27)
0022-killed-c068.md
    UNTRACKED:doctrine.md (body lines 23)
0023-killed-c100.md
    UNTRACKED:doctrine.md (body lines 27)
    UNTRACKED:coverage_critique.md (body lines 27)
tracked files cited but not in sources: 0
```

The same sweep on the records at `6df5115a` (`git archive 6df5115a docs/decisions`
into the scratchpad, swept by the same `sweep()` with the worktree's file
list):

```text
0009-dollars-in-the-ledger.md
    nexus.toml (body lines 11)
0010-the-gaia-seat.md
    nexus.toml (body lines 11)
    UNTRACKED:~/.codex/config.toml (body lines 11)
0018-killed-c003.md
    UNTRACKED:doctrine.md (body lines 27)
0019-killed-c014.md
    ui/client/src/components/nexus/NarrativePane.tsx (body lines 23)
    nexus/agents/lore/logon_utility.py (body lines 27)
0020-killed-c030.md
    migrations/091_backstory_secrets.sql (body lines 23)
0022-killed-c068.md
    UNTRACKED:doctrine.md (body lines 23)
0023-killed-c100.md
    prompts/storyteller_core.md (body lines 23)
    UNTRACKED:doctrine.md (body lines 27)
    UNTRACKED:coverage_critique.md (body lines 27)
0024-killed-c102.md
    nexus.toml (body lines 23)
    docs/orrery_retrograde_spec.md (body lines 27)
    docs/orrery_design_plan.md (body lines 27)
0025-legacy-new-story-seed-columns.md
    docs/dead_retrieval_subtraction.md (body lines 13, 17, 18, 19, 20, 21)
0026-entity-tag-clear-on-override.md
    docs/dead_retrieval_subtraction.md (body lines 13, 17)
0027-narration-job-provider-columns.md
    docs/dead_retrieval_subtraction.md (body lines 13, 17, 18)
0028-world-event-narration-link.md
    docs/dead_retrieval_subtraction.md (body lines 13, 17)
0029-legacy-vector-helper-functions.md
    docs/dead_retrieval_subtraction.md (body lines 13, 17, 18, 19, 20, 21, 22)
    nexus/agents/memnon/utils/db_access.py (body lines 17, 18, 19)
0034-conspiracy-channel.md
    nexus.toml (body lines 31)
```

(`nexus/cli.py` for 0009 comes from the reading, not the sweep: the record
names the `nexus usage` command, not the file.)

`table_check.py` now compares each record's sources with the order table's list
followed by its `SOURCE_ADDITIONS` entry (the table above), so the order copy
stays byte for byte. Negative control on `d338db76`: `nexus/cli.py` removed from
0009 and `prompts/storyteller_core.md` removed from 0023, then both files
restored with `git checkout -- docs/decisions` (`git diff --stat docs/decisions`
empty after):

```text
$ PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/table_check.py $PWD
[...]
MISMATCHES:
0009: front differs from the order
0023: front differs from the order
exit 1
```

## 819-S3 Merge Check

819-S3 (#1109, `e0966c6d`) landed before this branch was cut, so rows
0025-0029 were written from `config/schema_docs_baseline.json` at the merge base.

```text
$ git grep -n "Legacy Columns Without Evidence" origin/main -- docs/dead_retrieval_subtraction.md
origin/main:docs/dead_retrieval_subtraction.md:182:## Legacy Columns Without Evidence
$ git log --oneline -1 e0966c6d
e0966c6d Route the legacy schema-docs baseline debt into #813's manifest (#819 S3) (#1109)
$ git merge-base --is-ancestor e0966c6d origin/main && echo "e0966c6d is an ancestor of origin/main"
e0966c6d is an ancestor of origin/main
```

Rerun on `f7b73277` with `origin/main` at `b0da93ea`; the output is the same.

## Quote Audit

`docs/qa/817-decision-ledger/quote_audit.py` fetches every cited comment and
issue fresh with `gh api repos/pythagorakase/nexus/issues/comments/<ID>` and
`gh api repos/pythagorakase/nexus/issues/<N>`, and reads the raw Markdown from
the JSON `.body` (the same text as `-q .body`, without the newline `gh` appends).
It does not import the generator. For each record it:

- parses every block that follows a `Source: <URL>.` line and a blank line,
  and fails the record when a line that starts with `>` or a fence line lies
  outside every such block, so every quoted block in a record is compared;
- recomputes the expected block from the fetched text: the whole comment body;
  for a relay, the first maximal run of `^>( |$)` lines after the first line
  containing `verbatim` (case-insensitive), or lines 3-10 of 5817898265 (the
  #737 fence); the `## Risks` paragraph of #837 and #839; the
  `**Amendment / carry-forward:**`, `**Summary:**` and `REFUTED` verdict lines of
  the #849 section; the 819-Q1 `Decision:` line, the `<key>: <reason>` lines of
  `config/schema_docs_baseline.json` and the #819 Summary sentence;
- strips `^> ?` from each quoted line (the #737 fence is compared as it is) and
  asserts equality, not containment, with the whole expected text after the
  quoting rule and the same strip (so a relay run loses its own `> `, and a
  source line that already starts with `>` compares as itself), and also
  asserts that the quoted lines equal the expected lines under the quoting rule
  byte for byte;
- prints, per record, the `gh api` commands that record reads (the Fetch
  column);
- checks the source URL and section of each block, the block count, that every
  inline quotation in Rejected Alternatives and Reopening Criteria occurs
  verbatim in the linked issue or cited comments, and that a relay record has
  one bullet per "not chosen" occurrence (0033 and 0044 take the order's
  wording).

Run on `4c9ebb83`: `PYTHONPATH=$PWD $PY docs/qa/817-decision-ledger/quote_audit.py $PWD`.
Rerun on `f7b73277` as `PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/quote_audit.py $PWD`
(exit 0); its output is identical to the block below (`diff` empty). Rerun on
`d338db76`, after the source additions, the same way: exit 0, and `diff`
against the block below is empty.

```text
| Record | Sources | Fetch | Blocks | Inline quotes | Result |
|---|---|---|---|---|---|
| 0001 | https://github.com/pythagorakase/nexus/issues/850#issuecomment-5556777011 | `gh api repos/pythagorakase/nexus/issues/comments/5556777011`<br>`gh api repos/pythagorakase/nexus/issues/850` | 1 | 2 | MATCH |
| 0002 | https://github.com/pythagorakase/nexus/issues/851#issuecomment-5556777557 | `gh api repos/pythagorakase/nexus/issues/comments/5556777557`<br>`gh api repos/pythagorakase/nexus/issues/851` | 1 | 1 | MATCH |
| 0003 | https://github.com/pythagorakase/nexus/issues/852#issuecomment-5556778630 | `gh api repos/pythagorakase/nexus/issues/comments/5556778630`<br>`gh api repos/pythagorakase/nexus/issues/852` | 1 | 2 | MATCH |
| 0004 | https://github.com/pythagorakase/nexus/issues/853#issuecomment-5565300043 | `gh api repos/pythagorakase/nexus/issues/comments/5565300043`<br>`gh api repos/pythagorakase/nexus/issues/853` | 1 | 1 | MATCH |
| 0005 | https://github.com/pythagorakase/nexus/issues/854#issuecomment-5565301694 | `gh api repos/pythagorakase/nexus/issues/comments/5565301694`<br>`gh api repos/pythagorakase/nexus/issues/854` | 1 | 2 | MATCH |
| 0006 | https://github.com/pythagorakase/nexus/issues/855#issuecomment-5565439618 | `gh api repos/pythagorakase/nexus/issues/comments/5565439618`<br>`gh api repos/pythagorakase/nexus/issues/855` | 1 | 1 | MATCH |
| 0007 | https://github.com/pythagorakase/nexus/issues/856#issuecomment-5800949507 | `gh api repos/pythagorakase/nexus/issues/comments/5800949507`<br>`gh api repos/pythagorakase/nexus/issues/856` | 1 | 1 | MATCH |
| 0008 | https://github.com/pythagorakase/nexus/issues/857#issuecomment-5800951144 | `gh api repos/pythagorakase/nexus/issues/comments/5800951144`<br>`gh api repos/pythagorakase/nexus/issues/857` | 1 | 1 | MATCH |
| 0009 | https://github.com/pythagorakase/nexus/issues/858#issuecomment-5800952750 | `gh api repos/pythagorakase/nexus/issues/comments/5800952750`<br>`gh api repos/pythagorakase/nexus/issues/858` | 1 | 1 | MATCH |
| 0010 | https://github.com/pythagorakase/nexus/issues/859#issuecomment-5800955522 | `gh api repos/pythagorakase/nexus/issues/comments/5800955522`<br>`gh api repos/pythagorakase/nexus/issues/859` | 1 | 0 | MATCH |
| 0011 | https://github.com/pythagorakase/nexus/issues/860#issuecomment-5565414838 | `gh api repos/pythagorakase/nexus/issues/comments/5565414838`<br>`gh api repos/pythagorakase/nexus/issues/860` | 1 | 0 | MATCH |
| 0012 | https://github.com/pythagorakase/nexus/issues/861#issuecomment-5565410350 | `gh api repos/pythagorakase/nexus/issues/comments/5565410350`<br>`gh api repos/pythagorakase/nexus/issues/861` | 1 | 1 | MATCH |
| 0013 | https://github.com/pythagorakase/nexus/issues/786#issuecomment-5915495413 | `gh api repos/pythagorakase/nexus/issues/comments/5915495413`<br>`gh api repos/pythagorakase/nexus/issues/786` | 1 | 1 | MATCH |
| 0014 | https://github.com/pythagorakase/nexus/issues/792#issuecomment-5915496685 | `gh api repos/pythagorakase/nexus/issues/comments/5915496685`<br>`gh api repos/pythagorakase/nexus/issues/792` | 1 | 1 | MATCH |
| 0015 | https://github.com/pythagorakase/nexus/issues/832#issuecomment-5915670598 | `gh api repos/pythagorakase/nexus/issues/comments/5915670598`<br>`gh api repos/pythagorakase/nexus/issues/832` | 1 | 1 | MATCH |
| 0016 | https://github.com/pythagorakase/nexus/issues/837 | `gh api repos/pythagorakase/nexus/issues/837` | 1 | 1 | MATCH |
| 0017 | https://github.com/pythagorakase/nexus/issues/839 | `gh api repos/pythagorakase/nexus/issues/839` | 1 | 1 | MATCH |
| 0018 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0019 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0020 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0021 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0022 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0023 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0024 | https://github.com/pythagorakase/nexus/issues/849 | `gh api repos/pythagorakase/nexus/issues/849` | 4 | 0 | MATCH |
| 0025 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | `gh api repos/pythagorakase/nexus/issues/comments/5915950416`<br>`gh api repos/pythagorakase/nexus/issues/819` | 3 | 0 | MATCH |
| 0026 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | `gh api repos/pythagorakase/nexus/issues/comments/5915950416`<br>`gh api repos/pythagorakase/nexus/issues/819` | 3 | 0 | MATCH |
| 0027 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | `gh api repos/pythagorakase/nexus/issues/comments/5915950416`<br>`gh api repos/pythagorakase/nexus/issues/819` | 3 | 0 | MATCH |
| 0028 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | `gh api repos/pythagorakase/nexus/issues/comments/5915950416`<br>`gh api repos/pythagorakase/nexus/issues/819` | 3 | 0 | MATCH |
| 0029 | config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185, https://github.com/pythagorakase/nexus/issues/819, https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416 | `gh api repos/pythagorakase/nexus/issues/comments/5915950416`<br>`gh api repos/pythagorakase/nexus/issues/819` | 3 | 0 | MATCH |
| 0030 | https://github.com/pythagorakase/nexus/issues/476#issuecomment-5035538982 | `gh api repos/pythagorakase/nexus/issues/comments/5035538982`<br>`gh api repos/pythagorakase/nexus/issues/476` | 1 | 0 | MATCH |
| 0031 | https://github.com/pythagorakase/nexus/issues/479#issuecomment-5035539149 | `gh api repos/pythagorakase/nexus/issues/comments/5035539149`<br>`gh api repos/pythagorakase/nexus/issues/479` | 1 | 0 | MATCH |
| 0032 | https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035539341, https://github.com/pythagorakase/nexus/issues/480#issuecomment-5035716638 | `gh api repos/pythagorakase/nexus/issues/comments/5035539341`<br>`gh api repos/pythagorakase/nexus/issues/comments/5035716638`<br>`gh api repos/pythagorakase/nexus/issues/480` | 2 | 0 | MATCH |
| 0033 | https://github.com/pythagorakase/nexus/issues/566#issuecomment-5070275155 | `gh api repos/pythagorakase/nexus/issues/comments/5070275155`<br>`gh api repos/pythagorakase/nexus/issues/566` | 1 | 1 | MATCH |
| 0034 | https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113803006, https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113867184, https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113874777 | `gh api repos/pythagorakase/nexus/issues/comments/5113803006`<br>`gh api repos/pythagorakase/nexus/issues/comments/5113867184`<br>`gh api repos/pythagorakase/nexus/issues/comments/5113874777`<br>`gh api repos/pythagorakase/nexus/issues/617` | 3 | 0 | MATCH |
| 0035 | https://github.com/pythagorakase/nexus/issues/737#issuecomment-5817898265 | `gh api repos/pythagorakase/nexus/issues/comments/5817898265`<br>`gh api repos/pythagorakase/nexus/issues/737` | 1 | 0 | MATCH |
| 0036 | https://github.com/pythagorakase/nexus/issues/750#issuecomment-5915474062 | `gh api repos/pythagorakase/nexus/issues/comments/5915474062`<br>`gh api repos/pythagorakase/nexus/issues/750` | 1 | 0 | MATCH |
| 0037 | https://github.com/pythagorakase/nexus/issues/756#issuecomment-5915474827 | `gh api repos/pythagorakase/nexus/issues/comments/5915474827`<br>`gh api repos/pythagorakase/nexus/issues/756` | 1 | 1 | MATCH |
| 0038 | https://github.com/pythagorakase/nexus/issues/759#issuecomment-5915475165 | `gh api repos/pythagorakase/nexus/issues/comments/5915475165`<br>`gh api repos/pythagorakase/nexus/issues/759` | 1 | 1 | MATCH |
| 0039 | https://github.com/pythagorakase/nexus/issues/780#issuecomment-5915474444 | `gh api repos/pythagorakase/nexus/issues/comments/5915474444`<br>`gh api repos/pythagorakase/nexus/issues/780` | 1 | 1 | MATCH |
| 0040 | https://github.com/pythagorakase/nexus/issues/822#issuecomment-5915475477 | `gh api repos/pythagorakase/nexus/issues/comments/5915475477`<br>`gh api repos/pythagorakase/nexus/issues/822` | 1 | 1 | MATCH |
| 0041 | https://github.com/pythagorakase/nexus/issues/781#issuecomment-5915494108 | `gh api repos/pythagorakase/nexus/issues/comments/5915494108`<br>`gh api repos/pythagorakase/nexus/issues/781` | 1 | 1 | MATCH |
| 0042 | https://github.com/pythagorakase/nexus/issues/782#issuecomment-5915494408 | `gh api repos/pythagorakase/nexus/issues/comments/5915494408`<br>`gh api repos/pythagorakase/nexus/issues/782` | 1 | 1 | MATCH |
| 0043 | https://github.com/pythagorakase/nexus/issues/783#issuecomment-5915494698 | `gh api repos/pythagorakase/nexus/issues/comments/5915494698`<br>`gh api repos/pythagorakase/nexus/issues/783` | 1 | 0 | MATCH |
| 0044 | https://github.com/pythagorakase/nexus/issues/784#issuecomment-5915495072 | `gh api repos/pythagorakase/nexus/issues/comments/5915495072`<br>`gh api repos/pythagorakase/nexus/issues/784` | 1 | 1 | MATCH |
| 0045 | https://github.com/pythagorakase/nexus/issues/787#issuecomment-5915495765 | `gh api repos/pythagorakase/nexus/issues/comments/5915495765`<br>`gh api repos/pythagorakase/nexus/issues/787` | 1 | 0 | MATCH |
| 0046 | https://github.com/pythagorakase/nexus/issues/788#issuecomment-5915496016 | `gh api repos/pythagorakase/nexus/issues/comments/5915496016`<br>`gh api repos/pythagorakase/nexus/issues/788` | 1 | 1 | MATCH |
| 0047 | https://github.com/pythagorakase/nexus/issues/789#issuecomment-5915496362 | `gh api repos/pythagorakase/nexus/issues/comments/5915496362`<br>`gh api repos/pythagorakase/nexus/issues/789` | 1 | 0 | MATCH |
| 0048 | https://github.com/pythagorakase/nexus/issues/840#issuecomment-5915497021 | `gh api repos/pythagorakase/nexus/issues/comments/5915497021`<br>`gh api repos/pythagorakase/nexus/issues/840` | 1 | 2 | MATCH |
| 0049 | https://github.com/pythagorakase/nexus/issues/841#issuecomment-5915497315 | `gh api repos/pythagorakase/nexus/issues/comments/5915497315`<br>`gh api repos/pythagorakase/nexus/issues/841` | 1 | 2 | MATCH |
| 0050 | https://github.com/pythagorakase/nexus/issues/767#issuecomment-5915668877 | `gh api repos/pythagorakase/nexus/issues/comments/5915668877`<br>`gh api repos/pythagorakase/nexus/issues/767` | 1 | 0 | MATCH |
| 0051 | https://github.com/pythagorakase/nexus/issues/768#issuecomment-5915669173 | `gh api repos/pythagorakase/nexus/issues/comments/5915669173`<br>`gh api repos/pythagorakase/nexus/issues/768` | 1 | 1 | MATCH |
| 0052 | https://github.com/pythagorakase/nexus/issues/770#issuecomment-5915669468 | `gh api repos/pythagorakase/nexus/issues/comments/5915669468`<br>`gh api repos/pythagorakase/nexus/issues/770` | 1 | 1 | MATCH |
| 0053 | https://github.com/pythagorakase/nexus/issues/776#issuecomment-5915669789 | `gh api repos/pythagorakase/nexus/issues/comments/5915669789`<br>`gh api repos/pythagorakase/nexus/issues/776` | 1 | 1 | MATCH |
| 0054 | https://github.com/pythagorakase/nexus/issues/777#issuecomment-5915670142 | `gh api repos/pythagorakase/nexus/issues/comments/5915670142`<br>`gh api repos/pythagorakase/nexus/issues/777` | 1 | 1 | MATCH |
| 0055 | https://github.com/pythagorakase/nexus/issues/838#issuecomment-5915671010 | `gh api repos/pythagorakase/nexus/issues/comments/5915671010`<br>`gh api repos/pythagorakase/nexus/issues/838` | 1 | 1 | MATCH |

distinct objects fetched: 90 (45 comments, 45 issues)

all 55 records match (merge base b0da93eaedb4d1661af50742440e7988c7e48185)
```

Negative control (an earlier run of the same comparison): changing one word inside the 0034 quote of comment
5113874777 and one word of the 0053 not-chosen bullet makes the audit fail
(both edits reverted):

```text
FAILURES:
0034: block from https://github.com/pythagorakase/nexus/issues/617#issuecomment-5113874777 differs
0053: inline quotation not in source: 'The option not chosen reran from a fresh start.'
```

## Order Table and Fixed-Text Check

`docs/qa/817-decision-ledger/table_check.py` parses the work order's record
table and the fixed text of its Required Changes 3 from
`docs/qa/817-decision-ledger/order_817_S3.md` (the order's "Required Changes"
section, committed byte for byte; a different order file may be passed as the
second argument), and compares every record with them. It requires equality, not containment:

- the file name `NNNN-slug.md` and the set of files under `docs/decisions/`;
- the front matter: `status`, `sources` in the table's order, `verified_commit`
  equal to the merge base, the 0030 `superseded_by` and 0005 `supersedes`
  entries, and no other key;
- the blank line, `# NNNN: Title`, `**Kind:**` and `**Links:**` lines, and the
  three `##` headings;
- the Ruling lead-in lines of 0016-0029, and that every other unquoted Ruling
  line is a `Source:` line;
- every Rejected Alternatives bullet: the order's exact bullets for 0001-0012,
  0016-0017, 0025-0029, 0033 and 0044, no bullet for 0018-0024, and for the
  other relay rows one `- "<sentence>". No reason recorded.` (or `Reason:`)
  bullet per "not chosen" sentence of the fetched relay, equal to the whole
  sentence, or `- None recorded in the public relay.` when the relay has none;
  a `Reason:` must come from its sentence, and a sentence that says "because"
  may not take `No reason recorded.`;
- every Reopening Criteria bullet: the order's exact bullet for 0018-0030 and
  every row the order does not name, and for 0013-0017 the whole sentence the
  order names, recomputed from a fresh fetch (the last sentence of the relay's
  "State of this issue." bullet; the #837 and #839 sentences).

Quoted blocks are left to the quote audit above.

Run on `f7b73277` with the committed order copy (exit 0). The table rows are
identical to the earlier run on `4c9ebb83`, which passed the coordinator's
order file under `temp/` as the second argument. Rerun on `d338db76`, with
`SOURCE_ADDITIONS` (exit 0): `diff` against the block below is empty.
`PYTHONPATH=$PWD nice -n 15 $PY docs/qa/817-decision-ledger/table_check.py $PWD`

```text
order: order_817_S3.md
order table rows: 55; files under docs/decisions/: 56
lead-ins: 14; fixed Rejected rows: 28; fixed Reopening rows: 13

| Record | Front matter | Title, Kind, Links | Ruling | Rejected | Reopening |
|---|---|---|---|---|---|
| 0001 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0002 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0003 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0004 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0005 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0006 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0007 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0008 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0009 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0010 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0011 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0012 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0013 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0014 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0015 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0016 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0017 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0018 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0019 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0020 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0021 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0022 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0023 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0024 | ok | ok | ok (lead-in, Source lines) | ok (0 bullets) | ok |
| 0025 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0026 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0027 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0028 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0029 | ok | ok | ok (lead-in, Source lines) | ok (1 bullet) | ok |
| 0030 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0031 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0032 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0033 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0034 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0035 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0036 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0037 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0038 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0039 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0040 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0041 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0042 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0043 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0044 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0045 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0046 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0047 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0048 | ok | ok | ok (Source lines) | ok (2 bullets) | ok |
| 0049 | ok | ok | ok (Source lines) | ok (2 bullets) | ok |
| 0050 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0051 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0052 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0053 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0054 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |
| 0055 | ok | ok | ok (Source lines) | ok (1 bullet) | ok |

mismatches: 0
```

Negative control: five plants (a 0002 bullet given a reason, 0006 sources
swapped, a 0013 Reopening sentence that is not the last one, one word of the
0018 lead-in, and a 0040 reason not in its sentence), reverted with
`git checkout -- docs/decisions`:

```diff
diff --git a/docs/decisions/0002-disengagement-in-the-menu.md b/docs/decisions/0002-disengagement-in-the-menu.md
index 6a555098..a0760395 100644
--- a/docs/decisions/0002-disengagement-in-the-menu.md
+++ b/docs/decisions/0002-disengagement-in-the-menu.md
@@ -18,7 +18,7 @@ Source: https://github.com/pythagorakase/nexus/issues/851#issuecomment-555677755
 
 ## Rejected Alternatives
 
-- "should the menu stay inside the scene". No reason recorded.
+- "should the menu stay inside the scene". Reason: "None."
 
 ## Reopening Criteria
 
diff --git a/docs/decisions/0006-who-owns-the-choice.md b/docs/decisions/0006-who-owns-the-choice.md
index ac250113..e9538d20 100644
--- a/docs/decisions/0006-who-owns-the-choice.md
+++ b/docs/decisions/0006-who-owns-the-choice.md
@@ -1,8 +1,8 @@
 ---
 status: canonical
 sources:
-  - nexus/api/choice_handling.py
   - nexus/api/slot_endpoints.py
+  - nexus/api/choice_handling.py
 verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
 ---
 
diff --git a/docs/decisions/0013-institutional-cadence.md b/docs/decisions/0013-institutional-cadence.md
index 3e458414..b8fe8cec 100644
--- a/docs/decisions/0013-institutional-cadence.md
+++ b/docs/decisions/0013-institutional-cadence.md
@@ -24,4 +24,4 @@ Source: https://github.com/pythagorakase/nexus/issues/786#issuecomment-591549541
 
 ## Reopening Criteria
 
-- "It returns to the loom only on the owner's request."
+- "It stays open with the `parked` label."
diff --git a/docs/decisions/0018-killed-c003.md b/docs/decisions/0018-killed-c003.md
index 6fd937ad..a632e969 100644
--- a/docs/decisions/0018-killed-c003.md
+++ b/docs/decisions/0018-killed-c003.md
@@ -12,7 +12,7 @@ verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
 
 ## Ruling
 
-Not adopted. The three-angle verification of the 2026-09-04 brainstorm killed this cluster; #849 records it.
+Not adopted. A three-angle verification of the 2026-09-04 brainstorm killed this cluster; #849 records it.
 
 Source: https://github.com/pythagorakase/nexus/issues/849.
 
diff --git a/docs/decisions/0040-story-bundles.md b/docs/decisions/0040-story-bundles.md
index 50a19742..dc04bbdd 100644
--- a/docs/decisions/0040-story-bundles.md
+++ b/docs/decisions/0040-story-bundles.md
@@ -21,7 +21,7 @@ Source: https://github.com/pythagorakase/nexus/issues/822#issuecomment-591547547
 
 ## Rejected Alternatives
 
-- "The options not chosen were "refuse" and "replace", so an import never overwrites an existing story." No reason recorded.
+- "The options not chosen were "refuse" and "replace", so an import never overwrites an existing story." Reason: "Forks are safer."
 
 ## Reopening Criteria
 
```

```text
MISMATCHES:
0002: rejected differs from the order
0006: front differs from the order
0013: reopen differs from the order
0018: ruling differs from the order
0040: rejected differs from the order
```

## Red Run

Three scratch plants on the committed tree, reverted with `git checkout` and
never committed: `## Reopening Criteria` removed from 0001, the 0055 Records
line removed, and 0055's `**Kind:** decision` changed to `**Kind:** parked`.

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

Run on `4c9ebb83` with `-vv`, so that the assertion prints the whole error
list. The backfill test's `-vv` output prints both 55-entry dicts in full; the
lines marked `[...]` below are elided from that dict output and from the
warnings summary, and nothing else is cut.

```text
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -vv tests/test_doc_front_matter.py -k decision_ledger --tb=short
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/817-decision-ledger
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 66 items / 64 deselected / 2 selected

tests/test_doc_front_matter.py::test_decision_ledger_follows_the_record_format FAILED [ 50%]
tests/test_doc_front_matter.py::test_decision_ledger_backfill_holds FAILED [100%]

=================================== FAILURES ===================================
________________ test_decision_ledger_follows_the_record_format ________________
tests/test_doc_front_matter.py:799: in test_decision_ledger_follows_the_record_format
    assert ledger_errors(ROOT, paths, classification.documents) == []
E   assert ["docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']", "docs/decisions/README.md: the Records list lacks '- [0055: Weirdness Control](0055-weirdness-control.md)'"] == []
E     
E     Left contains 2 more items, first extra item: "docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']"
E     
E     Full diff:
E     - []
E     + [
E     +     "docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## "
E     +     "Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that "
E     +     "order, not ['## Ruling', '## Rejected Alternatives']",
E     +     "docs/decisions/README.md: the Records list lacks '- [0055: Weirdness "
E     +     "Control](0055-weirdness-control.md)'",
E     + ]
_____________________ test_decision_ledger_backfill_holds ______________________
tests/test_doc_front_matter.py:822: in test_decision_ledger_backfill_holds
    assert declared == DECISION_LEDGER
E   AssertionError: assert {'0001': ('decision', 850, 'canonical'), [...]
[... 56 lines: the rest of the two 55-entry dicts and their common items ...]
E     Differing items:
E     {'0055': ('parked', 838, 'canonical')} != {'0055': ('decision', 838, 'canonical')}
[... the -vv full dict diff and the warnings summary ...]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_doc_front_matter.py::test_decision_ledger_follows_the_record_format - assert ["docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']", "docs/decisions/README.md: the Records list lacks '- [0055: Weirdness Control](0055-weirdness-control.md)'"] == []
FAILED tests/test_doc_front_matter.py::test_decision_ledger_backfill_holds - AssertionError: assert {'0001': ('decision', 850, 'canonical'), [...]
================= 2 failed, 64 deselected, 5 warnings in 0.57s =================
```

The format test's error list printed directly on the same planted tree:

```text
$ PYTHONPATH=$PWD $PY -c "from tests.test_doc_front_matter import ROOT, classify, ledger_errors, repository_paths; paths = repository_paths(ROOT); print(chr(10).join(ledger_errors(ROOT, paths, classify(ROOT, paths).documents)))"
docs/decisions/0001-the-cut.md: the ## headings must be exactly ['## Ruling', '## Rejected Alternatives', '## Reopening Criteria'] in that order, not ['## Ruling', '## Rejected Alternatives']
docs/decisions/README.md: the Records list lacks '- [0055: Weirdness Control](0055-weirdness-control.md)'
```

## Test Tails

All runs with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.
No PostgreSQL proof is owed: no code path that opens a database changes.

On `f7b73277`:

```text
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
120 passed, 5 warnings in 17.38s
```

The earlier run on `4c9ebb83` (two more rejection cases than the first
`118 passed`) was recorded without its command; it gave `120 passed, 5 warnings
in 20.29s`.

### Offline Suites

The Astra review of `6df5115a` found that the earlier offline tails named no
tested commit and predated the test changes of `4c9ebb83`. Those tails
(`2986 passed, 562 skipped` and `1848 passed, 1369 skipped`, recorded before
`5830781b`) are superseded by the runs in the next commit, which name the
commit they ran on and the state of the tree.

## Static Checks

On `d338db76`:

```text
$ $PY -m black --check tests/test_doc_front_matter.py docs/qa/817-decision-ledger/quote_audit.py docs/qa/817-decision-ledger/table_check.py docs/qa/817-decision-ledger/source_sweep.py
All done!
4 files would be left unchanged.
$ $PY -m flake8 tests/test_doc_front_matter.py docs/qa/817-decision-ledger/quote_audit.py docs/qa/817-decision-ledger/table_check.py docs/qa/817-decision-ledger/source_sweep.py
(no output, exit 0)
$ nice -n 15 $PY -m mypy --explicit-package-bases tests/test_doc_front_matter.py
Success: no issues found in 1 source file
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

`origin/main`'s `tests/test_doc_front_matter.py` is likewise clean under flake8
and mypy (`Success: no issues found in 1 source file`). mypy is not a gate for
the audit scripts; `$PY -m mypy docs/qa/817-decision-ledger/table_check.py`
reports 5 errors at both `6df5115a` and `d338db76`, so the source additions add
none.
