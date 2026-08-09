-- Remove stamped, vectorless summaries for excluded project-start provenance.

DO $$
DECLARE
    embedding_table record;
    deleted_count bigint := 0;
BEGIN
    CREATE TEMPORARY TABLE migration_101_summary_candidates (
        summary_id bigint PRIMARY KEY
    ) ON COMMIT DROP;

    INSERT INTO migration_101_summary_candidates (summary_id)
    SELECT rs.id
    FROM retrograde_summaries AS rs
    JOIN world_events AS we ON we.id = rs.world_event_id
    WHERE we.event_type IN (
        'relocation_plan_started',
        'recruit_ally_started',
        'build_venture_started',
        'pursue_romance_started',
        'court_patron_started',
        'seek_redemption_started'
    )
      AND rs.embedding_generated_at IS NOT NULL;

    FOR embedding_table IN
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
          AND table_name ~ '^retrograde_summary_embeddings_[0-9]+d$'
        ORDER BY table_name
    LOOP
        EXECUTE format(
            'DELETE FROM migration_101_summary_candidates AS candidate '
            'USING %I.%I AS embedding '
            'WHERE embedding.summary_id = candidate.summary_id',
            embedding_table.table_schema,
            embedding_table.table_name
        );
    END LOOP;

    DELETE FROM retrograde_summaries AS summary
    USING migration_101_summary_candidates AS candidate
    WHERE summary.id = candidate.summary_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    RAISE NOTICE
        'migration 101 deleted % project-start Retrograde summary orphan(s)',
        deleted_count;
END $$;
