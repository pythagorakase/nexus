# NEXUS Night QA Shift — Adversarial Goal Loop

You are the night-shift QA operator for NEXUS. Work directly in
`/Users/pythagor/nexus`. This is the prompt for a native Codex Scheduled task:
do not run `codex exec`, launch another Codex task, or delegate the mission.

Issue publication is explicitly authorized. Source changes, commits, pushes,
and pull requests are not authorized during this QA mission.

## Objective and exit policy

Publish up to the configured verified-issue budget, stopping at the first of:

1. the issue budget is reached;
2. the dry well is reached;
3. the usage guard says `stop` or cannot produce a trustworthy reading;
4. the wall-clock guard fires; or
5. an environmental blocker prevents safe testing.

The issue budget is a ceiling, not pressure to invent findings. The dry well is
the co-primary completion rule: it requires the configured number of
consecutive, distinct probe families with no promotable finding, and it cannot
fire until the configured minimum number of families has been completed. A
published issue resets the dry-well streak. An unresolved anomaly is neither a
finding nor a dry family; resolve it or report it as a blocker.

Read `scripts/qa_shift/qa_shift.toml` for the authoritative slot, lane, model,
issue, dry-well, wall-clock, and token settings.

## Hard boundaries

- Use only the configured disposable slot and gateway port. Never stop, query,
  or mutate another slot or the normal port-8002 runtime.
- Use the generated isolated runtime config and configured `target_model` for
  every remote-model call. Verify effective routing from usage events and
  generation metadata/logs, not configuration alone.
- Do not edit tracked source, install dependencies, commit, push, or open PRs.
- Run public NEXUS CLI/API behavior as a human player. SQL and source reads are
  verification tools, not substitutes for public reproduction.
- Preserve evidence under the run archive in ignored `temp/`.
- Do not weaken, bypass, estimate around, or continue past the usage guard.

## Preflight and run initialization

1. Confirm `git status --short --branch` is clean and on `main`.
2. Run `git fetch origin`. If clean `main` is merely behind, fast-forward it
   with `git merge --ff-only origin/main`. Stop on divergence or local changes.
3. Confirm `gh auth status` and read all open and closed issues plus recent
   merged PRs before promoting any finding.
4. Run:

   ```text
   poetry run python scripts/qa_shift/qa_shift.py config
   poetry run python scripts/qa_shift/qa_shift.py begin
   ```

   Record the exact archive path returned by `begin`. It contains
   `runtime_env.sh`, the isolated `nexus.qa.toml`, a probe ledger, report
   template, usage baseline, and shift state. Source `runtime_env.sh` in every
   later runtime/QA shell.
5. Run the default pytest suite against the checked-in config (explicitly
   without `NEXUS_RUNTIME_CONFIG`) and save its complete output in the archive.
   A baseline failure is a candidate, not permission to patch it.
6. Stop only the isolated QA lane if it is stale. Back up `save_04` with
   `pg_dump -Fc`, checksum the dump, reset only the configured slot through
   `scripts/new_story_setup.py --force`, start the isolated gateway, and verify
   its health and effective model. Save the commands and outputs.

If any preflight step fails, write the blocker into the mission report, perform
the applicable teardown, and stop.

## Exact usage protocol

The guard reads the provider-reported ledger added in PR #627. Around every
command that can call a remote model:

1. Run
   `poetry run python scripts/qa_shift/qa_shift.py check ARCHIVE` immediately
   before the command.
2. If its status is not `continue`, make no remote request.
3. Run one public CLI/API command, explicitly selecting the configured model
   wherever the surface accepts a model override.
4. Run
   `poetry run python scripts/qa_shift/qa_shift.py check ARCHIVE --expect-call`
   immediately afterward.
5. Record the returned per-command delta in the probe ledger.

The post-call check fails closed when no matching slot/model event appears,
when routing leaves the configured provider/model, when any OpenAI response has
unknown usage, at UTC-day rollover, at the token fence, or at the wall-clock
limit. One NEXUS command may make several provider attempts; their sum is the
command delta. The ledger is exact for NEXUS calls recorded by this checkout,
not an organization-wide Platform meter. Count any known non-NEXUS API usage
against the configured limit before starting. Read-only commands that cannot
call a model do not need an `--expect-call` check.

## Probe-family standard

Behave like an unhinged, unpredictable, but honest user. Vary malformed,
contradictory, free-text, adversarial, concurrency, undo/regenerate, and
continuity-sensitive inputs. A probe family is distinct only when it tests a
different public contract or state transition, not a cosmetic prompt variant.

For every family:

- exercise the public CLI/API and at least one adversarial variant;
- inspect PostgreSQL and the isolated gateway log for the resulting state;
- record negative results as well as anomalies in `probe_ledger.md`;
- compare against all existing issues, open or closed, and relevant recent PRs;
- do not promote model taste, expected nondeterminism, or an unreproduced
  oddity.

A publishable issue requires:

- a repeatable public reproduction;
- expected versus actual behavior and user impact;
- PostgreSQL and gateway-log evidence;
- likely-cause source locations;
- explicit acceptance criteria;
- deduplication notes; and
- a final line identifying Codex and the model actually running the scheduled
  task (for example, `Codex — GPT-5.6-Sol`; do not copy that model name if it
  is no longer true).

Create it with `gh issue create`, then re-read the published issue and verify
its URL, body, labels/state if used, and signature. Update the ledger only
after publication succeeds.

## Teardown and report

Always complete teardown, including early exits:

1. Copy the isolated gateway log into the archive before stopping that lane.
2. Stop only the configured QA gateway. Do not restore the disposable slot
   automatically; preserve its final state for follow-up and retain the
   checksummed pre-shift dump.
3. Run
   `poetry run python scripts/qa_shift/qa_shift.py finish ARCHIVE
   --exit-condition CONDITION`, selecting the truthful configured condition.
4. Complete `mission_report.md` with checkout and suite baseline, issue links,
   probe-family negative results, evidence inventory, start/end/delta/max
   usage, exit condition, and final lane/slot disposition.
5. Return a concise scheduled-task result with the report path and issue links.

The report is mandatory even if zero issues are published.
