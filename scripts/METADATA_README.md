# Narrative Metadata Processing

This document explains how to use the metadata processing system to enrich narrative chunks with structured metadata.

## Overview

The metadata extraction process has been split into two main stages for optimal performance and cost efficiency:

1. **Extract season and episode information** (fast, doesn't use API)
2. **Process complex metadata fields** (uses Claude API)

## Database Setup

The scripts require two main tables:
1. `narrative_chunks` - Contains the raw text chunks
2. `chunk_metadata` - Stores the extracted metadata

The metadata schema is based on `narrative_metadata_schema_2.json` and includes:
- Orientation (world_layer, setting)
- Chronology (season, episode, time_delta)
- Characters (present and mentioned)
- Narrative vector (arc_position, direction, magnitude)
- Character elements and developments
- Perspective and interactions
- Prose analysis (dialogue, emotional tone, techniques)
- Thematic elements and causality
- Continuity markers

## Workflow

### Step 1: Extract Season and Episode

First, run the `extract_season_episode.py` script to extract season and episode information from narrative chunks. This doesn't require API calls and can be done quickly:

```bash
# Extract season/episode for all chunks
python scripts/extract_season_episode.py --all

# Or, for chunks without metadata
python scripts/extract_season_episode.py --missing

# Or, for a specific range of chunks
python scripts/extract_season_episode.py --range 1 100
```

This script looks for patterns like `S01E02_003` or `# S01E02:` in the text and extracts the season and episode values.

### Step 2: Process Complex Metadata with Claude API

After you've extracted basic season/episode information, use the `batch_metadata_processing.py` script to generate the rest of the metadata using Claude's API:

```bash
# Process a small batch first to validate quality
python scripts/batch_metadata_processing.py --range 1 10 --save-prompt

# Then process all chunks without metadata
python scripts/batch_metadata_processing.py --missing --batch-size 15

# Or process a specific chunk by ID
python scripts/batch_metadata_processing.py --chunk-id 12345678-1234-5678-1234-567812345678
```

This script will:
- Preserve existing season/episode values that were extracted in Step 1
- Use context-aware processing with surrounding chunks
- Generate all complex metadata fields like character analysis, narrative vectors, etc.
- Save results to the database

## Script Options

### extract_season_episode.py

```
--all              Process all chunks
--missing          Process only chunks without metadata
--range START END  Process chunks in a sequence range (inclusive)
--dry-run          Don't save results to the database (test mode)
```

### batch_metadata_processing.py

```
--all              Process all chunks
--missing          Process only chunks without metadata 
--range START END  Process chunks in a sequence range (inclusive)
--chunk-id ID      Process a specific chunk by UUID
--batch-size N     Number of chunks per batch (default: 10)
--window-before N  Token count for context before chunk (default: 4000)
--window-after N   Token count for context after chunk (default: 2000)
--save-prompt      Save prompts to files for inspection
--dry-run          Don't save results to the database (test mode)
--api-key KEY      Manually specify Claude API key
```

## API Setup

Ensure you have a Claude API key set in one of the following locations:
- Environment variable: `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY`, or `ANTHROPIC_KEY`
- File at `~/.anthropic/api_key` or `~/.claude/api_key`
- In your `~/.zshrc` file as `ANTHROPIC_API_KEY=<key>`

## Database Configuration

Configure the database connection via environment variables if needed:
```bash
export DB_USER=your_username
export DB_PASSWORD=your_password
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=NEXUS
```

## Cost Considerations

The batch processing script includes cost estimation based on Claude 3 Opus pricing (as of April 2025):
- Input tokens: $15 per million tokens
- Output tokens: $75 per million tokens

To minimize costs:
1. Use `--range` to process small batches for testing before full runs
2. Consider using smaller context windows with `--window-before` and `--window-after`
3. Use `--dry-run` to test without saving results or making API calls

## Performance

On a typical system:
- Extracting season/episode for all chunks takes seconds
- Processing 10-15 chunks with Claude takes about 1-2 minutes
- Token-based windowing optimizes context usage
- For 1000+ chunks, consider running overnight in batches

## Troubleshooting

If you encounter issues:
- Check the `metadata_processing.log` file for detailed error messages
- Use `--save-prompt` to inspect the prompt structure
- Try processing a smaller batch first
- Ensure your API key has sufficient quota

For schema validation errors, you may need to adjust the schema to better match Claude's output format.