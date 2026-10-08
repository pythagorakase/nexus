# Attention Class Source Checkpoint

Status: source implementation authored; focused, PostgreSQL and UI validation
pending. This is not a passing gate or a publication-ready branch.

## Scope and Decisions

The frozen order is `temp/orders_2026_10_07/784-S2.md`, with its shared rules
and `coord/world-time-attention-refresh.md`. Source preparation was explicitly
advanced while the coordinator owns the shared gate. This branch starts at
main `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`; no shared ref was fetched or
moved. The later landed main must be merged normally before publication.

Live #784 was read on 2026-10-08. The [mechanism decisions](https://github.com/pythagorakase/nexus/issues/784#issuecomment-5922753528)
keep branch attention separate from template drive band and insert-status
`promotable`. The [Sequence 41 ruling](https://github.com/pythagorakase/nexus/issues/784#issuecomment-6043523766)
includes mundane activity plus sleep/eat/drink, while first meetings and
routine project continuations stay meaningful. The critical-need runtime
hatch remains 784-S3b. No built-in deviation or urgent roster is authored.
The earlier [S1 grammar measurement](https://github.com/pythagorakase/nexus/issues/784#issuecomment-5926233048)
is historical evidence, not a fresh measurement by this branch.

## Implementation and Source Review

- `substrate.py` adds the server-only enum and branch fields. New branches
  default to meaningful and no deviation. Template construction refuses
  background crisis bands, project milestones, relationship effects and
  status effects, and refuses deviation outside background. The extracted
  milestone predicate preserves the exact prior keys, Mapping check and
  truthiness test used by `configure_project_magnitudes`.
- `settings_models.py` checks configured claim events against both event
  fields emitted by background branches, after vocabulary validation and
  before birth-role policy validation. The existing `known_event_types()`
  already lazily imports `BUILTIN_TEMPLATES`; the new lazy reads follow that
  established dependency path. No top-level settings load is added.
- `templates.py` explicitly authors the 35 background and 29 meaningful pins
  below. Other branch fields and predicates are unchanged. The landed #785
  charted-place and timed-route fields, predicates, and catalog prose remain.
- Catalog markers are ordered preemptive, non-meaningful class, deviation,
  not-promotable. Audit and explanation emit the authored metadata; coverage
  includes chosen and per-branch classes. A failed explanation gate reports
  null attention and initializes its unchosen branch explicitly.
- Backstage looks up `(template_id, branch_label)` and leaves unknown labels
  null. Its optional TypeScript field and `data-attention` attribute feed one
  `.55` opacity rule. There is no new visible label, element, icon or hue.
- Pure tests cover the authoring refusals, defaults, exact roster, claim
  refusal order, catalog markers, audit payload and chosen/unchosen trace.
  Existing coverage fixtures receive the new required metadata. The PG tests
  compare real card branches to every Backstage inventory row and preserve
  null for an unknown fixture label. The new drawer test exercises rendered
  row attributes without printing the class.

No change routes, exposes, commits, escalates or seeds on attention. The
resolution type, resolver, events, worker, cards, model wire schemas, grammar
probe, `nexus.toml`, migrations and exception baseline are unchanged. No
policy, condition, tunable, prompt, persisted column or paid operation is
added. The later slices retain their original responsibilities.

## Authored Background Roster

The table is extracted from the authored source without importing product
code; runtime roster validation is pending. Each listed branch has an
explicit `AttentionClass.BACKGROUND` keyword. Total: 35.

| Template | Branch |
| --- | --- |
| `sleep` | Collapse into deferred sleep |
| `sleep` | Sleep at home |
| `sleep` | Sleep in safe lodgings |
| `sleep` | Sleep rough in cover or transit |
| `drink` | Drink desperately, whatever is available |
| `drink` | Drink in a public room |
| `drink` | Drink from a public or wild source |
| `drink` | Drink routinely from what is at hand |
| `eat` | Eat ravenously, whatever is available |
| `eat` | Eat at home with household |
| `eat` | Eat at home alone |
| `eat` | Eat in a public dining place |
| `eat` | Forage or hunt from the country |
| `eat` | Eat from rations or what was packed |
| `eat` | Find something and eat it |
| `train` | Drill the fighting forms |
| `train` | Condition the body |
| `train` | Sharpen the finer skill |
| `train` | Keep the edge from dulling |
| `run_errands` | Make the market run |
| `run_errands` | Scrounge for what the day needs |
| `run_errands` | Provision the household |
| `run_errands` | Knock out the small obligations |
| `stroll` | Walk under open sky |
| `stroll` | Walk the familiar streets |
| `stroll` | Take the night air |
| `stroll` | Pace the near ground |
| `upkeep` | Maintain the working tools |
| `upkeep` | Mend and ready the kit |
| `upkeep` | Set the home in order |
| `upkeep` | Tidy what is theirs |
| `recreate` | Find games and company |
| `recreate` | Lose an hour to the loved thing |
| `recreate` | Watch the world go by |
| `recreate` | Take a small private pleasure |

## Explicit Meaningful Pins

Every listed branch retains `promotable=False` and has an adjacent explicit
`AttentionClass.MEANINGFUL` keyword. Total: 29.

| Template | Branch |
| --- | --- |
| `make_acquaintance` | Exchange names |
| `advance_relocation_plan` | Put another share aside |
| `advance_relocation_plan` | Scout a candidate place |
| `advance_relocation_plan` | Lose ground to a setback |
| `advance_relocation_plan` | Press on with the next practical step |
| `advance_recruit_ally` | Lose ground through neglect |
| `advance_recruit_ally` | Learn what the candidate actually wants |
| `advance_recruit_ally` | Prove reliable in a small consequential way |
| `advance_recruit_ally` | Make the next commitment concrete |
| `advance_pursue_romance` | Lose romantic ground through neglect |
| `advance_pursue_romance` | Offer another honest opening |
| `advance_pursue_romance` | Build closeness through chosen time |
| `advance_pursue_romance` | Make the next intention legible |
| `advance_court_patron` | Lose ground through neglect |
| `advance_court_patron` | Make useful work visible |
| `advance_court_patron` | Prove reliable under scrutiny |
| `advance_court_patron` | Make the next claim on favor legible |
| `advance_court_patron_faction` | Lose institutional ground through neglect |
| `advance_court_patron_faction` | Make useful work visible to the faction |
| `advance_court_patron_faction` | Prove reliable under institutional scrutiny |
| `advance_court_patron_faction` | Make the next claim on standing legible |
| `advance_seek_redemption` | Lose ground through neglected amends |
| `advance_seek_redemption` | Name the wrong without self-exoneration |
| `advance_seek_redemption` | Make one concrete repair |
| `advance_seek_redemption` | Leave forgiveness in the wronged party's hands |
| `advance_build_venture` | Lose ground through neglect |
| `advance_build_venture` | Make the venture legible |
| `advance_build_venture` | Secure one more commitment |
| `advance_build_venture` | Finish the next opening task |

## Canonical Documents

A source-only scan of actual leading front matter finds exactly two affected
canonical records: 0042 declares `substrate.py`, and 0054 declares
`nexus-layout.css`. Their bodies, owner quotations, statuses and source lists
are unchanged; only their stamps move to the main base above. The records
state rulings, not claims that their full issues are implemented: #782 still
has the unchanged one-active-project policy here, and #777's bottom-rail
implementation is pending in the separately owned lane. Attention metadata
changes neither policy. `AGENTS.md` and `docs/turn_flow_sequence.md` declare
none of this slice's changed files. Formal freshness validation is pending.

## Completed Source Operations

At one-minute load 19.4765625, with the exact worktree `PYTHONPATH`, shared
interpreter, disabled keyring, TEST-provider guard and inherited runtime,
live-test, pytest and libpq target overrides cleared:

```text
nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m black <15 changed Python files>
6 files reformatted, 9 files left unchanged.

nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m nexus.agents.orrery.catalog --write
Wrote /Users/pythagor/.codex/worktrees/resume-attention-class/nexus/docs/orrery_packages.md
```

The 15 files are the eight production files (`audit.py`, `backstage.py`,
`catalog.py`, `coverage.py`, `explain.py`, `substrate.py`, `templates.py` under
`nexus/agents/orrery/`, plus `nexus/config/settings_models.py`) and the seven
changed Python test files named in the commands below. The catalog diff has
35 changed headings plus the exact ordered intro paragraph: 37 insertions
and 35 deletions. The generator successfully loaded the built-in templates.
Source inspection confirms removing just those markers and the paragraph
reproduces the base catalog bytes. The coordinator's independent production
review found no blocker against the frozen scope, including the unchanged
milestone expression. Neither check replaces the pending behavioral tests.

No pytest, mypy, PostgreSQL, owner database query, browser, npm install,
build, state-surface capture, service start or paid call has run for this
checkpoint. Formatting and normal hooks do not establish behavioral proof.

## Pending Validation

Request the shared heavy slot before any tests. Pin the source head, verify
the import root, clear inherited routing/libpq/pytest/live flags, use nice15
and load at most 24, and require the secret-store, owner-target and receipt
isolation summaries. Run one session at a time.

```bash
nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_orrery/test_substrate.py tests/test_orrery/test_catalog.py \
  tests/test_orrery/test_audit.py tests/test_orrery/test_explain.py \
  tests/test_orrery/test_coverage_accounting.py \
  tests/test_reachability.py tests/test_doc_front_matter.py

NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_api/test_backstage_endpoints_pg.py \
  tests/test_orrery/test_attention_class_grammar_probe.py \
  tests/test_orrery/test_claim_birth_coverage_pg.py
```

The two ordered controls remain pending: remove the background invariants
and require the pure refusal cases to fail; remove only the background pin
from Stroll's `Pace the near ground` and require the roster check to fail.
Preserve exact failure identities and raw tails, and record before/planted/
restored hashes while restoring the source bytes even on interruption.

Also pending: changed-file flake8 and `mypy --explicit-package-bases`
comparisons against the approved main, Black check, explicit configuration
validation, exception-disposition check, and generated catalog no-diff check.
The coordinator owns one combined full gate; no independent whole/offline
partition run is claimed by this branch.

UI proof waits for the landed #777/#824 source and current baseline: merge
normally, preserve their changes, install this worktree's dependencies, run
type/build and the new drawer test, then regenerate state surfaces under the
serialized browser slot and run the full UI tests including state-shades.
Never hand-merge a receipt. All measured samples must remain identical; a
moved sample is a stop-report item. No regenerated receipt or capture is
claimed or staged in this source checkpoint.

Landing requires no migration or fleet application. Product backend changes
owe a gateway restart when the owner services next run; UI changes owe a
build. Those operations, full validation and PR publication remain with the
coordinator. This slice closes neither #784 nor the deferred routing,
critical-need, texture, recollection-formation or texture-surface work.

Codex — GPT-6
