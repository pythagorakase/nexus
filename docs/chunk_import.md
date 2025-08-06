# Chunk Import Script

`chunk_import.py` is a Python script designed to parse markdown files containing scene breaks and store the content in a PostgreSQL database.

## Overview

The script performs the following functions:

1. Scans markdown files for scene break markers in the format: `<!-- SCENE BREAK: S01E01_001 (optional comment) -->`
2. Extracts the following metadata from each scene break:
   - Slug (e.g., "S01E01_001")
   - Season number
   - Episode number
   - Scene number
3. Collects all text between scene breaks into chunks
4. Stores each chunk and its metadata in a PostgreSQL database using SQLAlchemy

## Database Schema

The script uses two tables:

1. `narrative_chunks`
   - `id` (UUID): Primary key
   - `raw_text` (Text): The raw content of the chunk

2. `chunk_metadata`
   - `chunk_id` (UUID): Foreign key to narrative_chunks.id
   - `season` (Integer): Season number
   - `episode` (Integer): Episode number 
   - `scene_number` (Integer): Scene number
   - `slug` (String): Unique identifier (e.g., "S01E01_001")

## Usage

```
python chunk_import.py [files] [--db-url DB_URL]
```

Arguments:
- `files`: Optional list of markdown files to process. If not provided, all .md files in the current directory will be processed.
- `--db-url`: Optional database URL. Default is `postgresql://postgres:postgres@localhost/nexus`.

## Example

```
python chunk_import.py ALEX_1_copy_notime.md ALEX_2_copy_notime.md --db-url postgresql://user:password@localhost/mydatabase
```

## Future Enhancements

The script is designed to be extended with pgvector support for storing embeddings. This would involve:

1. Installing the pgvector extension in PostgreSQL
2. Adding a vector column to the `narrative_chunks` table
3. Implementing a function to generate embeddings from text
4. Updating the import process to include embedding generation 