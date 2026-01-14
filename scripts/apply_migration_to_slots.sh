#!/bin/bash
# Apply a SQL migration file to all 5 slot databases (save_01 through save_05)
#
# Usage:
#   ./scripts/apply_migration_to_slots.sh <migration_file.sql>
#
# Example:
#   ./scripts/apply_migration_to_slots.sh scripts/migrate_slots.sql
#
# This script:
# - Takes a SQL migration file as an argument
# - Applies it to each slot database (save_01, save_02, save_03, save_04, save_05)
# - Reports success or failure for each database
# - Continues even if one database fails (for idempotency)

set -e

# Check if migration file argument provided
if [ -z "$1" ]; then
    echo "Error: No migration file specified"
    echo "Usage: $0 <migration_file.sql>"
    exit 1
fi

MIGRATION_FILE="$1"

# Check if migration file exists
if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

echo "Applying migration: $MIGRATION_FILE"
echo "Target: All slot databases (save_01 through save_05)"
echo "----------------------------------------"

# PostgreSQL connection settings
PGUSER="${PGUSER:-pythagor}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"

SUCCESS_COUNT=0
FAIL_COUNT=0

# Apply migration to each slot database
for slot in 01 02 03 04 05; do
    DB_NAME="save_$slot"
    echo ""
    echo "Processing $DB_NAME..."

    # Check if database exists
    if psql -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        # Database exists, apply migration
        if psql -U "$PGUSER" -h "$PGHOST" -p "$PGPORT" -d "$DB_NAME" -f "$MIGRATION_FILE" > /dev/null 2>&1; then
            echo "✓ Successfully applied migration to $DB_NAME"
            ((SUCCESS_COUNT++))
        else
            echo "✗ Failed to apply migration to $DB_NAME"
            ((FAIL_COUNT++))
        fi
    else
        echo "⊘ Database $DB_NAME does not exist (skipping)"
    fi
done

echo ""
echo "----------------------------------------"
echo "Migration Summary:"
echo "  Successful: $SUCCESS_COUNT"
echo "  Failed: $FAIL_COUNT"
echo "  Skipped: $((5 - SUCCESS_COUNT - FAIL_COUNT))"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
    echo "⚠ Some migrations failed. Check errors above."
    exit 1
else
    echo "✓ All available databases migrated successfully!"
    exit 0
fi
