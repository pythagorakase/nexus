#!/usr/bin/env python3
"""
Narrative Learning System for Night City Stories

This module implements a learning system that tracks successful narrative retrievals,
adjusts retrieval weights based on historical performance, and identifies patterns
in successful narrative continuations.

Key features:
- Track successful vs. unsuccessful retrievals
- Learn optimal model weights for different query types
- Identify patterns in high-quality narrative continuations
- Automatic prompt template refinement
"""

import sqlite3
import json
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
import time
import numpy as np
from datetime import datetime
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("narrative_learner.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("narrative_learner")

# Database path
DB_PATH = Path("NightCityStories.db")
LEARNING_DB_PATH = Path("narrative_learning.db")

class QueryType:
    """Query type constants for categorization"""
    CHARACTER_INFO = "character_info"
    PLOT_RECAP = "plot_recap"
    EVENT_CONTEXT = "event_context"
    RELATIONSHIP = "relationship"
    WORLD_STATE = "world_state"
    THEMATIC = "thematic"
    UNKNOWN = "unknown"

class FeedbackSource:
    """Feedback source constants"""
    EXPLICIT_USER = "explicit_user"  # Direct user feedback
    NARRATIVE_COHERENCE = "narrative_coherence"  # Measured coherence
    ENTITY_CONSISTENCY = "entity_consistency"  # Consistent entity portrayal
    CONTINUITY = "continuity"  # Narrative continuity
    ENGAGEMENT = "engagement"  # User engagement signals

class NarrativeLearner:
    """
    Learning system for narrative intelligence that improves retrieval and generation
    based on feedback and success patterns
    """
    
    def __init__(self, db_path: Path = LEARNING_DB_PATH):
        self.db_path = db_path
        
        # Initialize the database connection
        self.db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        
        # Initialize the main story database connection
        self.story_conn = sqlite3.connect(str(DB_PATH))
        self.story_conn.row_factory = sqlite3.Row
        
        # Ensure database has the necessary tables
        self._ensure_tables_exist()
        
        # Load current model weights and other parameters
        self.model_weights = self._load_model_weights()
        self.chunk_success_scores = self._load_chunk_success_scores()
        self.query_patterns = self._load_query_patterns()
    
    def _ensure_tables_exist(self):
        """Create necessary tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Retrieval tracking table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS retrieval_tracking (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            timestamp REAL NOT NULL,
            query_text TEXT NOT NULL,
            query_type TEXT NOT NULL,
            model_used TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            chunk_rank INTEGER NOT NULL,
            success_score REAL,
            feedback_source TEXT,
            feedback_details TEXT,
            narrative_id TEXT,
            episode TEXT
        )
        ''')
        
        # Model weights table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_weights (
            id INTEGER PRIMARY KEY,
            timestamp REAL NOT NULL,
            model_name TEXT NOT NULL,
            query_type TEXT NOT NULL,
            weight REAL NOT NULL,
            confidence REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            is_current BOOLEAN NOT NULL DEFAULT 1
        )
        ''')
        
        # Chunk success metrics
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS chunk_success_metrics (
            chunk_id TEXT PRIMARY KEY,
            retrieval_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            average_score REAL NOT NULL DEFAULT 0,
            last_retrieved REAL,
            last_updated REAL NOT NULL
        )
        ''')
        
        # Query pattern recognition
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS query_patterns (
            id INTEGER PRIMARY KEY,
            pattern_type TEXT NOT NULL,
            pattern_regex TEXT NOT NULL,
            query_type TEXT NOT NULL,
            success_rate REAL NOT NULL DEFAULT 0,
            sample_count INTEGER NOT NULL DEFAULT 0,
            weight_adjustments TEXT,  -- JSON of model weight adjustments
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        ''')
        
        # Narrative quality metrics
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS narrative_quality (
            narrative_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            coherence_score REAL,
            engagement_score REAL,
            consistency_score REAL,
            creativity_score REAL,
            overall_score REAL,
            feedback_source TEXT,
            feedback_details TEXT,
            retrieval_ids TEXT  -- JSON array of retrieval IDs used
        )
        ''')
        
        self.conn.commit()
        
        # Initialize default model weights if none exist
        self._initialize_default_weights()
        self._initialize_default_patterns()
    
    def _initialize_default_weights(self):
        """Initialize default model weights if none exist"""
        cursor = self.conn.cursor()
        
        # Check if we have any weights
        cursor.execute("SELECT COUNT(*) as count FROM model_weights WHERE is_current = 1")
        row = cursor.fetchone()
        if row and row['count'] > 0:
            return  # We already have weights
        
        # Default weights for different models and query types
        default_weights = [
            # General weights
            ("bge_large", "unknown", 0.4, 0.5, 0),
            ("e5_large", "unknown", 0.4, 0.5, 0),
            ("bge_small", "unknown", 0.2, 0.5, 0),
            
            # Character info weights
            ("bge_large", QueryType.CHARACTER_INFO, 0.35, 0.5, 0),
            ("e5_large", QueryType.CHARACTER_INFO, 0.5, 0.5, 0),
            ("bge_small", QueryType.CHARACTER_INFO, 0.15, 0.5, 0),
            
            # Plot recap weights
            ("bge_large", QueryType.PLOT_RECAP, 0.45, 0.5, 0),
            ("e5_large", QueryType.PLOT_RECAP, 0.45, 0.5, 0),
            ("bge_small", QueryType.PLOT_RECAP, 0.1, 0.5, 0),
            
            # Event context weights
            ("bge_large", QueryType.EVENT_CONTEXT, 0.5, 0.5, 0),
            ("e5_large", QueryType.EVENT_CONTEXT, 0.3, 0.5, 0),
            ("bge_small", QueryType.EVENT_CONTEXT, 0.2, 0.5, 0),
            
            # Relationship weights
            ("bge_large", QueryType.RELATIONSHIP, 0.3, 0.5, 0),
            ("e5_large", QueryType.RELATIONSHIP, 0.5, 0.5, 0),
            ("bge_small", QueryType.RELATIONSHIP, 0.2, 0.5, 0),
            
            # World state weights
            ("bge_large", QueryType.WORLD_STATE, 0.4, 0.5, 0),
            ("e5_large", QueryType.WORLD_STATE, 0.4, 0.5, 0),
            ("bge_small", QueryType.WORLD_STATE, 0.2, 0.5, 0),
            
            # Thematic weights
            ("bge_large", QueryType.THEMATIC, 0.5, 0.5, 0),
            ("e5_large", QueryType.THEMATIC, 0.3, 0.5, 0),
            ("bge_small", QueryType.THEMATIC, 0.2, 0.5, 0)
        ]
        
        now = time.time()
        for model_name, query_type, weight, confidence, sample_count in default_weights:
            cursor.execute('''
            INSERT INTO model_weights
            (timestamp, model_name, query_type, weight, confidence, sample_count, is_current)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (now, model_name, query_type, weight, confidence, sample_count))
        
        self.conn.commit()
        logger.info("Initialized default model weights")
    
    def _initialize_default_patterns(self):
        """Initialize default query patterns if none exist"""
        cursor = self.conn.cursor()
        
        # Check if we have any patterns
        cursor.execute("SELECT COUNT(*) as count FROM query_patterns")
        row = cursor.fetchone()
        if row and row['count'] > 0:
            return  # We already have patterns
        
        # Default patterns for query categorization
        default_patterns = [
            # Character info patterns
            ("keyword", r"\b(character|who is|about|backstory|history of)\b.+\b([A-Z][a-z]+)\b", 
             QueryType.CHARACTER_INFO, 0.0, 0, None),
            
            # Plot recap patterns
            ("keyword", r"\b(what happened|recap|summarize|summary|previous|before)\b", 
             QueryType.PLOT_RECAP, 0.0, 0, None),
            
            # Event context patterns
            ("keyword", r"\b(event|incident|when|how did|why did)\b", 
             QueryType.EVENT_CONTEXT, 0.0, 0, None),
            
            # Relationship patterns
            ("keyword", r"\b(relationship|between|with|feel about|think of)\b.+\b([A-Z][a-z]+).+\b([A-Z][a-z]+)\b", 
             QueryType.RELATIONSHIP, 0.0, 0, None),
            
            # World state patterns
            ("keyword", r"\b(world|city|faction|corporation|gang|status|state of)\b", 
             QueryType.WORLD_STATE, 0.0, 0, None),
            
            # Thematic patterns
            ("keyword", r"\b(theme|meaning|symbolism|represent|metaphor)\b", 
             QueryType.THEMATIC, 0.0, 0, None)
        ]
        
        now = time.time()
        for pattern_type, pattern_regex, query_type, success_rate, sample_count, weight_adjustments in default_patterns:
            cursor.execute('''
            INSERT INTO query_patterns
            (pattern_type, pattern_regex, query_type, success_rate, sample_count, 
             weight_adjustments, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pattern_type, 
                pattern_regex, 
                query_type, 
                success_rate, 
                sample_count, 
                json.dumps(weight_adjustments) if weight_adjustments else None,
                now,
                now
            ))
        
        self.conn.commit()
        logger.info("Initialized default query patterns")
    
    def _load_model_weights(self) -> Dict[str, Dict[str, float]]:
        """Load current model weights from the database"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT model_name, query_type, weight
        FROM model_weights
        WHERE is_current = 1
        ''')
        
        weights = {}
        for row in cursor.fetchall():
            model_name = row['model_name']
            query_type = row['query_type']
            weight = row['weight']
            
            if model_name not in weights:
                weights[model_name] = {}
            
            weights[model_name][query_type] = weight
        
        return weights
    
    def _load_chunk_success_scores(self) -> Dict[str, float]:
        """Load chunk success scores from the database"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT chunk_id, average_score
        FROM chunk_success_metrics
        ''')
        
        scores = {}
        for row in cursor.fetchall():
            scores[row['chunk_id']] = row['average_score']
        
        return scores
    
    def _load_query_patterns(self) -> List[Dict[str, Any]]:
        """Load query patterns from the database"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT id, pattern_type, pattern_regex, query_type, success_rate, weight_adjustments
        FROM query_patterns
        ORDER BY success_rate DESC
        ''')
        
        patterns = []
        for row in cursor.fetchall():
            pattern = {
                'id': row['id'],
                'pattern_type': row['pattern_type'],
                'pattern_regex': row['pattern_regex'],
                'query_type': row['query_type'],
                'success_rate': row['success_rate'],
                'weight_adjustments': json.loads(row['weight_adjustments']) if row['weight_adjustments'] else None
            }
            patterns.append(pattern)
        
        return patterns
    
    def categorize_query(self, query_text: str) -> str:
        """
        Categorize a query into one of the predefined types
        
        Args:
            query_text: The query text to categorize
            
        Returns:
            Query type (one of QueryType constants)
        """
        for pattern in self.query_patterns:
            regex = pattern['pattern_regex']
            if re.search(regex, query_text, re.IGNORECASE):
                return pattern['query_type']
        
        return QueryType.UNKNOWN
    
    def get_model_weights(self, query_text: str = None, query_type: str = None) -> Dict[str, float]:
        """
        Get optimized model weights for a query
        
        Args:
            query_text: Optional query text (used for categorization if query_type not provided)
            query_type: Optional explicit query type
            
        Returns:
            Dictionary of model names to weights
        """
        if query_type is None:
            if query_text:
                query_type = self.categorize_query(query_text)
            else:
                query_type = QueryType.UNKNOWN
        
        # Get weights specific to this query type
        weights = {}
        for model_name in ["bge_large", "e5_large", "bge_small"]:
            if model_name in self.model_weights and query_type in self.model_weights[model_name]:
                weights[model_name] = self.model_weights[model_name][query_type]
            elif model_name in self.model_weights and QueryType.UNKNOWN in self.model_weights[model_name]:
                # Fall back to unknown type weights
                weights[model_name] = self.model_weights[model_name][QueryType.UNKNOWN]
            else:
                # Use default weights if nothing else available
                if model_name == "bge_large":
                    weights[model_name] = 0.4
                elif model_name == "e5_large":
                    weights[model_name] = 0.4
                else:
                    weights[model_name] = 0.2
        
        # Check for pattern-specific adjustments
        if query_text:
            for pattern in self.query_patterns:
                if pattern['weight_adjustments'] and re.search(pattern['pattern_regex'], query_text, re.IGNORECASE):
                    for model_name, adjustment in pattern['weight_adjustments'].items():
                        if model_name in weights:
                            weights[model_name] += adjustment
        
        # Normalize weights to ensure they sum to 1.0
        total = sum(weights.values())
        if total > 0:
            for model_name in weights:
                weights[model_name] /= total
        
        return weights
    
    def track_retrieval(self, session_id: str, query_text: str, model_used: str, 
                      chunk_id: str, chunk_rank: int, episode: Optional[str] = None) -> int:
        """
        Track a retrieval for later evaluation
        
        Args:
            session_id: Unique identifier for the narrative session
            query_text: The query that was used
            model_used: The embedding model that retrieved this chunk
            chunk_id: ID of the retrieved chunk
            chunk_rank: Rank position of this chunk in results
            episode: Optional episode context
            
        Returns:
            ID of the tracking entry
        """
        cursor = self.conn.cursor()
        
        query_type = self.categorize_query(query_text)
        timestamp = time.time()
        
        cursor.execute('''
        INSERT INTO retrieval_tracking
        (session_id, timestamp, query_text, query_type, model_used, 
         chunk_id, chunk_rank, episode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id, timestamp, query_text, query_type, model_used,
            chunk_id, chunk_rank, episode
        ))
        
        tracking_id = cursor.lastrowid
        self.conn.commit()
        
        # Update retrieval count for this chunk
        cursor.execute('''
        INSERT INTO chunk_success_metrics
        (chunk_id, retrieval_count, success_count, average_score, last_retrieved, last_updated)
        VALUES (?, 1, 0, 0.0, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
        retrieval_count = retrieval_count + 1,
        last_retrieved = excluded.last_retrieved,
        last_updated = excluded.last_updated
        ''', (chunk_id, timestamp, timestamp))
        
        self.conn.commit()
        
        logger.info(f"Tracked retrieval: {chunk_id} (rank {chunk_rank}) for query type {query_type}")
        return tracking_id
    
    def record_feedback(self, tracking_id: int, success_score: float, 
                      feedback_source: str, narrative_id: Optional[str] = None,
                      feedback_details: Optional[str] = None) -> bool:
        """
        Record feedback on a retrieval's success
        
        Args:
            tracking_id: ID of the tracking entry
            success_score: Score indicating success (0.0-1.0)
            feedback_source: Source of the feedback
            narrative_id: Optional ID of the narrative this contributed to
            feedback_details: Optional details about the feedback
            
        Returns:
            True if feedback was recorded successfully
        """
        cursor = self.conn.cursor()
        
        # Update the tracking entry
        cursor.execute('''
        UPDATE retrieval_tracking
        SET success_score = ?, feedback_source = ?, feedback_details = ?, narrative_id = ?
        WHERE id = ?
        ''', (success_score, feedback_source, feedback_details, narrative_id, tracking_id))
        
        if cursor.rowcount == 0:
            logger.warning(f"No retrieval found with ID {tracking_id}")
            return False
        
        # Get the chunk ID and query type to update metrics
        cursor.execute('''
        SELECT chunk_id, query_type, model_used
        FROM retrieval_tracking
        WHERE id = ?
        ''', (tracking_id,))
        
        row = cursor.fetchone()
        if not row:
            logger.warning(f"Could not retrieve details for tracking ID {tracking_id}")
            self.conn.commit()
            return False
        
        chunk_id = row['chunk_id']
        query_type = row['query_type']
        model_used = row['model_used']
        
        # Update chunk success metrics
        cursor.execute('''
        SELECT retrieval_count, success_count, average_score
        FROM chunk_success_metrics
        WHERE chunk_id = ?
        ''', (chunk_id,))
        
        metrics_row = cursor.fetchone()
        if metrics_row:
            retrieval_count = metrics_row['retrieval_count']
            success_count = metrics_row['success_count']
            average_score = metrics_row['average_score']
            
            # Update based on this new feedback
            new_success_count = success_count + (1 if success_score >= 0.5 else 0)
            new_average_score = ((average_score * success_count) + success_score) / (success_count + 1)
            
            cursor.execute('''
            UPDATE chunk_success_metrics
            SET success_count = ?, average_score = ?, last_updated = ?
            WHERE chunk_id = ?
            ''', (new_success_count, new_average_score, time.time(), chunk_id))
            
            # Update our in-memory cache
            self.chunk_success_scores[chunk_id] = new_average_score
        
        # Update model weights if the feedback is significant
        if success_score >= 0.8 or success_score <= 0.2:
            self._update_model_weights(query_type, model_used, success_score)
        
        self.conn.commit()
        
        logger.info(f"Recorded feedback for retrieval {tracking_id}: score {success_score}")
        return True
    
    def record_narrative_quality(self, narrative_id: str, retrieval_ids: List[int],
                               coherence_score: Optional[float] = None,
                               engagement_score: Optional[float] = None,
                               consistency_score: Optional[float] = None,
                               creativity_score: Optional[float] = None,
                               overall_score: Optional[float] = None,
                               feedback_source: str = FeedbackSource.EXPLICIT_USER,
                               feedback_details: Optional[str] = None) -> bool:
        """
        Record quality metrics for a generated narrative
        
        Args:
            narrative_id: Unique identifier for the narrative
            retrieval_ids: List of retrieval tracking IDs used in this narrative
            coherence_score: Optional narrative coherence score (0.0-1.0)
            engagement_score: Optional engagement score
            consistency_score: Optional consistency score
            creativity_score: Optional creativity score
            overall_score: Optional overall quality score
            feedback_source: Source of this feedback
            feedback_details: Optional details about the feedback
            
        Returns:
            True if quality metrics were recorded successfully
        """
        cursor = self.conn.cursor()
        
        # Insert or update the narrative quality record
        cursor.execute('''
        INSERT INTO narrative_quality
        (narrative_id, timestamp, coherence_score, engagement_score, consistency_score,
         creativity_score, overall_score, feedback_source, feedback_details, retrieval_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(narrative_id) DO UPDATE SET
        timestamp = excluded.timestamp,
        coherence_score = excluded.coherence_score,
        engagement_score = excluded.engagement_score,
        consistency_score = excluded.consistency_score,
        creativity_score = excluded.creativity_score,
        overall_score = excluded.overall_score,
        feedback_source = excluded.feedback_source,
        feedback_details = excluded.feedback_details,
        retrieval_ids = excluded.retrieval_ids
        ''', (
            narrative_id,
            time.time(),
            coherence_score,
            engagement_score,
            consistency_score,
            creativity_score,
            overall_score,
            feedback_source,
            feedback_details,
            json.dumps(retrieval_ids)
        ))
        
        # Now also update the individual retrievals with this feedback
        if overall_score is not None:
            for tracking_id in retrieval_ids:
                self.record_feedback(
                    tracking_id=tracking_id,
                    success_score=overall_score,
                    feedback_source=feedback_source,
                    narrative_id=narrative_id,
                    feedback_details=f"From narrative quality: {overall_score}"
                )
        
        self.conn.commit()
        
        logger.info(f"Recorded narrative quality for {narrative_id}: overall score {overall_score}")
        return True
    
    def _update_model_weights(self, query_type: str, model_used: str, success_score: float):
        """
        Update model weights based on success/failure
        
        This implements a simple reinforcement learning approach:
        - Successful retrievals increase the weight of the model that found them
        - Unsuccessful retrievals decrease the weight of the model that found them
        - Weights for other models are adjusted proportionally to maintain sum = 1.0
        """
        cursor = self.conn.cursor()
        
        # Get current weights and metadata
        cursor.execute('''
        SELECT id, model_name, weight, confidence, sample_count
        FROM model_weights
        WHERE query_type = ? AND is_current = 1
        ''', (query_type,))
        
        rows = cursor.fetchall()
        if not rows:
            # Fall back to UNKNOWN type if this specific type doesn't exist
            cursor.execute('''
            SELECT id, model_name, weight, confidence, sample_count
            FROM model_weights
            WHERE query_type = ? AND is_current = 1
            ''', (QueryType.UNKNOWN,))
            rows = cursor.fetchall()
        
        if not rows:
            logger.warning(f"No weights found for query type {query_type}")
            return
        
        # Prepare for updates
        model_data = {}
        for row in rows:
            model_data[row['model_name']] = {
                'id': row['id'],
                'weight': row['weight'],
                'confidence': row['confidence'],
                'sample_count': row['sample_count']
            }
        
        # Calculate learning rate based on confidence and sample count
        # As confidence increases and we collect more samples, we adjust more conservatively
        base_learning_rate = 0.05
        model_info = model_data.get(model_used, {})
        confidence = model_info.get('confidence', 0.5)
        sample_count = model_info.get('sample_count', 0)
        
        learning_rate = base_learning_rate * (1.0 - (confidence * 0.5)) / (1.0 + (sample_count / 100))
        
        # Adjust success_score to be a modifier (-0.5 to 0.5 range)
        score_modifier = (success_score - 0.5) * 2.0
        
        # Calculate the adjustment for the used model
        if model_used in model_data:
            current_weight = model_data[model_used]['weight']
            model_data[model_used]['weight'] += learning_rate * score_modifier
            model_data[model_used]['sample_count'] += 1
            
            # If the score was very good or very bad, adjust confidence
            if success_score >= 0.8 or success_score <= 0.2:
                # The more extreme the score, the more it affects confidence
                confidence_adjustment = abs(score_modifier) * 0.1
                
                # Increase confidence for very successful retrievals
                if success_score >= 0.8:
                    model_data[model_used]['confidence'] = min(1.0, model_data[model_used]['confidence'] + confidence_adjustment)
                # Decrease confidence for very unsuccessful retrievals
                else:
                    model_data[model_used]['confidence'] = max(0.1, model_data[model_used]['confidence'] - confidence_adjustment)
        
        # Normalize weights to ensure they sum to 1.0
        total_weight = sum(m['weight'] for m in model_data.values())
        for model_name in model_data:
            model_data[model_name]['weight'] /= total_weight
        
        # Update all weights in the database
        timestamp = time.time()
        
        # First, mark all current weights as not current
        cursor.execute('''
        UPDATE model_weights
        SET is_current = 0
        WHERE query_type = ? AND is_current = 1
        ''', (query_type,))
        
        # Then insert new weights
        for model_name, data in model_data.items():
            cursor.execute('''
            INSERT INTO model_weights
            (timestamp, model_name, query_type, weight, confidence, sample_count, is_current)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (
                timestamp,
                model_name,
                query_type,
                data['weight'],
                data['confidence'],
                data['sample_count']
            ))
        
        self.conn.commit()
        
        # Update in-memory weights
        for model_name, data in model_data.items():
            if model_name not in self.model_weights:
                self.model_weights[model_name] = {}
            self.model_weights[model_name][query_type] = data['weight']
        
        logger.info(f"Updated model weights for query type {query_type} based on success score {success_score}")
    
    def analyze_successful_patterns(self):
        """
        Analyze patterns in successful retrievals
        
        This method identifies common patterns in queries that led to successful
        retrievals and updates the query pattern database accordingly.
        """
        cursor = self.conn.cursor()
        
        # Get successful retrievals (success_score >= 0.7)
        cursor.execute('''
        SELECT query_text, query_type, success_score, model_used
        FROM retrieval_tracking
        WHERE success_score >= 0.7
        ORDER BY success_score DESC
        LIMIT 1000
        ''')
        
        successful_queries = cursor.fetchall()
        if not successful_queries:
            logger.info("No successful queries found for pattern analysis")
            return
        
        # Group by query type
        queries_by_type = {}
        for row in successful_queries:
            query_type = row['query_type']
            if query_type not in queries_by_type:
                queries_by_type[query_type] = []
            
            queries_by_type[query_type].append({
                'text': row['query_text'],
                'score': row['success_score'],
                'model': row['model_used']
            })
        
        # For each query type, find common n-grams and patterns
        for query_type, queries in queries_by_type.items():
            # Skip if we don't have enough samples
            if len(queries) < 5:
                continue
            
            # Calculate model performance for this query type
            model_performance = {}
            for query in queries:
                model = query['model']
                score = query['score']
                
                if model not in model_performance:
                    model_performance[model] = {'total': 0, 'score': 0}
                
                model_performance[model]['total'] += 1
                model_performance[model]['score'] += score
            
            # Calculate average score per model
            weight_adjustments = {}
            for model, perf in model_performance.items():
                if perf['total'] > 0:
                    avg_score = perf['score'] / perf['total']
                    # Calculate a small weight adjustment based on relative performance
                    weight_adjustments[model] = (avg_score - 0.5) * 0.1
            
            # Implement advanced pattern recognition here
            # For this example, we'll just update the existing patterns with new performance data
            
            # Update the pattern record
            cursor.execute('''
            UPDATE query_patterns
            SET success_rate = (success_rate * sample_count + ?) / (sample_count + ?),
                sample_count = sample_count + ?,
                weight_adjustments = ?,
                updated_at = ?
            WHERE query_type = ?
            ''', (
                sum(q['score'] for q in queries),
                len(queries),
                len(queries),
                json.dumps(weight_adjustments) if weight_adjustments else None,
                time.time(),
                query_type
            ))
        
        self.conn.commit()
        
        # Reload patterns
        self.query_patterns = self._load_query_patterns()
        
        logger.info("Updated query patterns based on successful retrievals")
    
    def get_chunk_recommendations(self, query_text: str, exclude_chunks: Optional[List[str]] = None) -> List[str]:
        """
        Get chunk recommendations based on historical success
        
        Args:
            query_text: The query text
            exclude_chunks: Optional list of chunk IDs to exclude
            
        Returns:
            List of recommended chunk IDs in priority order
        """
        if exclude_chunks is None:
            exclude_chunks = []
        
        # Query category affects which chunks we recommend
        query_type = self.categorize_query(query_text)
        
        # Get chunks that have been successful for similar queries
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT rt.chunk_id, AVG(rt.success_score) as avg_score, COUNT(*) as count
        FROM retrieval_tracking rt
        WHERE rt.query_type = ? AND rt.success_score >= 0.6
        GROUP BY rt.chunk_id
        ORDER BY avg_score DESC, count DESC
        LIMIT 20
        ''', (query_type,))
        
        recommended_chunks = []
        for row in cursor.fetchall():
            chunk_id = row['chunk_id']
            if chunk_id not in exclude_chunks:
                recommended_chunks.append(chunk_id)
        
        # If we don't have enough recommendations, add some generally successful chunks
        if len(recommended_chunks) < 5:
            cursor.execute('''
            SELECT chunk_id, average_score
            FROM chunk_success_metrics
            WHERE success_count > 0
            ORDER BY average_score DESC, retrieval_count DESC
            LIMIT 20
            ''')
            
            for row in cursor.fetchall():
                chunk_id = row['chunk_id']
                if chunk_id not in exclude_chunks and chunk_id not in recommended_chunks:
                    recommended_chunks.append(chunk_id)
        
        return recommended_chunks[:10]  # Return top 10
    
    def analyze_narrative_performance(self):
        """
        Analyze what makes successful narratives
        
        This method identifies patterns in retrievals that led to high-quality narratives
        and can be used to improve future retrieval strategies.
        """
        cursor = self.conn.cursor()
        
        # Get high-quality narratives (overall_score >= 0.7)
        cursor.execute('''
        SELECT narrative_id, overall_score, retrieval_ids
        FROM narrative_quality
        WHERE overall_score >= 0.7
        ORDER BY overall_score DESC
        LIMIT 50
        ''')
        
        high_quality_narratives = cursor.fetchall()
        if not high_quality_narratives:
            logger.info("No high-quality narratives found for analysis")
            return
        
        # Collect all retrieval IDs used in high-quality narratives
        all_retrieval_ids = []
        for row in high_quality_narratives:
            retrieval_ids = json.loads(row['retrieval_ids']) if row['retrieval_ids'] else []
            all_retrieval_ids.extend(retrieval_ids)
        
        # Get details of these retrievals
        placeholders = ','.join(['?'] * len(all_retrieval_ids))
        cursor.execute(f'''
        SELECT rt.id, rt.query_text, rt.query_type, rt.model_used, rt.chunk_id, rt.chunk_rank
        FROM retrieval_tracking rt
        WHERE rt.id IN ({placeholders})
        ''', all_retrieval_ids)
        
        retrievals = cursor.fetchall()
        
        # Analyze patterns
        rank_distribution = {}  # How important is rank?
        query_type_distribution = {}  # Which query types are most valuable?
        model_distribution = {}  # Which models find the most useful results?
        
        for row in retrievals:
            # Rank analysis
            rank = row['chunk_rank']
            rank_bucket = min(rank, 10)  # Bucket ranks above 10
            if rank_bucket not in rank_distribution:
                rank_distribution[rank_bucket] = 0
            rank_distribution[rank_bucket] += 1
            
            # Query type analysis
            query_type = row['query_type']
            if query_type not in query_type_distribution:
                query_type_distribution[query_type] = 0
            query_type_distribution[query_type] += 1
            
            # Model analysis
            model = row['model_used']
            if model not in model_distribution:
                model_distribution[model] = 0
            model_distribution[model] += 1
        
        # Log insights
        logger.info("=== Narrative Performance Analysis ===")
        logger.info(f"Analyzed {len(high_quality_narratives)} high-quality narratives with {len(retrievals)} retrievals")
        
        logger.info("Rank Distribution:")
        for rank, count in sorted(rank_distribution.items()):
            logger.info(f"  Rank {rank}: {count} occurrences")
        
        logger.info("Query Type Distribution:")
        for qtype, count in sorted(query_type_distribution.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {qtype}: {count} occurrences")
        
        logger.info("Model Distribution:")
        for model, count in sorted(model_distribution.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {model}: {count} occurrences")
    
    def get_optimal_retrieval_parameters(self, query_text: str) -> Dict[str, Any]:
        """
        Get optimal retrieval parameters for a query based on learning history
        
        Args:
            query_text: The query text
            
        Returns:
            Dictionary of optimized parameters:
            - model_weights: Weights for each embedding model
            - top_k: Suggested number of results to retrieve
            - recommended_chunks: Chunks to prioritize
            - query_type: Categorized query type
        """
        query_type = self.categorize_query(query_text)
        model_weights = self.get_model_weights(query_text, query_type)
        
        # Determine optimal top_k based on query type
        top_k = 3  # Default
        if query_type == QueryType.PLOT_RECAP:
            top_k = 5  # Plot recaps need more context
        elif query_type == QueryType.THEMATIC:
            top_k = 4  # Thematic queries benefit from more diverse chunks
        
        # Get recommended chunks
        recommended_chunks = self.get_chunk_recommendations(query_text)
        
        return {
            'model_weights': model_weights,
            'top_k': top_k,
            'recommended_chunks': recommended_chunks,
            'query_type': query_type
        }
    
    def record_user_feedback(self, narrative_id: str, feedback_score: float, 
                          feedback_details: Optional[str] = None) -> bool:
        """
        Record explicit user feedback on a narrative
        
        Args:
            narrative_id: ID of the narrative
            feedback_score: User's score (0.0-1.0)
            feedback_details: Optional details from the user
            
        Returns:
            True if feedback was recorded successfully
        """
        cursor = self.conn.cursor()
        
        # Get retrievals associated with this narrative
        cursor.execute('''
        SELECT retrieval_ids FROM narrative_quality
        WHERE narrative_id = ?
        ''', (narrative_id,))
        
        row = cursor.fetchone()
        if not row or not row['retrieval_ids']:
            logger.warning(f"No retrievals found for narrative {narrative_id}")
            return False
        
        retrieval_ids = json.loads(row['retrieval_ids'])
        
        # Record narrative quality with user feedback
        self.record_narrative_quality(
            narrative_id=narrative_id,
            retrieval_ids=retrieval_ids,
            overall_score=feedback_score,
            feedback_source=FeedbackSource.EXPLICIT_USER,
            feedback_details=feedback_details
        )
        
        logger.info(f"Recorded user feedback for narrative {narrative_id}: score {feedback_score}")
        return True
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive performance report for the narrative system
        
        Returns:
            Dictionary with performance metrics and insights
        """
        cursor = self.conn.cursor()
        
        # Overall retrieval statistics
        cursor.execute('''
        SELECT COUNT(*) as total_retrievals,
               AVG(success_score) as avg_success_score,
               SUM(CASE WHEN success_score >= 0.7 THEN 1 ELSE 0 END) as high_success_count
        FROM retrieval_tracking
        WHERE success_score IS NOT NULL
        ''')
        
        retrieval_stats = dict(cursor.fetchone())
        
        # Query type performance
        cursor.execute('''
        SELECT query_type,
               COUNT(*) as count,
               AVG(success_score) as avg_score
        FROM retrieval_tracking
        WHERE success_score IS NOT NULL
        GROUP BY query_type
        ORDER BY avg_score DESC
        ''')
        
        query_type_stats = [dict(row) for row in cursor.fetchall()]
        
        # Model performance
        cursor.execute('''
        SELECT model_used,
               COUNT(*) as count,
               AVG(success_score) as avg_score
        FROM retrieval_tracking
        WHERE success_score IS NOT NULL
        GROUP BY model_used
        ORDER BY avg_score DESC
        ''')
        
        model_stats = [dict(row) for row in cursor.fetchall()]
        
        # Narrative quality statistics
        cursor.execute('''
        SELECT COUNT(*) as total_narratives,
               AVG(overall_score) as avg_overall_score,
               AVG(coherence_score) as avg_coherence_score,
               AVG(engagement_score) as avg_engagement_score
        FROM narrative_quality
        WHERE overall_score IS NOT NULL
        ''')
        
        narrative_stats = dict(cursor.fetchone())
        
        # Performance trend over time (last 10 periods)
        cursor.execute('''
        SELECT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch')) as date,
               AVG(success_score) as avg_score,
               COUNT(*) as count
        FROM retrieval_tracking
        WHERE success_score IS NOT NULL
        GROUP BY date
        ORDER BY date DESC
        LIMIT 10
        ''')
        
        time_trends = [dict(row) for row in cursor.fetchall()]
        
        # Combine into a comprehensive report
        report = {
            'generated_at': datetime.now().isoformat(),
            'retrieval_stats': retrieval_stats,
            'query_type_stats': query_type_stats,
            'model_stats': model_stats,
            'narrative_stats': narrative_stats,
            'time_trends': time_trends,
            'current_model_weights': self.model_weights
        }
        
        logger.info("Generated performance report")
        return report
    
    def close(self):
        """Close database connections"""
        if self.conn:
            self.conn.close()
        if self.story_conn:
            self.story_conn.close()


# Example usage
if __name__ == "__main__":
    learner = NarrativeLearner()
    
    # Track some retrievals
    session_id = f"test_{int(time.time())}"
    
    track1 = learner.track_retrieval(
        session_id=session_id,
        query_text="What happened between Alex and Emilia in the Neon Bay?",
        model_used="bge_large",
        chunk_id="S01E05_012",
        chunk_rank=1,
        episode="S01E08"
    )
    
    track2 = learner.track_retrieval(
        session_id=session_id,
        query_text="What happened between Alex and Emilia in the Neon Bay?",
        model_used="e5_large",
        chunk_id="S01E05_013",
        chunk_rank=2,
        episode="S01E08"
    )
    
    # Record feedback
    learner.record_feedback(
        tracking_id=track1,
        success_score=0.9,
        feedback_source=FeedbackSource.NARRATIVE_COHERENCE,
        narrative_id="test_narrative_1"
    )
    
    learner.record_feedback(
        tracking_id=track2,
        success_score=0.7,
        feedback_source=FeedbackSource.NARRATIVE_COHERENCE,
        narrative_id="test_narrative_1"
    )
    
    # Record narrative quality
    learner.record_narrative_quality(
        narrative_id="test_narrative_1",
        retrieval_ids=[track1, track2],
        coherence_score=0.85,
        engagement_score=0.9,
        overall_score=0.88,
        feedback_source=FeedbackSource.EXPLICIT_USER
    )
    
    # Get optimized parameters for a new query
    params = learner.get_optimal_retrieval_parameters(
        "How does Alex feel about the recent events in Arasaka Tower?"
    )
    print("Optimized parameters:", params)
    
    # Generate a performance report
    report = learner.generate_performance_report()
    print("Performance report:", report)
    
    learner.close()
    