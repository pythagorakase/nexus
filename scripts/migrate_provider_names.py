#!/usr/bin/env python3
"""
Rewrite apex_audition.conditions provider values to use proper casing.

Changes:
- openai -> OpenAI
- anthropic -> Anthropic
- openrouter -> DeepSeek

The values OpenAI, Anthropic and DeepSeek must already exist in
apex_audition.provider_enum: no migration owns that type, and this script
does not alter it.
"""

from nexus.database import url_connection_kwargs

import psycopg2

DB_URL = None


def migrate():
    conn = psycopg2.connect(**url_connection_kwargs(DB_URL))
    cur = conn.cursor()

    try:
        print("Starting provider enum migration...")

        cur.execute(
            "SELECT enumlabel FROM pg_enum "
            "WHERE enumtypid = to_regtype('apex_audition.provider_enum')"
        )
        labels = {row[0] for row in cur.fetchall()}
        missing = {"OpenAI", "Anthropic", "DeepSeek"} - labels
        if missing:
            raise RuntimeError(
                f"Missing apex_audition.provider_enum values {sorted(missing)}; "
                "no migration owns apex_audition.provider_enum, and this script "
                "no longer alters it. scripts/migrate.py is the only migration "
                "runner."
            )

        # Step 2: Update records to use new values
        print("Updating conditions records...")

        # openai -> OpenAI
        cur.execute(
            """
            UPDATE apex_audition.conditions
            SET provider = 'OpenAI'
            WHERE provider = 'openai'
        """
        )
        print(f"  Updated {cur.rowcount} records: openai -> OpenAI")

        # anthropic -> Anthropic
        cur.execute(
            """
            UPDATE apex_audition.conditions
            SET provider = 'Anthropic'
            WHERE provider = 'anthropic'
        """
        )
        print(f"  Updated {cur.rowcount} records: anthropic -> Anthropic")

        # openrouter -> DeepSeek
        cur.execute(
            """
            UPDATE apex_audition.conditions
            SET provider = 'DeepSeek'
            WHERE provider = 'openrouter'
        """
        )
        print(f"  Updated {cur.rowcount} records: openrouter -> DeepSeek")

        conn.commit()

        # Step 3: Verify no records remain with old values
        print("Verifying migration...")
        cur.execute(
            """
            SELECT provider, COUNT(*)
            FROM apex_audition.conditions
            GROUP BY provider
        """
        )
        results = cur.fetchall()
        print("Current provider distribution:")
        for provider, count in results:
            print(f"  {provider}: {count}")

        print("\n✓ Migration completed successfully!")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migrate()
