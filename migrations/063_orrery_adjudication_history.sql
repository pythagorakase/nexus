-- 063_orrery_adjudication_history.sql
--
-- Adjudication-history enrichment for the Orrery audit dashboard (step 6 of
-- docs/orrery_audit_dashboard_notes.md). Closes the recorded-history holes:
-- the log's subject is recoverable after the incubator row is deleted
-- (actor_entity_id + bindings), scene pressures persist past commit, and the
-- set of proposals actually rendered to the storyteller is recorded so
-- "ratified by omission" and "never shown" stop being indistinguishable.
-- Pre-migration rows keep NULLs; consumers treat NULL as the pre-063 epoch.

ALTER TABLE orrery_adjudication_log
ADD COLUMN IF NOT EXISTS actor_entity_id bigint REFERENCES entities(id),
ADD COLUMN IF NOT EXISTS bindings jsonb;

COMMENT ON COLUMN orrery_adjudication_log.actor_entity_id IS
    'Acting entity of the adjudicated draft, stamped at insert while the draft is in hand; NULL on rows written before migration 063 (the incubator proposal that carried it is deleted at commit).';
COMMENT ON COLUMN orrery_adjudication_log.bindings IS
    'Serialized slot bindings of the adjudicated draft (e.g. {"actor": 5, "target": 7}); NULL on pre-063 rows. binding_hash remains the opaque dedup key.';

CREATE INDEX IF NOT EXISTS ix_orrery_adjudication_log_actor_entity_id
    ON orrery_adjudication_log (actor_entity_id);

CREATE TABLE IF NOT EXISTS orrery_scene_pressures (
    id               bigserial PRIMARY KEY,
    tick_chunk_id    bigint NOT NULL REFERENCES narrative_chunks(id),
    template_id      text NOT NULL,
    binding_hash     text NOT NULL,
    actor_entity_id  bigint REFERENCES entities(id),
    target_entity_id bigint REFERENCES entities(id),
    priority         int NOT NULL,
    magnitude        numeric(4,3),
    branch_label     text,
    pressure_stub    text,
    prompt_text      text,
    bindings         jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tick_chunk_id, template_id, binding_hash)
);

COMMENT ON TABLE orrery_scene_pressures IS
    'Storyteller-mediated scene pressures persisted at chunk commit. Before migration 063 pressures were prompt-only and vanished with the incubator row, so "which packages pressured on-screen entities" was answerable live but never historically.';
COMMENT ON COLUMN orrery_scene_pressures.template_id IS
    'Behavior package (or {need}_need_pressure pseudo-template) that produced the pressure.';
COMMENT ON COLUMN orrery_scene_pressures.binding_hash IS
    'sha256 of the sorted bindings; with template_id forms the stable per-tick pressure identity.';
COMMENT ON COLUMN orrery_scene_pressures.actor_entity_id IS
    'Off-screen (or need-pressured present) actor exerting the pressure.';
COMMENT ON COLUMN orrery_scene_pressures.target_entity_id IS
    'On-screen target of a two-party pressure; NULL for need pseudo-pressures.';
COMMENT ON COLUMN orrery_scene_pressures.prompt_text IS
    'Rendered pressure line as offered to the storyteller.';

CREATE INDEX IF NOT EXISTS ix_orrery_scene_pressures_tick_chunk_id
    ON orrery_scene_pressures (tick_chunk_id);
CREATE INDEX IF NOT EXISTS ix_orrery_scene_pressures_actor_entity_id
    ON orrery_scene_pressures (actor_entity_id);

CREATE TABLE IF NOT EXISTS orrery_prompt_exposures (
    id            bigserial PRIMARY KEY,
    tick_chunk_id bigint NOT NULL REFERENCES narrative_chunks(id),
    kind          text NOT NULL CHECK (kind IN ('resolution', 'scene_pressure')),
    proposal_id   text NOT NULL,
    template_id   text NOT NULL,
    binding_hash  text NOT NULL,
    position      int NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tick_chunk_id, kind, template_id, binding_hash)
);

COMMENT ON TABLE orrery_prompt_exposures IS
    'Which Orrery proposals and scene pressures were rendered to the storyteller for a tick (the render cap is [orrery.prompt] in nexus.toml). Distinguishes "Skald saw and ratified by omission" from "never shown beyond the render cap". Rows exist only for ticks committed after migration 063.';
COMMENT ON COLUMN orrery_prompt_exposures.position IS
    'Zero-based render order within the kind, matching proposal order.';

CREATE INDEX IF NOT EXISTS ix_orrery_prompt_exposures_tick_chunk_id
    ON orrery_prompt_exposures (tick_chunk_id);
