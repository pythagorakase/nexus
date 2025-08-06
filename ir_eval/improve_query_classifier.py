#!/usr/bin/env python3
"""
Improved version of MEMNON query classifier based on evaluation results.

This script improves the patterns used in MEMNON's query classifier
based on the confusion matrix analysis, aiming to achieve better
precision and recall for all query categories.
"""

import re
import sys
import os
import json
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Any, Tuple
from sklearn.metrics import classification_report, confusion_matrix
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Database connection parameters
DB_PARAMS = {
    "dbname": "NEXUS",
    "user": "pythagor",
    "host": "localhost",
    "port": 5432
}

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

def analyze_query_original(query_text: str) -> Dict[str, Any]:
    """
    Original implementation of MEMNON's query analyzer.
    
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

def analyze_query_improved(query_text: str) -> Dict[str, Any]:
    """
    Improved implementation of MEMNON's query analyzer with better patterns.
    
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
    
    # Check for character-focused query (highest priority to match confusion matrix)
    character_patterns = [
        r"\b(alex|emilia|pete|alina|dr\. nyati|stacey|amanda|liz|michael|david|james|sarah)\b",  # Extended character names
        r"\bwho (is|was|are|were)\b",
        r"\bcharacter['s]?\b",
        r"\bperson['s]?\b",
        r"\b(his|her|their) (personality|background|history|appearance)\b",
        r"\bdescribe [a-z]+ (personality|appearance)\b",
        r"\bwhat (is|was) [a-z]+ like\b",
        r"\babout [a-z]+'s (personality|background|history|appearance)\b",
        r"\b(gender|age|name|alias|occupation|job)\b"
    ]
    
    for pattern in character_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "character"
            return query_info  # Early return since character has highest priority
    
    # Check for relationship-focused query
    relationship_patterns = [
        r"\brelationship\b",
        r"\bfeel[s]? about\b",
        r"\bthink[s]? about\b",
        r"\bfeel[s]? towards\b",
        r"\bthink[s]? of\b",
        r"\b(how|what) does [a-z]+ (feel|think) about\b",
        r"\b(like|hate|love|trust|distrust|respect)\b [a-z]+\b",
        r"\b(friend|enemy|ally|lover|partner|colleague|mentor|rival)\b",
        r"\b(connection|interaction|dynamic) (with|between)\b",
        r"\b(dating|married|involved with|working with)\b"
    ]
    
    for pattern in relationship_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "relationship"
            return query_info  # Early return for next priority
    
    # Check for event-focused query
    event_patterns = [
        r"\bwhat happened\b",
        r"\bevent[s]?\b",
        r"\boccurred\b",
        r"\btook place\b",
        r"\bwhen (did|was|were)\b",
        r"\b(timeline|chronology|sequence) of\b",
        r"\b(before|after|during) [a-z]+\b",
        r"\bincident[s]?\b",
        r"\baction[s]?\b",
        r"\b(mission|operation|meeting|fight|battle|conflict|confrontation)\b",
        r"\b(how|why|when) did [a-z]+ (happen|start|end|occur)\b",
        r"\bvisit(ed)? [a-z]+\b"
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "event"
            return query_info
    
    # Check for location-focused query
    location_patterns = [
        r"\bwhere\b",
        r"\blocation['s]?\b",
        r"\bplace['s]?\b",
        r"\b(city|district|area|region|zone|neighborhood)['s]?\b",
        r"\b(building|facility|complex|headquarters|center|base)['s]?\b",
        r"\bwhat is [a-z]+ (like|layout|description)\b",
        r"\b(bar|club|restaurant|office|laboratory|lab|bridge)['s]?\b",
        r"\bdescribe [a-z]+ (layout|appearance|design)\b",
        r"\b(what|where) is\b [a-z]+ (located|situated)"
    ]
    
    for pattern in location_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "location"
            return query_info
    
    # Check for theme-focused query
    theme_patterns = [
        r"\btheme[s]?\b",
        r"\bmotif[s]?\b",
        r"\bsymbolism\b",
        r"\bmeaning\b",
        r"\bconcept[s]?\b",
        r"\bsignificance\b",
        r"\bimportance\b",
        r"\bpurpose\b",
        r"\bgoal[s]?\b",
        r"\bmission\b",
        r"\bphilosophy\b",
        r"\bideology\b",
        r"\b(what is the|what's the) (point|purpose|goal|meaning)\b",
        r"\b(why does|why is|why was) [a-z]+ (important|significant|created|developed)"
    ]
    
    for pattern in theme_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "theme"
            return query_info
    
    # If no patterns matched, it remains "general"
    return query_info

def evaluate_classifier(queries: List[Dict[str, Any]], analyzer_func) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], np.ndarray]:
    """
    Evaluate the classifier against ground truth.
    
    Args:
        queries: List of dictionaries containing query ID, text, and ground truth category
        analyzer_func: Function to use for query analysis
        
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
        result = analyzer_func(text)
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

def plot_confusion_matrices(original_matrix: np.ndarray, improved_matrix: np.ndarray, labels: List[str], output_path: str):
    """
    Plot and save original and improved confusion matrices side by side.
    
    Args:
        original_matrix: Original confusion matrix as numpy array
        improved_matrix: Improved confusion matrix as numpy array
        labels: Category labels
        output_path: Path to save the visualization
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))
    
    # Plot original matrix
    df_cm1 = pd.DataFrame(original_matrix, index=labels, columns=labels)
    sns.heatmap(df_cm1, annot=True, fmt='d', cmap='Blues', ax=ax1)
    ax1.set_title('Original Query Classifier')
    ax1.set_ylabel('True Category')
    ax1.set_xlabel('Predicted Category')
    
    # Plot improved matrix
    df_cm2 = pd.DataFrame(improved_matrix, index=labels, columns=labels)
    sns.heatmap(df_cm2, annot=True, fmt='d', cmap='Blues', ax=ax2)
    ax2.set_title('Improved Query Classifier')
    ax2.set_ylabel('True Category')
    ax2.set_xlabel('Predicted Category')
    
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Comparison matrix saved to {output_path}")

def main():
    """Main function to compare original and improved classifiers."""
    print("Comparing original and improved MEMNON query classifiers...")
    
    # Fetch queries from database
    queries = get_queries_from_db()
    print(f"Fetched {len(queries)} queries from database")
    
    # Evaluate original classifier
    original_precision, original_recall, original_f1, original_matrix = evaluate_classifier(
        queries, analyze_query_original
    )
    
    # Evaluate improved classifier
    improved_precision, improved_recall, improved_f1, improved_matrix = evaluate_classifier(
        queries, analyze_query_improved
    )
    
    # Define category labels
    labels = ['character', 'location', 'event', 'relationship', 'theme', 'general']
    
    # Display comparison results
    print("\nClassification Metrics Comparison:")
    print("=================================")
    
    threshold = 0.9
    original_meets = {cat: (original_precision[cat] >= threshold and original_recall[cat] >= threshold) for cat in labels}
    improved_meets = {cat: (improved_precision[cat] >= threshold and improved_recall[cat] >= threshold) for cat in labels}
    
    print(f"\n{'Category':<15} {'Original F1':<12} {'Improved F1':<12} {'Change':<10}")
    print("-" * 49)
    
    for cat in labels:
        change = improved_f1[cat] - original_f1[cat]
        change_str = f"{change:+.4f}"
        print(f"{cat:<15} {original_f1[cat]:.4f}{'':6} {improved_f1[cat]:.4f}{'':6} {change_str}")
    
    # Detailed metrics
    print("\nDetailed Metrics by Category:")
    print("============================")
    
    for cat in labels:
        print(f"\n{cat.upper()}:")
        print(f"  Precision: {original_precision[cat]:.4f} -> {improved_precision[cat]:.4f} ({improved_precision[cat] - original_precision[cat]:+.4f})")
        print(f"  Recall:    {original_recall[cat]:.4f} -> {improved_recall[cat]:.4f} ({improved_recall[cat] - original_recall[cat]:+.4f})")
        print(f"  F1 Score:  {original_f1[cat]:.4f} -> {improved_f1[cat]:.4f} ({improved_f1[cat] - original_f1[cat]:+.4f})")
        print(f"  Meets ≥{threshold}: {'✓' if original_meets[cat] else '✗'} -> {'✓' if improved_meets[cat] else '✗'}")
    
    # Overall assessment
    all_original_meet = all(original_meets.values())
    all_improved_meet = all(improved_meets.values())
    
    print("\nOverall Assessment:")
    print(f"  Original classifier: {'✓' if all_original_meet else '✗'} {sum(original_meets.values())}/{len(labels)} categories meet threshold")
    print(f"  Improved classifier: {'✓' if all_improved_meet else '✗'} {sum(improved_meets.values())}/{len(labels)} categories meet threshold")
    
    # Plot confusion matrices
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "query_classifier_comparison.png")
    plot_confusion_matrices(original_matrix, improved_matrix, labels, output_path)
    
    # Save detailed results to JSON
    results = {
        "original": {
            "precision": original_precision,
            "recall": original_recall,
            "f1": original_f1,
            "confusion_matrix": original_matrix.tolist(),
            "meets_threshold": original_meets
        },
        "improved": {
            "precision": improved_precision,
            "recall": improved_recall,
            "f1": improved_f1,
            "confusion_matrix": improved_matrix.tolist(),
            "meets_threshold": improved_meets
        },
        "threshold": threshold,
        "improvement": {
            cat: {
                "precision": improved_precision[cat] - original_precision[cat],
                "recall": improved_recall[cat] - original_recall[cat],
                "f1": improved_f1[cat] - original_f1[cat]
            } for cat in labels
        }
    }
    
    json_path = os.path.join(output_dir, "query_classifier_improvement.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Detailed comparison results saved to {json_path}")
    
    # Generate code for implementation
    code_path = os.path.join(output_dir, "improved_analyzer_implementation.py")
    with open(code_path, 'w') as f:
        f.write('''
def _analyze_query(self, query_text: str) -> Dict[str, Any]:
    """
    Analyze the query to determine type and characteristics.
    Improved version with better pattern matching based on evaluation results.
    
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
    
    # Check for character-focused query (highest priority to match confusion matrix)
    character_patterns = [
        r"\\b(alex|emilia|pete|alina|dr\\. nyati|stacey|amanda|liz|michael|david|james|sarah)\\b",  # Extended character names
        r"\\bwho (is|was|are|were)\\b",
        r"\\bcharacter['s]?\\b",
        r"\\bperson['s]?\\b",
        r"\\b(his|her|their) (personality|background|history|appearance)\\b",
        r"\\bdescribe [a-z]+ (personality|appearance)\\b",
        r"\\bwhat (is|was) [a-z]+ like\\b",
        r"\\babout [a-z]+'s (personality|background|history|appearance)\\b",
        r"\\b(gender|age|name|alias|occupation|job)\\b"
    ]
    
    for pattern in character_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "character"
            return query_info  # Early return since character has highest priority
    
    # Check for relationship-focused query
    relationship_patterns = [
        r"\\brelationship\\b",
        r"\\bfeel[s]? about\\b",
        r"\\bthink[s]? about\\b",
        r"\\bfeel[s]? towards\\b",
        r"\\bthink[s]? of\\b",
        r"\\b(how|what) does [a-z]+ (feel|think) about\\b",
        r"\\b(like|hate|love|trust|distrust|respect)\\b [a-z]+\\b",
        r"\\b(friend|enemy|ally|lover|partner|colleague|mentor|rival)\\b",
        r"\\b(connection|interaction|dynamic) (with|between)\\b",
        r"\\b(dating|married|involved with|working with)\\b"
    ]
    
    for pattern in relationship_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "relationship"
            return query_info  # Early return for next priority
    
    # Check for event-focused query
    event_patterns = [
        r"\\bwhat happened\\b",
        r"\\bevent[s]?\\b",
        r"\\boccurred\\b",
        r"\\btook place\\b",
        r"\\bwhen (did|was|were)\\b",
        r"\\b(timeline|chronology|sequence) of\\b",
        r"\\b(before|after|during) [a-z]+\\b",
        r"\\bincident[s]?\\b",
        r"\\baction[s]?\\b",
        r"\\b(mission|operation|meeting|fight|battle|conflict|confrontation)\\b",
        r"\\b(how|why|when) did [a-z]+ (happen|start|end|occur)\\b",
        r"\\bvisit(ed)? [a-z]+\\b"
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "event"
            return query_info
    
    # Check for location-focused query
    location_patterns = [
        r"\\bwhere\\b",
        r"\\blocation['s]?\\b",
        r"\\bplace['s]?\\b",
        r"\\b(city|district|area|region|zone|neighborhood)['s]?\\b",
        r"\\b(building|facility|complex|headquarters|center|base)['s]?\\b",
        r"\\bwhat is [a-z]+ (like|layout|description)\\b",
        r"\\b(bar|club|restaurant|office|laboratory|lab|bridge)['s]?\\b",
        r"\\bdescribe [a-z]+ (layout|appearance|design)\\b",
        r"\\b(what|where) is\\b [a-z]+ (located|situated)"
    ]
    
    for pattern in location_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "location"
            return query_info
    
    # Check for theme-focused query
    theme_patterns = [
        r"\\btheme[s]?\\b",
        r"\\bmotif[s]?\\b",
        r"\\bsymbolism\\b",
        r"\\bmeaning\\b",
        r"\\bconcept[s]?\\b",
        r"\\bsignificance\\b",
        r"\\bimportance\\b",
        r"\\bpurpose\\b",
        r"\\bgoal[s]?\\b",
        r"\\bmission\\b",
        r"\\bphilosophy\\b",
        r"\\bideology\\b",
        r"\\b(what is the|what's the) (point|purpose|goal|meaning)\\b",
        r"\\b(why does|why is|why was) [a-z]+ (important|significant|created|developed)"
    ]
    
    for pattern in theme_patterns:
        if re.search(pattern, query_lower):
            query_info["type"] = "theme"
            return query_info
    
    # If no patterns matched, it remains "general"
    return query_info
''')
    
    print(f"Implementation code saved to {code_path}")

if __name__ == "__main__":
    import numpy as np
    main()