# Time Delta Calculator

This utility processes narrative chunks using a local LLM to estimate realistic time_delta values for each narrative chunk.

## Overview

The time delta calculator analyzes narrative chunks from the NEXUS database and uses a local Large Language Model (LLM) to estimate how much in-world time passes during each chunk. These estimations are then stored in the database for use in narrative continuity tracking and timeline visualization.

## Features

- Process single chunks, ranges of chunks, or all chunks needing time_delta values
- Test mode to preview results without modifying the database
- Provides preceding and following chunks as context to the LLM
- Detailed activity breakdown for time estimation
- Multiple fallback mechanisms for LLM integration
- Compatible with LM Studio's just-in-time model loading

## Requirements

- Python 3.11+
- SQLAlchemy and psycopg2 (for database access)
- One of the following LLM interfaces:
  1. LM Studio API (preferred) - running on http://localhost:1234
  2. llama.cpp executable in PATH or standard locations
- Access to a suitable language model (DeepSeek R1 Distill or equivalent)

## LM Studio Setup (Recommended)

1. **Install LM Studio**: Download from [lmstudio.ai](https://lmstudio.ai)
2. **Start the API Server**:
   - Go to the "API" tab in LM Studio
   - Click "Start Server" if it's not already running
   - Ensure the server is running on port 1234 (default)
   - The API status indicator should show "Running"
3. **Just-in-time Model Loading**:
   - LM Studio supports just-in-time model loading (loads models on demand)
   - The script will specify the model ID in the API request
   - LM Studio will load the model if it's available on your system
   - **Important**: First request may take 3-5 minutes while the model loads
   - The script has a 5-minute timeout to accommodate large model loading

## Usage

```bash
# Test mode - process chunks 1-10 without writing to database
python estimate_time_delta.py --start 1 --end 10 --test

# Process a single chunk and write to database
python estimate_time_delta.py --start 5 --end 5 --write

# Process all chunks needing time_delta values
python estimate_time_delta.py --all --write

# Specify a different model ID for LM Studio
python estimate_time_delta.py --start 1 --end 1 --test --model-id "llama-3-8b"

# Use a specific model file (for llama.cpp fallback only)
python estimate_time_delta.py --all --write --model /path/to/model.gguf
```

## Command Line Arguments

| Argument | Description |
|----------|-------------|
| `--start` | Starting chunk sequence number |
| `--end` | Ending chunk sequence number (defaults to same as start) |
| `--all` | Process all chunks needing time_delta |
| `--test` | Test mode, print results only (no database updates) |
| `--write` | Write results to database |
| `--model-id` | Model ID for LM Studio (default: "deepseek-r1-distill-llama-70b@q8_0") |
| `--model` | Path to model file (for llama.cpp fallback) |

## How It Works

1. **Chunk Selection**: The script retrieves narrative chunks from the database
2. **Context Building**: For each chunk, the script retrieves preceding and following chunks for context
3. **Prompt Creation**: A detailed prompt is constructed for the LLM, with clear instructions
4. **LLM Query**: The script connects to LM Studio API with the specified model ID
5. **Response Parsing**: Time estimates are extracted from the LLM's response
6. **Database Update**: The time_delta values are written to the chunk_metadata table

## LLM Prompt Structure

The prompt instructs the LLM to:
1. List all discrete activities in the target chunk
2. Estimate a realistic duration for each activity
3. Sum these durations to calculate the total time delta

Guidelines for common activities are provided in the prompt.

## Troubleshooting

If you encounter issues with LM Studio integration:

1. **Check LM Studio**: Ensure LM Studio is running and the API server is started
2. **Verify API Status**: The API indicator in LM Studio should show "Running"
3. **Model Availability**: Check if the specified model is available on your system
4. **Model ID Format**: Make sure the model ID matches the format used in LM Studio
5. **First Request Delay**: The first request will take 3-5 minutes for a 70B model to load
6. **Be Patient**: Don't interrupt the script during the first request - it's normal for it to appear "stuck" while loading
7. **Check Logs**: Watch the LM Studio logs to monitor model loading progress
8. **Memory Requirements**: Large models (70B) require substantial RAM and GPU memory

## Output Format

Time deltas are stored in the format: "X hours Y minutes" 