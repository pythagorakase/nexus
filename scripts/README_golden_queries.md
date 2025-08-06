# Golden Queries Testing Framework

This framework provides tools for evaluating MEMNON's retrieval performance using standardized "golden" queries.

## Overview

The Golden Queries testing framework consists of:

1. A collection of standard queries in `golden_queries.json`
2. A script to run these queries through MEMNON and collect results
3. The ability to evaluate results with a large language model

This enables rapid testing of different retrieval configurations and parameters to optimize MEMNON's performance.

## Running Golden Queries

To run the golden queries:

```bash
python scripts/run_golden_queries.py
```

This will:
1. Run all queries in `golden_queries.json` through MEMNON
2. Save the results to a timestamped JSON file (`golden_query_results_YYYYMMDD_HHMMSS.json`)

### Options

- `--input PATH` - Specify a different input file (default: `golden_queries.json`)
- `--limit N` - Limit to running N queries (for testing)
- `--k N` - Return N results per query (default: 10)
- `--hybrid` - Force enable hybrid search
- `--no-hybrid` - Force disable hybrid search

Example:

```bash
# Run only 3 queries with hybrid search enabled and 5 results per query
python scripts/run_golden_queries.py --limit 3 --hybrid --k 5
```

## Evaluating Results with an LLM

The output JSON file contains everything needed for evaluation by a large language model:

1. **Configuration details**: All relevant MEMNON settings
2. **Evaluation prompt**: Loaded from the `"prompt"` field in `golden_queries.json`
3. **Query data**: Each query, its positive/negative guidelines, and results

To evaluate results:

1. Open the JSON file in a text editor to review
2. Copy the entire contents or relevant sections
3. Paste into a chat with a large context model (Claude 3.5 Sonnet or similar)
4. Ask the model to evaluate the results according to the prompt

This approach allows for flexible, qualitative assessment of retrieval performance.

## Adding New Golden Queries

To add new queries, edit the `golden_queries.json` file. Queries are organized by category (characters, places, events, etc.), but the testing framework will run all queries regardless of their category.

Each query should include:
- `query` - The actual query text
- `positives` - Guidelines for what constitutes a good result
- `negatives` - Guidelines for what constitutes a bad result

Example:

```json
{
  "characters": {
    "sullivan": {
      "query": "Who is Sullivan?",
      "positives": [
        "direct references to Sullivan the cat",
        "passages about adopting the cat"
      ],
      "negatives": [
        "references to dogs",
        "references to Sullivan street"
      ]
    }
  }
}
```

## Usage Examples

### Testing Multiple Embedding Models

To compare different embedding models:

1. Edit `settings.json` to enable/disable models
2. Run the golden queries
3. Evaluate the results
4. Repeat with different model combinations

### Tuning Hybrid Search Parameters

To find optimal hybrid search weights:

1. Edit the vector/text weights in `settings.json`
2. Run the golden queries with `--hybrid`
3. Evaluate the results
4. Repeat with different weight values

### Automated Parameter Sweep

For more thorough testing, create a shell script that:
1. Modifies `settings.json` with different parameters
2. Runs the golden queries
3. Collects all results for later comparison