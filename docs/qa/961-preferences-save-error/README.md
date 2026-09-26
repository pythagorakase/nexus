# Rejected font and theme saves (#961)

A font or theme save that failed used to roll the preferences cache back silently: the selection returned to its saved value and nothing said why. The rollback was correct; the font and theme providers held their own mutation instances and never exposed the error, and the pane's WRITE REJECTED block watched only the story-settings mutation.

Both providers now expose the most recent save error. The THEME and TYPOGRAPHY cards render an accessible WRITE REJECTED alert with that message next to the control that failed. The saved selection is unchanged because the cache rollback still applies, and a successful retry clears the alert because the mutation resets. Model and story settings are untouched. Because the theme mutation is shared with the nav and splash theme switchers, which render no error, each card forgets any earlier rejection when it mounts, so an alert always describes an action taken during the current Settings visit.

## Rendered verification

Real Chrome used the production bundle built from this branch against a disclosed fixture: the real preferences and settings routes with a private `runtime.state_dir` inside the evidence directory, empty slot state through the real slot router, and read-only stubs for story settings, local models, secrets and the developer gate. No database or provider access occurred; the fixture's tripwires stayed at zero. The only failure injection was a `chmod` on the fixture's own state directory, exactly as in the nightly probe, and stopping the fixture process for a real network failure.

- Online HTTP failure: with the state directory read-only, the production writer raised `PermissionError` and the route answered 500. Clicking Cormorant Garamond twice showed the alert inside TYPOGRAPHY and left Spectral selected; clicking Gilded showed the alert inside THEME and left Veil pressed. The interface did not show OFFLINE, and the preferences file hash was constant across each window of failed writes.
- Recovery: after permissions were restored, the same font click returned 200, the alert cleared, and the new font survived a reload with no alerts.
- Network failure: with the fixture stopped, the theme and font clicks each showed a `Failed to fetch` alert in their own card and kept the saved values. After the fixture returned, the theme click saved Gilded, cleared its alert, and survived a reload.

![Both surfaces rejected while the gateway is online](both-rejected-online-500.jpg)

![Font save rejected by a network failure](font-network-rejected.jpg)

![After retry and reload](after-retry-and-reload.jpg)

## Validation and limits

Unit regressions cover an online 500 on a font save and a network `TypeError` on a theme save, each followed by a successful retry; both were red on the original files. The pane suite, the full UI suite, TypeScript and the production build passed. The private full PostgreSQL gate on `1c2d8099` is permanently RED (3504 passed, 164 failed, 67 errors, 85 skipped, 231 red nodes) against the RED `b0645daf` baseline (232 red nodes): 230 red nodes in common, no outcome changes. It is not an isolation-compliant run and not an exact baseline match: the lane's profile lacked the Keychain guard step for the whole run, so two baseline-guarded secret-store tests executed the real `security` CLI and passed, deleting, writing, reading and deleting the login Keychain item `nexus-api/test-secret-455`; a source audit found no executed owner provider-account path, but a pre-existing item under that synthetic account could have been deleted and cannot be reconstructed. One scheduler node missed its mock-provider readiness deadline and passed twice on rerun. The guard was then restored and proven and both secret nodes fail closed on focused rerun; those are separate later evidence and do not correct the original run. Raw results, the node comparison, the correction record and cleanup proofs are under `temp/qa_fix_961/full-gate/` (ignored locally). In the driving session the extension's click frame was scaled relative to CSS pixels and several clicks did not register; every asserted state was read from the DOM and the fixture log rather than from click acknowledgements.

## Rendered follow-up on the final bundle

After the review fix (`3425017c`), the bundle was rebuilt and the mount behaviour checked in the same fixture with a fresh tab: a Veil pick from the splash screen's theme menu failed against the locked directory with no surface there, then a same-document route change into Settings rendered the THEME card with no stale alert and Gilded still pressed. Inside Settings the Veil card failed with the alert and Gilded retained, and after the directory was restored the same click saved Veil, cleared the alert and survived a reload. For fonts, a Cormorant click failed with the alert and Spectral retained, real rail navigation out to Narrative and back remounted the pane without a stale alert while the directory was still locked, and the retry after restoring permissions saved Cormorant and survived a reload. Two chip clicks by coordinate did not register and one landed after an unlock; every asserted state was read from the DOM and the fixture log.

![Settings after a splash-menu failure: no stale alert](settings-after-splash-failure-no-stale-alert.jpg)

![Retry after an inside-Settings failure](theme-retry-after-inside-failure.jpg)

Claude Fable 5.1, from the Codex (GPT-6) handoff of nightly report `qa_night_2026-09-26_033343Z`.
