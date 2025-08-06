# PostgreSQL Migration for IR Evaluation System

This document outlines the migration of the NEXUS IR Evaluation System from SQLite to PostgreSQL.

## Why PostgreSQL?

The migration to PostgreSQL fixes several critical issues with the previous SQLite implementation:

1. **Document ID consistency** - The primary issue causing identical metrics between different search results was due to inconsistent document ID handling. PostgreSQL ensures IDs are properly typed (BIGINT).

2. **Direct integration with NEXUS database** - The evaluation system now works directly with the main NEXUS database, ensuring chunk IDs are consistent.

3. **Triggers and constraints** - Proper validation checks ensure data integrity between narrative chunks and evaluation results.

4. **Transaction support** - Better error handling and atomic operations.

5. **Advanced indexing** - Better performance for large result sets.

## Migration Components

The migration includes the following components:

1. **Database Schema** (`pg_schema.sql`) - Defines the ir_eval schema within the NEXUS database

2. **PostgreSQL DB Manager** (`pg_db.py`) - Replaces SQLite implementation with PostgreSQL

3. **QRELS Manager** (`scripts/pg_qrels.py`) - PostgreSQL version of relevance judgment manager

4. **Migration Script** (`migrate_sqlite_to_postgres.py`) - Imports existing data from SQLite

5. **Connection Test** (`test_pg_connection.py`) - Verifies database connectivity

6. **Main Application** (`ir_eval_pg.py`) - PostgreSQL version of the IR evaluation tool

## Migration Process

1. **Create Schema**

```bash
# Create the schema
psql -h localhost -U pythagor -d NEXUS -f ir_eval/pg_schema.sql
```

2. **Import Golden Queries**

```bash
# Import reference queries
python ir_eval/import_golden_queries.py
```

3. **Migrate Existing Data** (if needed)

```bash
# Import existing judgments and runs
python ir_eval/migrate_sqlite_to_postgres.py
```

4. **Run the PostgreSQL Version**

```bash
# Launch the evaluation tool
python ir_eval_pg.py
```

## Key Improvements

The PostgreSQL version includes several workflow improvements:

1. **Automatic judgment prompting** - After running a control/experiment pair, the system prompts to judge any new results before comparison.

2. **Chunk ID validation** - Triggers validate that chunk IDs exist in the narrative_chunks table.

3. **Clearer debug logging** - Better tracking of ID formats and data types.

4. **Enhanced result displays** - Clear difference highlighting in comparisons.

## Troubleshooting

If you encounter issues:

1. Check database connectivity with `test_pg_connection.py`
2. Verify that ir_eval schema exists in NEXUS database
3. Look for additional logging in `ir_eval/ir_eval_pg.log`

## Data Migration Notes

When migrating existing judgments:

- Document IDs in SQLite are converted to integer chunk IDs
- Invalid document IDs are skipped
- String type conflicts are automatically resolved