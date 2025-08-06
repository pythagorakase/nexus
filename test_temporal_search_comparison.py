#!/usr/bin/env python3
"""
Test script to compare categorical and continuous temporal search approaches.

This script runs A/B tests with both temporal search implementations to see if the
continuous approach provides better results.
"""

import os
import sys
import json
import logging
import tempfile
import subprocess
from typing import Dict, List, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("temporal_comparison")

# Import IR eval tools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_eval"))
from ir_eval import IREvalPGCLI

# Global settings path
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json file."""
    try:
        with open(SETTINGS_PATH, "r") as f:
            settings = json.load(f)
            logger.info(f"Loaded settings from {SETTINGS_PATH}")
            return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}

def create_settings_with_temporal_approach(approach: str, boost_factor: float) -> str:
    """
    Create a temporary settings file with the specified temporal approach.
    
    Args:
        approach: 'categorical' or 'continuous'
        boost_factor: Value for temporal_boost_factor (0.0-1.0)
        
    Returns:
        Path to the temporary settings file
    """
    # Load base settings
    settings = load_settings()
    
    # Update hybrid search configuration
    if "Agent Settings" in settings and "MEMNON" in settings["Agent Settings"]:
        if "retrieval" in settings["Agent Settings"]["MEMNON"]:
            if "hybrid_search" in settings["Agent Settings"]["MEMNON"]["retrieval"]:
                # Set temporal boost factor
                settings["Agent Settings"]["MEMNON"]["retrieval"]["hybrid_search"]["temporal_boost_factor"] = boost_factor
                
                # Add a flag for which approach to use (actual module import handled in code)
                settings["Agent Settings"]["MEMNON"]["retrieval"]["hybrid_search"]["temporal_approach"] = approach
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings, f, indent=2)
    
    logger.info(f"Created temporary settings file at {temp_path} with {approach} approach and boost factor {boost_factor}")
    return temp_path

def run_ir_eval_with_settings(settings_path: str, run_name: str, config_type: str) -> int:
    """
    Run the IR evaluation system with the specified settings.
    
    Args:
        settings_path: Path to the settings file
        run_name: Name for this run
        config_type: 'control' or 'experiment'
        
    Returns:
        Run ID from the IR evaluation system
    """
    # Set environment variable for settings
    os.environ["NEXUS_SETTINGS_PATH"] = settings_path
    
    # Import the golden queries module with fresh settings
    import importlib
    
    # Force reload the ir_eval.scripts.golden_queries_module
    if 'ir_eval.scripts.golden_queries_module' in sys.modules:
        importlib.reload(sys.modules['ir_eval.scripts.golden_queries_module'])
    
    # Initialize IR evaluation system
    ir_eval = IREvalPGCLI()
    
    # Run queries with these settings
    run_id = ir_eval.run_all_queries(
        settings_path=settings_path,
        golden_queries_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_eval", "golden_queries.json"),
        config_type=config_type,
        run_name=run_name,
        db=ir_eval.db,
        description=f"{run_name} - {config_type}"
    )
    
    logger.info(f"Completed run {run_name} with ID {run_id}")
    return run_id

def run_comparison_experiment(control_approach: str, experiment_approach: str, boost_factor: float) -> Dict[str, Any]:
    """
    Run an A/B test comparing two temporal search approaches.
    
    Args:
        control_approach: 'categorical' or 'continuous' for control group
        experiment_approach: 'categorical' or 'continuous' for experiment group
        boost_factor: Temporal boost factor to use for both
        
    Returns:
        Dictionary with experiment results
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create temporary settings files
    control_settings_path = create_settings_with_temporal_approach(control_approach, boost_factor)
    experiment_settings_path = create_settings_with_temporal_approach(experiment_approach, boost_factor)
    
    try:
        # Run control configuration
        control_run_name = f"{control_approach}_f{boost_factor}_{timestamp}"
        control_run_id = run_ir_eval_with_settings(
            settings_path=control_settings_path,
            run_name=control_run_name,
            config_type="control"
        )
        
        # Run experimental configuration
        experiment_run_name = f"{experiment_approach}_f{boost_factor}_{timestamp}"
        experiment_run_id = run_ir_eval_with_settings(
            settings_path=experiment_settings_path,
            run_name=experiment_run_name,
            config_type="experiment"
        )
        
        # Compare results
        ir_eval = IREvalPGCLI()
        
        # Judge any unjudged results
        ir_eval.judge_results()
        
        # Evaluate both runs
        for run_id in [control_run_id, experiment_run_id]:
            ir_eval.evaluate_run(run_id, ir_eval.qrels, ir_eval.db)
        
        # Generate comparison
        comparison = ir_eval.compare_runs(
            run_ids=[control_run_id, experiment_run_id],
            run_names=[control_run_name, experiment_run_name],
            db=ir_eval.db
        )
        
        # Return results
        return {
            "control_run_id": control_run_id,
            "experiment_run_id": experiment_run_id,
            "comparison": comparison
        }
    
    finally:
        # Clean up temporary files
        for path in [control_settings_path, experiment_settings_path]:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Removed temporary settings file: {path}")

def main():
    """Main function to run the comparison experiment."""
    print("NEXUS Temporal Search Approach Comparison")
    print("=========================================")
    
    # Run experiment with categorical vs continuous approaches
    print("\nRunning A/B test: Categorical vs Continuous Temporal Search")
    
    # Use a moderate boost factor that will show differences
    boost_factor = 0.5
    
    results = run_comparison_experiment(
        control_approach="categorical",
        experiment_approach="continuous",
        boost_factor=boost_factor
    )
    
    # Display experiment results
    print("\nExperiment completed:")
    print(f"Control: Categorical approach (Run ID: {results['control_run_id']})")
    print(f"Experiment: Continuous approach (Run ID: {results['experiment_run_id']})")
    
    # Get best run
    best_run = results['comparison']['best_run']['name']
    print(f"\nBest performer: {best_run}")
    
    # Display metrics summary
    print("\nOverall metrics comparison:")
    for metric in ["p@5", "p@10", "mrr", "bpref"]:
        metric_data = results['comparison']['comparison']['overall'][metric]
        control_value = metric_data['values'][0]
        experiment_value = metric_data['values'][1]
        change = experiment_value - control_value
        change_percent = (change / control_value) * 100 if control_value else float('inf')
        
        print(f"{metric}: {control_value:.4f} vs {experiment_value:.4f} ({change:+.4f}, {change_percent:+.2f}%)")
    
    # Show results by category
    print("\nResults by category:")
    for category, metrics in results['comparison']['comparison']['by_category'].items():
        print(f"- {category.capitalize()}:")
        for metric in ["p@5", "p@10", "mrr"]:
            metric_data = metrics[metric]
            control_value = metric_data['values'][0]
            experiment_value = metric_data['values'][1]
            change = experiment_value - control_value
            change_percent = (change / control_value) * 100 if control_value else float('inf')
            
            print(f"  {metric}: {control_value:.4f} vs {experiment_value:.4f} ({change:+.4f}, {change_percent:+.2f}%)")

if __name__ == "__main__":
    main()