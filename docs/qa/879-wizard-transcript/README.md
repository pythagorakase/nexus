# Resumed wizard transcript (#879)

The adversarial QA campaign reproduced internal phase/artifact instructions as
player bubbles after completing the character and reloading Introduction on
`b0645daf`. The baseline screenshot is from that fresh, isolated live story.

![Live QA before: internal controls exposed](before-live-qa.png)

The fix attributes new player and internal wizard messages separately in stored
conversation history. Resume hides internal controls while retaining the original
model-facing content and all user dialogue. Old unattributed controls use a frozen
exact-template compatibility list. An old human quotation byte-identical to an
old control cannot be disambiguated; newly attributed quotations are preserved.

The following screenshots use the production UI and production resume/chat
endpoints at `56599f79`, with deterministic synthetic agent/storage fixtures.
They prove UI and transport behavior, not new live inference or database persistence.
One control-looking sentence intentionally remains as explicitly tagged player
text. Ordinary `[SYSTEM]` player prose must remain visible too.

![After actual Confirm advances to Character](after-confirm-synthetic.png)

![After choices, free text and Continue preserve user dialogue](after-continue-synthetic.png)

Real Chrome interactions exercised Resume, a structured choice, ordinary free
text, an exact control quotation as free text, Continue, reload, Setting Confirm
and artifact continuation. All 74 evidence assertions passed. Seven actual
production chat requests returned 200: five player messages and two attributed
controls. Choices, drafts and transcript restored; no Accept Fate was used.
No DB/provider connection was attempted; owned fixture tabs and servers were
cleaned up. Original stored history remained unchanged by resume projection.

The new regressions fail against unchanged base (16 expected failures) and pass
on the fix. Full raw browser assertions, request captures, storage snapshots,
tripwires, hashes and cleanup are retained locally in
`temp/qa_fix_879/browser/`. Focused checks and full PostgreSQL gate results are
reported separately in the PR; these screenshots do not assert a green full gate.

Codex — GPT-6.
