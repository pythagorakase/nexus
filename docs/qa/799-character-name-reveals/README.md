# Explicit character name reveal verification

QA on b0645daf reproduced an unnamed witness becoming a second character when
she supplied her name. This change accepts an explicit, narrative-supported
`same_as` declaration and retains the existing character and entity IDs.
It does not infer identities from similarity or merge historical duplicates.

The screenshots below show the production UI built at 78968b6c against immutable
`/api/characters` payloads exported from actual private PostgreSQL acceptance
runs at 53813213. Both synchronous and asynchronous commit paths produced these
before/after responses. Later changes only register production reachability and
annotate the identity key's type. Browser fixture setup supplies other read-only
endpoints; the browser phase has no database or provider access. Generation and
model compliance were not exercised in this rendered verification.

Chrome selection, reselection and reload showed one renamed witness and the
unchanged protagonist. The witness's summary remains visible. PostgreSQL tests
separately verify retained history/background, old authored alias, stable
character/entity IDs and historical roster IDs, one durable ruling, and replayable
scalar name changes. The browser fixture never changes these exported payloads.

![Original witness](before.png)
![Same witness after synchronous acceptance](after-sync.png)
![Same witness after asynchronous acceptance](after-async.png)

The offline regression suite passed 327 tests (one skipped, five PG cases
excluded in that invocation). Final targeted private PostgreSQL validation passed
82 tests, including all new reveal, staged-binding, tag, replay and reader tests
and ten schema documentation checks; four unrelated reconstruction fixture
failures match unchanged b0645daf exactly. Both additional API-export cases passed.
Scoped mypy and the UI production build passed. Full-gate results are reported in
the PR rather than inferred from these checks.

Evidence is retained locally under `temp/qa_fix_799/`. The first browser fixture
used incorrect polling-setting property names; this caused fixture-only OFFLINE
state and rapid read-only polling. It was corrected and reloaded before the final
captures. No product change was made in response. All requests were GET/HEAD;
database and provider tripwires remained zero. The owned tab and fixture listener
were closed after verification.

Codex — GPT-6.
