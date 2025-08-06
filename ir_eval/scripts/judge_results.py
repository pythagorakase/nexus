#!/usr/bin/env python3
"""
Judge Results - Interactive tool for NEXUS IR Evaluation System

This tool helps with the manual judging of search results from the NEXUS system.
It loads result files produced by run_golden_queries.py, identifies unjudged
documents, and lets you assign relevance scores to them.

This script is a compatibility wrapper around the new judgments.py module.

Usage:
    python judge_results.py --results [RESULTS_FILE] --qrels [QRELS_FILE]
    
    Optional arguments:
    --skip-judged         Skip already judged documents
    --golden-queries      Path to golden queries file (default: golden_queries.json)
"""

import sys
import argparse

# Import the newer module
from judgments import judge_results_interactive

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Judge NEXUS search results")
    parser.add_argument("--results", required=True, 
                      help="Path to the results JSON file")
    parser.add_argument("--qrels", default="qrels.json",
                      help="Path to the QRELS JSON file (default: qrels.json)")
    parser.add_argument("--golden-queries", default="golden_queries.json",
                      help="Path to the golden queries JSON file (default: golden_queries.json)")
    parser.add_argument("--skip-judged", action="store_true",
                      help="Skip already judged documents")
    
    args = parser.parse_args()
    
    # Call the function from the new module
    judge_results_interactive(
        args.results,
        args.qrels,
        args.golden_queries,
        args.skip_judged
    )
    
if __name__ == "__main__":
    main()