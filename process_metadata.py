#!/usr/bin/env python3
"""
NEXUS Metadata Processing Script

This script handles both export and import operations for narrative metadata:
1. Export narrative chunks with context information to a structured JSON file
2. Import processed metadata from a JSON file back into the PostgreSQL database

Features:
- Support for both export and import modes via CLI arguments
- Context chunks for better LLM analysis
- LLM-friendly JSON structure
- Schema information inclusion in export mode
- Database connection configuration
- Error handling
- Batch processing with start/end sequence IDs
- Progress reporting

Usage Examples:
    # Export mode - single batch:
    python process_metadata.py export --start 11 --end 30 --output batch_0011_to_0030.json

    # Export mode - multiple batches:
    python process_metadata.py export --start 11 --end 100 --batch 20

    # Import mode - single file:
    python process_metadata.py import --input batch_0011_to_0030_processed.json

    # Import mode - multiple files using pattern:
    python process_metadata.py import --pattern "batch_*_processed.json"

Note: 
- For import mode, use '--input' to specify a single file or '--pattern' for multiple files
- The script requires subcommands 'export' or 'import' before the arguments
"""

import argparse
import json
import os
import logging
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker, relationship
from sqlalchemy.sql import func

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('metadata_processing.log')
    ]
)
logger = logging.getLogger(__name__)

# Database models
Base = declarative_base()

class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(Integer, primary_key=True)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    id = Column(Integer, primary_key=True)
    chunk_id = Column(Integer, ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    # Basic metadata fields
    season = Column(Integer)
    episode = Column(Integer)
    scene = Column(Integer)
    world_layer = Column(String(50))
    time_delta = Column(String(100))
    location = Column(String(255))
    atmosphere = Column(String(255))
    
    # Arc and narrative positioning
    arc_position = Column(String(50))
    magnitude = Column(String(50))
    
    # Complex fields stored as JSONB
    characters = Column(JSONB)
    direction = Column(JSONB)
    character_elements = Column(JSONB)
    perspective = Column(JSONB)
    interactions = Column(JSONB)
    dialogue_analysis = Column(JSONB)
    emotional_tone = Column(JSONB)
    narrative_function = Column(JSONB)
    narrative_techniques = Column(JSONB)
    thematic_elements = Column(JSONB)
    causality = Column(JSONB)
    continuity_markers = Column(JSONB)
    
    # Metadata about metadata
    metadata_version = Column(String(20))
    generation_date = Column(DateTime)
    
    # Relationship to parent chunk
    chunk = relationship("NarrativeChunk", backref="metadata")

def get_db_connection():
    """Get database connection from environment variables or settings."""
    # Try to load from settings.json first
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
            db_url = settings.get("Agent Settings", {}).get("MEMNON", {}).get("database", {}).get("url")
            if db_url:
                return db_url
    except Exception as e:
        logger.warning(f"Failed to load database URL from settings.json: {e}")
    
    # Fall back to environment variables
    DB_USER = os.environ.get("DB_USER", "pythagor")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "NEXUS")
    
    if DB_PASSWORD:
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def load_metadata_schema() -> Dict:
    """Load metadata schema from file."""
    schema_path = "narrative_metadata_schema_modified.json"
    if not os.path.exists(schema_path):
        logger.warning(f"Modified schema file not found at {schema_path}, falling back to original schema")
        schema_path = "narrative_metadata_schema_2.json"
        if not os.path.exists(schema_path):
            logger.warning(f"Original schema file not found at {schema_path}")
            return {}
    
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load schema: {e}")
        return {}

def export_chunks(start_id: int, end_id: int, output_file: str, db_url: str, 
                  context_size: int = 2, include_schema: bool = True) -> None:
    """
    Export narrative chunks to JSON file.
    
    Args:
        start_id: Starting chunk ID
        end_id: Ending chunk ID
        output_file: Output JSON file path
        db_url: Database connection URL
        context_size: Number of context chunks to include before/after the batch
        include_schema: Whether to include metadata schema
    """
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Build output structure
        output = {
            "instructions": generate_instructions(),
            "chunks": []
        }
        
        # Add schema if requested
        if include_schema:
            schema = load_metadata_schema()
            if schema:
                output["metadata_schema"] = schema
        
        # Query chunks in the batch
        chunks = session.query(NarrativeChunk)\
            .filter(NarrativeChunk.id >= start_id)\
            .filter(NarrativeChunk.id <= end_id)\
            .order_by(NarrativeChunk.id).all()
        
        if not chunks:
            logger.warning(f"No chunks found in range {start_id}-{end_id}")
            return
            
        logger.info(f"Found {len(chunks)} chunks in range {start_id}-{end_id}")
        
        # Get external context once - chunks before the batch
        external_preceding = session.query(NarrativeChunk)\
            .filter(NarrativeChunk.id < start_id)\
            .order_by(NarrativeChunk.id.desc())\
            .limit(context_size).all()
        external_preceding.reverse()  # Put in chronological order
        
        # Get external context once - chunks after the batch
        external_following = session.query(NarrativeChunk)\
            .filter(NarrativeChunk.id > end_id)\
            .order_by(NarrativeChunk.id)\
            .limit(context_size).all()
        
        # The full set of chunks in order is: external_preceding + chunks + external_following
        # We'll provide this as context for the LLM to understand the narrative flow
        
        # All the chunks will be sent to the LLM, but we organize them as:
        # 1. Main chunks (the ones we want metadata for)
        # 2. Context chunks (external ones that provide context)
        
        # Process each chunk in the batch
        for chunk in chunks:
            # Get existing metadata
            existing_meta = session.query(ChunkMetadata)\
                .filter(ChunkMetadata.chunk_id == chunk.id).first()
            
            # Initialize chunk data without context
            chunk_data = {
                "chunk_id": chunk.id,
                "text": chunk.raw_text
            }
            
            # Add ONLY season, episode, and scene from existing metadata
            if existing_meta:
                # Extract ONLY these specific fields to preserve
                preserved_fields = {
                    "season": existing_meta.season,
                    "episode": existing_meta.episode,
                    "scene": existing_meta.scene
                }
                
                # Filter out None values
                preserved_fields = {k: v for k, v in preserved_fields.items() if v is not None}
                
                if preserved_fields:
                    chunk_data["essential_metadata"] = preserved_fields
            
            output["chunks"].append(chunk_data)
        
        # Add batch context information only once, at the top level
        if external_preceding or external_following:
            output["batch_context"] = {}
            
            if external_preceding:
                output["batch_context"]["preceding"] = [
                    {"id": c.id, "text": c.raw_text}
                    for c in external_preceding
                ]
                
            if external_following:
                output["batch_context"]["following"] = [
                    {"id": c.id, "text": c.raw_text}
                    for c in external_following
                ]
                
            # Add a note explaining how to use the batch context
            output["batch_context_note"] = (
                "These chunks provide context for the entire batch. They should be "
                "considered when analyzing all chunks to maintain narrative continuity."
            )
        
        # Write to file
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Exported {len(chunks)} chunks to {output_file}")
    
    except Exception as e:
        logger.error(f"Error exporting chunks: {e}", exc_info=True)
        raise
    finally:
        session.close()

def import_metadata(input_file: str, db_url: str) -> None:
    """
    Import processed metadata from JSON file.
    
    Args:
        input_file: Input JSON file with processed metadata
        db_url: Database connection URL
    """
    if not os.path.exists(input_file):
        logger.error(f"Input file not found: {input_file}")
        return
    
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        processed = 0
        errors = 0
        
        # Check various possible structures for results
        if isinstance(data, list):
            # Direct array of results
            results = data
        elif "results" in data and isinstance(data["results"], list):
            # Nested under "results" key
            results = data["results"]
        elif "chunks" in data and isinstance(data["chunks"], list):
            # Results may be under a "chunks" key
            results = data["chunks"] 
        else:
            # Try to look for array values that might contain our results
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and "chunk_id" in value[0]:
                    results = value
                    break
            else:
                results = []
                logger.error("Could not find results array in input file")
        
        logger.info(f"Found {len(results)} metadata entries to import")
        
        for item in results:
            try:
                # Get chunk ID - it could be at the top level or nested in the orientation section
                chunk_id = item.get("chunk_id")
                
                # If not at top level, try to get it from the orientation section
                if not chunk_id and "orientation" in item and isinstance(item["orientation"], dict):
                    chunk_id = item["orientation"].get("chunk_id")
                
                if not chunk_id:
                    logger.error("Missing chunk_id in result item")
                    errors += 1
                    continue
                
                # Check if metadata exists
                existing = session.query(ChunkMetadata)\
                    .filter(ChunkMetadata.chunk_id == chunk_id).first()
                
                # Extract metadata from result
                metadata = extract_metadata_from_result(item)
                
                if existing:
                    # Update existing entry
                    for key, value in metadata.items():
                        if value is not None:  # Only update if we have a value
                            setattr(existing, key, value)
                    
                    logger.debug(f"Updated metadata for chunk {chunk_id}")
                else:
                    # Create new entry
                    metadata['chunk_id'] = chunk_id
                    new_metadata = ChunkMetadata(**metadata)
                    session.add(new_metadata)
                    logger.debug(f"Created new metadata for chunk {chunk_id}")
                
                processed += 1
                if processed % 10 == 0:
                    logger.info(f"Processed {processed}/{len(results)} entries")
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_id}: {e}")
                errors += 1
        
        # Commit changes
        session.commit()
        logger.info(f"Successfully imported {processed} metadata entries ({errors} errors)")
    
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
    finally:
        session.close()

def extract_metadata_from_result(item: Dict) -> Dict:
    """Extract metadata fields from a result item."""
    # This function maps the LLM output format to database fields
    metadata = {}
    
    # First, preserve the essential metadata from what we sent
    essential = item.get("essential_metadata", {})
    if essential:
        for key in ["season", "episode", "scene"]:
            if key in essential and essential[key] is not None:
                metadata[key] = essential[key]
    
    # Handle orientation fields
    if "orientation" in item:
        orientation = item.get("orientation", {})
        
        # Skip chunk_id in orientation since we handle it separately
        
        # Extract scalar fields
        if "world_layer" in orientation:
            metadata["world_layer"] = orientation.get("world_layer")
            
        # Handle setting subfields
        setting = orientation.get("setting", {})
        if isinstance(setting, dict):
            if "location" in setting:
                metadata["location"] = setting.get("location")
            if "atmosphere" in setting:
                metadata["atmosphere"] = setting.get("atmosphere")
        
        # Handle continuity markers (JSONB)
        if "continuity_markers" in orientation:
            metadata["continuity_markers"] = orientation.get("continuity_markers")
    
    # Handle narrative vector fields
    if "narrative_vector" in item:
        vector = item.get("narrative_vector", {})
        
        # Extract scalar fields
        if "arc_position" in vector:
            metadata["arc_position"] = vector.get("arc_position")
        if "magnitude" in vector:
            metadata["magnitude"] = vector.get("magnitude")
        
        # Extract JSONB field
        if "direction" in vector:
            metadata["direction"] = vector.get("direction")
    
    # Handle character-related fields (all JSONB)
    if "characters" in item:
        chars = item.get("characters", {})
        metadata["characters"] = chars
        
        # Character subfields
        if "elements" in chars:
            metadata["character_elements"] = chars.get("elements")
        if "perspective" in chars:
            metadata["perspective"] = chars.get("perspective")
        if "interactions" in chars:
            metadata["interactions"] = chars.get("interactions")
    
    # Handle prose-related fields (all JSONB)
    if "prose" in item:
        prose = item.get("prose", {})
        
        if "dialogue_analysis" in prose:
            metadata["dialogue_analysis"] = prose.get("dialogue_analysis")
        if "emotional_tone" in prose:
            metadata["emotional_tone"] = prose.get("emotional_tone")
        if "function" in prose:
            metadata["narrative_function"] = prose.get("function")
        if "narrative_techniques" in prose:
            metadata["narrative_techniques"] = prose.get("narrative_techniques")
        if "thematic_elements" in prose:
            metadata["thematic_elements"] = prose.get("thematic_elements")
    
    # Handle causality field (JSONB)
    if "causality" in item:
        metadata["causality"] = item.get("causality")
    
    # Set metadata version and generation date
    metadata["metadata_version"] = "2.0"
    metadata["generation_date"] = datetime.now()
    
    return metadata

def get_nested_value(data: Dict, path: str) -> Any:
    """Get a value from a nested dictionary using a dotted path string."""
    parts = path.split('.')
    current = data
    
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    
    return current

def generate_instructions() -> str:
    """Generate instructions for the LLM."""
    return """
# Narrative Metadata Analysis Task

You are an expert narrative analyst working on an AI-driven interactive storytelling project. 
Your task is to analyze each narrative chunk and generate rich, detailed metadata according to 
the provided schema.

## Batch Context
This is a batch of narrative chunks that are sequential in the story. At the top level, you'll 
find "batch_context" with preceding and following chunks that provide context for the entire 
batch. Use this broader context to understand the narrative flow and maintain continuity 
across all your analysis.

## Analysis Guidelines
For each chunk, carefully consider:

1. **Characters**: Who appears, their interactions, and emotional states
2. **Narrative Vector**: The direction and magnitude of story movement
3. **Prose Elements**: Dialogue, emotional tone, techniques used
4. **Thematic Elements**: Core themes, motifs, and symbolic elements
5. **Continuity**: How this chunk connects to the broader narrative

## Output Format
The JSON schema is provided at the top level of this request under the "metadata_schema" key.
Your task is to follow this schema exactly, providing a JSON array where each object corresponds 
to one chunk in the batch.

IMPORTANT NOTES:
- Your response must be a valid JSON array containing metadata for ALL chunks
- Follow the schema exactly - do not add or remove fields
- Only analyze the fields defined in the schema
- Analyze each chunk deeply, looking beyond surface-level text
- Focus on meaningful narrative analysis rather than arbitrary classification
- Maintain narrative continuity across the entire batch
- Consider how each chunk relates to others in the sequence
"""

def main():
    parser = argparse.ArgumentParser(
        description="Process narrative metadata",
        epilog="""
Examples:
  Export chunks 11-30:
    python process_metadata.py export --start 11 --end 30
    
  Import a processed file:
    python process_metadata.py import --input batch_0011_to_0030_processed.json
    
  Import multiple files:
    python process_metadata.py import --pattern "batch_*_processed.json"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode", required=True)
    
    # Export parser
    export_parser = subparsers.add_parser("export", help="Export chunks to JSON")
    export_parser.add_argument("--start", type=int, required=True, help="Starting chunk ID")
    export_parser.add_argument("--end", type=int, required=True, help="Ending chunk ID")
    export_parser.add_argument("--batch", type=int, help="Batch size for splitting into multiple files")
    export_parser.add_argument("--output", type=str, help="Output JSON file (optional, defaults to batch_START_to_END.json)")
    export_parser.add_argument("--context", type=int, default=2, help="Number of context chunks (default: 2)")
    export_parser.add_argument("--no-schema", action="store_true", help="Skip including schema in output")
    export_parser.add_argument("--db-url", type=str, help="Database URL (optional)")
    
    # Import parser
    import_parser = subparsers.add_parser("import", help="Import metadata from JSON")
    import_group = import_parser.add_mutually_exclusive_group(required=True)
    import_group.add_argument("--input", type=str, help="Input JSON file")
    import_group.add_argument("--pattern", type=str, help="Glob pattern for batch imports (e.g., 'batch_*_processed.json')")
    import_parser.add_argument("--db-url", type=str, help="Database URL (optional)")
    
    args = parser.parse_args()
    
    # Get database connection
    db_url = args.db_url if hasattr(args, 'db_url') and args.db_url else get_db_connection()
    
    if args.mode == "export":
        # Check if we should split into batches
        if args.batch:
            # Process in batches
            batch_size = args.batch
            total_batches = (args.end - args.start + 1 + batch_size - 1) // batch_size  # Ceiling division
            
            logger.info(f"Processing {args.end - args.start + 1} chunks in {total_batches} batches of size {batch_size}")
            
            for i in range(total_batches):
                batch_start = args.start + i * batch_size
                batch_end = min(batch_start + batch_size - 1, args.end)
                
                # Generate filename for this batch
                output_file = f"batch_{batch_start:04d}_to_{batch_end:04d}.json"
                
                logger.info(f"Exporting batch {i+1}/{total_batches}: chunks {batch_start}-{batch_end} to {output_file}")
                
                export_chunks(
                    start_id=batch_start,
                    end_id=batch_end,
                    output_file=output_file,
                    db_url=db_url,
                    context_size=args.context,
                    include_schema=not args.no_schema
                )
                
            logger.info(f"Exported {total_batches} batch files successfully")
        else:
            # Process as a single batch
            # Generate automatic output filename if not provided
            output_file = args.output
            if not output_file:
                output_file = f"batch_{args.start:04d}_to_{args.end:04d}.json"
            
            logger.info(f"Exporting chunks {args.start}-{args.end} to {output_file}")
            export_chunks(
                start_id=args.start,
                end_id=args.end,
                output_file=output_file,
                db_url=db_url,
                context_size=args.context,
                include_schema=not args.no_schema
            )
    elif args.mode == "import":
        if args.pattern:
            # Import multiple files matching the pattern
            import glob
            matching_files = glob.glob(args.pattern)
            
            if not matching_files:
                logger.error(f"No files found matching pattern '{args.pattern}'")
                return 1
                
            logger.info(f"Found {len(matching_files)} files matching pattern '{args.pattern}'")
            
            for i, input_file in enumerate(sorted(matching_files)):
                logger.info(f"Importing file {i+1}/{len(matching_files)}: {input_file}")
                import_metadata(
                    input_file=input_file,
                    db_url=db_url
                )
                
            logger.info(f"Imported {len(matching_files)} files successfully")
        elif args.input:
            # Import a single file
            logger.info(f"Importing metadata from {args.input}")
            import_metadata(
                input_file=args.input,
                db_url=db_url
            )
        else:
            logger.error("Either --input or --pattern must be specified for import mode")
            return 1
    else:
        parser.print_help()

if __name__ == "__main__":
    main()