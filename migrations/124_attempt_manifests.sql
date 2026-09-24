-- Correlation is not identity. Existing jobs remain nullable and unchanged.
ALTER TABLE character_experience_jobs ADD COLUMN generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid;
COMMENT ON COLUMN character_experience_jobs.generation_session_id IS 'Originating accepting generation session, set at enqueue; NULL for legacy or independent work. The job retains its own primary key.';
CREATE INDEX character_experience_jobs_generation_session_idx ON character_experience_jobs (generation_session_id);

ALTER TABLE orrery_maturation_jobs ADD COLUMN generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid;
COMMENT ON COLUMN orrery_maturation_jobs.generation_session_id IS 'Originating accepting generation session, set at enqueue; NULL for legacy or independent work. The job retains its own primary key.';
CREATE INDEX orrery_maturation_jobs_generation_session_idx ON orrery_maturation_jobs (generation_session_id);

ALTER TABLE correspondence_compaction_jobs ADD COLUMN generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid;
COMMENT ON COLUMN correspondence_compaction_jobs.generation_session_id IS 'Originating accepting generation session, set at enqueue; NULL for legacy or independent work. The job retains its own primary key.';
CREATE INDEX correspondence_compaction_jobs_generation_session_idx ON correspondence_compaction_jobs (generation_session_id);

ALTER TABLE relationship_milestone_queue ADD COLUMN generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid;
COMMENT ON COLUMN relationship_milestone_queue.generation_session_id IS 'Originating accepting generation session, set at enqueue; NULL for legacy or independent work. The job retains its own primary key.';
CREATE INDEX relationship_milestone_queue_generation_session_idx ON relationship_milestone_queue (generation_session_id);

ALTER TABLE orrery_narration_jobs ADD COLUMN generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid;
COMMENT ON COLUMN orrery_narration_jobs.generation_session_id IS 'Originating accepting generation session, set at enqueue; NULL for legacy or independent work. The job retains its own primary key.';
CREATE INDEX orrery_narration_jobs_generation_session_idx ON orrery_narration_jobs (generation_session_id);

CREATE TABLE generation_attempt_manifests (
    generation_session_id uuid NOT NULL REFERENCES narrative_generation_sessions(session_id) ON DELETE CASCADE,
    seat text NOT NULL,
    attempt integer NOT NULL CHECK (attempt > 0),
    schema_version integer NOT NULL DEFAULT 1,
    blocks jsonb NOT NULL,
    window_record jsonb NOT NULL,
    retrieval_ids bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
    recall_ids bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
    exposure_ids bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
    model_id text NOT NULL,
    story_pin jsonb NOT NULL,
    config_sha256 text NOT NULL,
    wire_schema_sha256 text NOT NULL,
    prompt_sha256 text NOT NULL,
    response_sha256 text,
    validation jsonb NOT NULL DEFAULT '[]'::jsonb,
    outcome text CHECK (outcome IN ('accepted','superseded','discarded','error')),
    provider_outcome text CHECK (provider_outcome IN ('accepted','rejected_validation','error')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (generation_session_id, seat, attempt)
);
COMMENT ON TABLE generation_attempt_manifests IS 'Durable per-seat attempts containing only references, hashes, counts and configuration identities. Pruned only by explicit maintenance.';
COMMENT ON COLUMN generation_attempt_manifests.generation_session_id IS 'Shared generation-session correlation key; never a chunk or job identity.';
COMMENT ON COLUMN generation_attempt_manifests.seat IS 'Provider seat that rendered this attempt.';
COMMENT ON COLUMN generation_attempt_manifests.attempt IS 'One-based provider attempt within the seat.';
COMMENT ON COLUMN generation_attempt_manifests.schema_version IS 'Version of this reference-and-hash manifest contract.';
COMMENT ON COLUMN generation_attempt_manifests.blocks IS 'Ordered rendered block kinds, local token counts and SHA-256 hashes; no text.';
COMMENT ON COLUMN generation_attempt_manifests.window_record IS 'Prompt-window token counts and limits; excludes free-text validation notes.';
COMMENT ON COLUMN generation_attempt_manifests.retrieval_ids IS 'References to retrieval_coverage_log rows for this generation session.';
COMMENT ON COLUMN generation_attempt_manifests.recall_ids IS 'References to orrery_recall_trace rows, including disclosure decisions.';
COMMENT ON COLUMN generation_attempt_manifests.exposure_ids IS 'References to accepted orrery_prompt_exposures; empty until acceptance.';
COMMENT ON COLUMN generation_attempt_manifests.model_id IS 'Resolved model registry ID used for this attempt.';
COMMENT ON COLUMN generation_attempt_manifests.story_pin IS 'Story model, Gaia model and context-window pins at dispatch.';
COMMENT ON COLUMN generation_attempt_manifests.config_sha256 IS 'SHA-256 of canonical effective runtime configuration.';
COMMENT ON COLUMN generation_attempt_manifests.wire_schema_sha256 IS 'SHA-256 of the provider structured-output schema/request contract.';
COMMENT ON COLUMN generation_attempt_manifests.prompt_sha256 IS 'SHA-256 of canonical JSON system and rendered user prompt strings.';
COMMENT ON COLUMN generation_attempt_manifests.response_sha256 IS 'SHA-256 of the raw SDK response serialized as canonical JSON before repairs; NULL without a response.';
COMMENT ON COLUMN generation_attempt_manifests.validation IS 'Validation/repair codes, counts and hashes; never error or response text.';
COMMENT ON COLUMN generation_attempt_manifests.outcome IS 'Canonical terminal outcome copied atomically from the owning generation session; NULL until terminal.';
COMMENT ON COLUMN generation_attempt_manifests.provider_outcome IS 'Provider validation outcome, distinct from the generation-session terminal outcome.';
COMMENT ON COLUMN generation_attempt_manifests.created_at IS 'Manifest creation time used by explicit retention pruning.';
COMMENT ON COLUMN generation_attempt_manifests.updated_at IS 'Time of the latest attempt measurement or response update.';
CREATE INDEX generation_attempt_manifests_retention_idx ON generation_attempt_manifests (created_at);

CREATE TABLE generation_session_phases (
    id bigserial PRIMARY KEY,
    generation_session_id uuid NOT NULL REFERENCES narrative_generation_sessions(session_id) ON DELETE CASCADE,
    phase text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE generation_session_phases IS 'Observed durable phase transitions; no inferred historical transitions.';
COMMENT ON COLUMN generation_session_phases.id IS 'Monotonic transition identity.';
COMMENT ON COLUMN generation_session_phases.generation_session_id IS 'Generation session owning this observed transition.';
COMMENT ON COLUMN generation_session_phases.phase IS 'Durable engine phase entered.';
COMMENT ON COLUMN generation_session_phases.recorded_at IS 'Server wall-clock time of transition.';
CREATE INDEX generation_session_phases_session_idx ON generation_session_phases (generation_session_id, id);
CREATE FUNCTION record_generation_session_phase() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.phase IS DISTINCT FROM OLD.phase THEN
        INSERT INTO generation_session_phases (generation_session_id, phase)
        VALUES (NEW.session_id, NEW.phase);
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.terminal_outcome IS DISTINCT FROM OLD.terminal_outcome THEN
        UPDATE generation_attempt_manifests SET outcome=NEW.terminal_outcome, updated_at=now()
        WHERE generation_session_id=NEW.session_id;
    END IF;
    RETURN NULL;
END;
$$;
COMMENT ON FUNCTION record_generation_session_phase() IS 'Record actual phase transitions without duplicating session or prose state.';
CREATE TRIGGER generation_session_phase_history AFTER INSERT OR UPDATE OF phase, terminal_outcome
ON narrative_generation_sessions FOR EACH ROW EXECUTE FUNCTION record_generation_session_phase();
