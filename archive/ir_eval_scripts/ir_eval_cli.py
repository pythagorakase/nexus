#!/usr/bin/env python3
"""
NEXUS IR Evaluation System - Interactive CLI

This module provides an interactive command-line interface for the NEXUS IR Evaluation System.
It allows users to run queries, judge results, compare runs, and more through a menu-driven interface.
"""

import os
import sys
import logging
import datetime
from typing import Dict, List, Any, Tuple, Optional

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import local modules
try:
    from ir_eval.scripts.query_runner import run_golden_queries
    from ir_eval.scripts.judgments import judge_all_unjudged_results
    from ir_eval.scripts.display import (
        print_comparison_table,
        print_configuration_details,
        print_current_parameters,
        display_query_variations,
        display_query_pairs
    )
    from ir_eval.scripts.utils import (
        load_json,
        save_json,
        extract_memnon_settings,
        create_temp_settings_file,
        get_query_data_by_category,
        extract_query_variations,
        create_variations_file,
        create_variations_file_all_categories
    )
    from ir_eval.scripts.ir_metrics import calculate_all_metrics, average_metrics_by_category
    from ir_eval.scripts.comparison import compare_runs
    from ir_eval.scripts.qrels import QRELSManager
    from ir_eval.db import IRDatabase, DEFAULT_DB_PATH
    from ir_eval.scripts.ir_eval import evaluate_run
except ImportError:
    # Try relative imports if the above fails
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from query_runner import run_golden_queries
    from judgments import judge_all_unjudged_results
    from display import (
        print_comparison_table,
        print_configuration_details,
        print_current_parameters,
        display_query_variations,
        display_query_pairs
    )
    from utils import (
        load_json,
        save_json,
        extract_memnon_settings,
        create_temp_settings_file,
        get_query_data_by_category,
        extract_query_variations,
        create_variations_file,
        create_variations_file_all_categories
    )
    from ir_metrics import calculate_all_metrics, average_metrics_by_category
    from comparison import compare_runs
    from qrels import QRELSManager
    from db import IRDatabase, DEFAULT_DB_PATH
    from ir_eval import evaluate_run

# Constants
DEFAULT_GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden_queries.json")
DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
CONTROL_CONFIG_NAME = "control"
EXPERIMENT_CONFIG_NAME = "experiment"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.ir_eval_cli")

class IREvalCLI:
    """Interactive CLI for NEXUS IR Evaluation System."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the IR Evaluation CLI.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.golden_queries_path = DEFAULT_GOLDEN_QUERIES_PATH
        self.settings_path = DEFAULT_SETTINGS_PATH
        self.db_path = db_path
        
        # Initialize database and QRELS manager
        self.db = IRDatabase(db_path)
        self.qrels = QRELSManager(db_path)
        
        # Track the latest run IDs for each configuration
        self.latest_run_ids = self.db.get_latest_run_ids([CONTROL_CONFIG_NAME, EXPERIMENT_CONFIG_NAME])
        
        # Load settings and queries on startup
        self.reload_settings()
    
    def reload_settings(self):
        """Reload settings and golden queries from their respective files."""
        logger.info(f"Loading golden queries from {self.golden_queries_path}")
        logger.info(f"Loading settings from {self.settings_path}")
        
        # Load golden queries and settings
        self.golden_queries = load_json(self.golden_queries_path)
        self.settings = load_json(self.settings_path)
        
        # Load control and experimental settings
        self.control_settings = extract_memnon_settings(self.settings)
        self.experimental_settings = None
        if "settings" in self.golden_queries:
            if "retrieval" in self.golden_queries["settings"]:
                self.experimental_settings = {
                    "retrieval": self.golden_queries["settings"]["retrieval"]
                }
            if "models" in self.golden_queries["settings"]:
                if not self.experimental_settings:
                    self.experimental_settings = {}
                self.experimental_settings["models"] = self.golden_queries["settings"]["models"]
                
        logger.info("Settings and golden queries loaded successfully")
    
    def show_main_menu(self):
        """Display the main menu and handle user input."""
        while True:
            print("\n" + "="*80)
            print("NEXUS IR Evaluation System")
            print("="*80)
            print("1. Run all golden queries (control vs experiment)")
            print("2. Run query subset")
            print("3. Judge results")
            print("4. Compare results")
            print("5. View configuration details")
            print("6. Display current parameters")
            print("7. Reload settings")
            print("8. Delete runs")
            print("9. Exit")
            
            choice = input("\nEnter choice (1-9): ")
            
            if choice == "1":
                self.run_all_queries()
            elif choice == "2":
                self.run_category_queries()
            elif choice == "3":
                self.judge_results()
            elif choice == "4":
                self.compare_results()
            elif choice == "5":
                self.view_configurations()
            elif choice == "6":
                self.display_current_parameters()
            elif choice == "7":
                self.reload_settings()
                print("Settings and queries reloaded successfully")
            elif choice == "8":
                self.delete_runs()
            elif choice == "9":
                print("Exiting NEXUS IR Evaluation System")
                self.db.close()
                break
            else:
                print("Invalid choice. Please try again.")
    
    def run_all_queries(self):
        """Run all golden queries with both control and experimental settings."""
        print("\n" + "="*80)
        print("Running all golden queries")
        print("="*80)
        
        # Get experiment description
        print("\nEnter a brief description of the experimental condition (e.g., 'adding cross-encoder'):")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = "Unnamed experiment"
        
        # Run with control settings (from settings.json)
        print("\nRunning with CONTROL settings (from settings.json)...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        control_run_name = f"Control {timestamp}"
        
        control_run_id = run_golden_queries(
            self.settings_path,
            self.golden_queries_path,
            CONTROL_CONFIG_NAME,
            control_run_name,
            db=self.db,
            description=f"Control run for: {experiment_description}"
        )
        
        if control_run_id:
            self.latest_run_ids[CONTROL_CONFIG_NAME] = control_run_id
            print(f"Control run saved with ID: {control_run_id}")
        else:
            print("Failed to run control queries")
            return
        
        # Run with experimental settings (from golden_queries.json)
        if self.experimental_settings:
            print("\nRunning with EXPERIMENTAL settings (from golden_queries.json)...")
            
            # Create temporary settings file with experimental settings
            temp_settings_path = create_temp_settings_file(self.settings, self.experimental_settings)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_run_name = f"Experiment {timestamp}"
            
            exp_run_id = run_golden_queries(
                temp_settings_path,
                self.golden_queries_path,
                EXPERIMENT_CONFIG_NAME,
                exp_run_name,
                db=self.db,
                description=f"Experimental run for: {experiment_description}"
            )
            
            # Clean up temporary file
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
            
            if exp_run_id:
                self.latest_run_ids[EXPERIMENT_CONFIG_NAME] = exp_run_id
                print(f"Experimental run saved with ID: {exp_run_id}")
                
                # Link the runs as a pair in the database
                self.db.link_run_pair(control_run_id, exp_run_id, experiment_description)
                print(f"Control run {control_run_id} and Experimental run {exp_run_id} linked as a pair.")
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
    
    def run_category_queries(self):
        """Run queries for a specific category or compare query variations."""
        # Get queries by category
        queries_by_category = get_query_data_by_category(self.golden_queries)
        
        if not queries_by_category:
            print("No categories found in golden_queries.json")
            return
        
        # Display available options
        print("\n" + "="*80)
        print("Query Subset Options")
        print("="*80)
        print("1. Run queries for specific category")
        print("2. Compare query variations")
        print("3. Return to main menu")
        
        # Get user choice for mode
        choice = input("\nSelect option (1-3): ")
        
        if choice == "3":
            return
        elif choice == "2":
            self.run_query_variations()
            return
        elif choice != "1":
            print("Invalid choice. Please try again.")
            return
            
        # Display available categories
        print("\n" + "="*80)
        print("Available query categories")
        print("="*80)
        
        for i, category in enumerate(queries_by_category.keys(), 1):
            print(f"{i}. {category} ({len(queries_by_category[category])} queries)")
        
        print(f"{len(queries_by_category) + 1}. Return to main menu")
        
        # Get user choice
        while True:
            try:
                choice = int(input("\nSelect category (1-{0}): ".format(len(queries_by_category) + 1)))
                if 1 <= choice <= len(queries_by_category) + 1:
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        
        # Return to main menu if last option selected
        if choice == len(queries_by_category) + 1:
            return
        
        # Get selected category and queries
        category = list(queries_by_category.keys())[choice - 1]
        category_queries = queries_by_category[category]
        
        print(f"\nSelected category: {category} ({len(category_queries)} queries)")
        
        # Get experiment description
        print("\nEnter a brief description of the experimental condition (e.g., 'adding cross-encoder'):")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = f"Unnamed experiment - {category} category"
            
        print(f"Running queries for category: {category}")
        
        # Run with control settings (from settings.json)
        print("\nRunning with CONTROL settings (from settings.json)...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        control_run_name = f"Control {category} {timestamp}"
        
        control_run_id = run_golden_queries(
            self.settings_path,
            self.golden_queries_path,
            CONTROL_CONFIG_NAME,
            control_run_name,
            db=self.db,
            category=category,
            description=f"Control run for: {experiment_description} - {category} category"
        )
        
        if control_run_id:
            self.latest_run_ids[CONTROL_CONFIG_NAME] = control_run_id
            print(f"Control run saved with ID: {control_run_id}")
        else:
            print("Failed to run control queries")
            return
        
        # Run with experimental settings (from golden_queries.json)
        if self.experimental_settings:
            print("\nRunning with EXPERIMENTAL settings (from golden_queries.json)...")
            
            # Create temporary settings file with experimental settings
            temp_settings_path = create_temp_settings_file(self.settings, self.experimental_settings)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_run_name = f"Experiment {category} {timestamp}"
            
            exp_run_id = run_golden_queries(
                temp_settings_path,
                self.golden_queries_path,
                EXPERIMENT_CONFIG_NAME,
                exp_run_name,
                db=self.db,
                category=category,
                description=f"Experimental run for: {experiment_description} - {category} category"
            )
            
            # Clean up temporary file
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
            
            if exp_run_id:
                self.latest_run_ids[EXPERIMENT_CONFIG_NAME] = exp_run_id
                print(f"Experimental run saved with ID: {exp_run_id}")
                
                # Link the runs as a pair in the database
                self.db.link_run_pair(control_run_id, exp_run_id, f"{experiment_description} - {category} category")
                print(f"Control run {control_run_id} and Experimental run {exp_run_id} linked as a pair.")
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
            
    def run_query_variations(self):
        """Run query variations using control settings only."""
        # Get queries and their variations
        query_variations = extract_query_variations(self.golden_queries)
        
        if not query_variations:
            print("\nNo query variations found in golden_queries.json.")
            print("To use this feature, add a 'query_variation' field next to 'query' fields.")
            return
            
        # Display available categories with variations
        print("\n" + "="*80)
        print("Available categories with query variations")
        print("="*80)
        
        # Count total variations across all categories
        total_variations = sum(len(variations) for variations in query_variations.values())
        
        print("0. Run ALL query variations across ALL categories")
        
        categories_with_variations = {}
        i = 1
        
        for category, variations in query_variations.items():
            if len(variations) > 0:
                categories_with_variations[i] = category
                print(f"{i}. {category} ({len(variations)} variations)")
                i += 1
        
        if not categories_with_variations:
            print("No categories with query variations found.")
            return
            
        print(f"{len(categories_with_variations) + 1}. Return to main menu")
        
        # Get user choice
        while True:
            try:
                choice = int(input(f"\nSelect option (0-{len(categories_with_variations) + 1}): "))
                if 0 <= choice <= len(categories_with_variations) + 1:
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        
        # Return to main menu if last option selected
        if choice == len(categories_with_variations) + 1:
            return
            
        # Run all variations across all categories
        if choice == 0:
            # Flatten all variations into a single list
            all_variations = []
            for category, variations in query_variations.items():
                for var in variations:
                    var["category"] = category  # Ensure category is set
                    all_variations.append(var)
                    
            print(f"\nPreparing to run ALL query variations ({total_variations} total)...")
            
            # Get experiment description
            print("\nEnter a brief description for this query variation comparison:")
            experiment_description = input("> ").strip()
            if not experiment_description:
                experiment_description = f"All query variations comparison"
            
            # Create temp golden queries file with all variations as regular queries
            variations_file = create_variations_file_all_categories(self.golden_queries, all_variations)
            
            print(f"\nRunning {total_variations} query variations with control settings...")
            
            # Run with control settings only
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = f"All Query Variations {timestamp}"
            
            run_id = run_golden_queries(
                self.settings_path,
                variations_file,
                "query_variations",
                run_name,
                db=self.db,
                description=f"Query variation comparison: {experiment_description} - ALL categories"
            )
            
            # Clean up temporary file
            if os.path.exists(variations_file):
                os.remove(variations_file)
            
            if run_id:
                print(f"\nQuery variations run completed and saved with ID: {run_id}")
                print("Use 'Compare results' to view metrics for this run.")
            else:
                print("Failed to run query variations.")
            
            return
        
        # Get selected category and variations
        category = categories_with_variations[choice]
        variations = query_variations[category]
        
        print(f"\nSelected category: {category} ({len(variations)} variations)")
        
        # Get experiment description
        print("\nEnter a brief description for this query variation comparison:")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = f"Query variation comparison - {category} category"
        
        # Create temp golden queries file with variations as regular queries
        variations_file = create_variations_file(self.golden_queries, category, variations)
        
        print(f"\nRunning {len(variations)} query variations with control settings...")
        
        # Run with control settings only
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"Query Variations {category} {timestamp}"
        
        run_id = run_golden_queries(
            self.settings_path,
            variations_file,
            "query_variations",
            run_name,
            db=self.db,
            category=category,
            description=f"Query variation comparison: {experiment_description} - {category} category"
        )
        
        # Clean up temporary file
        if os.path.exists(variations_file):
            os.remove(variations_file)
        
        if run_id:
            print(f"\nQuery variations run completed and saved with ID: {run_id}")
            print("Use 'Compare results' to view metrics for this run.")
        else:
            print("Failed to run query variations.")
    
    def judge_results(self):
        """Judge results interactively using a unified review pipeline."""
        # Get all runs with unjudged results
        runs = self.db.get_runs_with_unjudged_results(self.qrels)
        
        if not runs:
            print("\nNo unjudged results found in any runs.")
            return
        
        print("\n" + "="*80)
        print("Unified Review Pipeline")
        print("="*80)
        print("Starting interactive judgment process for all unjudged results.")
        print("Press 'Q' to exit at any time.")
        
        # Create a list of run IDs
        run_ids = [run['id'] for run in runs]
        
        # Judge all unjudged results across all runs
        judgments_added = judge_all_unjudged_results(
            run_ids,
            self.qrels,
            self.golden_queries,
            self.db
        )
        
        print(f"\nAdded {judgments_added} new judgments")
    
    def compare_results(self):
        """Compare results from different experimental runs."""
        # Get paired runs
        pairs = self.db.get_run_pairs()
        
        # Get all runs for manual comparison
        all_runs = self.db.get_runs(limit=20)  # Get up to 20 most recent runs
        
        # Check if we have any query variation runs
        query_variation_runs = []
        for run in all_runs:
            if run.get('config_type') == 'query_variations':
                query_variation_runs.append(run)
        
        if not pairs and not query_variation_runs:
            print("\nNo experiment pairs or query variation runs found. Please run queries with control/experiment settings first.")
            return
        
        # Display options menu
        print("\n" + "="*80)
        print("Available Comparisons")
        print("="*80)
        print("1. Compare control vs experiment runs")
        print("2. Compare query variations")
        print("3. Return to main menu")
        
        choice = input("\nSelect comparison type (1-3): ")
        
        if choice == "3":
            return
        elif choice == "2":
            self._compare_query_variations(query_variation_runs)
            return
        elif choice != "1":
            print("Invalid choice. Please try again.")
            return
            
        # Continue with control vs experiment comparison
        if not pairs:
            print("\nNo experiment pairs found. Please run queries with control/experiment settings first.")
            return
            
        # Display pairs
        print("\n" + "="*80)
        print("Available experimental runs")
        print("="*80)
        
        for i, pair in enumerate(pairs, 1):
            description = pair.get("description", "No description")
            control_name = pair.get("control_name", f"Control {pair['control_run_id']}")
            experiment_name = pair.get("experiment_name", f"Experiment {pair['experiment_run_id']}")
            timestamp = pair.get("timestamp", "unknown")
            print(f"{i}. {description}")
            print(f"   Control: {control_name} (ID: {pair['control_run_id']})")
            print(f"   Experiment: {experiment_name} (ID: {pair['experiment_run_id']})")
            print(f"   Time: {timestamp}")
            print()
            
        print(f"{len(pairs) + 1}. Return to main menu")
            
        # Get user choice
        try:
            pair_choice = int(input(f"\nSelect experiment to view metrics (1-{len(pairs) + 1}): "))
            if pair_choice == len(pairs) + 1:
                return
                
            if 1 <= pair_choice <= len(pairs):
                pair = pairs[pair_choice - 1]
                run_ids = [pair['control_run_id'], pair['experiment_run_id']]
                run_names = [pair.get("control_name", "Control"), pair.get("experiment_name", "Experiment")]
            else:
                print("Invalid choice. Please try again.")
                return
        except ValueError:
            print("Invalid input. Please enter a number.")
            return
        
        # Evaluate each run
        for run_id in run_ids:
            evaluate_run(run_id, self.qrels, self.db)
        
        # Generate comparison
        comparison = compare_runs(run_ids, run_names, self.db)
        
        # Print comparison table
        print_comparison_table(comparison)
        
        print(f"\nComparison saved to database with ID: {comparison.get('id')}")
        
    def _compare_query_variations(self, query_variation_runs):
        """Compare results from query variation runs."""
        if not query_variation_runs:
            print("\nNo query variation runs found.")
            return
            
        # Use the display module function
        selected, run_id = display_query_variations(query_variation_runs, self.qrels, self.db)
        
        if selected:
            print("\nPress Enter to continue...")
            input()
    
    def view_configurations(self):
        """View details of control and experimental configurations."""
        print_configuration_details(self.control_settings, self.experimental_settings)
        input("\nPress Enter to continue...")
    
    def display_current_parameters(self):
        """Display current parameter values in a copy-paste friendly format."""
        print_current_parameters(self.settings_path, self.golden_queries_path)
        input("\nPress Enter to continue...")
    
    def delete_runs(self):
        """Delete runs from the database."""
        # Get runs from database
        runs = self.db.get_runs(limit=20)  # Show up to 20 most recent runs
        
        if not runs:
            print("No runs found in database")
            return
        
        # Display available runs
        print("\n" + "="*80)
        print("Delete Runs")
        print("="*80)
        
        print("\nAvailable runs:")
        print(f"{'ID':<5} {'Name':<30} {'Type':<15} {'Timestamp':<25}")
        print("-"*80)
        
        for run in runs:
            run_id = run.get('id', 'N/A')
            run_name = run.get('name', 'Unknown')[:28]
            config_type = run.get('config_type', 'Unknown')[:13]
            timestamp = run.get('timestamp', 'Unknown')[:23]
            
            print(f"{run_id:<5} {run_name:<30} {config_type:<15} {timestamp:<25}")
        
        print("\nOptions:")
        print("  - Enter specific run ID(s) to delete (comma-separated)")
        print("  - Enter 'A' to delete all runs")
        print("  - Enter 'C' to cancel")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice.upper() == 'C':
            print("Deletion cancelled")
            return
            
        if choice.upper() == 'A':
            # Confirm deletion of all runs
            confirm = input("Are you sure you want to delete ALL runs? This cannot be undone. (y/n): ")
            if confirm.lower() != 'y':
                print("Deletion cancelled")
                return
                
            # Delete all runs
            deleted = self._delete_all_runs()
            if deleted:
                print("All runs deleted successfully")
            else:
                print("Failed to delete runs")
            return
            
        # Process specific run IDs
        try:
            run_ids = [int(id.strip()) for id in choice.split(',')]
            if not run_ids:
                print("No valid run IDs provided")
                return
                
            # Confirm deletion
            id_list = ', '.join(str(id) for id in run_ids)
            confirm = input(f"Are you sure you want to delete run(s) {id_list}? This cannot be undone. (y/n): ")
            if confirm.lower() != 'y':
                print("Deletion cancelled")
                return
                
            # Delete specific runs
            deleted = self._delete_specific_runs(run_ids)
            if deleted:
                print(f"Run(s) {id_list} deleted successfully")
            else:
                print("Failed to delete runs")
                
        except ValueError:
            print("Invalid input. Please enter comma-separated run IDs or 'A' for all runs")
    
    def _delete_all_runs(self):
        """Delete all runs from the database."""
        try:
            conn = self.db.conn
            cursor = conn.cursor()
            
            # Start a transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Delete records from all related tables
            cursor.execute("DELETE FROM comparisons")
            cursor.execute("DELETE FROM metrics")
            cursor.execute("DELETE FROM results")
            cursor.execute("DELETE FROM runs")
            
            # Commit the transaction
            conn.commit()
            
            # Update latest run IDs
            self.latest_run_ids = {k: None for k in self.latest_run_ids.keys()}
            
            return True
        except Exception as e:
            print(f"Error deleting runs: {e}")
            conn.rollback()
            return False
    
    def _delete_specific_runs(self, run_ids):
        """Delete specific runs from the database."""
        try:
            conn = self.db.conn
            cursor = conn.cursor()
            
            # Start a transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Format IDs for SQL
            ids_str = ','.join('?' for _ in run_ids)
            
            # Delete from comparisons
            cursor.execute(f"DELETE FROM comparisons WHERE best_run_id IN ({ids_str})", run_ids)
            
            # Delete from metrics
            cursor.execute(f"DELETE FROM metrics WHERE run_id IN ({ids_str})", run_ids)
            
            # Delete from results
            cursor.execute(f"DELETE FROM results WHERE run_id IN ({ids_str})", run_ids)
            
            # Delete from runs
            cursor.execute(f"DELETE FROM runs WHERE id IN ({ids_str})", run_ids)
            
            # Commit the transaction
            conn.commit()
            
            # Update latest run IDs if any were deleted
            for config_type, run_id in self.latest_run_ids.items():
                if run_id in run_ids:
                    self.latest_run_ids[config_type] = None
            
            return True
        except Exception as e:
            print(f"Error deleting runs: {e}")
            conn.rollback()
            return False

def main():
    """Main entry point for command-line usage."""
    cli = IREvalCLI()
    cli.show_main_menu()

if __name__ == "__main__":
    main()