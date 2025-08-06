#!/usr/bin/env python3
"""
Test script for run comparison functionality in the SQLite IR evaluation system.
"""

import os
import json
import logging
from db import IRDatabase
from scripts.qrels import QRELSManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_comparison")

def main():
    """Run tests for the comparison functionality."""
    # Use a test database file
    test_db_path = "test_comparison.db"
    
    # Remove test database if it exists
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        logger.info(f"Removed existing test database: {test_db_path}")
    
    # Initialize database
    db = IRDatabase(test_db_path)
    logger.info("Initialized test database")
    
    # Initialize QRELS manager
    qrels = QRELSManager(test_db_path)
    logger.info("Initialized QRELS manager")
    
    # Create two test runs with different settings
    control_settings = {
        "retrieval": {
            "hybrid_search": {
                "enabled": False
            },
            "models": {
                "bge-small": {
                    "is_active": True,
                    "weight": 1.0
                }
            }
        }
    }
    
    experiment_settings = {
        "retrieval": {
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.7,
                "text_weight_default": 0.3
            },
            "models": {
                "infly_inf-retriever-v1-1.5b": {
                    "is_active": True,
                    "weight": 1.0
                }
            }
        }
    }
    
    # Add runs
    control_run_id = db.add_run("Control", control_settings, "control", "Vector search only with bge-small")
    experiment_run_id = db.add_run("Experiment", experiment_settings, "experiment", "Hybrid search with inf-retriever")
    logger.info(f"Added runs: control={control_run_id}, experiment={experiment_run_id}")
    
    # Add test queries
    queries = [
        ("Who is Johnny Silverhand?", "character", "silverhand"),
        ("What happened at Arasaka Tower?", "event", "arasaka"),
        ("Where is Lizzie's Bar?", "location", "lizzies"),
        ("Who is Saburo Arasaka?", "character", "saburo"),
        ("What is braindance?", "concept", "braindance")
    ]
    
    for query_text, category, name in queries:
        db.add_query(query_text, category, name)
    
    logger.info(f"Added {len(queries)} test queries")
    
    # Add judgments for testing
    for query_text, category, _ in queries:
        # Add some sample judgments (in practice these would be from user input)
        for i in range(10):
            doc_id = f"doc_{category}_{i+1}"
            # Simulate different relevance distributions for different queries
            if i < 3:
                relevance = 3  # Highly relevant
            elif i < 6:
                relevance = 2  # Relevant
            elif i < 8:
                relevance = 1  # Marginally relevant
            else:
                relevance = 0  # Irrelevant
                
            qrels.add_judgment(query_text, doc_id, relevance, category, f"Sample document {i+1} for {category}")
    
    logger.info(f"Added judgments, total count: {qrels.get_judgment_count()}")
    
    # Simulate results for control run
    control_results = []
    for query_text, category, name in queries:
        # For control run, simulate okay but not great results (good docs mixed with irrelevant)
        results = []
        for i in range(10):
            # For control, put some irrelevant docs at higher positions
            if i % 3 == 0:
                doc_id = f"doc_{category}_{8+i%2}"  # Irrelevant docs
            else:
                doc_id = f"doc_{category}_{i+1}"
            
            results.append({
                "id": doc_id,
                "score": 0.9 - (i * 0.05),
                "vector_score": 0.9 - (i * 0.05),
                "text_score": None,
                "text": f"Sample document {i+1} for {category}",
                "source": "lore"
            })
        
        control_results.append({
            "query": query_text,
            "category": category,
            "name": name,
            "results": results
        })
    
    # Simulate results for experiment run
    experiment_results = []
    for query_text, category, name in queries:
        # For experiment run, simulate better results (more relevant docs at top)
        results = []
        for i in range(10):
            # For experiment, put more relevant docs at top positions
            if i < 6:
                doc_id = f"doc_{category}_{i+1}"  # More relevant docs at top
            else:
                doc_id = f"doc_{category}_{7+i%3}"
            
            results.append({
                "id": doc_id,
                "score": 0.95 - (i * 0.04),
                "vector_score": 0.9 - (i * 0.05),
                "text_score": 0.85 - (i * 0.06),
                "text": f"Sample document {i+1} for {category}",
                "source": "lore"
            })
        
        experiment_results.append({
            "query": query_text,
            "category": category,
            "name": name,
            "results": results
        })
    
    # Save results to database
    db.save_results(control_run_id, control_results)
    db.save_results(experiment_run_id, experiment_results)
    logger.info("Saved results for both runs")
    
    # Calculate and save metrics
    from scripts.ir_metrics import calculate_all_metrics
    
    # Process control results
    for query_data in control_results:
        query_text = query_data["query"]
        query_id = db.get_query_id(query_text)
        judgments = qrels.get_judgments_for_query(query_text)
        
        if judgments:
            metrics = calculate_all_metrics(query_data["results"], judgments)
            db.save_metrics(control_run_id, query_id, metrics)
    
    # Process experiment results
    for query_data in experiment_results:
        query_text = query_data["query"]
        query_id = db.get_query_id(query_text)
        judgments = qrels.get_judgments_for_query(query_text)
        
        if judgments:
            metrics = calculate_all_metrics(query_data["results"], judgments)
            db.save_metrics(experiment_run_id, query_id, metrics)
    
    logger.info("Calculated and saved metrics for both runs")
    
    # Get run metrics
    control_metrics = db.get_run_metrics(control_run_id)
    experiment_metrics = db.get_run_metrics(experiment_run_id)
    
    # Simulate comparison data (in practice this would be generated by compare_runs.py)
    comparison_data = {
        "overall": {
            "p@5": {
                "values": [
                    control_metrics["aggregated"]["overall"]["p@5"],
                    experiment_metrics["aggregated"]["overall"]["p@5"]
                ],
                "changes": [
                    0,
                    experiment_metrics["aggregated"]["overall"]["p@5"] - control_metrics["aggregated"]["overall"]["p@5"]
                ],
                "best_run": "Experiment" if experiment_metrics["aggregated"]["overall"]["p@5"] > control_metrics["aggregated"]["overall"]["p@5"] else "Control"
            },
            "p@10": {
                "values": [
                    control_metrics["aggregated"]["overall"]["p@10"],
                    experiment_metrics["aggregated"]["overall"]["p@10"]
                ],
                "changes": [
                    0,
                    experiment_metrics["aggregated"]["overall"]["p@10"] - control_metrics["aggregated"]["overall"]["p@10"]
                ],
                "best_run": "Experiment" if experiment_metrics["aggregated"]["overall"]["p@10"] > control_metrics["aggregated"]["overall"]["p@10"] else "Control"
            },
            "mrr": {
                "values": [
                    control_metrics["aggregated"]["overall"]["mrr"],
                    experiment_metrics["aggregated"]["overall"]["mrr"]
                ],
                "changes": [
                    0,
                    experiment_metrics["aggregated"]["overall"]["mrr"] - control_metrics["aggregated"]["overall"]["mrr"]
                ],
                "best_run": "Experiment" if experiment_metrics["aggregated"]["overall"]["mrr"] > control_metrics["aggregated"]["overall"]["mrr"] else "Control"
            },
            "bpref": {
                "values": [
                    control_metrics["aggregated"]["overall"]["bpref"],
                    experiment_metrics["aggregated"]["overall"]["bpref"]
                ],
                "changes": [
                    0,
                    experiment_metrics["aggregated"]["overall"]["bpref"] - control_metrics["aggregated"]["overall"]["bpref"]
                ],
                "best_run": "Experiment" if experiment_metrics["aggregated"]["overall"]["bpref"] > control_metrics["aggregated"]["overall"]["bpref"] else "Control"
            }
        }
    }
    
    # Save comparison
    run_ids = [control_run_id, experiment_run_id]
    run_names = ["Control", "Experiment"]
    
    # Determine best run (simplified)
    p5_diff = experiment_metrics["aggregated"]["overall"]["p@5"] - control_metrics["aggregated"]["overall"]["p@5"]
    p10_diff = experiment_metrics["aggregated"]["overall"]["p@10"] - control_metrics["aggregated"]["overall"]["p@10"]
    mrr_diff = experiment_metrics["aggregated"]["overall"]["mrr"] - control_metrics["aggregated"]["overall"]["mrr"]
    
    # Simple scoring - count how many metrics are better in experiment
    better_count = (p5_diff > 0) + (p10_diff > 0) + (mrr_diff > 0)
    best_run_id = experiment_run_id if better_count >= 2 else control_run_id
    
    comparison_id = db.save_comparison(run_ids, run_names, comparison_data, best_run_id)
    logger.info(f"Saved comparison with ID: {comparison_id}")
    
    # Print summary of results
    print("\nSummary of Test Results:")
    print("-" * 70)
    print(f"Control Run (ID: {control_run_id})")
    print(f"  P@5:  {control_metrics['aggregated']['overall']['p@5']:.4f}")
    print(f"  P@10: {control_metrics['aggregated']['overall']['p@10']:.4f}")
    print(f"  MRR:  {control_metrics['aggregated']['overall']['mrr']:.4f}")
    print(f"  BPREF: {control_metrics['aggregated']['overall']['bpref']:.4f}")
    print()
    print(f"Experiment Run (ID: {experiment_run_id})")
    print(f"  P@5:  {experiment_metrics['aggregated']['overall']['p@5']:.4f} ({p5_diff:+.4f})")
    print(f"  P@10: {experiment_metrics['aggregated']['overall']['p@10']:.4f} ({p10_diff:+.4f})")
    print(f"  MRR:  {experiment_metrics['aggregated']['overall']['mrr']:.4f} ({mrr_diff:+.4f})")
    print(f"  BPREF: {experiment_metrics['aggregated']['overall']['bpref']:.4f} ({experiment_metrics['aggregated']['overall']['bpref'] - control_metrics['aggregated']['overall']['bpref']:+.4f})")
    print()
    print(f"Best Overall Run: {'Experiment' if best_run_id == experiment_run_id else 'Control'}")
    print("-" * 70)
    
    # Print category breakdown
    print("\nCategory Breakdown:")
    print("-" * 70)
    for category in control_metrics["aggregated"]["by_category"]:
        print(f"Category: {category}")
        print(f"  Control P@5:    {control_metrics['aggregated']['by_category'][category]['p@5']:.4f}")
        print(f"  Experiment P@5: {experiment_metrics['aggregated']['by_category'][category]['p@5']:.4f} ({experiment_metrics['aggregated']['by_category'][category]['p@5'] - control_metrics['aggregated']['by_category'][category]['p@5']:+.4f})")
        print()
    
    # Close database connection
    db.close()
    logger.info("Database connection closed")
    
    # Cleanup
    os.remove(test_db_path)
    logger.info("Cleanup complete, test database removed")

if __name__ == "__main__":
    main()