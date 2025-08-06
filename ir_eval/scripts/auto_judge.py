#!/usr/bin/env python3
"""
AI-assisted Judging for NEXUS IR Evaluation System

This script uses OpenAI to judge search results automatically based on query examples
and a generalized scoring rubric. It can process unjudged results for one or more runs.

Usage:
    python auto_judge.py --run-id 5 [options]
    python auto_judge.py --run-ids 5,7,9 [options]

Options:
    --model MODEL           OpenAI model to use (default: gpt-4.1)
    --dry-run               Show what would be judged but don't update database
    --debug                 Print detailed debug information
    --temperature FLOAT     Model temperature (default: 0.2)
    --disable-abort         Disable ESC key and Ctrl+C abort capability

Abort Functionality:
    - Press ESC key to abort the judging process (requires 'keyboard' package)
    - Press Ctrl+C to abort the judging process
    - The script will complete the current judgment and then exit gracefully
"""

import os
import sys
import json
import argparse
import logging
import time
import datetime
from typing import Dict, List, Any, Optional, Set, Tuple, Literal

# Import Pydantic for structured output
from pydantic import BaseModel, Field

# Make sure we can import from parent directories
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import IR evaluation modules
from pg_db import IRDatabasePG
from pg_qrels import PGQRELSManager

# Import OpenAI API library from scripts directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from api_openai import OpenAIProvider, LLMResponse, setup_abort_handler, is_abort_requested, reset_abort_flag

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_judge.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.ir_eval.auto_judge")

# Constants
DEFAULT_MODEL = "gpt-4.1"
DEFAULT_TEMPERATURE = 0.2
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

class AIJudge:
    """
    AI-assisted judge for NEXUS IR evaluation system.
    Uses OpenAI to score query results based on examples and a general rubric.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        dry_run: bool = False,
        debug: bool = False
    ):
        """
        Initialize the AI Judge.
        
        Args:
            model: OpenAI model to use
            temperature: Model temperature (0.0-1.0)
            dry_run: If True, don't save judgments to database
            debug: If True, print detailed debug information
        """
        self.model = model
        self.temperature = temperature
        self.dry_run = dry_run
        self.debug = debug
        self.provider = self._initialize_provider()
        
    def _initialize_provider(self) -> OpenAIProvider:
        """Initialize the OpenAI provider."""
        try:
            # Initialize with structured output setup
            provider = OpenAIProvider(
                model=self.model,
                temperature=self.temperature,
                reasoning_effort="high"  # Use high reasoning effort for better accuracy
            )
            logger.info(f"Initialized OpenAI provider with model: {self.model}")
            return provider
        except Exception as e:
            logger.error(f"Error initializing OpenAI provider: {e}")
            raise
    
    def build_judgment_prompt(
        self,
        query_text: str,
        chunk_text: str,
        examples: Optional[List[str]] = None,
        category: Optional[str] = None
    ) -> str:
        """
        Build a prompt for judging the relevance of a chunk to a query.
        
        Args:
            query_text: The query text
            chunk_text: The text of the chunk to judge
            examples: Optional list of example scores for this query
            category: Optional query category
            
        Returns:
            A prompt for the LLM
        """
        # Use the system prompt as a base
        prompt = """You are a specialized evaluator for narrative information retrieval systems. Your task is to determine the relevance of retrieved content to specific queries about a narrative story.

## Task Definition:
1. You will receive query texts and retrieved narrative chunks.
2. For each chunk, assign a relevance score (0-3) based on how well it answers the query.
3. Be consistent in your scoring approach across all judgments.

## Relevance Scale:
0: Irrelevant - Does not match the query at all
1: Marginally relevant - Mentions the topic but not very helpful
2: Relevant - Contains useful information about the query
3: Highly relevant - Perfect match for the query

## Special Considerations:
- For character-related queries, consider both explicit mentions and clearly implied references
- For relationship queries, assess both factual statements and emotional/interpersonal context
- For temporal queries (first, after, etc.), prioritize content that directly addresses the temporal aspect
- For abstract concept queries, look for direct explanations or clear demonstrations of the concept

When query-specific scoring criteria are provided, use those guidelines to determine the appropriate score.
"""

        # Add the specific query and document
        prompt += f"\n\nQUERY: {query_text}\n\n"
        prompt += f"DOCUMENT TO EVALUATE:\n{chunk_text}\n\n"

        # Add category-specific context if available
        if category:
            prompt += f"QUERY CATEGORY: {category}\n\n"
        
        # Add specific examples for this query if available
        if examples and len(examples) > 0:
            prompt += "SPECIFIC SCORING EXAMPLES FOR THIS QUERY:\n"
            for i, example in enumerate(examples, 1):
                prompt += f"{i}. {example}\n"
            prompt += "\nIf the document matches one of these examples, score accordingly. Otherwise, use the general rubric above.\n\n"
        
        return prompt

    def judge_chunk(
        self,
        query_text: str,
        chunk_text: str,
        chunk_id: str,
        examples: Optional[List[str]] = None,
        category: Optional[str] = None,
        retry_count: int = 0
    ) -> Tuple[int, str]:
        """
        Judge the relevance of a chunk to a query using OpenAI.
        
        Args:
            query_text: The query text
            chunk_text: The text of the chunk to judge
            chunk_id: The ID of the chunk (for logging)
            examples: Optional list of example scores for this query
            category: Optional query category
            retry_count: Number of retries attempted
            
        Returns:
            Tuple of (relevance score, reasoning)
        """
        try:
            # Build the prompt
            prompt = self.build_judgment_prompt(
                query_text=query_text,
                chunk_text=chunk_text,
                examples=examples,
                category=category
            )
            
            # Log the prompt if in debug mode
            if self.debug:
                logger.debug(f"Prompt for chunk {chunk_id}:\n{prompt}\n")
            
            # We'll use Pydantic models for structured output with the responses API
            
            # Create system message with the system prompt
            messages = [
                {"role": "user", "content": prompt}
            ]
            
            # Call the API
            start_time = time.time()
            
            # Use Pydantic model for structured output
            
            # Create a Pydantic model for the assessment
            class RelevanceAssessment(BaseModel):
                relevance_score: Literal[0, 1, 2, 3] = Field(
                    description="Relevance score from 0-3 where 0=Irrelevant, 1=Marginally relevant, 2=Relevant, 3=Highly relevant"
                )
                justification: str = Field(
                    description="Brief explanation of why this score was assigned"
                )
            
            # Use the responses.parse method for structured output
            response = self.provider.client.responses.parse(
                model=self.model,
                input=messages,
                temperature=self.temperature,
                text_format=RelevanceAssessment
            )
            
            # Extract the parsed data and construct a compatible response object for downstream code
            parsed_data = {
                "relevance_score": response.output_parsed.relevance_score,
                "justification": response.output_parsed.justification
            }
            
            # Create simple response structure that matches what the rest of the code expects
            class SimpleResponse:
                def __init__(self, parsed_data, usage):
                    self.choices = [SimpleChoice(parsed_data)]
                    self.usage = SimpleUsage(usage)
            
            class SimpleChoice:
                def __init__(self, data):
                    self.message = SimpleMessage(data)
            
            class SimpleMessage:
                def __init__(self, data):
                    self.content = json.dumps(data)
            
            class SimpleUsage:
                def __init__(self, usage):
                    self.prompt_tokens = usage.input_tokens
                    self.completion_tokens = usage.output_tokens
            
            # Create a response object with the same structure as the chat completions API
            response = SimpleResponse(parsed_data, response.usage)
            
            end_time = time.time()
            
            # Extract response content
            if hasattr(response, 'choices') and len(response.choices) > 0:
                content = response.choices[0].message.content
            else:
                content = "{}"
                
            # Log API usage
            logger.info(f"API call completed in {end_time - start_time:.2f}s")
            
            # Log the response if in debug mode
            if self.debug:
                logger.debug(f"Raw response:\n{content}\n")
            
            # Parse the JSON response
            try:
                data = json.loads(content)
                
                # Extract the score and justification
                score = data.get('relevance_score', 0)
                justification = data.get('justification', '')
                
                # Validate score
                if not isinstance(score, int) or score < 0 or score > 3:
                    logger.warning(f"Invalid score format: {score}, defaulting to 0")
                    score = 0
                
                return score, justification
                
            except Exception as e:
                logger.warning(f"Error parsing JSON from response: {e}")
                logger.warning(f"Raw response: {content}")
                
                # If parsing fails, try to extract using regex as fallback
                try:
                    import re
                    # Look for the score as a digit 0-3
                    score_match = re.search(r'"relevance_score"\s*:\s*([0-3])', content)
                    if score_match:
                        score = int(score_match.group(1))
                        # Try to extract justification
                        justification_match = re.search(r'"justification"\s*:\s*"([^"]*)"', content)
                        justification = justification_match.group(1) if justification_match else "No justification found"
                        return score, justification
                except:
                    pass
                
                # If all parsing attempts fail, use a conservative default score
                logger.warning(f"Failed to parse relevance score for chunk {chunk_id}, defaulting to 0")
                return 0, "Failed to parse judgment"
        
        except Exception as e:
            logger.error(f"Error judging chunk {chunk_id}: {e}")
            
            # Retry on API errors, with exponential backoff
            if retry_count < MAX_RETRIES:
                retry_delay = RETRY_DELAY * (2 ** retry_count)
                logger.info(f"Retrying in {retry_delay} seconds... (attempt {retry_count + 1}/{MAX_RETRIES})")
                time.sleep(retry_delay)
                return self.judge_chunk(
                    query_text, chunk_text, chunk_id, examples, category, retry_count + 1
                )
            else:
                logger.error(f"Max retries exceeded for chunk {chunk_id}")
                return 0, f"Error after {MAX_RETRIES} retries: {str(e)}"

def get_query_examples(db: IRDatabasePG, query_id: int) -> List[str]:
    """
    Get scoring examples for a specific query from the database.
    
    Args:
        db: Database connection
        query_id: ID of the query
        
    Returns:
        List of example strings, or empty list if none found
    """
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT examples FROM ir_eval.queries WHERE id = %s", (query_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result and result[0]:
            # result[0] should be a Postgres array (list in Python)
            return result[0]
        return []
    except Exception as e:
        logger.error(f"Error getting examples for query {query_id}: {e}")
        return []

def get_unjudged_results(
    db: IRDatabasePG,
    qrels: PGQRELSManager,
    run_id: int
) -> List[Dict[str, Any]]:
    """
    Get all unjudged results for a run.
    
    Args:
        db: Database connection
        qrels: QRELSManager instance
        run_id: ID of the run to get results for
        
    Returns:
        List of dictionaries with unjudged results
    """
    try:
        # Get all results for this run
        query_results = db.get_run_results(run_id)
        
        # Filter to only unjudged results
        unjudged_results = []
        
        for query_data in query_results:
            query_text = query_data.get("query", "")
            query_id = db.get_query_id(query_text)
            category = query_data.get("category", "unknown")
            name = query_data.get("name", "unknown")
            
            # Get examples for this query
            examples = get_query_examples(db, query_id) if query_id else []
            
            # Get already judged documents for this query
            judged_docs = qrels.get_judged_documents(query_text)
            
            # Filter to unjudged results
            for result in query_data.get("results", []):
                chunk_id = str(result.get("id", ""))
                
                if chunk_id not in judged_docs:
                    # Add necessary data to the result
                    result["query_text"] = query_text
                    result["query_id"] = query_id
                    result["category"] = category
                    result["name"] = name
                    result["examples"] = examples
                    
                    unjudged_results.append(result)
        
        return unjudged_results
    except Exception as e:
        logger.error(f"Error getting unjudged results for run {run_id}: {e}")
        return []

def judge_run(
    run_id: int,
    ai_judge: AIJudge,
    db: IRDatabasePG,
    qrels: PGQRELSManager,
) -> int:
    """
    Judge all unjudged results for a run.
    
    Args:
        run_id: ID of the run to judge
        ai_judge: AIJudge instance
        db: Database connection
        qrels: QRELSManager instance
        
    Returns:
        Number of judgments added
    """
    logger.info(f"Processing run {run_id}")
    
    # Get run metadata
    run_data = db.get_run_metadata(run_id)
    if not run_data:
        logger.error(f"No run found with ID {run_id}")
        return 0
    
    run_name = run_data.get("name", f"Run {run_id}")
    logger.info(f"Run: {run_name} (ID: {run_id})")
    
    # Get unjudged results
    unjudged_results = get_unjudged_results(db, qrels, run_id)
    logger.info(f"Found {len(unjudged_results)} unjudged results for run {run_id}")
    
    if not unjudged_results:
        logger.info(f"No unjudged results found for run {run_id}")
        return 0
    
    # Process results one at a time, saving after each
    judgments_added = 0
    
    # If in dry-run mode, only process the first result
    if ai_judge.dry_run and unjudged_results:
        unjudged_results = [unjudged_results[0]]
        logger.info(f"DRY RUN - Only processing 1 result for testing")
    
    for i, result in enumerate(unjudged_results):
        # Check if abort was requested
        if is_abort_requested():
            logger.info(f"Aborting after {judgments_added} judgments")
            return judgments_added
        
        chunk_id = str(result.get("id", ""))
        query_text = result.get("query_text", "")
        category = result.get("category", "unknown")
        examples = result.get("examples", [])
        text = result.get("text", "")
        
        logger.info(f"Processing result {i+1}/{len(unjudged_results)} - Chunk {chunk_id}, Query: {query_text[:50]}...")
        
        # Skip if no text content
        if not text:
            logger.warning(f"Skipping chunk {chunk_id} - No text content")
            continue
        
        # Judge the result
        relevance, reasoning = ai_judge.judge_chunk(
            query_text=query_text,
            chunk_text=text,
            chunk_id=chunk_id,
            examples=examples,
            category=category
        )
        
        logger.info(f"Judgment for chunk {chunk_id}: Score = {relevance}, Reasoning = {reasoning[:100]}...")
        
        # Skip saving in dry run mode
        if ai_judge.dry_run:
            logger.info("DRY RUN - Not saving judgment")
            judgments_added += 1
            continue
        
        # Add judgment to the database
        success = qrels.add_judgment(
            query=query_text,
            chunk_id=chunk_id,
            relevance=relevance,
            category=category,
            doc_text=text,
            justification=reasoning
        )
        
        if success:
            judgments_added += 1
            logger.info(f"Saved judgment {judgments_added} to database")
        else:
            logger.error(f"Failed to add judgment for chunk {chunk_id}")
        
        # After each judgment, check for abort again
        if is_abort_requested():
            logger.info(f"Aborting after {judgments_added} judgments")
            return judgments_added
    
    logger.info(f"Completed judging run {run_id}")
    logger.info(f"Added {judgments_added} new judgments")
    
    return judgments_added

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="AI-assisted judging for NEXUS IR evaluation system",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Create mutually exclusive group for run selection
    run_group = parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--run-id", type=int, help="ID of the run to judge")
    run_group.add_argument("--run-ids", help="Comma-separated list of run IDs to judge")
    
    # OpenAI options
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                      help=f"Model temperature (default: {DEFAULT_TEMPERATURE})")
    
    # Processing options
    parser.add_argument("--dry-run", action="store_true", help="Show what would be judged but don't update database")
    parser.add_argument("--debug", action="store_true", help="Print detailed debug information")
    parser.add_argument("--disable-abort", action="store_true", help="Disable ESC key and Ctrl+C abort capability")
    
    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    # Initialize database and QRELS manager
    db = IRDatabasePG()
    qrels = PGQRELSManager()
    
    # Set up abort handler (unless disabled)
    if not args.disable_abort:
        setup_abort_handler("Abort requested! Finishing current judgment and stopping...")
        logger.info("Abort functionality enabled - Press ESC or Ctrl+C to stop judging")
    else:
        logger.info("Abort functionality disabled")
    
    # Initialize AI judge
    ai_judge = AIJudge(
        model=args.model,
        temperature=args.temperature,
        dry_run=args.dry_run,
        debug=args.debug
    )
    
    # Set up run IDs to process
    run_ids = []
    if args.run_id:
        run_ids = [args.run_id]
    elif args.run_ids:
        try:
            run_ids = [int(id.strip()) for id in args.run_ids.split(",")]
        except ValueError:
            logger.error("Invalid run IDs format. Please use comma-separated integers.")
            return 1
    
    if not run_ids:
        logger.error("No run IDs specified")
        return 1
    
    # Process each run
    total_judgments = 0
    start_time = time.time()
    
    for run_id in run_ids:
        judgments = judge_run(
            run_id=run_id,
            ai_judge=ai_judge,
            db=db,
            qrels=qrels
        )
        total_judgments += judgments
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Print summary
    logger.info("=" * 60)
    logger.info(f"AI Judging Complete")
    logger.info(f"Total judgments added: {total_judgments}")
    logger.info(f"Total time: {elapsed:.2f} seconds")
    logger.info(f"Average time per judgment: {elapsed / max(1, total_judgments):.2f} seconds")
    logger.info("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())