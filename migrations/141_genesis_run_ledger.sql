-- Migration 141: Durable Genesis Run Ledger (issue #776, slice S1a)
--
-- Before this migration, progress is process-local: _PROGRESS_LOCK and
-- _PROGRESS_BY_SLOT in nexus/agents/orrery/retrograde_orchestrator.py:61-62,
-- record_retrograde_progress:97-124, get_retrograde_progress:127-146, and
-- reset_retrograde_progress:149-166 (base 9ac0caf6). Another worker or a
-- restarted gateway answers idle with run null (wizard_chat.py:1426-1444).
-- Packet, seeds, and expansion survive only in the returned bundle
-- (retrograde_orchestrator.py:196-256); trait inputs only in transition_data
-- (new_story_flow.py:535-557; trait_input_derivation.py:343-374).
-- Derivation and generation failures record nothing (new_story_flow.py:551-557,
-- 599-614), and persistence is announced only inside its transaction hook
-- (retrograde_orchestrator.py:290). The cache is cleared after world commit
-- (new_story_db_mapper.py:694-701), so completion needs a separate ledger.
--
-- These are operational wall-clock timestamps, never narrative story time
-- (the Two Clocks doctrine). Rows remain after completion. Input reuse,
-- ownership/idempotency, and bootstrap ownership belong to later #776 slices.
-- No wizard cache is changed and no hosted thread is migrated here.

CREATE TABLE genesis_runs (
    run_id uuid PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('running', 'failed', 'done')),
    stage text CHECK (stage IN ('derivation', 'packet', 'seed_candidates', 'expansion', 'persistence', 'embedding', 'done')),
    skip_reason text,
    error text,
    input_fingerprint text,
    opening_session_id uuid REFERENCES narrative_generation_sessions(session_id),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    CHECK ((status = 'running') = (finished_at IS NULL)),
    CHECK ((status = 'failed') = (error IS NOT NULL)),
    CHECK (skip_reason IS NULL OR status = 'done')
);

COMMENT ON TABLE genesis_runs IS 'One retained wizard genesis attempt; start_genesis_run creates it, record_retrograde_progress, record_genesis_failure and finish_skipped_genesis_run advance its state.';
COMMENT ON COLUMN genesis_runs.run_id IS 'Attempt UUID minted by start_genesis_run; API callers use its 32-character hex form.';
COMMENT ON COLUMN genesis_runs.status IS 'Operational running, failed or done state written by start_genesis_run, record_retrograde_progress, record_genesis_failure and finish_skipped_genesis_run.';
COMMENT ON COLUMN genesis_runs.stage IS 'Last entered genesis stage, NULL before the first stage; record_retrograde_progress writes it and record_genesis_failure preserves it.';
COMMENT ON COLUMN genesis_runs.skip_reason IS 'Reason Retrograde was skipped, written with the world by finish_skipped_genesis_run.';
COMMENT ON COLUMN genesis_runs.error IS 'Raised exception type and text for a failed attempt, written by record_genesis_failure.';
COMMENT ON COLUMN genesis_runs.input_fingerprint IS 'NULL in S1a; 776-S1b writes the whole-run input fingerprint for safe output reuse.';
COMMENT ON COLUMN genesis_runs.opening_session_id IS 'NULL in S1a; a later #776 slice writes the gateway-owned opening generation session UUID.';
COMMENT ON COLUMN genesis_runs.started_at IS 'Operational wall-clock attempt start, defaulted by the start_genesis_run insert; never story time.';
COMMENT ON COLUMN genesis_runs.updated_at IS 'Operational wall-clock latest run-state write by start_genesis_run, record_retrograde_progress, record_genesis_failure or finish_skipped_genesis_run.';
COMMENT ON COLUMN genesis_runs.finished_at IS 'Operational wall-clock completion or failure, NULL while running; record_retrograde_progress, record_genesis_failure or finish_skipped_genesis_run writes it.';

CREATE TABLE genesis_run_stages (
    run_id uuid NOT NULL REFERENCES genesis_runs(run_id) ON DELETE CASCADE,
    stage text NOT NULL CHECK (stage IN ('derivation', 'packet', 'seed_candidates', 'expansion', 'persistence', 'embedding', 'done')),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    output jsonb,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY (run_id, stage)
);

COMMENT ON TABLE genesis_run_stages IS 'One retained stage of one genesis attempt; record_retrograde_progress inserts it, record_genesis_stage_output and finish_genesis_persistence save its output.';
COMMENT ON COLUMN genesis_run_stages.run_id IS 'Owning attempt UUID written by record_retrograde_progress; links the stage to genesis_runs.';
COMMENT ON COLUMN genesis_run_stages.stage IS 'Entered genesis stage name written by record_retrograde_progress; unique per attempt.';
COMMENT ON COLUMN genesis_run_stages.detail IS 'Player progress detail for the stage, written by record_retrograde_progress.';
COMMENT ON COLUMN genesis_run_stages.output IS 'Stage output saved by record_genesis_stage_output or finish_genesis_persistence; SQL NULL means no output value.';
COMMENT ON COLUMN genesis_run_stages.started_at IS 'Operational wall-clock stage entry, defaulted by record_retrograde_progress; never story time.';
COMMENT ON COLUMN genesis_run_stages.finished_at IS 'Operational wall-clock stage close, written by record_retrograde_progress, record_genesis_stage_output, record_genesis_failure or finish_genesis_persistence.';
