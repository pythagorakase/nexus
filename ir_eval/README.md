# NEXUS IR Evaluation System

This system provides a comprehensive toolkit for evaluating and comparing information retrieval performance in the NEXUS project. It implements a pooled relevance judgment approach that helps systematically evaluate and improve search quality across different embedding configurations.

## Key Features

- **Interactive CLI** for managing the entire evaluation workflow
- **A/B Testing** between control (settings.json) and experimental (golden_queries.json) configurations
- **Relevance Judgments** on a 0-3 scale with persistent storage
- **Industry-standard IR Metrics** (Precision@k, MRR, bpref)
- **Detailed Comparisons** between different retrieval configurations
- **Category-based Analysis** for different query types

## Getting Started

### Installation

No installation required! Just make sure you have all dependencies installed via Poetry:

```bash
cd /path/to/nexus
poetry install
```

### Quick Start

1. Run the integrated IR evaluation tool:

```bash
cd /path/to/nexus
python ir_eval/ir_eval.py
```

2. Follow the interactive menu to:
   - Run golden queries with different configurations
   - Judge search results
   - Compare performance across configurations

## Workflow

The typical workflow for the system is:

1. **Run queries** with both control and experimental settings
2. **Judge results** to build a pool of relevance judgments
3. **Compare metrics** to see which configuration performs better
4. **Refine settings** in golden_queries.json based on insights
5. **Repeat** until you achieve optimal performance

## Components

### Main Interactive Tool (`ir_eval.py`)

The main script integrates all components into a user-friendly CLI interface:

```
NEXUS IR Evaluation System
========================================================================
1. Run all golden queries (control vs experiment)
2. Run queries for specific category
3. Judge results
4. Compare results
5. View configuration details
6. Exit
```

### Component Libraries

- **db.py**: SQLite database for storing evaluation data, results, and judgments
- **scripts/qrels.py**: Manages relevance judgments for query-document pairs
- **scripts/ir_metrics.py**: Calculates standard IR metrics (P@k, MRR, bpref)
- **scripts/compare_runs.py**: Compares metrics across configurations

## Configuration

The system uses two sets of configurations:

1. **Control**: From `settings.json` (current production settings)
2. **Experimental**: From `golden_queries.json` (your test settings)

To experiment with different settings, modify the retrieval settings in `golden_queries.json`:

```json
"settings": {
    "retrieval": {
        "hybrid_search": {
            "enabled": true,
            "vector_weight_default": 0.8,
            "text_weight_default": 0.2
        },
        "models": {
            "bge-large": {
                "is_active": true,
                "weight": 0.3
            },
            "infly_inf-retriever-v1-1.5b": {
                "is_active": true,
                "weight": 0.7
            }
        }
    }
}
```

## Metrics

The system calculates four key IR metrics:

- **Precision@5**: Percentage of relevant documents in the top 5 results
- **Precision@10**: Percentage of relevant documents in the top 10 results
- **Mean Reciprocal Rank (MRR)**: Average of 1/rank of the first relevant document
- **Binary Preference (bpref)**: Measure of how often relevant documents are ranked above irrelevant ones

## Output Example

```
NEXUS IR Evaluation - Run Comparison
========================================================================

Overall Metrics:
--------------------------------------------------------------------------------
Metric    Control        Experiment     Best Run      
--------------------------------------------------------------------------------
p@5       0.6000         0.7200 (+0.1200) Experiment    
p@10      0.5500         0.6100 (+0.0600) Experiment    
mrr       0.8333         0.9000 (+0.0667) Experiment    
bpref     0.7123         0.7546 (+0.0423) Experiment    

Unjudged Documents:
Count     12             8              

========================================================================
BEST OVERALL PERFORMER: Experiment
========================================================================
```

## Tips for Effective Evaluation

1. **Judge a representative sample** of documents first
2. Focus on **key query categories** that are important for your use case
3. Adjust **one setting at a time** to understand its impact
4. Pay attention to both **overall metrics** and **category-specific performance**
5. Consider the **trade-offs** between different metrics (e.g., P@5 vs. MRR)

## Advanced Usage

For advanced users who want more control, individual component scripts can be used directly:

```bash
# Judge results manually
python ir_eval/scripts/judge_results.py --results path/to/results.json

# Compare specific result files
python ir_eval/scripts/compare_runs.py --runs result1.json result2.json --names "Baseline" "Experiment"
```

## Troubleshooting

- **Missing settings**: Ensure both settings.json and golden_queries.json are properly configured
- **No results**: Check that your MEMNON agent is properly initialized and connected to the database
- **Low judged document counts**: Make more relevance judgments to get more reliable metrics
- **Inconsistent results**: Try running the same configuration multiple times to check for stability
- **Database access errors**: Ensure SQLite is working properly and the ir_eval.db file has proper permissions

## Database Schema

The evaluation system uses SQLite to store results and judgments in a structured format:

```
- queries: Stores query information (id, text, category, name)
- judgments: Stores relevance judgments (query_id, doc_id, relevance)
- runs: Stores information about evaluation runs (name, timestamp, settings)
- results: Stores search results (run_id, query_id, doc_id, rank, score)
- metrics: Stores calculated metrics (run_id, query_id, p@5, p@10, mrr, bpref)
- comparisons: Stores comparison results between different runs
```

This database approach provides better data organization, easier querying, and more robust storage than the previous JSON-based approach.