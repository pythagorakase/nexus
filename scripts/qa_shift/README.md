# NEXUS adversarial QA shift

This tracked utility turns the previous one-off `temp/qa_shift` experiment into
a repeatable native Codex Scheduled task. The operator remains Codex itself;
there is no nested `codex exec`, launchd plist, systemd unit, or six-hour shell
wrapper.

Run evidence still belongs in ignored `temp/qa_night_*` archives. The durable
policy, usage guard, configuration, and templates live here in version control.

## Schedule it in Codex

Create a recurring standalone task that uses the local project at
`/Users/pythagor/nexus`. A nightly 11:30 PM `America/Chicago` start leaves the
normal workday alone and avoids the OpenAI UTC-day boundary during the
configured one-hour shift.

Use this task prompt:

```text
Open /Users/pythagor/nexus/scripts/qa_shift/mission_prompt.md and execute the
NEXUS Night QA Shift exactly as written. Issue publication is explicitly
authorized.
```

The machine must be awake, the Codex app must be running, and the scheduled
task must have the shell, local-filesystem, network, PostgreSQL, Keychain, and
GitHub access needed by the mission. Run the prompt once manually before
enabling recurrence.

## Completion policy

Defaults in `qa_shift.toml` deliberately combine independent bounds:

- at most five verified, published issues;
- three consecutive dry probe families, after at least five total families;
- a 60-minute wall clock; and
- a 10,000,000-token daily allowance with a 1,000,000-token reserve.

The issue count is a cap, not a quota. The dry-well rule lets a healthy build
finish without manufacturing bugs, while the token and time fences remain
backstops. A seeded run also owes an observed roster transition, one bounded
concurrency family, two-run family novelty, and classification of every
current-run structured-output rejection before it may end dry.

The 10M figure is operational configuration, not a billing entitlement
discovery mechanism. Reconfirm the organization’s current complimentary-token
enrollment and eligible model group before raising it or changing
`target_model`.

## Seeds

Shallow single-request probes stop finding bugs once the early-game surface
hardens; state-threshold defects (compaction, alias accumulation) only appear
deep into a campaign. Drop a checksummed mid-campaign `pg_dump -Fc` dump into
`temp/qa_seeds/` (ignored, conventionally preserved) and the shift seeds the
disposable slot from the newest one instead of a bare reset, then owes the
deep-state and coverage gates in `mission_prompt.md`.

A dry final state is only a seed candidate. Promotion requires a trustworthy
usage ledger, no unresolved anomaly, current migrations, zero active generation
leases, empty Orrery job queues, coherent measured counts, a final public load,
and a checksummed dump that restores successfully into a disposable verification
database. Qualified seeds carry an adjacent manifest with their source archive,
commit, schema/model metadata, exact chunk/exchange/digest counts, known-issue
hotspots, and sha256. Retain the previous seed; do not silently replace the only
known-good depth checkpoint. Prune stale seeds only when the schema or campaign
shape they capture stops being representative.

## Usage guard

Run the helper through Poetry:

```text
poetry run python scripts/qa_shift/qa_shift.py config
poetry run python scripts/qa_shift/qa_shift.py begin
poetry run python scripts/qa_shift/qa_shift.py check temp/qa_night_...
poetry run python scripts/qa_shift/qa_shift.py check temp/qa_night_... --expect-call
poetry run python scripts/qa_shift/qa_shift.py finish temp/qa_night_... --exit-condition dry_well
```

`begin` creates the archive, captures the UTC-day baseline, copies the report
and ledger templates, and generates an isolated runtime config. That config
pins both the default and Gaia OpenAI roles to the configured target model and
sets the slot default to the same model. It never edits `nexus.toml`.

The ledger is exact for API responses recorded by this NEXUS checkout; it is
not the OpenAI organization-wide usage meter. Concurrent NEXUS traffic is
conservatively included in the shift delta, while API calls made outside NEXUS
are invisible. Run the shift when no other API client is drawing on the same
allowance, or reduce the configured limit to leave room for that traffic.

Each `check` calls `nexus usage --json` and records:

- the OpenAI delta since the previous check;
- the provider-reported token fields for each new QA-slot API response;
- cumulative shift and UTC-day totals;
- the largest check-to-check delta;
- events and effective model routes for the QA slot;
- remaining room before the token fence; and
- elapsed wall time.

Exit code `0` means generation may continue. Exit code `2` means stop
generating and report. Exit code `1` means the guard itself could not establish
a trustworthy reading, which is also a stop. Checks are appended to
`usage_checks.jsonl`; `shift_state.json`, `usage_start.json`, and
`usage_end.json` provide the end-to-end tally. If UTC midnight interrupts a
shift, `finish` explicitly re-reads the archived quota day rather than mixing
the new day’s cumulative total with the old baseline.

Normal model-generating probes run one public command between checks. A bounded
concurrency probe may launch at most two public requests from one recorded shell
invocation, wait for both, and reconcile their complete request-group delta in
one post-check. Detached requests and process termination with an unaccounted
provider response remain outside the safe boundary.

The usage delta is also the authoritative rejection ledger. `finish` writes
`rejection_ledger.json` with every current-run QA-slot
`rejected_validation` attempt, exact rejected tokens, repair-tax percentage,
seat subtotals, and the `skald_writer` tripwire. Teardown enriches it with
validation classes from only the current gateway process's log slice. A
recovered retry still represents real cost and latency; a novel class must still
meet the normal repeatability standard before publication.

## Safety boundary

The configured lane is disposable slot 4 on port 8012. The mission prompt
forbids touching the normal port-8002 runtime, changing tracked source, or
filing anything weaker than a reproduced and deduplicated issue. A pre-shift
database dump is retained because the final QA state is intentionally left
available for diagnosis.
