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
