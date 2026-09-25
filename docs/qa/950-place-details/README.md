# Place details without setup diagnostics (#950)

Product code tested: `d4419fcd9271a7d50a4a887a30e2739a4fb1a486`, based on `b0645dafb646bf849a084d6a0eda77c076492bd4`.

The place producer now leaves summary and status NULL while retaining Retrograde provenance in `extra_data`. The reader masks only exact historical summary/status signatures when both provenance fields match. Genuine prose, including partially enriched records, remains visible. The Map dialog displays “No details recorded yet.” when every prose field and inhabitant list is empty. No schema or save migration is involved, and faction behavior is unchanged.

## Rendered evidence

The before screenshot was captured by independent adversarial QA on unchanged main, from a fresh private story. The after screenshots use the fixed production UI and production `/api/places` endpoint in a private fixture server. Storage access was replaced with in-memory rows copied from that QA response; two clearly synthetic places cover new empty rows and enriched prose with retained provenance. No database or provider access was made during this browser verification. It does not claim new live inference or database persistence proof.

![Before: historical place diagnostics exposed as summary and status](before-legacy-place.png)

![After: the historical place shows an empty state following reload](after-legacy-place.png)

![Genuine summary, history and status remain visible after reload](genuine-place.png)

Actual Chrome interactions opened Map, expanded Mid-Radius Administrative Ring, opened Old Pump Annex, closed it with Escape, reopened it, reloaded, and reopened it again. New Pump Shelter also showed the empty state. Restored Pump Shelter retained its synthetic summary/history/status after reload despite matching creation provenance. The original Council Office Archive and Hearing Suite retained every captured API field and its genuine prose in the rendered dialog.

The production bundle was copied unchanged from `ui/dist/public` into a fresh origin at `127.0.0.1:18083`. Only read requests occurred. macOS sandboxing denied all outbound network connections; driver/provider tripwires counted zero attempts. The disposable server and owned Chrome tab were closed, and the port was verified free. Owner and source-QA services were untouched.

## Regression coverage

- 43 focused Python tests passed, including 11 new place payload regressions and adjacent character/Retrograde persistence coverage. These ran with provider/database tripwires and outbound denial.
- All 249 UI tests passed, including six new Map dialog cases for missing details, genuine prose, whitespace and sparse history/secrets/inhabitants.
- TypeScript, production build and commit hooks passed.
- Two new PostgreSQL tests exercise actual `_insert_place_stub`, real reader SQL/API projection, legacy/new rows, unchanged stored records across repeated reads, and enrichment with later prose. PostgreSQL validation is recorded separately by the parent task; this browser run did not execute a PostgreSQL gate.

The first UI test attempt lacked ThemeProvider and failed before exercising the component; the fixture was corrected and the full suite passed. Some initial post-reload screenshots preceded compositor painting despite a populated accessibility tree. Subsequent settled screenshots visibly confirmed the dialog without a product change; both captures are retained in the evidence archive.

Local durable evidence: `/Users/pythagor/nexus/temp/qa_fix_950/`. It includes the schema extracted from the archived QA dump, guarded test logs, browser request/AX captures, copied row data, bundle/source hashes, tripwire counters and cleanup proof. No live save was inspected or rewritten.

Codex — GPT-6
