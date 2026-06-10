"""Durable runtime stub-maturation job queue for Retrograde Phase B-Lite (M8).

Spec decisions 9/10/12 in ``docs/orrery_retrograde_spec.md`` ("Stub
Maturation"): when Skald-as-narrator declares a new entity via the
``new_entities`` structured-output field and that entity appears in the
committed chunk, the commit path enqueues one durable maturation job. A
post-commit worker drain runs the scoped Retrograde pipeline (seed
generation, expansion, persistence, summary-chunk embedding) per job.

Two schema deltas:

1. ``incubator.new_entities`` — the declaration list rides the incubator row
   so the commit transaction (the outbox boundary) can validate hints,
   create stub rows, gate on the engagement signal, and enqueue jobs
   atomically with the chunk insert.
2. ``orrery_maturation_jobs`` — one row per declared entity, mirroring the
   ``orrery_narration_jobs`` lease/retry discipline. The unique index on
   ``entity_id`` is the per-entity idempotency boundary: a matured entity
   never re-matures, and double-enqueue is a no-op (``ON CONFLICT DO
   NOTHING``).

Reuses the ``orrery_job_state`` enum from migration 023.
"""

from __future__ import annotations


DDL = """
ALTER TABLE incubator
    ADD COLUMN IF NOT EXISTS new_entities jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN incubator.new_entities IS
    'Skald new-entity declarations (apex_schema.NewEntityDeclaration list): '
    'kind, name, one-line summary, optional registered tag/pair-tag hints. '
    'Processed at commit time: hints validated against the live registries, '
    'stub rows created when absent, and maturation jobs enqueued when the '
    'declared name appears in the committed chunk (spec decisions 9/12).';

CREATE TABLE IF NOT EXISTS orrery_maturation_jobs (
    id                  bigserial PRIMARY KEY,
    entity_id           bigint NOT NULL REFERENCES entities(id),
    entity_kind         text NOT NULL
        CHECK (entity_kind IN ('character', 'place', 'faction')),
    entity_subtype_id   bigint NOT NULL,
    entity_name         text NOT NULL,
    slot                text NOT NULL,
    requesting_chunk_id bigint NOT NULL REFERENCES narrative_chunks(id),
    declaration         jsonb NOT NULL,
    state               orrery_job_state NOT NULL DEFAULT 'queued',
    attempts            integer NOT NULL DEFAULT 0,
    available_at        timestamptz NOT NULL DEFAULT now(),
    lease_until         timestamptz,
    last_error          text,
    result_manifest     jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE orrery_maturation_jobs IS
    'Durable fire-and-forget queue for runtime Retrograde stub maturation '
    '(spec decision 10, Phase B-Lite). Enqueued inside the chunk-commit '
    'transaction; drained by the post-commit Orrery worker, which runs the '
    'scoped R4-R6 pipeline and persists generated history on completion.';
COMMENT ON COLUMN orrery_maturation_jobs.entity_id IS
    'Global entities.id of the declared entity. The unique index on this '
    'column is the idempotency boundary: one maturation per entity, ever.';
COMMENT ON COLUMN orrery_maturation_jobs.entity_kind IS
    'Entity kind: character, place, or faction.';
COMMENT ON COLUMN orrery_maturation_jobs.entity_subtype_id IS
    'Subtype-table id (characters.id / places.id / factions.id).';
COMMENT ON COLUMN orrery_maturation_jobs.entity_name IS
    'Declared entity name at enqueue time (engagement-signal evidence).';
COMMENT ON COLUMN orrery_maturation_jobs.slot IS
    'Save-slot label the job belongs to (matches orrery_narration_jobs.slot).';
COMMENT ON COLUMN orrery_maturation_jobs.requesting_chunk_id IS
    'Committed chunk whose Skald response declared this entity.';
COMMENT ON COLUMN orrery_maturation_jobs.declaration IS
    'Validated NewEntityDeclaration payload (kind, name, summary, hints) '
    'used as scoped prompt material for the maturation pipeline.';
COMMENT ON COLUMN orrery_maturation_jobs.state IS
    'queued -> leased -> succeeded | failed. Failed jobs below the attempt '
    'cap requeue with a delay; at the cap they stay failed and visible.';
COMMENT ON COLUMN orrery_maturation_jobs.attempts IS
    'Lease count. Incremented when the worker leases the job.';
COMMENT ON COLUMN orrery_maturation_jobs.available_at IS
    'Earliest time the worker may lease the job (retry backoff).';
COMMENT ON COLUMN orrery_maturation_jobs.lease_until IS
    'Current lease expiry; NULL when not leased.';
COMMENT ON COLUMN orrery_maturation_jobs.last_error IS
    'Most recent failure message, kept loud for inspection.';
COMMENT ON COLUMN orrery_maturation_jobs.result_manifest IS
    'Persistence/embedding result manifest. When it records persisted '
    'Retrograde rows, retries resume at the embedding step instead of '
    're-running generation (prevents duplicate history).';

CREATE UNIQUE INDEX IF NOT EXISTS ux_orrery_maturation_jobs_entity
    ON orrery_maturation_jobs (entity_id);
CREATE INDEX IF NOT EXISTS ix_orrery_maturation_jobs_state_available
    ON orrery_maturation_jobs (state, available_at);
"""


def run(conn) -> None:
    """Add the incubator declaration column and the maturation job queue."""

    with conn.cursor() as cur:
        cur.execute(DDL)

    conn.commit()
