# IR Evaluation Database Issues

## Problem Description
When attempting to check or interact with the `ir_eval.judgments` table in the PostgreSQL database, we're experiencing timeout issues or slow responses. This happened after attempting to add a new `comment` column to store the AI's justifications.

## Observations

1. **Basic Structure Query Timeout**:
   ```
   psql -U pythagor -d NEXUS -c "\d ir_eval.judgments"
   ```
   → Timed out after 2 minutes

2. **Schema Verification**:
   ```
   psql -U pythagor -d NEXUS -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'ir_eval' AND table_name = 'judgments' ORDER BY ordinal_position;"
   ```
   → Showed the following columns:
   - id (integer)
   - query_id (integer)
   - chunk_id (bigint)
   - relevance (integer)
   - doc_text (text)
   
   Note: No `comment` column visible in the results.

3. **Row Count Query Timeout**:
   ```
   psql -U pythagor -d NEXUS -c "SELECT COUNT(*) FROM ir_eval.judgments;"
   ```
   → Timed out after 2 minutes

4. **Table Statistics**:
   ```
   psql -U pythagor -d NEXUS -c "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'ir_eval';"
   ```
   → Found 775 rows in the judgments table

5. **Table Size Query**:
   ```
   psql -U pythagor -d NEXUS -c "SELECT table_name, pg_size_pretty(pg_total_relation_size('ir_eval.' || table_name)) AS size FROM information_schema.tables WHERE table_schema = 'ir_eval' ORDER BY pg_total_relation_size('ir_eval.' || table_name) DESC LIMIT 10;"
   ```
   → Timed out after 2 minutes

## Potential Issues

1. **Table Lock**: The table might be locked by another session or transaction.

2. **Missing Index**: If the `comment` addition resulted in a large increase in row size, some queries might be slower without proper indexes.

3. **Database Resource Issues**: The database might be experiencing high load or resource constraints.

4. **Transaction Issue**: There might be a long-running transaction causing locks or slowdowns.

5. **Corrupt Table Statistics**: The table statistics might be out of date, causing query planner issues.

## Recommended Actions

1. **System Reboot**: Performing a full system reboot may clear any locks or hung transactions.

2. **Check PostgreSQL Logs**: After reboot, examine PostgreSQL logs for any error messages related to the judgments table.

3. **Verify PostgreSQL Service Status**: Make sure PostgreSQL is running properly after reboot.

4. **Schema Change**: If issues persist, consider:
   - Adding the column with a default NULL value
   - Creating a new table with the desired schema and migrating data

5. **Database Maintenance**: Consider running `VACUUM ANALYZE` on the table after the reboot to update statistics.

## Notes for Implementation of AI Judging

When updating the `auto_judge.py` script to work with the fixed database:

1. **Check for Column Existence**: Add logic to check if the `justification` column exists before trying to store data in it.

2. **Fallback Behavior**: If the column doesn't exist, log a warning but continue with storing only the relevance score.

3. **Batch Processing**: Consider implementing smaller batch sizes when saving judgments to avoid long-running transactions.

## Post-Reboot Verification Steps

1. Attempt to add the justification column if it doesn't exist:
   ```sql
   ALTER TABLE ir_eval.judgments ADD COLUMN IF NOT EXISTS justification text;
   ```

2. Verify the table structure:
   ```sql
   \d ir_eval.judgments
   ```

3. Update table statistics:
   ```sql
   ANALYZE ir_eval.judgments;
   ```