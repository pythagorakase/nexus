# Character card provenance regression

Browser verification for issue #946 on 2026-09-25. Both screenshots show
private QA stories, not an owner save.

- **Fresh Celia Firth:** a new wizard-to-gameplay journey with structured and
  multiline free-text choices. Unknown prose is null; diagnostic provenance
  remains. The card retains this empty state after reload and reselection.
  The run combined the #946 fix at `6087f8bb` with the #947 bootstrap fix.
- **Legacy Nell Rourke:** the original QA snapshot, restored to a separate
  private database and served read-only by the standalone #946 build at
  `6087f8bb`. The screenshot is after reload. API responses and the entire
  stored character row are unchanged across both reads; legacy setup text is
  omitted only from the reader projection.
- A separate fresh Mara Venn card still displays genuine Current Activity.
  No replacement character details were generated to fill these empty cards.

![Fresh incomplete Celia card](fresh-celia.png)

![Legacy Nell card after reload](legacy-nell-after-reload.png)

The durable local archive is `temp/qa_fix_946_947/`, including accessibility,
API and SQL evidence, usage reconciliation, and cleanup receipts. These
screenshots establish rendered behavior; they do not claim the full
PostgreSQL gate passed.

Codex — GPT-6.
