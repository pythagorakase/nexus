#!/usr/bin/env python3
"""
classify_world_layers.py

This script classifies narrative chunks into world layers using an LLM (preferably OpenAI
for its structured output capabilities). World layer represents the narrative plane 
or dimension in which events occur.

Features:
- Batch processing with configurable batch size
- Character context from adjacent chunks for continuity
- Support for OpenAI's structured output with ENUMs
- Dry run mode for testing
- JSON output for statistics

Usage:
    python classify_world_layers.py --range 1 100 --batch-size 10
    python classify_world_layers.py --all --provider openai --model gpt-4o-mini
    python classify_world_layers.py --missing --dry-run
    python classify_world_layers.py --output-json world_layer_stats.json
"""

import os
import sys
import argparse
import logging
import json
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

# Import the main processor class
from batch_metadata_processing import (
    MetadataProcessor, LLMProvider, OpenAIProvider, 
    get_db_connection_string, NarrativeChunk, ChunkMetadata
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("world_layer_classification.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.world_layer")

# Possible world layer values as documented in the schema
WORLD_LAYERS = [
    "primary",
    "secondary",
    "memory",
    "dream",
    "vision",
    "simulation",
    "virtual",
    "alternate",
    "liminal"
]

class WorldLayerClassifier:
    """Classifies narrative chunks into world layers."""
    
    def __init__(self, db_url: str, 
                processor: MetadataProcessor,
                dry_run: bool = False,
                overwrite_existing: bool = False):
        """
        Initialize the world layer classifier.
        
        Args:
            db_url: PostgreSQL database URL
            processor: Initialized MetadataProcessor instance
            dry_run: If True, don't actually save results to the database
            overwrite_existing: If True, overwrite existing world_layer values
        """
        self.db_url = db_url
        self.processor = processor
        self.dry_run = dry_run
        self.overwrite_existing = overwrite_existing
        
        # Statistics
        self.stats = {
            "total_chunks": 0,
            "processed_chunks": 0,
            "api_calls": 0,
            "api_errors": 0,
            "updated_metadata": 0,
            "tokens_used": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_estimate": 0.0,
            "provider": processor.stats["provider"],
            "model": processor.stats["model"],
            "world_layers": {layer: 0 for layer in WORLD_LAYERS + ["unknown"]}
        }
    
    def process_chunks(self, chunks: List[NarrativeChunk], batch_size: int = 10) -> Dict[str, Any]:
        """
        Process narrative chunks to classify their world layers.
        
        Args:
            chunks: List of chunks to process
            batch_size: Number of chunks to process in each batch
            
        Returns:
            Statistics dictionary
        """
        if not chunks:
            logger.info("No chunks to process")
            return self.stats
            
        self.stats["total_chunks"] = len(chunks)
        logger.info(f"Processing {len(chunks)} chunks in batches of {batch_size}")
        
        # Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} of {(len(chunks) + batch_size - 1) // batch_size}")
            
            try:
                # Process the entire batch
                batch_result = self.classify_batch(batch)
                
                # Update stats
                for chunk_id, layer in batch_result.items():
                    # Find the chunk with this ID
                    chunk = next((c for c in batch if str(c.id) == str(chunk_id)), None)
                    if chunk:
                        self.update_world_layer(chunk, layer)
                        self.stats["processed_chunks"] += 1
                        # Update layer statistics
                        if layer in self.stats["world_layers"]:
                            self.stats["world_layers"][layer] += 1
                        else:
                            self.stats["world_layers"]["unknown"] += 1
                    else:
                        logger.warning(f"Chunk with ID {chunk_id} not found in batch")
                
            except Exception as e:
                logger.error(f"Error processing batch: {str(e)}")
                
            # Show progress
            cost = self.stats["cost_estimate"]
            logger.info(f"Batch complete. Progress: {self.stats['processed_chunks']}/{self.stats['total_chunks']}")
            logger.info(f"API calls: {self.stats['api_calls']} (errors: {self.stats['api_errors']})")
            logger.info(f"Tokens: {self.stats['tokens_used']} total (est. cost: ${cost:.4f})")
            
            # If this isn't the last batch, ask to continue
            if i + batch_size < len(chunks) and not self.dry_run:
                continue_val = input(f"Continue with next batch? [Y/n]: ")
                if continue_val.lower() == 'n':
                    logger.info("Processing stopped by user")
                    break
        
        return self.stats
    
    def classify_batch(self, chunks: List[NarrativeChunk]) -> Dict[str, str]:
        """
        Classify a batch of chunks by their world layer.
        
        Args:
            chunks: List of chunks to classify
            
        Returns:
            Dictionary mapping chunk IDs to world layer values
        """
        if not chunks:
            return {}
        
        # Use the processor to handle the API call
        if isinstance(self.processor.llm, OpenAIProvider):
            # OpenAI provider - use the function calling capability
            result = self.classify_batch_with_openai(chunks)
        else:
            # Other providers - build a custom prompt
            result = self.classify_batch_generic(chunks)
        
        # Update statistics from the processor
        self.stats["api_calls"] += self.processor.stats["api_calls"] - self.stats["api_calls"]
        self.stats["api_errors"] += self.processor.stats["api_errors"] - self.stats["api_errors"]
        self.stats["tokens_used"] += self.processor.stats["tokens_used"] - self.stats["tokens_used"]
        self.stats["input_tokens"] += self.processor.stats["input_tokens"] - self.stats["input_tokens"]
        self.stats["output_tokens"] += self.processor.stats["output_tokens"] - self.stats["output_tokens"]
        self.stats["cost_estimate"] += self.processor.stats["cost_estimate"] - self.stats["cost_estimate"]
        
        return result
    
    def classify_batch_with_openai(self, chunks: List[NarrativeChunk]) -> Dict[str, str]:
        """
        Classify chunks using OpenAI's function calling for structured output.
        
        Args:
            chunks: List of chunks to classify
            
        Returns:
            Dictionary mapping chunk IDs to world layer values
        """
        # Define the schema for structured output
        functions = [
            {
                "name": "classify_world_layers",
                "description": "Classify narrative chunks into world layers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "chunk_id": {
                                        "type": "string",
                                        "description": "The ID of the narrative chunk"
                                    },
                                    "world_layer": {
                                        "type": "string",
                                        "enum": WORLD_LAYERS,
                                        "description": "The world layer classification for this chunk"
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                        "description": "Confidence score for this classification (0-1)"
                                    },
                                    "reasoning": {
                                        "type": "string",
                                        "description": "Brief reasoning for this classification"
                                    }
                                },
                                "required": ["chunk_id", "world_layer"]
                            }
                        }
                    },
                    "required": ["classifications"]
                }
            }
        ]
        
        # Build the prompt
        prompt = """You are an expert narrative analyst specializing in determining the world layer of narrative passages. 
World layer refers to the narrative plane or dimension in which events occur.

World Layers:
- primary: The main reality/timeline of the narrative
- secondary: A different but equally "real" plane (like a parallel storyline)
- memory: Flashbacks or recollections
- dream: Dream sequences or dream-like states
- vision: Prophetic or hallucinatory visions
- simulation: Artificial or simulated realities
- virtual: Digital or virtual reality spaces
- alternate: Alternate timelines or realities
- liminal: Threshold spaces between worlds/realities

I'll provide you with narrative passages. For each, determine which world layer it belongs to.
Think carefully about textual clues that indicate shifts in reality level, consciousness, or timeline.
"""
        
        # Add chunks
        for chunk in chunks:
            prompt += f"\n\nCHUNK {chunk.id}:\n{chunk.raw_text}"
        
        # Add the system prompt to use structured output
        response = self.processor.llm.client.chat.completions.create(
            model=self.processor.llm.model,
            messages=[
                {"role": "system", "content": "You are a narrative analysis assistant with expertise in classifying world layers in fiction."},
                {"role": "user", "content": prompt}
            ],
            functions=functions,
            function_call={"name": "classify_world_layers"}
        )
        
        # Extract the function arguments from the JSON string
        function_args = json.loads(response.choices[0].message.function_call.arguments)
        
        # Convert the result to our expected format
        result = {}
        for item in function_args["classifications"]:
            result[item["chunk_id"]] = item["world_layer"]
            
            # Log the reasoning if available
            if "reasoning" in item:
                logger.info(f"Chunk {item['chunk_id']} classified as '{item['world_layer']}': {item['reasoning']}")
        
        return result
    
    def classify_batch_generic(self, chunks: List[NarrativeChunk]) -> Dict[str, str]:
        """
        Classify chunks using a generic prompt for any LLM provider.
        
        Args:
            chunks: List of chunks to classify
            
        Returns:
            Dictionary mapping chunk IDs to world layer values
        """
        # Build a prompt for the model
        prompt = """You are an expert narrative analyst specializing in determining the world layer of narrative passages. 
World layer refers to the narrative plane or dimension in which events occur.

World Layers:
- primary: The main reality/timeline of the narrative
- secondary: A different but equally "real" plane (like a parallel storyline)
- memory: Flashbacks or recollections
- dream: Dream sequences or dream-like states
- vision: Prophetic or hallucinatory visions
- simulation: Artificial or simulated realities
- virtual: Digital or virtual reality spaces
- alternate: Alternate timelines or realities
- liminal: Threshold spaces between worlds/realities

I'll provide you with narrative passages. For each, determine which world layer it belongs to.
Think carefully about textual clues that indicate shifts in reality level, consciousness, or timeline.

Return your analysis as a JSON object with chunk IDs as keys and world layer values as values. Example:

```json
{
  "1": "primary",
  "2": "memory",
  "3": "primary"
}
```

Only use the world layer values from the list above. Your response must be ONLY a valid JSON object.
"""
        
        # Add chunks
        for chunk in chunks:
            prompt += f"\n\nCHUNK {chunk.id}:\n{chunk.raw_text}"
        
        # Call the LLM API
        response = self.processor.llm.get_completion(prompt)
        
        # Parse JSON response
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        return json.loads(content)
    
    def update_world_layer(self, chunk: NarrativeChunk, world_layer: str) -> None:
        """
        Update the world_layer field in a chunk's metadata.
        
        Args:
            chunk: The narrative chunk to update
            world_layer: The world layer classification
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would set world_layer for chunk {chunk.id} to '{world_layer}'")
            return
            
        # Use the Session from the processor
        session = self.processor.Session()
        try:
            # Check if metadata already exists
            metadata = session.query(ChunkMetadata).filter(ChunkMetadata.chunk_id == chunk.id).first()
            
            if metadata:
                # Check if we should update the existing value
                if self.overwrite_existing or metadata.world_layer is None:
                    # If value exists and we're overwriting, or if it's null
                    if metadata.world_layer is not None and metadata.world_layer != world_layer:
                        logger.info(f"Overwriting existing world_layer for chunk {chunk.id}: '{metadata.world_layer}' -> '{world_layer}'")
                    
                    # Update the field
                    metadata.world_layer = world_layer
                    session.commit()
                    self.stats["updated_metadata"] += 1
                    logger.info(f"Updated world_layer for chunk {chunk.id} to '{world_layer}'")
                else:
                    # Skip updating because it already has a value and we're not overwriting
                    logger.info(f"Skipping chunk {chunk.id} - already has world_layer '{metadata.world_layer}' and overwrite_existing=False")
            else:
                # Create new metadata record with just the world_layer
                new_metadata = ChunkMetadata(
                    chunk_id=chunk.id,
                    world_layer=world_layer
                )
                session.add(new_metadata)
                session.commit()
                self.stats["updated_metadata"] += 1
                logger.info(f"Created metadata for chunk {chunk.id} with world_layer '{world_layer}'")
                
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating world_layer for chunk {chunk.id}: {str(e)}")
        finally:
            session.close()


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Classify narrative chunks into world layers")
    
    # Chunk selection options
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process all chunks")
    group.add_argument("--missing", action="store_true", help="Process only chunks without world_layer")
    group.add_argument("--range", nargs=2, type=int, metavar=("START", "END"),
                      help="Process chunks in an ID range (inclusive)")
    
    # Provider options
    provider_group = parser.add_argument_group("Provider Options")
    provider_group.add_argument("--provider", choices=["openai", "anthropic"], default="openai",
                             help="LLM provider to use (default: openai)")
    provider_group.add_argument("--model", 
                             help="Model name (defaults to provider's default)")
    provider_group.add_argument("--api-key", help="API key (optional)")
    provider_group.add_argument("--temperature", type=float, default=0.1,
                             help="Model temperature (default: 0.1)")
    
    # Processing options
    process_group = parser.add_argument_group("Processing Options")
    process_group.add_argument("--batch-size", type=int, default=10,
                             help="Number of chunks to process in each batch (default: 10)")
    process_group.add_argument("--edge-context", type=int, default=500,
                             help="Characters of context to include from adjacent chunks (default: 500)")
    process_group.add_argument("--dry-run", action="store_true", 
                             help="Don't actually save results to the database")
    process_group.add_argument("--overwrite-existing", action="store_true",
                             help="Overwrite existing world_layer values")
    process_group.add_argument("--save-prompt", action="store_true",
                             help="Save the generated prompts to files")
    process_group.add_argument("--db-url", 
                             help="Database connection URL (optional, defaults to environment variables or NEXUS database on localhost)")
    process_group.add_argument("--output-json", help="Save statistics to JSON file")
    
    args = parser.parse_args()
    
    # Get database connection
    db_url = args.db_url or get_db_connection_string()
    
    try:
        # Initialize the metadata processor
        processor = MetadataProcessor(
            db_url=db_url,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key,
            dry_run=args.dry_run,
            save_prompt=args.save_prompt,
            temperature=args.temperature,
            batch_mode=True,  # Always use batch mode
            edge_context_chars=args.edge_context
        )
        
        # Initialize the world layer classifier
        classifier = WorldLayerClassifier(
            db_url=db_url,
            processor=processor,
            dry_run=args.dry_run,
            overwrite_existing=args.overwrite_existing
        )
        
        # Determine which chunks to process
        if args.all:
            logger.info("Processing all chunks")
            chunks = processor.get_all_chunks()
            
        elif args.missing:
            logger.info("Processing chunks without world_layer")
            session = processor.Session()
            try:
                # Find chunks that have no metadata or have metadata with null world_layer
                chunks = session.query(NarrativeChunk)\
                    .outerjoin(ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id)\
                    .filter((ChunkMetadata.id == None) | (ChunkMetadata.world_layer == None))\
                    .order_by(NarrativeChunk.id).all()
            finally:
                session.close()
                
        elif args.range:
            start, end = args.range
            logger.info(f"Processing chunks in ID range {start}-{end}")
            chunks = processor.get_chunks_by_id_range(start, end)
        
        # Process chunks
        stats = classifier.process_chunks(chunks, batch_size=args.batch_size)
        
        # Print summary
        logger.info("\nProcessing Summary:")
        logger.info(f"Provider: {stats['provider']}")
        logger.info(f"Model: {stats['model']}")
        logger.info(f"Total chunks: {stats['total_chunks']}")
        logger.info(f"Processed chunks: {stats['processed_chunks']}")
        logger.info(f"API calls: {stats['api_calls']} (errors: {stats['api_errors']})")
        logger.info(f"Tokens: {stats['tokens_used']} total ({stats['input_tokens']} input, {stats['output_tokens']} output)")
        logger.info(f"Estimated cost: ${stats['cost_estimate']:.4f}")
        
        if args.dry_run:
            logger.info("DRY RUN: No changes were made to the database")
        else:
            logger.info(f"Updated metadata records: {stats['updated_metadata']}")
        
        # Print world layer distribution
        logger.info("\nWorld Layer Distribution:")
        for layer, count in stats["world_layers"].items():
            if count > 0:
                logger.info(f"  {layer}: {count} chunks ({count/stats['processed_chunks']*100:.1f}%)")
        
        # Save stats to JSON if requested
        if args.output_json:
            try:
                stats_copy = stats.copy()
                stats_copy["run_completed_at"] = datetime.utcnow().isoformat() + "Z"
                stats_copy["command_line_args"] = vars(args)
                
                with open(args.output_json, 'w') as f:
                    json.dump(stats_copy, f, indent=2)
                logger.info(f"Statistics saved to {args.output_json}")
            except Exception as e:
                logger.error(f"Failed to save statistics to {args.output_json}: {str(e)}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())