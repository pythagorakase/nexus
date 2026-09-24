# Prompt Registry Verification

Work order **742-A**, mechanical migration only. Base: `c341d7d4d80e36273ace0041fe5b5632289b2bf5`. Implementation: `63fd47e5`. All commands ran from `/Users/pythagor/nexus/.claude/worktrees/742-prompt-registry` with `/Users/pythagor/nexus/.venv/bin/python`. The import check printed this worktree's `nexus/__init__.py`.

## Byte Identity

A real CLI continuation on lane **8015**, using **TEST** for both seats, generated the before requests from a disposable `qa640_742_prompt_registry` clone of `save_04`. The accepted parent was chunk **49**. The after run replayed that exact captured context through `LogonUtility.generate_narrative_async` and both actual TEST-provider HTTP calls. All four system/user strings were compared with Python string equality and then hashed as UTF-8 bytes. Decimal relationship valences were restored from their lossless JSON strings for replay; no context text was edited. The writer's deterministic TEST response supplied Gaia's finished-narrative blocks in both runs.

The wizard render used the clone's Setting Card, character phase, developer preamble, Accept Fate signal, and live tag library. The Retrograde seed-generation render used the clone's character roster and live vocabulary. Those two probes rendered prompts without calling a provider.

| Prompt | UTF-8 Bytes | Before SHA-256 = After SHA-256 |
|---|---:|---|
| Writer system | 22405 | `c3b19e6093981ac9fbf4e7386b33f31310423818ac94a6e91e045be59ad6c360` |
| Writer user | 133577 | `f178135295bd9e04d0167bb04fde7613215ca4b75f8fc0b499f0e835d0079d00` |
| Gaia system | 9382 | `aad2b7214e4776689dbbb99dd061caee9da7657db5fbfa6bdf667f2e7399db42` |
| Gaia user | 134207 | `19801f4931c6c9765a45cfe7a6f73abbc73264febb80f0c3922ca0ff8581d625` |
| Wizard | 75049 | `856590c57499d3462f08e8f59c750bbef53c309662947ca2cffec253f16293c5` |
| Retrograde | 84979 | `603a5cf78862fa6c7fd2056c2807dc7032082ba323eaee0ca80afb298da6ff17` |

[Rendered receipts](rendered-hashes.json) contain separate before/after hashes. [Template receipts](template-proof.json) independently compare all **88** registered documents against the base: unchanged existing Markdown, extracted static fragments with placeholder names normalized, original ordered rule lists, and the five cleaned wizard-tool docstrings. This verifies static wording beyond the six rendered examples. The comparison reported:

```text
88 registered templates match the base static prose and original rule order.
234 Field(description=...) expressions unchanged across modified existing Python modules.
```

The runtime remains responsible for its original frontmatter parsing, `.strip()` calls, JSON serialization, and section separators. The registry preserves template whitespace; it neither dedents nor appends a newline. Existing core/seat documents were not edited.

## Registry and Lint

`nexus/prompts/registry.py` declares typed IDs, paths, seats, and placeholder sets. Cached file reads are serialized so concurrent first readers cannot cause duplicate reads. Missing files, empty files, missing template markers, missing substitution arguments, and unknown arguments fail loudly. Substitution runs once, without interpreting placeholders inside substituted data.

`tests/test_prompt_lint.py` is collected by the normal pytest gate. It verifies exact document coverage, unique paths, reader presence outside tests, placeholder contracts, wizard-tool descriptions, and the absence of ad-hoc prompt-directory constructors. Its documented AST heuristic rejects model-addressed triple-quoted prose throughout `nexus/` and `scripts/`, excluding actual docstrings and `Field(description=...)`. The missing-file and cache test performs real filesystem IO in an isolated installation, without mocked reads.

## Retirements and Retained Readers

- Deleted the ten `prompts/*.json` documents, including the unreferenced `_alt` and `_old` ranker variants. Deleted their ten batch-reader scripts: `character_chunk_ranker.py`, `character_episode_ranker.py`, `faction_former.py`, `generate_character_summaries_experimental.py`, `generate_psychology.py`, `generate_psychology copy.py`, `map_builder.py`, `map_builder_fail.py`, `map_illustrator.py`, and `relationship_analyst.py`. They had no production import path or supported operator root in `config/reachability.toml`.
- Deleted the unused `setting_night_city_stories.md`, LORE's unused `lore_system_prompt.md`, its eager loader, and the now-unreferenced `user_confirmation.py` prompt-path fallback. Removed the unused `*_SCHEMA_PROMPT` constants and the uncalled JSON-loader fallback in `faction_relationship_analyst.py`.
- Retained the legacy new-story generator functions because tests still exercise them; their prose now comes from the registry. Retained other standalone operators and moved their triple-quoted model prose into registered documents. Black formatted the touched legacy Python files, which accounts for the larger formatting diffs there.
- Updated reachability's baseline only for the two new registry modules and the explicit retirements. No new orphan exemption was added.

## Base Drift and Deferred Scope

The audit described an LLM narration prompt in `nexus/agents/orrery/worker.py`; that prompt was already retired on this base. The current worker creates deterministic, source-linked records (see its module docstring), so no narration prompt was reintroduced.

No wording revision, block reordering, chronological rendering, seat-specific closer, schema-description change, `nexus.toml` change, or database migration is included. The player-facing `InteractiveWizard.tsx` trait introduction remains a coordinator scope question: this slice treats it as UI copy rather than model-facing Python prose. The existing `docs/trait_menu.md` reference stays at its documented location. No UI files changed and no Node build was needed.

## Database and Service Boundaries

Only the disposable clone was written. [Database receipts](database-proof.json) record the exact SQL and show `save_04` before/after at **46 chunks, max ID 49, 23 characters**. These counts are a boundary check, not a content checksum. The clone was dropped. The lane's gateway was stopped with the same `NEXUS_GATEWAY_PORT=8015` / `NEXUS_API_URL=http://127.0.0.1:8015` environment; `lsof` subsequently found no listener on 8015. Ports 8002 and 8012 were not used.

The initial clone carried a provisional draft with an obsolete Pass-2 fingerprint. The first CLI continuation accepted that draft on the clone and then correctly refused its incompatible baseline before inference. SQL isolated the mismatch to the provisional draft; the source's accepted tail matched the current configuration. The clone was recreated and only its provisional draft discarded before the successful proof. No source baseline was restamped. Background non-TEST work was rejected by a guard before transport; no paid provider call was made.

## Validation

Exact commands and output tails are in [validation.txt](validation.txt). The offline skips are the repository's deliberate integration/live-provider gating; they are not used as PostgreSQL evidence. The separate required PostgreSQL prompt gate ran all 66 selected tests without skips. No #885 exemption was needed in that gate.

Temporary probe scripts and captured story text remain under the ignored `temp/742*` paths in this worktree. The committed receipts contain hashes and counts rather than the story's full prompt contents.

## PR #930 Completeness Amendments

The amendment baseline is `8020a550bb39f582945c7781bdd35f27910640e1`.
The correspondence privacy sentence, both faction-declaration policy variants,
Retrograde mechanical hints, and the faction analyst's four system/user messages
now load registered documents. The faction analyst remains a standalone operator;
its executable CLI and `--test` mode are retained. No additional operator was
retired in this amendment.

The all-string lint also exposed model-facing output-format and tool guidance,
Orrery scene-pressure instructions, Retrograde contract and maturation directions,
validation retries, and two operator instructions. These were mechanically moved
too, rather than exempted. There are 54 additional documents (142 total).
The 129 `Field(description=...)` expressions in amended modules are unchanged.

The lint examines string literals independent of quote style, implicit or explicit
concatenation, and f-string literal parts. Its documented heuristic recognizes
model-addressed phrases and sentence-opening imperatives. Ordinary Python
function documentation uses the narrower model-address heuristic; known model
phrases in docstrings still fail unless exactly allowlisted as developer docs.
`Field(description=...)` remains outside the mechanical slice;
SQL syntax does not match the natural-language imperative patterns. Exact
(path, literal) exceptions document operator diagnostics, CLI help, deterministic
player-facing TEST output, and Orrery branch labels or quoted in-world dialogue.
The gate rejects stale exceptions and confirms that adjacent model instructions
are still rejected. A subprocess test copies the source into a scratch directory
and runs the real lint three times, injecting the review's phrases with different
quote/concatenation styles. Each run must fail specifically at the injected file.

### Additional Byte-Identity Evidence

[Template evidence](amendment-template-proof.json) compares all 54 new documents
with their actual AST expressions at the frozen amendment baseline, checks every
static fragment, and evaluates the original expressions and current registry
calls with identical substitution inputs. All rendered UTF-8 bytes match.

[Complete-render evidence](amendment-rendered-hashes.json) compares ten full
renders against the frozen baseline using real data from `qa640_742_amend`,
a disposable `pg_dump`/`pg_restore` clone of `save_04`. Connections used
`PGOPTIONS='-c default_transaction_read_only=on'`; the real registry validator
queried the clone and raised real `ModelRetry` messages in both declaration-policy
modes. The faction message builders used real faction and character rows.
No provider transport was invoked for these amendment checks. The original
real-turn TEST-provider proofs above remain the evidence for both turn seats.

| Render | UTF-8 Bytes | Before SHA-256 = After SHA-256 |
|---|---:|---|
| accepted_correspondence | 27931 | `c3326b41dcece24f576e5387f4fa5a51386e79d7d08edfecfad579f142b807b4` |
| retrograde_packet | 31870 | `d34ed5c0628dc39b79f9bd927f83eb0fd83ff9f665248e5009794a032169ff8f` |
| retrograde_prompt | 85430 | `3afab2aaa1fb6794b69c413081da82b0f190dbb1a24dc815d5795a0e1845d241` |
| create_faction_to_faction_messages_system | 880 | `159ec7599928ce7a219036188f989444d31eb234f4584d6d8d436eda12fcfd19` |
| create_faction_to_faction_messages_user | 7319 | `3f2a61938643818185ee7643f23618156a334d1920124eebf1624c7375035136` |
| create_faction_to_character_messages_system | 882 | `5adc1c3d28a969915469a0ef647cb53293bd5c181f2766242de25b23f7fe8895` |
| create_faction_to_character_messages_user | 7216 | `af1c9ba078a81ebf7832caab274bd24edf4714863d6be3673dca6f69c47a731a` |
| registry_retry_declarations_False | 1196 | `0aa6d99ed269f24cc9d480240fe710b07a5408e414a89206cf86063e241c4bb2` |
| registry_retry_declarations_True | 1210 | `901a8ceb9ddcdb6fabcf7878d96a6139b519440527ea614c4031cb83fbf21aa1` |
| skald_format_guide | 6231 | `5f9e31e2e492f025fc2e23f3800680ac080a7961df75e8b6670fb73aa5a05ee4` |

### Merge and Boundaries

`origin/main` at `12510525654c50ef4afeb1ff4efa4cee924176e8` was merged
without conflicts in `ec5b1e4f`. Its historical-passage-limit change is upstream
work; this amendment does not revise its behavior. The original turn hashes
above describe the original migration before this upstream merge. The ten
amendment renders were rechecked after the merge and still match the frozen
amendment baseline.

[Database evidence](amendment-database-proof.json) records the exact final SELECT:
both source and clone had 46 chunks, maximum chunk ID 49, and 23 characters.
The source was read only. The clone was dropped and its absence verified in
`pg_database`. No gateway was started for the amendments, and no paid provider
was called.

An initial offline run overlapped the merge: its imported pre-merge Settings
class rejected the newly merged `lore.render_limits.historical_passages` config
field. It reported 27 failures and is discarded as a mixed-tree run. All final
gates were rerun in new processes against the fixed merged tree. The trailing
whitespace reported by `git diff --check` in prompt documents is deliberately
preserved original prompt whitespace, including the semicolon-space endings
of the two declaration-policy fragments.

### Coordinator Questions

The separate automated review's wheel-packaging finding remains outside the
frozen completeness amendments: top-level prompt documents are not included
in the wheel. The coordinator should assign its packaging fix before treating
wheel installation as verified. Source-checkout runtime behavior is what this
work order and its gates exercise. The earlier player-facing TSX scope question
also remains deferred.

Exact amendment commands and verbatim tails are in [amendment validation](amendment-validation.txt). The [file inventory](amendment-files.md) gives one line per amendment file. `tests/test_skald_wire.py` now pins its format-guide assertion to the Markdown document. No #885 exemption was required.

Final merged-tree gates: **2693 passed, 857 skipped** offline; **66 passed, 343 deselected, no skips** in the PostgreSQL selection; **21 passed** in prompt lint; **39 Python files** Black-clean. Reachability reports no new orphans, lost production paths, forbidden dependencies, tombstone violations, unresolved imports, or unregistered dynamic imports. All 301 `Field(description=...)` expressions in existing Python files changed by the complete PR match merged `origin/main`.
