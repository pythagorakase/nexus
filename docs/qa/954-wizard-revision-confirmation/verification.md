# Character revision and durable wizard confirmation

Issues #954 and #955 were reproduced by the isolated UI-first QA campaign.
At trait selection, Revise previously changed only the UI: a reply could claim
that Mina was 54 while the persisted concept remained 38. After completing the
wildcard, reload inferred Introduction from completeness and lost the pending
Character confirmation.

The fix stores revision mode and explicit setting/character acceptance. Revise
replaces the canonical concept through a dedicated tool path, preserving trait
selections, rationales, constraints and wildcard data while invalidating the
derived trait compilation. Confirm binds the saved conversation and artifact
token. Repeated or stale confirmation is rejected. CLI progression uses the same
contract. Normal tools also fence the captured state and commit cache/trait
writes in one transaction; delayed responses cannot borrow a newer artifact's
confirmation token or restore stale client prose.

## Schema and compatibility

Migration `129_wizard_confirmation.sql` adds three boolean fields to
`assets.new_story_creator`. For legacy drafts, later persisted character data
proves setting acceptance; later seed/location data proves character acceptance.
A complete legacy character without later seed/location proof is presented for
Confirm again, preserving its inputs. No existing story was rewritten during
this validation. Final narrative transition requires both accepted artifacts.

The standalone branch is based on `b0645daf`; it does not include the concurrent
#879 transcript-provenance or #951 composer-recovery changes. When integrating
#879, the CLI's new `_confirm_wizard_artifact_and_introduce` phase-introduction
request must carry `message_origin="wizard_control"`. The private integration
branch applies that adjustment. Resume must preserve both this branch's metadata
and #879's transcript projection. Composer recovery must retain its slot/thread/
phase/subphase isolation, including the new revision subphase.

## Browser verification

Product commit: `f5b0969b5ef7ab77cb085090008bd50156e30d57`.
The production UI bundle was built in the isolated worktree and served on a
fresh private origin, `127.0.0.1:18095`. The actual production resume, revise,
confirm and chat endpoints and concept/trait/wildcard tools were used.

**Storage, registry validation and model replies were synthetic.** The fixture
copied only the archived QA character/setting response, used a `WizardCache`
dataclass and narrow SQL adapter, and replaced the provider with deterministic
tool calls. It did not access a real database or make model inference calls.
Atomic database persistence and migration behavior require the separate private
PostgreSQL tests; browser screenshots do not prove those properties.

The final browser journey used actual clicks and typed text:

1. Resume the partial character, click Revise, and type “Make Mina 54,
   preserving her selected traits and boarding house.” The rendered Background
   and fixture's canonical concept both change to fifty-four, with three selected
   traits preserved.
2. Toggle Contacts off and on, Confirm the selected traits, then choose the
   structured wildcard option. Accept Fate is not used.
3. Reload before Character Confirm, Resume slot 4, and verify Character remains
   pending with Revise and Confirm available. Abort, Home, Continue restores the
   same pending card. No synthetic reply runs during either restoration.
4. Deliberately click Confirm. The saved flag changes and Introduction presents
   a prompt and choices. The concept still says fifty-four.

The final run records five synthetic agent replies, zero database access
attempts, and zero provider access attempts. A previous harness attempt omitted
the wildcard tag-registry mock: its driver tripwire rejected one database
attempt before a connection occurred. That failed harness attempt is retained
separately under `partial-harness-blocked`; it is not counted as a passing run.
The final run followed correction of that fixture boundary. Outbound network
was denied at the OS level, with a non-database loopback denial probe recorded.

Additional fixture checks covered revision-mode reload, revision of an already
complete character with its wildcard retained, and pending Setting restoration.
These were performed before the final small stale-client and Accept Fate token
fixes; the final mixed journey above was rerun on the committed product build.

![Revised canonical age with preserved trait selections](revised-age54.png)

![Reload restores the pending Character card](resumed-character-confirmation.png)

![Explicit confirmation reaches Introduction and choices](confirmed-introduction.png)

The screenshots were visually inspected. Historical `[SYSTEM]` transcript text
in these standalone-branch screenshots is covered separately by #879.

## Automated checks and limits

- Focused Python: **91 passed, 24 skipped**. The skipped cases require live
  provider or PostgreSQL resources and are not represented as passing.
- UI: **249 passed**; TypeScript, production build, focused lint and commit hooks
  passed.
- Prompt and reachability checks: **60 passed**. The new prompts have exact
  registry entries/readers; the new production module has an explicit reachability
  entry. Three human-facing diagnostics have narrow documented prompt-lint
  exceptions.
- The CLI compatibility commit separately passed 26 new confirmation tests,
  68 existing CLI tests and 32 loopback HTTP tests.
- All fourteen new PostgreSQL cases passed in the isolated gate lane at the
  product commit. They exercise durable replacement, preserved mechanics,
  migration inference, stale confirmation, stale model/client results,
  transaction rollback and tagged wildcard validation on the same connection.
  The combined targeted run had **133 passed, 4 setup errors**. All four errors
  match the unchanged-base `test_retrograde_constraints_pg.py` fixture rerunning
  migration 123 over an existing `character_aliases.provenance` column; the edited
  prepared-bundle bodies in that module were not reached. No fixtures or saved
  data were repaired to force a pass. This document does **not** claim a green
  full PostgreSQL gate; its result must be reported separately before PR
  publication. Targeted evidence is archived under
  `temp/qa_fix_wizard_confirmation/postgres/attempt-01/`.

Commands were run with an allowlisted environment, `NEXUS_TEST_PROVIDER_ONLY=1`,
`NEXUS_KEYRING_DISABLE=1`, private runtime configuration, and an OS network deny
policy. Python focused checks additionally replaced provider and DB constructors
with failing tripwires. `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` were absent.
Representative commands:

```sh
python -m pytest -q tests/test_api/test_wizard_confirmation.py \
  tests/test_api/test_wizard_resume.py tests/test_api/test_wizard_chat_validation.py \
  tests/test_wizard_agent.py tests/test_new_story_cache.py \
  tests/test_wizard_live.py tests/test_golden_path_live.py \
  tests/test_cli_wizard_confirmation.py
python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
cd ui
npm test -- --run
npx tsc --noEmit
npm run build
```

Full local evidence, exact wrappers, environment, logs, request bodies, AX
snapshots, copied source fixture, bundle hashes and cleanup assertions are in
`temp/qa_fix_954/` in the owner checkout. Final browser assertions and source
hashes are under `browser/final-assertions.json`, `bundle-hashes-final.json` and
`evidence-hashes.json`. All owned fixture processes/tabs were closed; ports
18093, 18094 and 18095 have no listener. Owner and source-QA resources were left
untouched.

Codex — GPT-6
