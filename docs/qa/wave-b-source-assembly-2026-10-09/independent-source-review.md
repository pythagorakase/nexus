# Independent assembly source review

Reviewed immutable merge objects through
`825c9fd997c1d75a47acd9f5ea6fbb06e3465b2a` (tree
`2a44c5d114910bc40f436e6a67f0609983c805b9`) against the input heads and
resolution ledger in `state.json`. This is source review only: no integration
tree edit, import, test, formatter, database call or ref mutation. It is not
runtime proof or final admission; final Wave A predecessors, canonical closure,
generated files and all combined proof remain pending.

One concrete correction was reported to the coordinator: the S1b/S6 merge
in `docs/orrery_retrograde_spec.md:191` accidentally changed the stage prose to
`derivation -> seed_candidates -> expansion`. Restore
`derivation -> packet -> seed_candidates`, retaining the embedding-resume and
settled-read sentences. Both source inputs preserve the packet stage. The
coordinator owns the correction and its subsequent hash. Root subsequently
reported the one-line fix in the still-uncommitted integration document; a
refreshed immutable checkpoint is pending.

The other inspected resolutions retain their contracts:

- 803 CLI docs retain models plan/fetch and doctor/init/receipts diagnostic
  exemptions. 815's transport union retains operator_api refusal and the
  existing remote write classification. Its real inspect test retains both
  S2 player-DTO parity and S5 private masked operator inspection.
- Readiness source/test/doc unions retain the production models.artifacts
  check and the desktop config/credential/runtime-command checks. The
  reachability reason unions do not silently discard init or desktop modules;
  final exact graph regeneration remains required.
- 840 retires the entire obsolete geo-only maturation test as ordered,
  including the 809 typed-settings adaptation inside that retired test.
  Surviving typed-reader assertions and the legacy pointless-place refusal
  remain. No 149 trigger is weakened by this resolution.
- S3 database prose retains the S1b claim/reuse/resume paragraph and then adds
  the transactional transcript section. Source inspection of the assembled
  flow retains UUID setup/model repointing, claim/join ownership and the
  post-claim reread; S6 retains full derivation projection and its new tests.
- 811 retains 840's retired cost-script deletion, adds the summary operator,
  preserves typed load_settings callers, and ports the new S3/836 migration
  tests to nexus.maintenance. Its newly merged caller inventory must still be
  checked on the final assembled source; source checkpoint counts are historic.
- Canonical stamp-only resolutions retain the current stamp without pretending
  the final closure has been reverified. The ledger explicitly leaves that
  work pending.

The new S1b Phase1 tests were cross-checked against 840's point requirements.
The fingerprint test is pure. The malformed-prefix test refuses before provider
boundaries; the process-claim test creates no places. The skipped-with-reused-
derivation case skips Retrograde and creates the same canned starting location
whose fixture already supplies latitude 51.47 and longitude 6.9. It reuses a
`trait_compile_inputs: None` result and does not introduce an unresolved Domain
place. No newly authored S1b case needs fabricated coordinates or bypass of
149. Existing 840 expansion point/stub-refusal assertions remain in the merged
orchestrator tests. This reasoning does not replace their later runtime proof.

The final cross-lane source pass also compared assembled `new_story_flow.py`
with S1b and the assembled transcript files with S3: differences are the ordered
UUID/model-repoint/removal changes, implementation import relocation, deferred
claim-owned transition preparation, and S6 stage prose. The assembled
`retrograde_orchestrator.py` differs from S1b only by S6's vocabulary/projection;
the saved-output and session-claim bodies remain intact. CLI source retains the
new accept/init dispatch and self-diagnostic gate. No additional actionable
source issue was found in this bounded cross-lane/conflict review. This does
not certify unrelated code, future merge deltas or runtime behavior.

Codex — GPT-6
