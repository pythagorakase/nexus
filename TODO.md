# Ongoing Work Log

## Completed
- Added Apex audition engine package (`nexus/audition/`) with repository, models, and orchestration to persist bakeoff runs in Postgres under the `apex_audition` schema.
- Wired CLI entrypoint `scripts/run_apex_audition_batch.py` to ingest context seeds, register conditions, and drive dry-run/full batches.
- Restored character extraction fallback in `ContextMemoryManager` so Pass 1 captures names even when alias tables aren’t loaded (keeps tests and early bakeoff contexts aligned).
- Regenerated unit/integration coverage for audition repository and karaoke regression; full suite now passes: `pytest tests/test_audition/test_repository.py tests/test_lore/test_memory_manager.py tests/test_lore/test_pass2_chunk1369.py tests/test_lore/test_turn_cycle.py -q`.

## In Progress
- Draft storyteller system prompt (blocked on creative review).
- Configure final `max_output_tokens` values per condition; re-register via CLI when ranges are agreed upon.
- Prepare batch job that executes live generations once the storyteller prompt is finalized.
- Plan ELO tournament scaffolding (pairing model and evaluation workflow) once initial generation bank is populated.

## Upcoming
- Hook generation results into comparison workflow (ELO updates, adjudication tooling).
- Extend automated tests to cover batch regeneration script and psychology directives once requirements settle.
- Review LM Studio logging noise; consider patch to quiet closed-stream warnings during pytest runs.
