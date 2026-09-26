# Rejected font and theme saves (#961)

A font or theme save that failed used to roll the preferences cache back silently: the selection returned to its saved value and nothing said why. The rollback was correct; the font and theme providers held their own mutation instances and never exposed the error, and the pane's WRITE REJECTED block watched only the story-settings mutation.

Both providers now expose the most recent save error. The THEME and TYPOGRAPHY cards render an accessible WRITE REJECTED alert with that message next to the control that failed. The saved selection is unchanged because the cache rollback still applies, and a successful retry clears the alert because the mutation resets. Model and story settings are untouched.

## Rendered verification

Real Chrome used the production bundle built from this branch against a disclosed fixture: the real preferences and settings routes with a private `runtime.state_dir` inside the evidence directory, empty slot state through the real slot router, and read-only stubs for story settings, local models, secrets and the developer gate. No database or provider access occurred; the fixture's tripwires stayed at zero. The only failure injection was a `chmod` on the fixture's own state directory, exactly as in the nightly probe, and stopping the fixture process for a real network failure.

- Online HTTP failure: with the state directory read-only, the production writer raised `PermissionError` and the route answered 500. Clicking Cormorant Garamond twice showed the alert inside TYPOGRAPHY and left Spectral selected; clicking Gilded showed the alert inside THEME and left Veil pressed. The interface did not show OFFLINE, and the preferences file hash was constant across each window of failed writes.
- Recovery: after permissions were restored, the same font click returned 200, the alert cleared, and the new font survived a reload with no alerts.
- Network failure: with the fixture stopped, the theme and font clicks each showed a `Failed to fetch` alert in their own card and kept the saved values. After the fixture returned, the theme click saved Gilded, cleared its alert, and survived a reload.

![Both surfaces rejected while the gateway is online](both-rejected-online-500.jpg)

![Font save rejected by a network failure](font-network-rejected.jpg)

![After retry and reload](after-retry-and-reload.jpg)

## Validation and limits

Unit regressions cover an online 500 on a font save and a network `TypeError` on a theme save, each followed by a successful retry; both were red on the original files. The pane suite, the full UI suite, TypeScript and the production build passed. The private full PostgreSQL gate result and its exact comparison with the unchanged `b0645daf` baseline are recorded under `temp/qa_fix_961/` (ignored locally) together with the fixture scripts, request log, driver notes and cleanup proofs. In the driving session the extension's click frame was scaled relative to CSS pixels and several clicks did not register; every asserted state was read from the DOM and the fixture log rather than from click acknowledgements.

Claude Fable 5.1, from the Codex (GPT-6) handoff of nightly report `qa_night_2026-09-26_033343Z`.
