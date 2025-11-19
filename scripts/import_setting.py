#!/usr/bin/env python3
"""
Import the setting backstory document into global_variables.setting
"""

import json
import psycopg2
from pathlib import Path


def main():
    # Read the backstory document
    backstory_path = Path(__file__).parent.parent / "temp" / "global_backstory.md"

    with open(backstory_path, 'r') as f:
        content = f.read()

    # Create minimal JSON wrapper
    setting_data = {
        "format": "markdown",
        "title": "The Zenith Pulse & Fractured Future",
        "content": content,
        "metadata": {
            "era": "2025-2073",
            "medium": "found document, historical dossier",
            "provenance": "compiled in 2073 from municipal archives, corporate white-books, and eyewitness logs"
        }
    }

    # Connect to database
    conn = psycopg2.connect(
        host="localhost",
        database="NEXUS",
        user="pythagor"
    )

    try:
        with conn.cursor() as cur:
            # Update the single row in global_variables
            cur.execute(
                "UPDATE global_variables SET setting = %s WHERE id = true",
                (json.dumps(setting_data),)
            )
            conn.commit()

            # Verify the update
            cur.execute("SELECT setting FROM global_variables WHERE id = true")
            result = cur.fetchone()

            if result and result[0]:
                print("✓ Setting data imported successfully")
                print(f"  Title: {result[0]['title']}")
                print(f"  Era: {result[0]['metadata']['era']}")
                print(f"  Content length: {len(result[0]['content'])} characters")
            else:
                print("✗ Failed to import setting data")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
