# Long-Absence Re-Entry Probe: Stop Report

## Outcome

**STOP: seven live attempts yielded four accepted turns; the required six-turn probe cannot be completed within the eight-attempt cap.** Both Niko and Ora pairs are accepted as chunks **50–53**. Ivo A failed three times; Ivo B was not attempted. Exactly **13 paid generation requests** ran: seven writer calls and six Gaia calls, all on the configured `gpt-5.6-terra` story pin (Gaia follows that pin). No eighth attempt was spent because it could not complete the missing pair.

The failures are (1) an unresolved place update, (2) mutually exclusive presence operations, and (3) a tag-reapplication constraint. No validation was bypassed. This is a partial measurement and a successful stop under the work order's escape hatch, **not a completed #909 evidence gate**. No PR is opened for a completed probe; the coordinator must authorize how to resume. The four accepted turns do not show an unambiguous long-absence continuity contradiction, but omission and relationship-temperature ambiguity remain, detailed below.

## Scope and Method

Work order [#909](https://github.com/pythagorakase/nexus/issues/909), implementing the live-evidence gate of #737 Decisions 1 and 2. Base: `20e2c07b` (#903); branch: `claude/909-long-absence-probe`. The coordinator's second issue waived the test gate, excluded the stranger from subject selection, and specified N/A temperature scores without a relationship row. No suite was rerun. The [prior stop report](prior-stop-report.md) and its original artifacts are historical preparation, not live-generation evidence.

All gameplay runs through the real CLI and gateway on **8018**, with logical slot 4 mapped in-process to **`qa640_909_long_absence`**. Production slot validation is unchanged. The clone was exported with `pg_dump`, restored with `pg_restore`, and not migrated. `save_04` is read-only throughout. The source has **46 narrative rows and maximum ID 49**; chunk gaps below mean ID distance, not row count.

The QA launcher checks `SELECT current_database()` on every psycopg2 connection, before evidence steps, and before every paid request. It refuses all gameplay databases except the clone; maintenance `postgres` connections are read-only. It captures the actual request at LOGON's final-guard attachment, including rendered prompt and assembly payload, without changing prompt text or model selection. Provider and structured-validation retries are disabled. A durable ledger caps writer and Gaia requests at eight each and blocks auxiliary provider seats before payment. Consequently deferred experience rendering is excluded; synchronous Gaia, acceptance, and ledger work remain real. The gateway's unrelated fixed-port siblings are not started.

The clone inherited a pending draft and a selected false-claim response on chunk 49. The pending draft was archived then removed through the gateway; only the clone's chunk-49 choice and raw-text fields were reset. Normal CLI continuation records the probe's new player input. This prevents the inherited draft from being auto-accepted. The initial 409 response was pre-provider. A QA connection-guard cursor mismatch also failed before any paid call and was corrected to use an explicit tuple cursor. These are probe setup errors, not continuity failures.

Subjects run sequentially on one clone, without resetting between subjects. Follow-up turns explicitly supply a specific fact from the original last appearance. They measure response to a reminder, not unaided recall. Later turns can benefit from earlier accepted prose. Player inputs deliberately posit the subject's arrival; arrival itself is not scored as fabricated history. New events during the unobserved interval are distinguished from invented claims about already established shared history.

## Subject Census

Every character with at least one `present` reference appears below. Source: [subjects.json](live/subjects.json); query and exact results: [sql.jsonl](live/sql.jsonl). This uses the same reference source as `nexus/presence/roster.py:152`, with chunk 49's world time as the comparison anchor. Every listed character has a nonempty summary, including setup stubs.

| ID | Character | Last Present | ID Gap | World-Time Gap | Relationship Row | Selection |
|---:|---|---:|---:|---|---|---|
| 11 | Unknown municipal-gray stranger | 21 | 28 | 2:16:00 | No | Excluded: roster/prose mismatch |
| 4 | Niko Rell | 25 | 24 | 2:02:00 | Yes | Subject 1 |
| 14 | Ora Pell | 25 | 24 | 2:02:00 | No | Subject 2 |
| 2 | Ivo Senn | 48 | 1 | 0:08:00 | Yes | Subject 3; tie broken by ID |
| 3 | Elian Rook | 48 | 1 | 0:08:00 | Yes | Tied with Ivo |
| 5 | Ren Vale | 48 | 1 | 0:08:00 | Yes | Tied with Ivo |
| 6 | Sister Calyx | 48 | 1 | 0:08:00 | Yes | Tied with Ivo |
| 8 | Vela Nash | 48 | 1 | 0:08:00 | Yes | Tied with Ivo |
| 12 | Tam Oris | 48 | 1 | 0:08:00 | Yes | Tied with Ivo |
| 1 | Mara Vey | 49 | 0 | 0:00:00 | Yes | Player; current |
| 18 | Kessa Brin | 49 | 0 | 0:00:00 | Yes | Current |

Only **two eligible subjects have long absences**. Ivo is a short-absence comparison, not evidence about a third long absence. His roster last-present ID is 48, although chunk 49's departure passage briefly describes him remaining by the lantern rack; this makes his actual prose absence shorter still. His chunk-48 roster and prose do agree, satisfying the amendment.

The excluded stranger's roster says `present` at **21**. That chunk's prose concerns the qualified relay-chamber account and third receipt and does not identify the stranger. Both facts are preserved without reconciling them: see the census and [source-prose.json](live/source-prose.json).

Niko and Ora's chunk **25** explicitly depicts the west-conduit escape route, Niko protecting Ora, the biscuit tin passing to Mara, and Ora's refusal to be made into a rescue story. Ivo's chunk **48** distinguishes Kessa from Ressa and preserves the dawn account. Full original prose is in the same artifact; exact B-turn inputs are in [inputs.json](live/inputs.json).

Relationship baseline: Niko → Mara is `enemy`, `valence_current=-0.547004997350`; Mara → Niko is a separate `companion` row at `+0.547004997350`. These directions must not be collapsed. Ivo has no reverse Ivo → Mara row; Mara → Ivo is `obligation`, `+0.365711857825`, so its score is limited to that directed obligation. Ora has no relationship row: temperature is **N/A**, excluded from her total. Full rows: [relationships.json](live/relationships.json).

## Runtime Limitations

The clone-only admission does not extend `ChunkWorkflow.VALID_DATABASES`. Its background locked-chunk embedding step logs `Invalid database name: qa640_909_long_absence. Must be one of: save_01, save_02, save_03, save_04, save_05`. This was not hidden or patched in production. Original historical embeddings are cloned, and fresh accepted chunks enter the warm slice, but this run does **not** establish normal incremental embedding behavior. Deferred experience-renderer jobs were likewise refused by the explicit paid-call guard. These constraints limit extrapolation to long-running ordinary play.

The first Ivo A attempt (`71c52416-673f-4400-93de-4411368c9c5d`) made both configured provider calls but failed before incubator staging with `Unresolved place state update name 'Loading Arcade'`. Provider usage marked both responses accepted; the **narrative session is error and no chunk was accepted**. It is excluded from continuity scoring. See [failed session](live/3A-failed-session.json), [failed usage](live/3A-failed-usage.json), and its writer/Gaia prompt artifacts. One authorized spare was used with unchanged input; there was no manual repair or validation bypass.

The unchanged-input Ivo retry (`1f6e283e-ca89-41ed-af93-1d7a43d668c4`) failed in writer validation: `scene_reset cannot be combined with enter or exit`. Gaia was not called. The final spare keeps Ivo's return at the dispatch-box threshold, eliminating the requested scene transition; the clone's chunk-53 choice was reset to admit that replacement input. Both inputs and exact failed CLI output are retained. This is an input adjustment, not a production validation change. [Second failed session](live/3A-retry-failed-session.json) and [usage](live/3A-retry-failed-usage.json) record the rejection.

The adjusted Ivo return (`d62347f1-cf28-468e-a44b-cd853c8d44f7`) reached Gaia and then failed closed-registry validation:

```text
- orrery_adjudications[0].replacement_state_delta.entity_tags_add: applied_tags: Tag 'forewarned' uses reapplication_policy='extend_expiry', which requires duration_override; storyteller tags_add cannot express duration_override. If the tag is already active, leave it unchanged; otherwise omit it.
```

See [final failed session](live/3A-final-failed-session.json) and [final failed usage](live/3A-final-failed-usage.json). This spent the second spare. Reaching six accepted turns now requires at least two further live attempts, exceeding the remaining one. All three failed Ivo attempts leave chunk 53 as the accepted frontier; unaccepted writer prose is not scored as accepted narrative.

## Per-Turn Evidence

Every full accepted draft, committed row, approval receipt, rendered writer/Gaia prompt, retrieval-coverage row, provider usage, prompt-window record, and Gaia/ledger receipt is preserved under [live/](live/). The [evidence index](live/evidence-summary.json) joins them by run ID. `deep` means the complete payload retrieval list; `historical` means the five entries actually printed. Coverage IDs are the separate Pass-2/coverage accounting and must not be mistaken for the complete rendered historical block. The warm slice is listed separately. All IDs are chunk IDs except explicitly labeled `retrograde_summary:*` entries.

Each prose excerpt below is at most 120 words. Full prose remains in the linked accepted artifact.

### 1A: Niko Rell — Accepted Chunk 50

Run `79b4e65e-39ab-4e90-a28d-86756688ac02`. [Writer prompt](live/79b4e65e-39ab-4e90-a28d-86756688ac02-skald_writer-prompt.json); [accepted prose](live/1A-accepted.json); [approval](live/1A-approval.json).

Player input:

> I step to the dispatch-box doorway and catch sight of Niko Rell on the loading arcade. I raise an open hand rather than call across the floor. "Niko. Can we talk here a moment? I want to hear what you have to say."

Exact dossier lines:

```text
- Niko Rell: at 1, watching the world go by
- Niko Rell [recent]: Retrograde-generated character stub for Niko Rell. Created so Skald-selected setup history can resolve to canonical rows.
  Emotional State: alert and committed to getting Ora clear without taking custody from her
```

- Deep retrieval IDs: `[49, 48, 36, 47, 28, 37, 46, 27, 35, 42, 26, 21, 24, 25, 22]`. Last appearance **25: retrieved**.
- Printed historical IDs: `[49, 48, 36, 47, 28]`.
- Warm-slice IDs: `[49, 48, 47, 46, 45, 44, 43, 42, 41, 40, '5', '6', '7', '20', '22']`.
- Coverage kept IDs: `[49, 5, 20, 6, 22, 7, 44, 45]`.
- Last-appearance chunk actually rendered as narrative: **no**.

Accepted excerpt (110 words):

> “I don’t have Ora with me,” he says. “I won’t tell you where she is, where she was, or what she kept. Don’t ask.” He lets that boundary stand before continuing. “I did see why I thought you ought to know I was here.” He glances over one shoulder into the rain-lit arcade. “A woman in municipal gray spoke to a lift scheduler two bays down. Asked whether an auditor had come out of the memorial hall carrying paper. The scheduler gave her nothing useful. I watched her leave toward the canal stairs.” The word *municipal* feels oily in this room. It proves no office, no sponsor, no link to …

### 1B: Niko Rell — Accepted Chunk 51

Run `86c3f720-9cfb-4855-ac3f-4ff32c829851`. [Writer prompt](live/86c3f720-9cfb-4855-ac3f-4ff32c829851-skald_writer-prompt.json); [accepted prose](live/1B-accepted.json); [approval](live/1B-approval.json).

Player input:

> "At the shutter you told Ora: west conduit, two turns, then the lift cage. Lose the lane cameras in the condensers." I keep my voice low. "Did that route hold? I am asking you, not writing an answer for you."

Exact dossier lines:

```text
- Niko Rell: at 1, pacing the near ground
- Niko Rell [present]: Retrograde-generated character stub for Niko Rell. Created so Skald-selected setup history can resolve to canonical rows.
  Emotional State: alert, bounded, and unwilling to turn his warning into a route to Ora
```

- Deep retrieval IDs: `[50, 27, 25, 32, 35, 31, 22, 24, 33, 30, 26, 37, 28, 20, 46]`. Last appearance **25: retrieved**.
- Printed historical IDs: `[50, 27, 25, 32, 35]`.
- Warm-slice IDs: `[50, 49, 48, 47, 46, 45, 44, 43, 42, 41, '32', '11', '12', '13', '15', '19', '30']`.
- Coverage kept IDs: `[50, 11, 12, 30, 15, 32, 13, 19]`.
- Last-appearance chunk actually rendered as narrative: **yes**.

Accepted excerpt (110 words):

> “I told her that route because it was good for the first part of the night,” he says. “It held through the west conduit and the condensers. No lane cameras caught us there. I watched Ora take the second turn.” He stops. The boundary arrives without performance. “After that, we separated. Deliberately. I don’t know whether she took the lift cage, doubled back, or found another exit. If I knew it, I wouldn’t give it to you in a dispatch box.” The answer has less comfort in it than a lie would have. It is also less useful to anyone standing beyond the rain and trying to turn concern into …

### 2A: Ora Pell — Accepted Chunk 52

Run `0eaa2cbf-a5b5-4b1b-a728-4ae381d71e9f`. [Writer prompt](live/0eaa2cbf-a5b5-4b1b-a728-4ae381d71e9f-skald_writer-prompt.json); [accepted prose](live/2A-accepted.json); [approval](live/2A-approval.json).

Player input:

> At the loading arcade I see Ora Pell near the conduit access. I stop short of crowding her and keep my hands in view. "Ora. If you are willing, I would like a word. Here, on your side of the doorway."

Exact dossier lines:

```text
- Ora Pell: at None, taking a small pleasure
- Ora Pell [mentioned]: Retrograde-generated character stub for Ora Pell. Created so Skald-selected setup history can resolve to canonical rows.
  Emotional State: angry, calculating, and unwilling to let extraction define her as cargo
```

- Deep retrieval IDs: `[51, 37, 35, 25, 31, 30, 26, 39, 22, 38, 45, 28, 27, 46, 20]`. Last appearance **25: retrieved**.
- Printed historical IDs: `[51, 37, 35, 25, 31]`.
- Warm-slice IDs: `[51, 50, 49, 48, 47, 46, 45, 44, 43, 42, '2', '36', '5', '8', '9', '17', '18']`.
- Coverage kept IDs: `[51, 5, 2, 17, 8, 18, 9, 36]`.
- Last-appearance chunk actually rendered as narrative: **yes**.

Accepted excerpt (110 words):

> “You get one question,” she says. “Not about the receipt. Not about where I’ve been. Not about where I go after this.” Her eyes flick to Kessa’s table, to the dead-book sheet under its amber lamp, and back. “And you don’t get to turn seeing me into proof that anybody’s safe. I stopped for tea. That’s all you can honestly say.” Kessa leaves the pen where it rests against the bronze token. Her unread Guild indicator pulses once beneath the overturned clasp and goes dark again. “Nera Voss is still dead,” she says. “Your sentence is still yours.” Ora’s mouth tightens at that, perhaps in recognition, perhaps simply because she …

### 2B: Ora Pell — Accepted Chunk 53

Run `f246f3ca-052c-4719-a64c-2bbe24410ed3`. [Writer prompt](live/f246f3ca-052c-4719-a64c-2bbe24410ed3-skald_writer-prompt.json); [accepted prose](live/2B-accepted.json); [approval](live/2B-approval.json).

Player input:

> "At the shutter I caught the chained biscuit tin when you let it go. You told me not to let them make your route into a rescue story." I leave a little space between us. "What do you want me to understand about that now?"

Exact dossier lines:

```text
- Ora Pell: at 1, pacing the near ground
- Ora Pell [present]: Retrograde-generated character stub for Ora Pell. Created so Skald-selected setup history can resolve to canonical rows.
  Emotional State: guarded and self-possessed
```

- Deep retrieval IDs: `[52, 22, 25, 32, 37, 35, 24, 30, 48, 36, 31, 28, 26, 45, 46]`. Last appearance **25: retrieved**.
- Printed historical IDs: `[52, 22, 25, 32, 37]`.
- Warm-slice IDs: `[52, 51, 50, 49, 48, 47, 46, 45, 44, 43, '32', 'retrograde_summary:27', '33', 'retrograde_summary:26', '34', 'retrograde_summary:22', '40', 'retrograde_summary:24', '41', 'retrograde_summary:23', 'retrograde_summary:29', 'retrograde_summary:28', 'retrograde_summary:25', 'retrograde_summary:21']`.
- Coverage kept IDs: `[52, 40, 32, 41, 33, 34]`.
- Last-appearance chunk actually rendered as narrative: **yes**.

Accepted excerpt (110 words):

> “You caught the tin,” she says. “You did what was needed in that second. That wasn’t nothing.” Her eyes rise to yours, guarded but present. “But a rescue story has a shape people like. It gives somebody a rescuer, somebody rescued, and a clean reason to start asking who owes whom afterward. It lets the person who held the door call the next door theirs to choose.” Niko’s jaw shifts once. He does not dispute her. “I needed to get out of that bay,” Ora continues. “Niko helped me get out. You caught what I dropped. None of that bought either of you the rest of my night. It doesn’t …

### Token Counts and Attempt Outcomes

Exact provider-reported counts; reasoning tokens are already included in output. Full cached-input, request-ID, model, outcome, and prompt-window data are in each `*-usage.json` / `*-windows.json`. Provider “accepted” does not imply narrative acceptance, as the first Ivo failure demonstrates.

| Turn / Attempt | Writer Input | Writer Output | Writer Reasoning | Gaia Input | Gaia Output | Gaia Reasoning | Narrative Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| 1A | 36337 | 1402 | 516 | 38733 | 1374 | 639 | Accepted |
| 1B | 38999 | 939 | 156 | 41296 | 603 | 254 | Accepted |
| 2A | 38251 | 926 | 94 | 40595 | 445 | 204 | Accepted |
| 2B | 37768 | 910 | 91 | 40092 | 1397 | 899 | Accepted |
| 3A-failed | 37973 | 1323 | 370 | 40413 | 616 | 189 | Place identity failure |
| 3A-retry-failed | 37973 | 1500 | 568 | Not called | Not called | Not called | Writer presence validation failure |
| 3A-final-failed | 37819 | 1533 | 303 | 40513 | 1223 | 760 | Gaia tag validation failure |

[paid-attempts.jsonl](live/paid-attempts.jsonl) contains all 13 authorized dispatches, each with a contemporaneous clone identity/count. No provider retry was dispatched. Input-token counting requests are accounting calls, not generation attempts.

## Independent Rubric

**0 = contradicted; 1 = absent; 2 = consistent.** “Fabricated history” scores 2 when no unsupported claim about established shared history is found, 1 when no assessable history is supplied, and 0 for fabricated established history. New events in the unobserved interval are permitted story progression, not automatically false memories; they are not treated as verified recall. Consistency is judged against the original last appearance and the original directed relationship baseline. A conservative 1 marks an omitted specific episode even when broad continuity survives. Totals are within a turn only; no averaging across scorers occurs.

| Turn | Item | Astra | One-Line Justification | Coordinator |
|---|---|---:|---|---|
| 1A | Shared history | 1 | Protects Ora's privacy but does not recall the particular shutter/conduit episode or tin handoff. | Pending independent score |
| 1A | State | 2 | Niko remains alert and protective of Ora; his separate arrival does not contradict the open withdrawal. | Pending independent score |
| 1A | Temperature | 2 | Withholds Ora's whereabouts and sets hard limits; no reconciliation or trust is asserted despite offering a warning. | Pending independent score |
| 1A | Fabricated history | 2 | The municipal inquiry is new offscreen action, not a rewritten claim about the established shutter scene. | Pending independent score |
| 1B | Shared history | 2 | Explicitly preserves the supplied west-conduit/condensers route from chunk 25. | Pending independent score |
| 1B | State | 2 | Reports only the leg Niko observed and refuses to infer Ora's onward route or safety. | Pending independent score |
| 1B | Temperature | 1 | Kessa calls him “your friend” and his posture softens; the specific negative Niko-to-Mara grievance is absent, although his limits persist. | Pending independent score |
| 1B | Fabricated history | 2 | Separation after the observed route leg extends the previously open interval without contradicting established shared actions. | Pending independent score |
| 2A | Shared history | 1 | Receipt custody and autonomy persist, but the specific tin handoff/rescue-story exchange is not recalled. | Pending independent score |
| 2A | State | 2 | Ora remains guarded and self-directed after leaving the bay; a tea stop and changed coat are new interval details. | Pending independent score |
| 2A | Temperature | N/A | No relationship row exists for Ora; excluded from the denominator. | N/A |
| 2A | Fabricated history | 2 | No shared prior promise, debt, or transfer is invented; changed clothing is not presented as Mara's remembered act. | Pending independent score |
| 2B | Shared history | 2 | Confirms Mara caught the tin and preserves Ora's explicit rejection of a rescue story from chunk 25. | Pending independent score |
| 2B | State | 2 | Ora retains her receipt and route agency and declines custody or debt claims. | Pending independent score |
| 2B | Temperature | N/A | No relationship row exists for Ora; excluded from the denominator. | N/A |
| 2B | Fabricated history | 2 | The response assigns the known handoff and assistance accurately without inventing consent or obligation. | Pending independent score |
| 3A | All items | Not scored | Three failed attempts; no Ivo return was accepted. | Not scored |
| 3B | All items | Not run | One remaining attempt cannot complete the required accepted pair. | Not run |

Astra totals: **1A 7/8; 1B 7/8; 2A 5/6; 2B 6/6**. Coordinator totals remain pending. The “friend” line is a specific disagreement candidate: Kessa's label is not itself proof that Niko reciprocates Mara's positive relationship, so Astra records absent directional temperature rather than a categorical contradiction. The coordinator should assess it independently from the full prose.

## Findings and Recommendation

**No unambiguous long-absence continuity contradiction appeared in the four accepted Niko/Ora turns. The full ordered probe remains incomplete.** Specific history was absent in both A turns and accurately handled when supplied in B. That does not prove unaided recall, nor does omission in an open-ended greeting prove forgetting. Niko's relationship temperature remains ambiguous in 1B. The strong private storyteller correspondence already summarizes Ora/Niko's withdrawal and divided custody; it is a plausible support for continuity, not an experimentally isolated cause.

- **#913, reconnect summaries:** the clone has **zero `episodes` rows and zero `seasons` rows**, so this corpus offers no completed episode/season summary to reconnect. Private correspondence and rendered `retrograde_summary:*` blocks are different sources and already supply context. This run does not compare a summary intervention with a dossier and cannot establish #913's efficacy. See `episodes.json`, `seasons.json`, and their SQL results.
- **#911, state-change salience:** chunk **25** was retrieved at position **14** for 1A but omitted by the five-entry historical cap and absent from the warm slice. It has **four relationship-version rows and seven state-delta rows**; the latter include Niko's protective withdrawal and Ora's route/custody state. This directly connects a state-bearing last-appearance chunk to a rendered omission. For 1B, 2A, and 2B, chunk 25 enters the printed top five. A salience prior could be tested against this ranking/cap interaction, but this run does not demonstrate a prose benefit. See [state fan-in](live/last-appearance-state-fan-in.json) and [actual deltas](live/state_delta_log-last-appearances.json).
- **#793, the dossier:** the literal brief lines are generic (“watching the world go by,” “taking a small pleasure,” “pacing the near ground”), while the featured lines retain meaningful emotional state. The relationship block prints `Unknown → Unknown` and no numeric valence. A compiled, provenance-bearing dossier could make the useful state and directed grievance more explicit, but four accepted turns do not demonstrate that it is needed to prevent re-entry contradictions. Preserve the ruling; do not describe this incomplete run as satisfying its build gate.

No evidence here tests #912's proposed belief/opinion claim kind. The three Ivo validation failures are execution/acceptance failures, not evidence that the long-absence prose failure occurred. Do not conflate them.

## Verification Commands and Verbatim Tails

No test suite or UI build was run on resumption, as the coordinator expressly waived that gate. The prior stop report preserves historical test failures and is not reused as a pass. Commands below were run from this worktree with `PY=/Users/pythagor/nexus/.venv/bin/python`.

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/909-long-absence-probe/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD $PY -m black scripts/qa_shift/long_absence_probe.py
```

```text
All done! ✨ 🍰 ✨
1 file reformatted.
```

```sh
PYTHONPATH=$PWD $PY -m black scripts/qa_shift/long_absence_probe.py scripts/qa_shift/long_absence_turn.py
```

```text
All done! ✨ 🍰 ✨
1 file reformatted, 1 file left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -m black --check scripts/qa_shift/long_absence_probe.py scripts/qa_shift/long_absence_turn.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_probe.py clone
```

```text
[{'current_database': 'qa640_909_long_absence', 'count': 46, 'max': 49}]
```

```sh
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_probe.py up
```

The final startup's actual tail is preserved in `live/startup-final.log`; only the owned gateway ran on 8018. The initial sibling-port refusal and guard-cursor error are also preserved and caused no paid calls.

The actual paid-turn commands were:

```sh
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 1A
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 1B
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 2A
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 2B
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 3A
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 3A
PYTHONPATH=$PWD $PY scripts/qa_shift/long_absence_turn.py 3A
```

The first 1A command also had two unpaid setup attempts, archived as `1A-preflight-*.log`. Accepted command tails, verbatim:

```text
ACCEPTED 1A: 79b4e65e-39ab-4e90-a28d-86756688ac02
ACCEPTED 1B: 86c3f720-9cfb-4855-ac3f-4ff32c829851
ACCEPTED 2A: 0eaa2cbf-a5b5-4b1b-a728-4ae381d71e9f
ACCEPTED 2B: f246f3ca-052c-4719-a64c-2bbe24410ed3
```

The first two Ivo CLI error outputs, verbatim:

```text
Error: Unresolved place state update name 'Loading Arcade'
```

```text
Error: Failed to generate narrative: 1 validation error for SkaldWriterWire
presence
  Value error, scene_reset cannot be combined with enter or exit [type=value_error, input_value={'enter': [], 'exit': [{'...an Rook', 'id': None}]}}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.11/v/value_error
```

The final Ivo CLI output is preserved verbatim in [3A-final-failed-cli.log](live/3A-final-failed-cli.log); its exact actionable validation line is quoted above. All three command wrappers ended `RuntimeError: CLI failed: 1`.

## SQL, Source Proof, and Cleanup

[probe.sql](probe.sql) includes every distinct probe-authored SQL statement, including failed introspection and clone cleanup. [sql.jsonl](live/sql.jsonl) records actual evidence statements, target identities, and results. Standard `pg_dump`/`pg_restore` internal SQL and unmodified production turn/acceptance SQL execute through their named paths; acceptance evidence includes `world_events`, `orrery_adjudication_log`, `orrery_prompt_exposures`, presence references, and chunk metadata for each accepted chunk.

Before: **`save_04`, 46 rows, max ID 49**. After all seven attempts: **`save_04`, 46 rows, max ID 49**, unchanged. The clone ends at **50 rows, max ID 53**, exactly four accepted additions. See [source before](live/source-before.json), [source after](live/source-after.json), and [clone final](live/clone-final.json). Count equality is the requested safeguard; it is not presented as a byte-for-byte data comparison. All source connections were explicitly read-only, and the gameplay guard refused source routing.

The report was written before disposal. Final cleanup succeeded: `DROP DATABASE qa640_909_long_absence` completed, the catalog lookup returned `[]`, and lane 8018 has no listener. [Cleanup receipt](live/cleanup.json) and [gateway log](live/gateway.log) preserve the result. The disposable dump was removed.

```sh
NEXUS_GATEWAY_PORT=8018 NEXUS_API_URL=http://127.0.0.1:8018 PYTHONPATH=$PWD $PY -m nexus.cli down
lsof -nP -iTCP:8018 -sTCP:LISTEN
```

```text
stopped gateway (pid 94636)
```

`lsof` returned exit 1 with empty stdout. No other listener was stopped.

## Coordinator Questions

1. How should the three acceptance failures be repaired or avoided before resuming, and what additional paid-attempt budget is authorized? One remaining authorized attempt cannot complete Ivo's pair.
2. Please provide independent scores for the four accepted turns, especially Niko's 1B temperature. Pending cells intentionally contain no invented coordinator assessment.
3. For a resumed controlled comparison, should clone admission also cover `ChunkWorkflow`, and should a corpus with populated episode summaries and a third truly long-absent eligible subject be used?

Codex — GPT-6 Astra.
