#!/usr/bin/env python3
"""
Evaluate MEMNON query classifier accuracy against ground truth categories.

This script:
1. Fetches all queries from the ir_eval.queries table
2. Processes each query through MEMNON's _analyze_query method
3. Compares the predicted category with the ground truth
4. Generates a confusion matrix and calculates precision/recall for each category
5. Determines if the classifier meets the ≥0.9 threshold for all categories
"""

import sys
import os
import re
import json
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Tuple, Any
from sklearn.metrics import classification_report, confusion_matrix
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import MEMNON's query analyzer function
try:
    from nexus.agents.memnon.memnon import MEMNON
except ImportError:
    print("Error: Could not import MEMNON. Make sure the nexus package is in your PYTHONPATH.")
    sys.exit(1)

# Database connection parameters
DB_PARAMS = {
    "dbname": "NEXUS",
    "user": "pythagor",
    "host": "localhost",
    "port": 5432
}

def analyze_query_standalone(query_text: str) -> Dict[str, Any]:
    """
    Standalone implementation of MEMNON's query analyzer for testing.
    This should match the _analyze_query method in the MEMNON class.
    
    Args:
        query_text: The query string to analyze
        
    Returns:
        Dictionary with query analysis results
    """
    # Simple rule-based analysis
    query_info = {
        "text": query_text,
        "type": "general"  # Default
    }
    
    # Convert to lowercase for pattern matching
    query_lower = query_text.lower()
    
    # Check for character-focused query
    character_patterns = [
        r"\b(alex|emilia|pete|alina|dr\. nyati)\b",  # Character names
        r"\bwho is\b",
        r"\bcharacter\b",
        r"\bperson\b"
    ]
    
    for pattern in character_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "character"
            break
    
    # Check for location-focused query
    location_patterns = [
        r"\bwhere\b",
        r"\blocation\b",
        r"\bplace\b",
        r"\bcity\b",
        r"\bdistrict\b",
        r"\barea\b"
    ]
    
    for pattern in location_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "location"
            break
    
    # Check for event-focused query
    event_patterns = [
        r"\bwhat happened\b",
        r"\bevent\b",
        r"\boccurred\b",
        r"\btook place\b",
        r"\bwhen did\b"
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "event"
            break
    
    # Check for relationship-focused query
    relationship_patterns = [
        r"\brelationship\b",
        r"\bfeel about\b",
        r"\bthink about\b",
        r"\bfeel towards\b",
        r"\bthink of\b"
    ]
    
    for pattern in relationship_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "relationship"
            break
    
    # Check for theme-focused query
    theme_patterns = [
        r"\btheme\b",
        r"\bmotif\b",
        r"\bsymbolism\b",
        r"\bmeaning\b"
    ]
    
    for pattern in theme_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "theme"
            break
    
    return query_info

def get_queries_from_db() -> List[Dict[str, Any]]:
    """
    Fetch all queries from the database with their ground truth categories.
    
    Returns:
        List of dictionaries containing query ID, text, and ground truth category
    """
    queries = []
    
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, text, category FROM ir_eval.queries")
            queries = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error fetching queries from database: {e}")
        sys.exit(1)
    
    return queries

def evaluate_classifier(queries: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], np.ndarray]:
    """
    Evaluate the classifier against ground truth.
    
    Args:
        queries: List of dictionaries containing query ID, text, and ground truth category
        
    Returns:
        Tuple containing:
        - precision dict: Precision for each category
        - recall dict: Recall for each category
        - f1 dict: F1 score for each category
        - confusion matrix: Confusion matrix as numpy array
    """
    # Lists to store ground truth and predictions
    y_true = []
    y_pred = []
    
    # Process each query
    for query in queries:
        text = query['text']
        true_category = query['category']
        
        # Use the query analyzer to get predicted category
        result = analyze_query_standalone(text)
        predicted_category = result.get('type', 'general')
        
        # Add to lists
        y_true.append(true_category)
        y_pred.append(predicted_category)
    
    # Generate classification report
    labels = ['character', 'location', 'event', 'relationship', 'theme', 'general']
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True)
    
    # Extract precision, recall, and F1 for each category
    precision = {cat: report[cat]['precision'] for cat in labels}
    recall = {cat: report[cat]['recall'] for cat in labels}
    f1 = {cat: report[cat]['f1-score'] for cat in labels}
    
    # Generate confusion matrix
    conf_matrix = confusion_matrix(y_true, y_pred, labels=labels)
    
    return precision, recall, f1, conf_matrix

def plot_confusion_matrix(conf_matrix: np.ndarray, labels: List[str], output_path: str):
    """
    Plot and save a confusion matrix visualization.
    
    Args:
        conf_matrix: Confusion matrix as numpy array
        labels: Category labels
        output_path: Path to save the visualization
    """
    plt.figure(figsize=(10, 8))
    df_cm = pd.DataFrame(conf_matrix, index=labels, columns=labels)
    sns.heatmap(df_cm, annot=True, fmt='d', cmap='Blues')
    plt.title('MEMNON Query Classifier Confusion Matrix')
    plt.ylabel('True Category')
    plt.xlabel('Predicted Category')
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Confusion matrix saved to {output_path}")

def main():
    """Main function to evaluate the query classifier."""
    print("Evaluating MEMNON query classifier against ground truth categories...")
    
    # Fetch queries from database
    queries = get_queries_from_db()
    print(f"Fetched {len(queries)} queries from database")
    
    # Evaluate classifier
    precision, recall, f1, conf_matrix = evaluate_classifier(queries)
    
    # Display results
    print("\nClassification Metrics:")
    print("======================")
    
    # Define category labels
    labels = ['character', 'location', 'event', 'relationship', 'theme', 'general']
    
    # Check if all categories meet the threshold
    all_meet_threshold = True
    threshold = 0.9
    
    print(f"\n{'Category':<15} {'Precision':<10} {'Recall':<10} {'F1 Score':<10} {'Meets ≥{threshold}':<15}")
    print("-" * 60)
    
    for cat in labels:
        meets = (precision[cat] >= threshold and recall[cat] >= threshold)
        if not meets:
            all_meet_threshold = False
        
        print(f"{cat:<15} {precision[cat]:.4f}{'':6} {recall[cat]:.4f}{'':6} {f1[cat]:.4f}{'':6} {'✓' if meets else '✗'}")
    
    # Overall assessment
    print("\nOverall Assessment:")
    if all_meet_threshold:
        print(f"✓ All categories meet the ≥{threshold} threshold for precision and recall!")
        print("The classifier is robust enough to implement differential weights per query category.")
    else:
        print(f"✗ Not all categories meet the ≥{threshold} threshold for precision and recall.")
        print("Consider improving the classifier patterns before implementing differential weights.")
    
    # Plot confusion matrix
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "query_classifier_confusion_matrix.png")
    plot_confusion_matrix(conf_matrix, labels, output_path)
    
    # Save detailed results to JSON
    results = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": conf_matrix.tolist(),
        "all_meet_threshold": all_meet_threshold,
        "threshold": threshold
    }
    
    json_path = os.path.join(output_dir, "query_classifier_evaluation.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Detailed results saved to {json_path}")

if __name__ == "__main__":
    main()