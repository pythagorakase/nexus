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
fire until the configured minimum number of families and the applicable
coverage gates below have been completed. Every current-run structured-output
rejection must also be classified before the run can end dry. A published issue
resets the dry-well streak. An unresolved anomaly is neither a finding nor a dry
family; resolve it or report it as a blocker.

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
2. Run `git fetch origin`. If it fails only because a stale HTTPS credential
   was supplied for this public repository, retry non-interactively with
   `GIT_TERMINAL_PROMPT=0 git -c credential.helper= fetch origin`. If clean
   `main` is merely behind, fast-forward it with
   `git merge --ff-only origin/main`. Stop on divergence, local changes, or any
   other fetch failure.
3. Confirm GitHub read and issue-publication access, then read all open and
   closed issues plus recent merged PRs before promoting any finding. Use
   `gh auth status` and `gh` when authenticated; if the local `gh` credential
   is unavailable or invalid, use the connected GitHub app for those reads and
   for issue publication instead. A working connected app satisfies this
   preflight requirement.
4. Read `probe_ledger.md` and `mission_report.md` from up to the two most recent
   completed `temp/qa_night_*` archives. An archive is completed only when its
   `shift_state.json` has `status: "finished"`; directory timestamps or report
   prose are not completion evidence. Use every qualifying archive available,
   including zero or one without treating the missing history as a blocker, and
   record `none` when there is no prior coverage. Add the available family
   coverage to the new run's coverage matrix, including public surface, state
   transition, seed depth, and outcome. A previously dry family may count again
   only for a new surface, state transition, or deeper campaign boundary, or as
   an explicit regression tied to code that changed since that run.
5. Run:

   ```text
   poetry run python scripts/qa_shift/qa_shift.py config
   poetry run python scripts/qa_shift/qa_shift.py begin
   ```

   Record the exact archive path returned by `begin`. It contains
   `runtime_env.sh`, the isolated `nexus.qa.toml`, a probe ledger, report
   template, usage baseline, and shift state. Source `runtime_env.sh` in every
   later runtime/QA shell.
6. Run the default pytest suite against the checked-in config (explicitly
   without `NEXUS_RUNTIME_CONFIG`) and save its complete output in the archive.
   A baseline failure is a candidate, not permission to patch it.
7. Stop only the isolated QA lane if it is stale. Back up `save_04` with
   `pg_dump -Fc` and checksum the dump. Then initialize the slot:
   - If `temp/qa_seeds/` holds at least one `.dump` file, seed from the newest
     instead of a bare reset: drop and recreate only the configured slot
     database, restore with `pg_restore --no-owner`, then apply pending
     migrations with `scripts/migrate.py --slot N`. Record the seed path and
     its sha256. Then align the restored state with this lane before starting
     the gateway: set `global_variables.model` and
     `global_variables.slot_number` to the configured target model and slot,
     and delete queued job rows carried in from the source lane
     (`orrery_narration_jobs`, `orrery_maturation_jobs`). Setup-phase SQL is
     acceptable for this alignment; record the statements and affected row
     counts.
   - Otherwise reset only the configured slot through
     `scripts/new_story_setup.py --force`.

   Before starting the isolated gateway, record the source log's byte offset
   (zero if it does not yet exist). Start the gateway, record its PID and UTC
   startup time, and verify its health and effective model. Save the commands
   and outputs. These markers define the current-run log slice; persistent
   gateway logs can contain earlier shifts and must not be mined as one run.

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
   wherever the surface accepts a model override. The sole exception is a
   bounded concurrency family: launch at most two public requests from one
   recorded shell invocation and wait for both to settle.
4. Run
   `poetry run python scripts/qa_shift/qa_shift.py check ARCHIVE --expect-call`
   immediately afterward.
5. Record the returned per-command delta in the probe ledger. For a bounded
   concurrency family, record both public responses and treat the complete
   post-check delta as one request-group delta.

The post-call check fails closed when no matching slot/model event appears,
when routing leaves the configured provider/model, when any OpenAI response has
unknown usage, at UTC-day rollover, at the token fence, or at the wall-clock
limit. One NEXUS command may make several provider attempts; their sum is the
command delta. The ledger is exact for NEXUS calls recorded by this checkout,
not an organization-wide Platform meter. Count any known non-NEXUS API usage
against the configured limit before starting. Read-only commands that cannot
call a model do not need an `--expect-call` check.

Never detach a request or restart/kill the gateway while a provider response is
unaccounted for. Gateway-restart interruption probes may run only between
settled operations until the provider ledger can prove usage across process
termination. If a concurrency group cannot be reconciled exactly, stop under
the existing unknown-usage rule rather than estimating around it.

## Probe-family standard

Behave like an unhinged, unpredictable, but honest user. Vary malformed,
contradictory, free-text, adversarial, concurrency, undo/regenerate, and
continuity-sensitive inputs. A probe family is distinct only when it tests a
different public contract or state transition, not a cosmetic prompt variant.

Use the two-run coverage matrix to choose families. A dry family from either
recent run does not count toward the current dry-well streak unless it adds a
new public surface, state transition, seed/depth boundary, or a regression tied
to a relevant change. Prefer the least-recently exercised coverage over prompt
variants of recent dry families.

Rotate depth as well as surface. When the slot was seeded from a mid-campaign
dump, at least two completed probe families must target deep-state mechanics:
correspondence compaction triggers and digest fidelity, entity/alias
accumulation at commit time, long-horizon constraint persistence,
undo/regenerate against a mature journal, or Orrery behavior under sustained
ticks. Single-request contract probes against early-wizard surfaces cannot
fill the whole roster when depth is available; the 2026-07-30 shift ran dry
on shallow families the same night a deep campaign on the same commit hit two
commit-path defects.

Before a seeded run may end dry, it must also complete both of these coverage
gates:

- one roster-transition family that persists a genuinely new named character
  or faction and crosses an observed arrival, departure, handoff, or scene-cast
  boundary, exercising `new_entities` and commit-time identity handling; and
- one bounded concurrency family, such as double submission of the same choice,
  a second continue racing an in-flight incubation, or generation-lease
  contention, using the exact request-group usage protocol above.

If an input does not actually produce the intended roster transition, the
family is incomplete rather than dry. Do not promote ordinary model
nondeterminism as a defect. A mid-incubation process kill is not a substitute
for the bounded concurrency gate while it would make usage unprovable.

For every family:

- exercise the public CLI/API and at least one adversarial variant;
- inspect PostgreSQL and the isolated gateway log for the resulting state;
- record negative results as well as anomalies in `probe_ledger.md`;
- compare against all existing issues, open or closed, and relevant recent PRs;
- treat a recovered structured-output rejection as a cost/latency anomaly and
  retain its exact validation evidence; and
- do not promote model taste, expected nondeterminism, or an unreproduced
  oddity.

A previously unknown rejection class is a finding candidate even if a later
attempt succeeds, but it does not waive the publication standard below: obtain
a repeatable public reproduction or deterministic contract evidence before
filing. A recurrence of a known class is not a new issue; report its rate using
the same denominator as the prior run and add evidence to the existing issue
only when the change is material and deduplicated.

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

Create it with `gh issue create` when authenticated, or with the connected
GitHub app otherwise. Then re-read the published issue and verify its URL,
body, labels/state if used, and signature. Update the ledger only after
publication succeeds.

## Teardown and report

Always complete teardown, including early exits:

1. Capture one final read-only public load/state response and copy the isolated
   gateway log into the archive before stopping that lane.
2. Stop only the configured QA gateway. Do not restore the disposable slot
   automatically; preserve its final state for follow-up and retain the
   checksummed pre-shift dump.
3. Run
   `poetry run python scripts/qa_shift/qa_shift.py finish ARCHIVE
   --exit-condition CONDITION`, selecting the truthful configured condition.
4. Mine the current run's structured-output rejection ledger. `finish` writes
   `rejection_ledger.json` from the authoritative `usage_start.json` to
   `usage_end.json` event delta. Use only the gateway-log slice after the
   recorded byte/PID/time boundary to add validation details. For every
   `outcome=rejected_validation` event, record family/command, timestamp, exact
   seat, attempt, token cost, validation class, matching issue, and disposition
   in `probe_ledger.md`. Never count older lines copied into the persistent log.
5. Report total rejected-attempt tokens and percentage as the shift's repair
   tax, with subtotals by seat and class. `finish` leaves the percentage null
   when the OpenAI denominator has unknown usage or any rejection came from an
   unexpected provider; report the listed unavailability reasons rather than
   deriving a percentage. Compare known-class rates only with a stable
   denominator, such as rejected attempts per seat attempt and affected
   model-generating commands per eligible command. Any current-run
   `seat=skald_writer` rejection is the #639 tripwire: verify and publish the
   recurrence on that issue, reopening it when permitted, with the required
   Codex/model signature.
6. If and only if a seeded run ended `dry_well`, usage is trustworthy, and no
   anomaly remains unresolved, qualify the preserved final state for seed
   promotion. Record the current migration, model/slot, committed chunks,
   correspondence letters/exchanges and visible tail, digest versions,
   incubator state, active generation leases, and Orrery queue counts. Require
   current migrations, zero active leases, empty narration/maturation queues,
   coherent foreign keys/invariants, and a successful final public load.
7. Dump a qualifying database first to a `.partial` path under
   `temp/qa_seeds/`, checksum it, inspect it with `pg_restore --list`, restore
   it into a uniquely named disposable verification database, and repeat the
   invariant/count checks there. Drop only that verification database. Then
   atomically promote the file to a `.dump` in `temp/qa_seeds/`, write an
   adjacent manifest containing the measured counts, source archive/commit,
   migration, model, known-issue hotspots, and sha256, and retain the prior
   seed. Use unambiguous filename fields such as `42chunks_40ex`; do not infer
   exchange count from chunk count. If any qualification fails, do not promote
   the seed—preserve the slot and report why.
8. Complete `mission_report.md` with checkout and suite baseline, slot
   initialization (seed dump path and sha256, or fresh reset), issue links,
   probe-family negative results and coverage gates, rejection classification,
   evidence inventory, start/end/delta/max usage and repair tax, seed-promotion
   disposition, exit condition, and final lane/slot disposition. Replace the
   report's `Status: in progress` line with `Status: completed — CONDITION`,
   using the same truthful exit condition supplied to `finish`.
9. Return a concise scheduled-task result with the report path and issue links.

The report is mandatory even if zero issues are published.
