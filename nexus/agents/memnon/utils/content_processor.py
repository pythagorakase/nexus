"""
Content Processor Module for MEMNON

Handles processing, chunking, and storage of narrative content.
"""

import logging
import re
import glob
import time
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from sqlalchemy import text

from .embedding_manager import EmbeddingManager
from .embedding_tables import resolve_dimension_table

logger = logging.getLogger("nexus.memnon.content_processor")

class ContentProcessor:
    """
    Handles processing, chunking, and storage of narrative content for MEMNON.
    """
    
    def __init__(self, 
                db_manager, 
                embedding_manager: EmbeddingManager, 
                settings: Dict[str, Any],
                load_aliases_func=None):
        """
        Initialize the ContentProcessor.
        
        Args:
            db_manager: Database manager for storing content
            embedding_manager: Embedding manager for generating embeddings
            settings: MEMNON settings dictionary
            load_aliases_func: Optional function to load character aliases
        """
        self.db_manager = db_manager
        self.embedding_manager = embedding_manager
        self.settings = settings
        self.load_aliases_func = load_aliases_func
        
        # Cache for character aliases
        self._character_aliases = None
        
        logger.info("ContentProcessor initialized")
    
    def process_all_narrative_files(self, glob_pattern: str = None) -> int:
        """
        Process all narrative files matching the glob pattern.
        
        Args:
            glob_pattern: Pattern to match files to process. 
                          If None, uses the pattern from settings.json
            
        Returns:
            Total number of chunks processed
        """
        # Use pattern from settings if not provided
        if glob_pattern is None:
            glob_pattern = self.settings.get("import", {}).get("file_pattern", "ALEX_*.md")
        
        # Get batch size from settings
        batch_size = self.settings.get("import", {}).get("batch_size", 10)
        verbose = self.settings.get("import", {}).get("verbose", True)
        
        # Find all files matching the pattern
        files = glob.glob(glob_pattern)
        
        if not files:
            logger.warning(f"No files found matching pattern: {glob_pattern}")
            return 0
        
        # Log settings used
        logger.info(f"Processing files with pattern: {glob_pattern}")
        logger.info(f"Batch size: {batch_size}")
        
        total_chunks = 0
        for i, file_path in enumerate(files):
            logger.info(f"Processing file {i+1}/{len(files)}: {file_path}")
            try:
                chunks_processed = self.process_chunked_file(file_path)
                total_chunks += chunks_processed
                
                # Process in batches to avoid overloading the system
                if batch_size > 0 and (i + 1) % batch_size == 0 and i < len(files) - 1:
                    logger.info(f"Completed batch of {batch_size} files. Taking a short break...")
                    time.sleep(2)  # Brief pause between batches
            
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
        
        logger.info(f"Completed processing {total_chunks} total chunks from {len(files)} files")
        return total_chunks
    
    def process_chunked_file(self, file_path: str) -> int:
        """
        Process a file containing chunked narrative text.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            Number of chunks processed
        """
        # Load file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise
        
        # Get regex pattern for chunk separation
        chunk_regex = self.settings.get("import", {}).get("chunk_regex", r"<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+))_(\d+).*-->")
        
        # Compile the pattern
        pattern = re.compile(chunk_regex)
        
        # Split by chunk markers
        chunks = []
        current_chunk = ""
        
        # Metadata tracking
        current_metadata = {
            "season": None,
            "episode": None,
            "scene": None,
        }
        
        # Map to track chunk IDs by their unique scene identifier
        chunk_id_map = {}
        
        # Process line by line
        lines = file_content.split("\n")
        for line in lines:
            # Check if line contains a chunk marker
            match = pattern.search(line)
            if match:
                # Store previous chunk if it exists
                if current_chunk.strip():
                    chunks.append({
                        "text": current_chunk.strip(),
                        "metadata": current_metadata.copy()
                    })
                
                # Start new chunk
                current_chunk = ""
                
                # Update metadata
                scene_id = match.group(1)
                current_metadata = {
                    "season": int(match.group(2)),
                    "episode": int(match.group(3)),
                    "scene": int(match.group(4)),
                    "scene_id": scene_id
                }
                
                # Parse any additional metadata in the comment
                # Formatted like: <!-- SCENE BREAK: S01E01_1 PERSPECTIVE:Alex LOCATION:"Night City Alley" -->
                metadata_text = line.split("SCENE BREAK:")[1] if "SCENE BREAK:" in line else ""
                
                # Parse perspective
                perspective_match = re.search(r"PERSPECTIVE:(\w+)", metadata_text)
                if perspective_match:
                    current_metadata["perspective"] = perspective_match.group(1)
                
                # Parse location
                location_match = re.search(r'LOCATION:"([^"]+)"', metadata_text)
                if location_match:
                    current_metadata["location"] = location_match.group(1)
                
                # Parse timecode
                time_match = re.search(r'TIME:"([^"]+)"', metadata_text)
                if time_match:
                    current_metadata["time_code"] = time_match.group(1)
                
                # Look for world layer marker
                world_layer_match = re.search(r'LAYER:"([^"]+)"', metadata_text)
                if world_layer_match:
                    current_metadata["world_layer"] = world_layer_match.group(1)
            else:
                # Not a marker, append to current chunk
                current_chunk += line + "\n"
        
        # Store last chunk if it exists
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "metadata": current_metadata.copy()
            })
        
        logger.info(f"Found {len(chunks)} chunks in file {file_path}")
        
        # Process chunks
        processed_count = 0
        for chunk in chunks:
            try:
                # Process chunk
                chunk_id = self.store_narrative_chunk(chunk["text"], chunk["metadata"])
                
                # Update tracking map
                if "scene_id" in chunk["metadata"]:
                    scene_id = chunk["metadata"]["scene_id"]
                    chunk_id_map[scene_id] = chunk_id
                
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing chunk: {e}")
        
        logger.info(f"Processed {processed_count} chunks from file {file_path}")
        return processed_count
    
    def store_narrative_chunk(self, text: str, metadata: Dict[str, Any]) -> int:
        """
        Store a narrative chunk in the database and generate embeddings.
        
        Args:
            text: The chunk text
            metadata: Metadata dictionary with season, episode, etc.
            
        Returns:
            The ID of the stored chunk
        """
        try:
            # Extract characters mentioned in the text
            character_mentions = self._extract_character_mentions(text)
            
            # Extract keywords
            keywords = self._extract_keywords(text)
            
            # Create session
            session = self.db_manager.create_session()
            
            try:
                # Start transaction
                with session.begin():
                    # Check if chunk already exists with this scene ID
                    if "scene_id" in metadata:
                        scene_id = metadata["scene_id"]
                        existing_id_query = text("""
                        SELECT nc.id 
                        FROM narrative_chunks nc
                        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                        WHERE cm.season = :season AND cm.episode = :episode AND cm.scene = :scene
                        """)
                        
                        result = session.execute(
                            existing_id_query,
                            {
                                "season": metadata["season"],
                                "episode": metadata["episode"],
                                "scene": metadata["scene"]
                            }
                        )
                        
                        existing_id = result.scalar()
                        if existing_id:
                            logger.info(f"Chunk already exists with ID {existing_id}, updating")
                            
                            # Update the chunk
                            chunk_update = text("""
                            UPDATE narrative_chunks
                            SET raw_text = :text
                            WHERE id = :id
                            """)
                            
                            session.execute(
                                chunk_update,
                                {"text": text, "id": existing_id}
                            )
                            
                            # Update metadata
                            metadata_update = text("""
                            UPDATE chunk_metadata
                            SET perspective = :perspective,
                                location = :location,
                                time_code = :time_code,
                                world_layer = :world_layer,
                                keywords = :keywords,
                                characters = :characters
                            WHERE chunk_id = :id
                            """)
                            
                            session.execute(
                                metadata_update,
                                {
                                    "id": existing_id,
                                    "perspective": metadata.get("perspective"),
                                    "location": metadata.get("location"),
                                    "time_code": metadata.get("time_code"),
                                    "world_layer": metadata.get("world_layer"),
                                    "keywords": keywords,
                                    "characters": character_mentions
                                }
                            )
                            
                            # Generate embeddings for this chunk
                            self._generate_chunk_embeddings(session, existing_id, text)
                            
                            return existing_id
                    
                    # Create new chunk
                    # First, insert the chunk
                    result = session.execute(
                        text("INSERT INTO narrative_chunks (raw_text) VALUES (:text) RETURNING id"),
                        {"text": text}
                    )
                    chunk_id = result.scalar()
                    
                    # Then insert metadata
                    metadata_insert = text("""
                    INSERT INTO chunk_metadata (
                        chunk_id, season, episode, scene, perspective, location, time_code, world_layer, keywords, characters
                    ) VALUES (
                        :chunk_id, :season, :episode, :scene, :perspective, :location, :time_code, :world_layer, :keywords, :characters
                    )
                    """)
                    
                    session.execute(
                        metadata_insert,
                        {
                            "chunk_id": chunk_id,
                            "season": metadata["season"],
                            "episode": metadata["episode"],
                            "scene": metadata["scene"],
                            "perspective": metadata.get("perspective"),
                            "location": metadata.get("location"),
                            "time_code": metadata.get("time_code"),
                            "world_layer": metadata.get("world_layer"),
                            "keywords": keywords,
                            "characters": character_mentions
                        }
                    )
                    
                    # Generate embeddings for this chunk
                    self._generate_chunk_embeddings(session, chunk_id, text)
                    
                # Transaction is automatically committed if no exceptions occurred
                logger.debug(f"Stored chunk {chunk_id} with metadata: {metadata}")
                return chunk_id
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error storing narrative chunk: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _generate_chunk_embeddings(self, session, chunk_id: int, text: str):
        """
        Generate embeddings for a chunk using all active models.
        Stores embeddings in dimension-specific tables with proper vector types.
        
        Args:
            session: The active database session
            chunk_id: The ID of the chunk
            text: The text to encode
        """
        # Use only active models from embedding manager
        for model_name in self.embedding_manager.get_available_models():
            try:
                # Generate embedding using embedding manager
                embedding = self.embedding_manager.generate_embedding(text, model_name)
                
                if embedding is None:
                    logger.warning(f"Embedding generation failed for model {model_name}, skipping")
                    continue
                    
                # Get embedding dimensions
                dim = len(embedding)
                logger.debug(f"Model {model_name} generated {dim}D embedding")
                
                # Format embedding as string for vector type
                embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                
                # Determine which table to use based on dimensions
                table_name = resolve_dimension_table(dim)
                if not table_name:
                    # No specific table exists for this dimension, log error
                    logger.error(f"No dimension-specific table for {dim}D vectors. Cannot store embedding.")
                    continue
                
                # Use dimension-specific table with proper vector type
                logger.debug(f"Using dimension-specific table {table_name} for {model_name}")
                
                # Check if embedding already exists in dimension table
                existing_query = text(f"""
                SELECT id FROM {table_name}
                WHERE chunk_id = :chunk_id AND model = :model
                """)
                
                result = session.execute(
                    existing_query,
                    {"chunk_id": chunk_id, "model": model_name}
                )
                
                existing_id = result.scalar()
                
                if existing_id:
                    # Update existing embedding with proper vector cast
                    embedding_update = text(f"""
                    UPDATE {table_name}
                    SET embedding = :embedding::vector({dim})
                    WHERE id = :id
                    """)
                    
                    session.execute(
                        embedding_update,
                        {"id": existing_id, "embedding": embedding_str}
                    )
                else:
                    # Insert new embedding with proper vector cast
                    embedding_insert = text(f"""
                    INSERT INTO {table_name} (chunk_id, model, embedding)
                    VALUES (:chunk_id, :model, :embedding::vector({dim}))
                    """)
                    
                    session.execute(
                        embedding_insert,
                        {
                            "chunk_id": chunk_id,
                            "model": model_name,
                            "embedding": embedding_str
                        }
                    )
                
                logger.debug(f"Generated {model_name} embedding for chunk {chunk_id}")
                
            except Exception as e:
                logger.error(f"Error generating {model_name} embedding for chunk {chunk_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    def _extract_character_mentions(self, text: str) -> List[str]:
        """
        Extract character mentions from text.
        
        Args:
            text: The text to analyze
            
        Returns:
            List of character names mentioned
        """
        # Load aliases if needed
        if self._character_aliases is None and self.load_aliases_func:
            self._character_aliases = self.load_aliases_func()
        
        # Default empty aliases dictionary if loading failed
        if not self._character_aliases:
            self._character_aliases = {}
        
        character_mentions = []
        
        # Check all possible character names
        for canonical_name, aliases in self._character_aliases.items():
            for alias in aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', text, re.IGNORECASE):
                    if canonical_name not in character_mentions:
                        character_mentions.append(canonical_name)
        
        return character_mentions
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract keywords from text.
        
        Args:
            text: The text to analyze
            
        Returns:
            List of keywords
        """
        keywords = []
        
        # Common themes and elements
        theme_terms = [
            "neural implant", "cybernetics", "augmentation", "corporation", "conspiracy",
            "memory", "identity", "consciousness", "AI", "network", "virtual", "hack",
            "combat", "mission", "operation", "corporate", "virus", "encryption"
        ]
        
        for term in theme_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', text, re.IGNORECASE):
                keywords.append(term.lower())
        
        return keywords 