# NEXUS IR Evaluation Scripts

This directory contains the refactored IR evaluation modules for the NEXUS system. The original monolithic `ir_eval.py` has been split into multiple focused modules to improve maintainability.

## Main Components

- **ir_eval.py**: Main entry point, now imports functionality from other modules
- **ir_eval_cli.py**: Interactive command-line interface
- **query_runner.py**: Functions for running golden queries
- **judgments.py**: Functions for judging search results
- **display.py**: Functions for displaying formatted output
- **utils.py**: Utility functions for common operations
- **ir_metrics.py**: Functions for calculating IR metrics
- **comparison.py**: Functions for comparing runs and query variations
- **qrels.py**: Manager for relevance judgments
- **db.py**: Database access layer (in parent directory)

## Task-Specific Scripts

- **add_query_relationships.py**: Create explicit relationships between query pairs
- **analyze_metrics_differences.py**: Detailed analysis of result differences
- **calculate_metrics.py**: Calculate metrics for specific runs
- **check_judgments.py**: Check and validate judgments
- **compare_query_pairs.py**: Compare metrics between query pairs
- **copy_judgments.py**: Copy judgments between paired queries
- **list_runs.py**: List available runs in the database
- **merge_runs_for_comparison.py**: Combine metrics from multiple runs

## Usage

The main interfaces for the system are:

1. Interactive CLI:
   ```
   python ir_eval_cli.py
   ```

2. Command-line tools for specific tasks:
   ```
   python query_runner.py --help
   python judgments.py --help
   python comparison.py --help
   # etc.
   ```

## Design Philosophy

The refactoring follows these principles:

1. **Single Responsibility**: Each module handles a specific aspect of the system
2. **Clean Interfaces**: Modules interact through well-defined interfaces
3. **Backward Compatibility**: Original functionality is preserved
4. **Extensibility**: Easier to add new features in isolated modules
5. **Error Handling**: Consistent error handling across modules

The refactoring process followed the plan in `refactoring_TODO.txt`.