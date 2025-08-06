# NEXUS IR Evaluation System

This system provides tools for evaluating and comparing information retrieval performance in the NEXUS project using pooled relevance judgments. It works with the golden query framework to assess search quality across different configurations.

## Overview

The IR evaluation system consists of four main components:

1. **QRELSManager** (`qrels.py`): Stores and manages relevance judgments for query-document pairs
2. **IR Metrics** (`ir_metrics.py`): Calculates standard information retrieval metrics
3. **Judge Results** (`judge_results.py`): Interactive tool for relevance assessment
4. **Compare Runs** (`compare_runs.py`): Compares metrics across different configurations

These tools integrate with the existing golden query framework to provide a systematic approach to evaluating and improving search quality.

## Workflow

The typical workflow for the system is:

1. Run golden queries with configuration A: `python scripts/run_golden_queries.py`
2. Judge the results: `python scripts/judge_results.py --results golden_query_results_*.json`
3. Run golden queries with configuration B: `python scripts/run_golden_queries.py [different settings]`
4. Judge only new results from B
5. Compare A vs B: `python scripts/compare_runs.py --runs run_A.json run_B.json`
6. Iterate with new configurations based on the results

## Components

### QRELSManager (`qrels.py`)

Manages relevance judgments for query-document pairs on a 0-3 scale:
- 0: Irrelevant
- 1: Marginally relevant
- 2: Relevant
- 3: Highly relevant

```python
from scripts.qrels import QRELSManager

qrels = QRELSManager()
qrels.add_judgment("Who is Sullivan?", "12345", 3, "character")
qrels.save()
```

### IR Metrics (`ir_metrics.py`)

Implements standard information retrieval metrics:
- Precision@k (for k=5 and k=10)
- Mean Reciprocal Rank (MRR)
- Binary Preference (bpref)

```python
from scripts.ir_metrics import calculate_all_metrics

metrics = calculate_all_metrics(results, judgments)
print(f"Precision@5: {metrics['p@5']}")
```

### Judge Results (`judge_results.py`)

Interactive CLI tool for judging search results:
- Shows guidelines from golden_queries.json for each query
- Displays document text for judgment
- Records relevance scores on a 0-3 scale
- Shows progress and saves automatically

```
python scripts/judge_results.py --results golden_query_results_20250422_183605.json
```

### Compare Runs (`compare_runs.py`)

Tool for comparing metrics across different configurations:
- Loads multiple result files
- Calculates metrics for each using the same qrels
- Shows side-by-side comparison tables
- Identifies the best performing configuration

```
python scripts/compare_runs.py --runs run_A.json run_B.json --names "Baseline" "Hybrid"
```

## Command-Line Usage

### Judge Results

```
python scripts/judge_results.py --results [RESULTS_FILE] [OPTIONS]

Options:
  --qrels FILE             Path to QRELS file (default: qrels.json)
  --golden-queries FILE    Path to golden queries file (default: golden_queries.json)
  --skip-judged            Skip already judged documents
```

### Compare Runs

```
python scripts/compare_runs.py --runs [RESULTS_FILE1] [RESULTS_FILE2] ... [OPTIONS]

Options:
  --qrels FILE             Path to QRELS file (default: qrels.json)
  --names NAME1 NAME2 ...  Names for each run (default: Run A, Run B, etc.)
  --output FILE            Output file for comparison results (JSON)
```

## Example Output

### Comparison Table

```
==============================================================================
NEXUS IR Evaluation - Run Comparison
==============================================================================

Overall Metrics:
------------------------------------------------------------------------------
Metric    Run A          Run B          Best Run      
------------------------------------------------------------------------------
p@5       0.6000         0.7200 (+0.1200) Run B         
p@10      0.5500         0.6100 (+0.0600) Run B         
mrr       0.8333         0.9000 (+0.0667) Run B         
bpref     0.7123         0.7546 (+0.0423) Run B         

Unjudged Documents:
Count     12             8              

==============================================================================
BEST OVERALL PERFORMER: Run B
==============================================================================
```

## Integration with Existing Code

The system integrates with the existing golden query framework:

- Works with `golden_queries.json` for query definitions and guidelines
- Consumes result files produced by `run_golden_queries.py`
- Preserves all metadata from the original runs
- Uses the same document and query identifiers

## Tips for Effective Evaluation

1. Judge a small batch of documents before running large experiments
2. Use the `--skip-judged` flag to focus on new results only
3. Regularly back up your qrels.json file
4. When comparing runs, use descriptive names for easier reference
5. Focus on the metrics that matter most for your use case (e.g., MRR for single-answer queries)