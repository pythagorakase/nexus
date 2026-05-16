-- migrations/022_compound_embedding_pk_lazy_tables.sql
-- Description: Use (chunk_id, model) as the primary key for dimension-specific
-- embedding tables and remove empty pre-created tables. Embedding tables are
-- now created lazily by write paths for the active model dimensions.
-- Date: 2026-05-16

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
DECLARE
    embedding_table RECORD;
    table_oid REGCLASS;
    row_count BIGINT;
    null_count BIGINT;
    duplicate_count BIGINT;
    pk_name TEXT;
    unique_constraint RECORD;
BEGIN
    FOR embedding_table IN
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ~ '^chunk_embeddings_[0-9]+d$'
        ORDER BY table_name
    LOOP
        table_oid := format('public.%I', embedding_table.table_name)::REGCLASS;

        EXECUTE format('SELECT COUNT(*) FROM %I', embedding_table.table_name)
            INTO row_count;

        IF row_count = 0 THEN
            EXECUTE format('DROP TABLE %I', embedding_table.table_name);
            EXECUTE format(
                'DROP SEQUENCE IF EXISTS %I',
                embedding_table.table_name || '_id_seq'
            );
            RAISE NOTICE 'Dropped empty embedding table %',
                embedding_table.table_name;
            CONTINUE;
        END IF;

        EXECUTE format(
            'SELECT COUNT(*)
             FROM %I
             WHERE chunk_id IS NULL
                OR model IS NULL',
            embedding_table.table_name
        )
            INTO null_count;

        IF null_count > 0 THEN
            RAISE EXCEPTION
                'Cannot migrate %. Found % rows with NULL chunk_id or model.',
                embedding_table.table_name,
                null_count;
        END IF;

        EXECUTE format(
            'SELECT COUNT(*) FROM (
                SELECT chunk_id, model
                FROM %I
                GROUP BY chunk_id, model
                HAVING COUNT(*) > 1
            ) duplicates',
            embedding_table.table_name
        )
            INTO duplicate_count;

        IF duplicate_count > 0 THEN
            RAISE EXCEPTION
                'Cannot migrate %. Found % duplicate (chunk_id, model) pairs.',
                embedding_table.table_name,
                duplicate_count;
        END IF;

        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN chunk_id SET NOT NULL',
            embedding_table.table_name
        );
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN model SET NOT NULL',
            embedding_table.table_name
        );

        SELECT conname
        INTO pk_name
        FROM pg_constraint
        WHERE conrelid = table_oid
          AND contype = 'p';

        IF pk_name IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT %I',
                embedding_table.table_name,
                pk_name
            );
        END IF;

        FOR unique_constraint IN
            SELECT conname
            FROM pg_constraint c
            WHERE c.conrelid = table_oid
              AND c.contype = 'u'
              AND (
                  SELECT array_agg(a.attname::TEXT ORDER BY keys.ordinality)
                  FROM unnest(c.conkey) WITH ORDINALITY AS keys(attnum, ordinality)
                  JOIN pg_attribute a
                    ON a.attrelid = c.conrelid
                   AND a.attnum = keys.attnum
              ) = ARRAY['chunk_id', 'model']::TEXT[]
        LOOP
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT %I',
                embedding_table.table_name,
                unique_constraint.conname
            );
        END LOOP;

        EXECUTE format(
            'ALTER TABLE %I DROP COLUMN IF EXISTS id CASCADE',
            embedding_table.table_name
        );
        EXECUTE format(
            'DROP SEQUENCE IF EXISTS %I',
            embedding_table.table_name || '_id_seq'
        );
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I PRIMARY KEY (chunk_id, model)',
            embedding_table.table_name,
            embedding_table.table_name || '_pkey'
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (model)',
            embedding_table.table_name || '_model_idx',
            embedding_table.table_name
        );

        RAISE NOTICE 'Migrated embedding table % to compound primary key',
            embedding_table.table_name;
    END LOOP;
END $$;
