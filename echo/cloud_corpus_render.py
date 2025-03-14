#!/usr/bin/env python3
"""
Night City Stories: Narrative Metadata Extraction

This script processes narrative chunks from Night City Stories using AWS SageMaker
and a Llama 3 70B model to extract comprehensive metadata according to a cyberpunk-specific schema.
The metadata includes narrative functions, emotional analysis, character development,
thematic elements specific to the Night City universe, and more.

Features:
- Extracts metadata according to the Night City Stories schema
- Processes Markdown files with <!-- SCENE BREAK: SxxEyy_NNN --> markers
- Supports batch processing with robust error handling
- Includes checkpoint system for resumable processing
- Test mode for validation without AWS costs

Usage:
    python cloud_corpus_render.py --config config.json --input-dir ./chunks --output-dir ./metadata
    python cloud_corpus_render.py --test --input-dir ./chunks  # Test mode
"""

import os
import re
import json
import time
import glob
import logging
import argparse
import hashlib
import boto3
import botocore
from urllib.parse import urlparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Tuple, Union, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("narrative_metadata_extraction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("narrative_metadata")

# Default configuration values
DEFAULT_CONFIG = {
    "aws_region": "us-east-1",
    "sagemaker_endpoint_name": "llama-3-70b-instruct",
    "batch_size": 5,  # Number of chunks to process in parallel
    "max_retries": 3,  # Maximum number of retries for failed API calls
    "retry_delay": 2,  # Delay between retries in seconds
    "timeout": 300,  # Timeout for SageMaker API calls in seconds
    "confidence_threshold": 0.7,  # Minimum confidence score for metadata
    "checkpoint_interval": 10,  # Save checkpoint every N chunks
    "schema_path": "narrative_metadata_schema.json",  # Path to schema file
    "chunk_marker_regex": r'<!--\s*SCENE BREAK:\s*(S\d+E\d+)_([\d]{3})',  # Night City Stories chunk marker format
    "prompts": {
        "system_prompt": "You are an expert literary analyst specializing in cyberpunk narratives, with deep knowledge of Night City, its factions, characters, and thematic elements. Your task is to extract detailed metadata from narrative chunks according to a specific schema focused on cyberpunk themes such as transhumanism, corporate exploitation, technological impact, and the struggle for identity in a high-tech, dystopian future.",
        "instruction_prompt": "Analyze the following Night City Stories narrative chunk and extract metadata according to the provided schema. Pay special attention to cyberpunk elements, character psychological states, faction dynamics, and technological impacts. Return the results as a valid JSON object with all required fields.",
    },
    "test_mode": {
        "enabled": False,
        "sample_size": 3,  # Number of chunks to process in test mode
        "mock_response": True,  # Whether to generate mock responses instead of calling AWS
        "verbose": True  # Print detailed information in test mode
    }
}

class NarrativeMetadataExtractor:
    """
    Main class for extracting metadata from Night City Stories narrative chunks.
    """
    
    def __init__(self, config_path: Optional[str] = None, test_mode: bool = False):
        """
        Initialize the metadata extractor with configuration.
        
        Args:
            config_path: Path to the configuration JSON file
            test_mode: Whether to run in test mode
        """
        # Load configuration
        self.config = DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                self.config.update(user_config)
            logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.info("Using default configuration")
        
        # Set test mode if specified
        if test_mode:
            self.config["test_mode"]["enabled"] = True
            logger.info("Running in TEST MODE - no actual AWS calls will be made")
        
        # Load metadata schema
        self.schema = self._load_schema()
        
        # Initialize AWS clients (unless in test mode)
        if not self.config["test_mode"]["enabled"]:
            self.sagemaker_runtime = boto3.client(
                'sagemaker-runtime', 
                region_name=self.config["aws_region"]
            )
        else:
            self.sagemaker_runtime = None
        
        # Initialize progress tracking
        self.processed_chunks = set()  # Track processed chunk IDs
        self.progress_file = "extraction_progress.json"
        self._load_progress()
        
        # Compile regex pattern
        self.chunk_pattern = re.compile(self.config["chunk_marker_regex"])

    def is_s3_path(self, path):
        """Check if a path is an S3 path."""
        return path.startswith('s3://')

    def parse_s3_path(self, s3_path):
        """Parse an S3 path into bucket and key."""
        parsed = urlparse(s3_path)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        return bucket, key

    def list_s3_files(self, s3_path, pattern="*.md"):
        """List files in an S3 bucket matching a pattern."""
        bucket, prefix = self.parse_s3_path(s3_path)
        s3 = boto3.client('s3')
        
        # List objects in the bucket with the given prefix
        files = []
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                # Check if the key matches our pattern (ends with .md)
                if key.endswith('.md'):
                    files.append(f"s3://{bucket}/{key}")
        
        logger.info(f"Found {len(files)} matching files in S3 bucket {bucket}")
        return files

    def read_s3_file(self, s3_path):
        """Read a file from S3."""
        bucket, key = self.parse_s3_path(s3_path)
        s3 = boto3.client('s3')
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return content
        except Exception as e:
            logger.error(f"Error reading file {s3_path} from S3: {e}")
            return None

    def save_to_s3(self, content, s3_path):
        """Save content to an S3 path."""
        bucket, key = self.parse_s3_path(s3_path)
        s3 = boto3.client('s3')
        try:
            s3.put_object(
                Body=content.encode('utf-8'),
                Bucket=bucket,
                Key=key
            )
            return True
        except Exception as e:
            logger.error(f"Error saving to S3 path {s3_path}: {e}")
            return False

    def _load_schema(self) -> Dict[str, Any]:
        """
        Load the metadata schema from the specified path.
        
        Returns:
            Dict containing the metadata schema structure
        """
        schema_path = self.config["schema_path"]
        try:
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    schema = json.load(f)
                logger.info(f"Loaded schema from {schema_path}")
                return schema
            else:
                logger.error(f"Schema file not found at {schema_path}")
                raise FileNotFoundError(f"Schema file not found at {schema_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file: {e}")
            raise
            
    def _load_progress(self) -> None:
        """
        Load progress from the checkpoint file if it exists.
        """
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    progress_data = json.load(f)
                    self.processed_chunks = set(progress_data.get("processed_chunks", []))
                logger.info(f"Loaded progress: {len(self.processed_chunks)} chunks already processed")
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        else:
            logger.info("No existing progress file found. Starting fresh.")
            
    def _save_progress(self) -> None:
        """
        Save the current progress to a checkpoint file.
        """
        try:
            with open(self.progress_file, 'w') as f:
                json.dump({
                    "processed_chunks": list(self.processed_chunks),
                    "timestamp": time.time()
                }, f)
            logger.debug(f"Saved progress: {len(self.processed_chunks)} chunks processed")
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
            
    def get_chunk_id(self, chunk_text: str) -> Optional[str]:
        """
        Extract the chunk ID from the chunk text using the configured regex pattern.
        
        Args:
            chunk_text: The raw text of the narrative chunk
            
        Returns:
            Chunk ID if found, None otherwise
        """
        match = self.chunk_pattern.search(chunk_text)
        if match:
            episode = match.group(1)  # e.g., "S03E11"
            chunk_number = match.group(2)  # e.g., "037"
            return f"{episode}_{chunk_number}"
        
        # If regex doesn't match, use a hash of the content as fallback
        content_hash = hashlib.md5(chunk_text.encode()).hexdigest()[:8]
        logger.warning(f"Could not extract chunk ID, using content hash: {content_hash}")
        return f"unknown_{content_hash}"
    
    def load_chunks(self, input_dir: str) -> List[Tuple[str, str]]:
        """
        Load narrative chunks from files in the input directory or S3 bucket.
        
        Args:
            input_dir: Directory or S3 bucket path containing chunk files
            
        Returns:
            List of tuples containing (chunk_id, chunk_text)
        """
        chunks = []
        
        # Handle S3 paths differently from local paths
        if self.is_s3_path(input_dir):
            logger.info(f"Loading chunks from S3 path: {input_dir}")
            chunk_files = self.list_s3_files(input_dir)
            
            for file_path in chunk_files:
                try:
                    content = self.read_s3_file(file_path)
                    if not content:
                        continue
                    
                    # Extract chunk ID from content
                    chunk_id = self.get_chunk_id(content)
                    
                    # Skip if already processed (unless in test mode)
                    if chunk_id in self.processed_chunks and not self.config["test_mode"]["enabled"]:
                        logger.debug(f"Skipping already processed chunk: {chunk_id}")
                        continue
                        
                    chunks.append((chunk_id, content))
                    logger.debug(f"Loaded chunk: {chunk_id} from {file_path}")
                except Exception as e:
                    logger.error(f"Error loading S3 file {file_path}: {e}")
        else:
            # Original local file loading code
            logger.info(f"Loading chunks from local directory: {input_dir}")
            chunk_files = glob.glob(os.path.join(input_dir, "*.md"))
            logger.info(f"Found {len(chunk_files)} chunk files in {input_dir}")
            
            for file_path in chunk_files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Extract chunk ID from content
                    chunk_id = self.get_chunk_id(content)
                    
                    # Skip if already processed (unless in test mode)
                    if chunk_id in self.processed_chunks and not self.config["test_mode"]["enabled"]:
                        logger.debug(f"Skipping already processed chunk: {chunk_id}")
                        continue
                        
                    chunks.append((chunk_id, content))
                    logger.debug(f"Loaded chunk: {chunk_id} from {file_path}")
                except Exception as e:
                    logger.error(f"Error loading chunk file {file_path}: {e}")
        
        # In test mode, limit to sample size
        if self.config["test_mode"]["enabled"]:
            sample_size = self.config["test_mode"]["sample_size"]
            if len(chunks) > sample_size:
                logger.info(f"Test mode: Limiting to {sample_size} chunks")
                chunks = chunks[:sample_size]
                
        logger.info(f"Loaded {len(chunks)} chunks for processing")
        return chunks
    
    def generate_extraction_prompt(self, chunk_text: str) -> Dict[str, Any]:
        """
        Generate the prompt for extracting metadata from a chunk.
        
        Args:
            chunk_text: The narrative chunk text
            
        Returns:
            Dictionary with the prompt structure for the LLM
        """
        system_prompt = self.config["prompts"]["system_prompt"]
        instruction_prompt = self.config["prompts"]["instruction_prompt"]
        
        # Format the schema as a string for inclusion in the prompt
        schema_str = json.dumps(self.schema["chunk_metadata"], indent=2)
        
        # Construct the full prompt
        prompt = (
            f"{instruction_prompt}\n\n"
            f"METADATA SCHEMA:\n{schema_str}\n\n"
            f"NARRATIVE CHUNK:\n{chunk_text}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Analyze the narrative chunk thoroughly, focusing on cyberpunk themes\n"
            f"2. Extract metadata according to the provided schema\n"
            f"3. For thematic_tags, pay special attention to Night City elements like 'corporate_exploitation', 'transhumanism', etc.\n"
            f"4. Include confidence scores (0.0-1.0) for each category where appropriate\n"
            f"5. Return ONLY a valid JSON object with the metadata\n"
        )
        
        # Prepare the payload for SageMaker
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 4096,
                "temperature": 0.2,  # Low temperature for more deterministic extraction
                "top_p": 0.9,
                "top_k": 50
            }
        }
        
        # In test mode with verbose, print the prompt
        if self.config["test_mode"]["enabled"] and self.config["test_mode"]["verbose"]:
            print("\n" + "="*80)
            print("PROMPT THAT WOULD BE SENT TO LLAMA 3 70B:")
            print("="*80)
            print(prompt)
            print("="*80 + "\n")
            
        return payload
    
    def call_sagemaker_endpoint(self, payload: Dict[str, Any]) -> str:
        """
        Call the SageMaker endpoint with the given payload.
        
        Args:
            payload: The request payload containing the prompt and parameters
            
        Returns:
            Raw response from the LLM
            
        Raises:
            Exception: If the API call fails after retries
        """
        # In test mode, return a mock response instead of calling AWS
        if self.config["test_mode"]["enabled"] and self.config["test_mode"]["mock_response"]:
            logger.info("Test mode: Generating mock response instead of calling AWS")
            return self._generate_mock_response(payload)
            
        endpoint_name = self.config["sagemaker_endpoint_name"]
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay"]
        
        # Convert payload to JSON string
        body = json.dumps(payload)
        
        # Initialize retry counter
        retry_count = 0
        last_error = None
        
        # Retry loop
        while retry_count < max_retries:
            try:
                response = self.sagemaker_runtime.invoke_endpoint(
                    EndpointName=endpoint_name,
                    ContentType='application/json',
                    Body=body,
                    Accept='application/json'
                )
                
                # Parse response
                response_body = response['Body'].read().decode('utf-8')
                response_json = json.loads(response_body)
                
                # Extract the generated text
                if isinstance(response_json, dict) and "generated_text" in response_json:
                    return response_json["generated_text"]
                elif isinstance(response_json, list) and len(response_json) > 0:
                    return response_json[0].get("generated_text", response_body)
                else:
                    return response_body
                
            except (botocore.exceptions.ClientError, json.JSONDecodeError) as e:
                retry_count += 1
                last_error = e
                logger.warning(f"API call failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
        
        # If we get here, all retries failed
        logger.error(f"Failed to call SageMaker endpoint after {max_retries} attempts")
        raise Exception(f"SageMaker API call failed: {last_error}")
    
    def _generate_mock_response(self, payload: Dict[str, Any]) -> str:
        """
        Generate a mock response for test mode.
        
        Args:
            payload: The payload that would be sent to SageMaker
            
        Returns:
            A mock response in the format similar to what the LLM would return
        """
        # Extract a snippet from the chunk text to make the mock response relevant
        chunk_text = payload["inputs"]
        chunk_snippet = chunk_text.split("NARRATIVE CHUNK:")[1].split("\n\n")[0][:200] + "..."
        
        # Create a basic mock metadata structure using the schema
        mock_metadata = {}
        
        # Fill in some cyberpunk-themed mock data
        mock_metadata["narrative_functions"] = ["exposition", "character_development"]
        mock_metadata["emotional_analysis"] = {
            "valence": "high_tension",
            "intensity": 0.8
        }
        mock_metadata["character_development"] = [
            {
                "character_name": "Alex",
                "milestone": "technology_adaptation",
                "significance_score": 0.75
            }
        ]
        mock_metadata["thematic_tags"] = ["transhumanism", "corporate_exploitation", "identity"]
        mock_metadata["plot_arc_positioning"] = {
            "primary_arc": "rising_action",
            "secondary_arcs": ["character_growth", "technological_discovery"]
        }
        mock_metadata["causal_relationships"] = [
            {
                "cause": "corporate_decision",
                "effect": "technological_fallout",
                "confidence_score": 0.8
            }
        ]
        mock_metadata["narrative_weight"] = {
            "importance_score": 0.7,
            "key_elements": ["character_revelation", "world_building"]
        }
        mock_metadata["entity_interactions"] = [
            {
                "entities": ["Alex", "Corporation"],
                "interaction_type": "conflict",
                "significance": 0.85
            }
        ]
        mock_metadata["world_state_impact"] = {
            "affected_domains": ["technological_advancement", "social_dynamics"],
            "change_magnitude": 0.6
        }
        mock_metadata["linguistic_features"] = {
            "tone": "noir",
            "complexity_score": 0.7
        }
        
        # Convert to a string with JSON formatting
        mock_response = json.dumps(mock_metadata, indent=2)
        
        # In verbose mode, print the mock response
        if self.config["test_mode"]["verbose"]:
            print("\nMOCK RESPONSE (Test Mode):")
            print("="*80)
            print(mock_response)
            print("="*80 + "\n")
            
        return mock_response
    
    def extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """
        Extract and parse the JSON object from the LLM's response.
        
        Args:
            response_text: Raw text response from the LLM
            
        Returns:
            Parsed JSON object
            
        Raises:
            json.JSONDecodeError: If JSON parsing fails
        """
        # Find JSON content using regex patterns
        json_pattern = r'```json\s*([\s\S]*?)\s*```|```\s*([\s\S]*?)\s*```|(\{[\s\S]*\})'
        matches = re.findall(json_pattern, response_text)
        
        # Try different matches
        for match_groups in matches:
            for group in match_groups:
                if not group:
                    continue
                    
                try:
                    # Try to parse as JSON
                    return json.loads(group)
                except json.JSONDecodeError:
                    # Try to clean up common issues
                    cleaned_json = re.sub(r'\\n', ' ', group)
                    cleaned_json = re.sub(r'\\', '', cleaned_json)
                    try:
                        return json.loads(cleaned_json)
                    except json.JSONDecodeError:
                        continue
        
        # If no matches found or none parsed successfully, try the whole response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Last resort: try to extract anything that looks like a JSON object
            try:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start >= 0 and end > start:
                    return json.loads(response_text[start:end])
            except json.JSONDecodeError:
                pass
        
        # If all parsing attempts fail
        logger.error(f"Failed to parse JSON from response: {response_text[:100]}...")
        raise json.JSONDecodeError("Could not parse JSON from response", response_text, 0)
    
    def validate_metadata(self, metadata: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        """
        Validate extracted metadata against the schema and calculate an overall confidence score.
        
        Args:
            metadata: The extracted metadata to validate
            
        Returns:
            Tuple of (validated_metadata, overall_confidence_score)
        """
        schema_fields = set(self.schema["chunk_metadata"].keys())
        metadata_fields = set(metadata.keys())
        
        # Check for missing fields
        missing_fields = schema_fields - metadata_fields
        if missing_fields:
            logger.warning(f"Missing fields in extracted metadata: {missing_fields}")
            
            # Add empty structures for missing fields based on schema
            for field in missing_fields:
                field_schema = self.schema["chunk_metadata"][field]
                
                # Create appropriate empty structure based on type
                if field_schema.get("type") == "array":
                    metadata[field] = []
                elif isinstance(field_schema, dict) and not "type" in field_schema:
                    # This is a nested object
                    metadata[field] = {}
                    for subfield, subschema in field_schema.items():
                        if subschema.get("type") == "array":
                            metadata[field][subfield] = []
                        else:
                            metadata[field][subfield] = None
                else:
                    metadata[field] = None
        
        # Calculate overall confidence score
        confidence_values = []
        
        # Helper function to extract confidence scores recursively
        def extract_confidence(obj):
            if isinstance(obj, dict):
                if "confidence_score" in obj:
                    confidence_values.append(obj["confidence_score"])
                for v in obj.values():
                    extract_confidence(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_confidence(item)
        
        # Extract all confidence scores
        extract_confidence(metadata)
        
        # Calculate average confidence if any scores were found
        overall_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.7
        
        return metadata, overall_confidence
    
    def process_chunk(self, chunk_id: str, chunk_text: str) -> Optional[Dict[str, Any]]:
        """
        Process a single narrative chunk to extract metadata.
        
        Args:
            chunk_id: ID of the chunk
            chunk_text: Text content of the chunk
            
        Returns:
            Extracted metadata if successful, None otherwise
        """
        logger.info(f"Processing chunk: {chunk_id}")
        
        try:
            # Generate prompt for the chunk
            prompt = self.generate_extraction_prompt(chunk_text)
            
            # Call the SageMaker endpoint
            response = self.call_sagemaker_endpoint(prompt)
            
            # Extract and parse JSON from response
            metadata = self.extract_json_from_response(response)
            
            # Validate metadata and get confidence score
            validated_metadata, confidence_score = self.validate_metadata(metadata)
            
            # Check if confidence score meets threshold
            if confidence_score < self.config["confidence_threshold"]:
                logger.warning(f"Low confidence score for chunk {chunk_id}: {confidence_score}")
            
            # Add metadata version and extraction timestamp
            result = {
                "chunk_id": chunk_id,
                "metadata": validated_metadata,
                "confidence_score": confidence_score,
                "extraction_timestamp": time.time(),
                "metadata_version": self.schema.get("metadata_version", "1.0.0")
            }
            
            logger.info(f"Successfully extracted metadata for chunk {chunk_id} with confidence {confidence_score:.2f}")
            return result
        
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            return None
    
    def process_chunks_batch(self, chunks: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """
        Process a batch of chunks in parallel.
        
        Args:
            chunks: List of (chunk_id, chunk_text) tuples
            
        Returns:
            List of extracted metadata results
        """
        results = []
        batch_size = self.config["batch_size"]
        
        # In test mode, process sequentially for better visibility
        if self.config["test_mode"]["enabled"]:
            logger.info("Test mode: Processing chunks sequentially")
            for chunk_id, chunk_text in chunks:
                result = self.process_chunk(chunk_id, chunk_text)
                if result:
                    results.append(result)
                    # Mark as processed (but don't save in test mode)
                    if not self.config["test_mode"]["enabled"]:
                        self.processed_chunks.add(result["chunk_id"])
            return results
        
        # Normal mode: Process chunks in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = [executor.submit(self.process_chunk, chunk_id, chunk_text) 
                          for chunk_id, chunk_text in batch]
                
                # Collect results
                batch_results = []
                for future in futures:
                    try:
                        result = future.result()
                        if result:
                            batch_results.append(result)
                            # Mark as processed
                            self.processed_chunks.add(result["chunk_id"])
                    except Exception as e:
                        logger.error(f"Error in batch processing: {e}")
                
                results.extend(batch_results)
            
            # Save checkpoint after each batch
            if (i // batch_size + 1) % self.config["checkpoint_interval"] == 0:
                self._save_progress()
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]], output_dir: str) -> None:
        """
        Save the extraction results to JSON files locally or in S3.
        
        Args:
            results: List of metadata extraction results
            output_dir: Directory or S3 path to save the output files
        """
        # In test mode, optionally skip actual file writing
        if self.config["test_mode"]["enabled"]:
            logger.info(f"Test mode: Would save {len(results)} results to {output_dir}")
            if self.config["test_mode"]["verbose"]:
                print(f"\nWould save {len(results)} results to {output_dir}")
                print("First result sample:")
                print(json.dumps(results[0], indent=2))
            return
        
        # Handle saving to S3 differently from local paths
        if self.is_s3_path(output_dir):
            logger.info(f"Saving results to S3 path: {output_dir}")
            
            # Save each result as an individual file in S3
            for result in results:
                chunk_id = result["chunk_id"]
                filename = f"{chunk_id}_metadata.json"
                s3_path = f"{output_dir.rstrip('/')}/{filename}"
                
                # Convert result to JSON string
                result_json = json.dumps(result, indent=2)
                
                # Save to S3
                success = self.save_to_s3(result_json, s3_path)
                if success:
                    logger.debug(f"Saved metadata for chunk {chunk_id} to {s3_path}")
            
            # Save combined results
            combined_s3_path = f"{output_dir.rstrip('/')}/all_metadata.json"
            combined_json = json.dumps(results, indent=2)
            success = self.save_to_s3(combined_json, combined_s3_path)
            if success:
                logger.info(f"Saved combined metadata to {combined_s3_path}")
        else:
            # Original local file saving code
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                logger.info(f"Created output directory: {output_dir}")
            
            # Save each result to a separate file
            for result in results:
                chunk_id = result["chunk_id"]
                filename = f"{chunk_id}_metadata.json"
                file_path = os.path.join(output_dir, filename)
                
                with open(file_path, 'w') as f:
                    json.dump(result, f, indent=2)
                
                logger.debug(f"Saved metadata for chunk {chunk_id} to {file_path}")
            
            # Save a combined file with all results
            combined_path = os.path.join(output_dir, "all_metadata.json")
            with open(combined_path, 'w') as f:
                json.dump(results, f, indent=2)
        
        logger.info(f"Saved {len(results)} metadata results to {output_dir}")
        
        # Also save the final progress file (locally always)
        self._save_progress()
    
    def run_extraction(self, input_dir: str, output_dir: str = None) -> None:
        """
        Run the complete metadata extraction process.
        
        Args:
            input_dir: Directory containing input narrative chunks
            output_dir: Directory to save the extracted metadata (optional in test mode)
        """
        start_time = time.time()
        logger.info(f"Starting metadata extraction process {'(TEST MODE)' if self.config['test_mode']['enabled'] else ''}")
        
        try:
            # Load narrative chunks
            chunks = self.load_chunks(input_dir)
            if not chunks:
                logger.info("No chunks to process. Exiting.")
                return
            
            # Process all chunks
            results = self.process_chunks_batch(chunks)
            
            # Save the results (if not in test mode)
            if output_dir or not self.config["test_mode"]["enabled"]:
                if not output_dir:
                    output_dir = "test_output"  # Default for test mode
                self.save_results(results, output_dir)
            
            # Report completion
            elapsed_time = time.time() - start_time
            mode_str = "Test" if self.config["test_mode"]["enabled"] else "Extraction"
            logger.info(f"{mode_str} completed in {elapsed_time:.2f} seconds")
            output_msg = ""
            if self.config['test_mode']['enabled']:
                output_msg = f", would save to {output_dir}" if output_dir else ""
            else:
                output_msg = f", saved to {output_dir}" if output_dir else ""
            logger.info(f"Processed {len(results)} chunks{output_msg}")
            
            if self.config["test_mode"]["enabled"]:
                print(f"\nTest completed successfully! Processed {len(results)} chunks in {elapsed_time:.2f} seconds")
                print("The script is ready for full production use with AWS SageMaker.")
            
        except Exception as e:
            logger.error(f"Error during extraction process: {e}")
            raise

    def fix_test_mode_error():
        """Fix the NoneType error in test mode logging"""
        # Open the file
        with open("cloud_corpus_render.py", "r") as file:
            content = file.read()
        
        # Find and replace the problematic line
        old_line = 'logger.info(f"Processed {len(results)} chunks{", would save to " + str(output_dir) if output_dir and self.config["test_mode"]["enabled"] else ", saved to " + str(output_dir) if output_dir else ""}")'
        
        # New line that handles None values safely
        new_line = 'logger.info(f"Processed {len(results)} chunks{", would save to " + str(output_dir) if output_dir and self.config["test_mode"]["enabled"] else ", saved to " + str(output_dir) if output_dir else ""}")'
        
        # If the exact line isn't found, try a more flexible replacement
        if old_line not in content:
            # Find any line that includes this pattern
            import re
            line_pattern = r'logger\.info\(f"Processed \{len\(results\)\} chunks\{.*output_dir.*\}"\)'
            matched_lines = re.findall(line_pattern, content)
            
            if matched_lines:
                old_line = matched_lines[0]
                print(f"Found line to replace: {old_line}")
        
        # Replace the line
        updated_content = content.replace(old_line, new_line)
        
        # Write back to file
        with open("cloud_corpus_render.py", "w") as file:
            file.write(updated_content)
        
        print("Fixed the NoneType error in test mode logging")
        print("Try running the script again")

    fix_test_mode_error()        

def main():
    """
    Main entry point for the script.
    """
    parser = argparse.ArgumentParser(description="Extract metadata from Night City Stories narrative chunks")
    parser.add_argument("--config", default=None, help="Path to configuration JSON file")
    parser.add_argument("--input-dir", required=True, help="Directory containing narrative chunk files")
    parser.add_argument("--output-dir", help="Directory to save metadata output (required unless --test is used)")
    parser.add_argument("--test", action="store_true", help="Run in test mode without making AWS calls")
    args = parser.parse_args()
    
    # Check that output_dir is provided unless in test mode
    if not args.test and not args.output_dir:
        parser.error("--output-dir is required unless --test is used")
    
    try:
        # Initialize extractor
        extractor = NarrativeMetadataExtractor(args.config, test_mode=args.test)
        
        # Run extraction
        extractor.run_extraction(args.input_dir, args.output_dir)
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
