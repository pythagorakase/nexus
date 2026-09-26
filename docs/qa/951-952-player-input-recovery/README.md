# Player input and failed-continuation recovery (#951, #952)

Reader and wizard drafts preserve exact Unicode, leading/trailing whitespace, and multiline text across navigation and reload. Acknowledgement clears only the submitted revision; unknown sends remain recoverable without automatic replay. Reader drafts are keyed by slot, stable story creation identity, and pending-session/committed-chunk frontier. Wizard drafts are keyed by slot, provider thread, and phase/subphase. Legacy stories with a null slot creation timestamp use their existing canonical protagonist ID and non-null creation timestamp, read-only.

A durable failed continuation remains visible after its toast disappears, Home/Continue, and reload. Consumed committed choices are hidden. The explicit Retry continuation action targets the displayed failed session; the backend validates that it is still the latest failure at the unchanged committed frontier with no pending draft, then reuses the saved action without writing or committing it again. Stale requests fail before inference.

## Rendered verification

Real Chrome used the production UI bundle. The isolated reader fixture used the real slot-state route with synthetic storage/generation responses. The wizard fixture used the production resume projection and chat route, in-memory TEST ConversationsClient, mocked cache, and a synthetic agent. These are disclosed fixtures: no new live model inference or real database connection occurred. Screenshots show synthetic prose/state; production database retry semantics are covered separately by private PostgreSQL tests.

- Reader: exact draft after Home/Continue and reload; a real stopped-fixture network failure followed by reconnect retained text and issued no automatic POST. One deliberate retry acknowledged and cleared it.
- Reader: an unknown response after a changed frontier preserved the prior action read-only; a structured choice produced a durable staging failure. Recovery persisted through toast expiry, Home/Continue, and reload. One explicit retry sent only slot plus expected failed session and restored a pending scene.
- Reader: another slot and a replacement story remained empty; returning to the original slot restored its draft.
- Wizard: reload/Resume and Abort/Home/Continue preserved exact text; controlled HTTP 503 retained it with an unconfirmed notice, including after reload. Deliberate free-text retry and a structured choice each received an acknowledged synthetic reply and cleared the captured draft. Reload stayed empty; changing phase did not inherit the prior phase draft, which returned when restoring its original phase.
- Unit regressions also exercise late acknowledgements after remount, revised input, multiple unconfirmed actions, slot/story/frontier isolation, storage failure, stale terminal responses, and stale retry rejection.

![Reader draft restored after offline reconnect](reader-reconnected-draft.png)

![Durable failure after reload](durable-failure-after-reload.png)

![Wizard unconfirmed draft after reload](wizard-unconfirmed-draft.png)

## Validation and limits

All **274 UI tests**, TypeScript, and the production build passed on `a4c53621`. Earlier reader bundle `bb1823c5` supplied the reader screenshots; the wizard bundle was `a4c53621`. Bundle hashes, complete AX observations, exact request logs, tripwire assertions, source QA evidence, and fixture scripts are archived at `temp/qa_fix_951/` (ignored locally). Reader fixture made four controlled synthetic POSTs: acknowledged free text, an unknown-result failure, a structured choice with terminal staging failure, and explicit retry. Wizard made one controlled 503 and two successful synthetic chat calls. Two earlier wizard harness-only 500 attempts referenced a provenance field absent on this base; the harness was corrected, logs retained, and no provider/DB access occurred. A toast-expiry click found a detached notification and was replaced by observing the durable panel; no action was repeated.

All provider/database tripwire counts remained zero. All owned fixture processes and browser tabs were closed; ports 18085, 18087, and 18091 had no listeners. Owner app, saved stories, credentials, configuration, and the live QA lane were not used. No Accept Fate action was taken.

The full PostgreSQL gate is owned by the parent review task and is **not claimed green here**. The identity regression expectations were normalized to UTC after private PostgreSQL exposed a test-connection timezone mismatch; no product, fixture, or saved-story data was altered to make that assertion pass.

Codex — GPT-6

## Follow-up: recorded action bound after a bind failure (d50f05ee)

A failure between accepting the player's action and binding the generation parent used to leave the failed session with no parent. The reader then opened ordinary input, where any different action received 409 and the accepted action had no recovery control. The binding is now written inside the acceptance transaction itself: recording a response on the committed frontier chunk (inferred or supplied as an explicit `chunk_id`) and committing a pending draft into its new chunk both bind the new generation session to that chunk atomically with the action, without requiring lease ownership. A failure after the commit, or a cancelled request whose worker commits later, therefore still leaves a retryable failed session; the abandon path additionally reconciles from the chunk's recorded action as a fallback. Failures before acceptance keep a NULL parent, so ordinary input stays open with the draft retained.

Rendered verification on the d50f05ee bundle used the same disclosed synthetic fixtures with two added reader outcomes. A structured choice followed by a bind failure produced a durable recovery panel that survived reload; one explicit Retry sent only the slot and expected session and restored a pending scene. A failure before acceptance showed the error, kept choices and free text enabled, retained the draft on the unchanged frontier, and an ordinary continue then advanced the scene. Reader and wizard drafts with Unicode, multiline and outer whitespace survived reload and Home/Continue; a rejected send kept the draft and logged an unconfirmed action; a delayed acknowledgement cleared only its own revision. Text was entered through the extension's form-input path because its keystroke path did not reach the page in that session; details, tripwire counts and driver limits are in `temp/qa_fix_951/claude/browser/browser-evidence.json`. The PostgreSQL boundary regression drives the production route through a real accept, bind outage, stale conflicting submission and eventual retry.

![Recovery after a bind failure, after reload](bind-failure-recovery-after-reload.jpg)

![Failure before acceptance leaves input open](pre-acceptance-failure-input-open.jpg)

The binding helper takes the lease row before the session row, matching every other writer in the lease module; a deterministic private PostgreSQL test pauses the worker between its two statements while a cancelled route's abandon contends, which deadlocked under the reversed order and now simply waits. The reader treats the bound parent as part of a failure's identity, so a session that was abandoned before its worker committed enters recovery on the next poll when its parent arrives, without a reload, a second toast, or any automatic request.

![Same session gains its parent on a later poll](same-session-parent-arrival-recovery.jpg)

Claude Fable 5.1, after the owner-directed handoff from Codex (GPT-6).
