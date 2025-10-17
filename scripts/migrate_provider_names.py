#!/usr/bin/env python3
"""
Migrate provider enum values to use proper casing.

Changes:
- openai -> OpenAI
- anthropic -> Anthropic
- openrouter -> DeepSeek
"""

import psycopg2

DB_URL = "postgresql://pythagor@localhost/NEXUS"


def migrate():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:
        print("Starting provider enum migration...")

        # Step 1: Add new enum values
        print("Adding new enum values...")
        cur.execute("ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'OpenAI'")
        cur.execute("ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'Anthropic'")
        cur.execute("ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'DeepSeek'")
        conn.commit()

        # Step 2: Update records to use new values
        print("Updating conditions records...")

        # openai -> OpenAI
        cur.execute("""
            UPDATE apex_audition.conditions
            SET provider = 'OpenAI'
            WHERE provider = 'openai'
        """)
        print(f"  Updated {cur.rowcount} records: openai -> OpenAI")

        # anthropic -> Anthropic
        cur.execute("""
            UPDATE apex_audition.conditions
            SET provider = 'Anthropic'
            WHERE provider = 'anthropic'
        """)
        print(f"  Updated {cur.rowcount} records: anthropic -> Anthropic")

        # openrouter -> DeepSeek
        cur.execute("""
            UPDATE apex_audition.conditions
            SET provider = 'DeepSeek'
            WHERE provider = 'openrouter'
        """)
        print(f"  Updated {cur.rowcount} records: openrouter -> DeepSeek")

        conn.commit()

        # Step 3: Verify no records remain with old values
        print("Verifying migration...")
        cur.execute("""
            SELECT provider, COUNT(*)
            FROM apex_audition.conditions
            GROUP BY provider
        """)
        results = cur.fetchall()
        print("Current provider distribution:")
        for provider, count in results:
            print(f"  {provider}: {count}")

        # Step 4: Remove old enum values by recreating the type
        # This is complex in PostgreSQL - we need to:
        # 1. Create a new enum type
        # 2. Alter the column to use the new type
        # 3. Drop the old type
        # 4. Rename the new type

        print("\nRecreating enum type with only new values...")

        # Create new temporary enum
        cur.execute("""
            CREATE TYPE apex_audition.provider_enum_new AS ENUM ('OpenAI', 'Anthropic', 'DeepSeek')
        """)

        # Change column to use new type
        cur.execute("""
            ALTER TABLE apex_audition.conditions
            ALTER COLUMN provider TYPE apex_audition.provider_enum_new
            USING provider::text::apex_audition.provider_enum_new
        """)

        # Drop old type and rename new one
        cur.execute("DROP TYPE apex_audition.provider_enum")
        cur.execute("ALTER TYPE apex_audition.provider_enum_new RENAME TO provider_enum")

        conn.commit()

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
