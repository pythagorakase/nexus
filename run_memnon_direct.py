#!/usr/bin/env python3
"""
Interactive MEMNON Agent Runner (Direct Mode)

This script provides a simple interactive interface for directly querying the MEMNON agent,
bypassing the Letta framework's agent loading mechanism.
"""

import sys
import os
import json
import logging
import traceback
from typing import Dict, Any, List

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("memnon_direct.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("memnon-direct")

# Add nexus directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json file"""
    try:
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                logger.info(f"Successfully loaded settings from {settings_path}")
                return settings
        else:
            logger.warning(f"Warning: settings.json not found at {settings_path}")
            return {}
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}

def check_environment():
    """Check environment prerequisites"""
    logger.info("Checking environment...")
    
    # Check if PostgreSQL is running
    try:
        import psycopg2
        import sqlalchemy
        logger.info("PostgreSQL libraries found")
    except ImportError:
        logger.error("PostgreSQL libraries not found. Run: pip install psycopg2-binary sqlalchemy")
        return False
    
    # Check if models are available
    try:
        import sentence_transformers
        logger.info("Sentence Transformers library found")
    except ImportError:
        logger.error("Sentence Transformers library not found. Run: pip install sentence-transformers")
        return False
    
    # Check if necessary files exist
    memnon_path = os.path.join(os.path.dirname(__file__), "nexus", "agents", "memnon", "memnon.py")
    if not os.path.exists(memnon_path):
        logger.error(f"MEMNON implementation not found at {memnon_path}")
        return False
    
    logger.info("Environment check completed")
    return True

def initialize_memnon(db_url, model_id, debug):
    """Initialize MEMNON with detailed logging"""
    logger.info("Starting MEMNON initialization...")
    
    try:
        # Import the MEMNON class
        from nexus.agents.memnon.memnon import MEMNON
        logger.info("Successfully imported MEMNON class")
        
        # Create a simple StreamingInterface class to handle output
        class SimpleInterface:
            def assistant_message(self, message):
                print(f"\n{message}\n")
        
        logger.info("Created SimpleInterface")
        
        # Instantiate the MEMNON agent directly with verbose logging
        logger.info(f"Initializing MEMNON with: db_url={db_url}, model_id={model_id}, debug={debug}")
        
        memnon = MEMNON(
            interface=SimpleInterface(),
            agent_state=None,  # Pass None since we'll bypass Letta's agent handling
            user=None,  # Pass None since we'll bypass Letta's user handling
            db_url=db_url,
            model_id=model_id,
            debug=debug
        )
        
        logger.info("MEMNON initialized successfully")
        return memnon
        
    except Exception as e:
        logger.error(f"Error initializing MEMNON: {e}")
        traceback.print_exc()
        return None

def process_query(memnon, user_input):
    """Process user query with detailed error handling"""
    logger.info(f"Processing query: '{user_input}'")
    
    try:
        if user_input.lower() == "status":
            logger.info("Getting MEMNON status")
            return memnon._get_status()
            
        elif user_input.lower().startswith("process_files"):
            # Extract pattern if specified
            parts = user_input.split("pattern=")
            pattern = parts[1].strip() if len(parts) > 1 else None
            logger.info(f"Processing files with pattern: {pattern}")
            processed = memnon.process_all_narrative_files(pattern)
            return f"Processed {processed} chunks from narrative files"
            
        elif user_input.lower() == "test_llm":
            # Test the LLM API connection directly
            logger.info("Testing LLM API connection")
            try:
                import requests
                import time
                
                # Get API endpoint from settings
                # First try getting it from MEMNON_SETTINGS
                try:
                    from nexus.agents.memnon.memnon import MEMNON_SETTINGS
                    api_base = MEMNON_SETTINGS.get("llm", {}).get("api_base", "http://localhost:1234")
                except:
                    # Fallback to default
                    api_base = "http://localhost:1234"
                
                model_id = memnon.model_id
                
                # Test the models endpoint
                start_time = time.time()
                models_response = requests.get(f"{api_base}/v1/models", timeout=5)
                models_time = time.time() - start_time
                
                result = f"Models endpoint: {models_response.status_code} ({models_time:.2f}s)\n"
                if models_response.status_code == 200:
                    models = models_response.json()
                    model_ids = [model["id"] for model in models.get("data", [])]
                    result += f"Available models: {', '.join(model_ids)}\n"
                    result += f"Selected model: {model_id}\n"
                
                # Test the completions endpoint with a simple prompt
                start_time = time.time()
                result += "\nTesting completions with 60 second timeout...\n"
                result += "(This may take a while if the model is still loading in LM Studio)\n"
                try:
                    payload = {
                        "model": model_id,
                        "prompt": "Hello, how are you?",
                        "temperature": 0.2,
                        "max_tokens": 20,
                        "stream": False
                    }
                    completions_response = requests.post(
                        f"{api_base}/v1/completions", 
                        json=payload, 
                        headers={"Content-Type": "application/json"},
                        timeout=60  # 1 minute timeout for model loading
                    )
                    completions_time = time.time() - start_time
                    
                    result += f"Completions endpoint: {completions_response.status_code} ({completions_time:.2f}s)\n"
                    if completions_response.status_code == 200:
                        response_data = completions_response.json()
                        if "choices" in response_data and len(response_data["choices"]) > 0:
                            text = response_data["choices"][0].get("text", "")
                            result += f"Response: {text}\n"
                    
                except requests.exceptions.Timeout:
                    result += "Completions endpoint: TIMEOUT (>60s)\n"
                    result += "The LLM is likely still loading. Check the LM Studio interface to see loading progress.\n"
                    result += "Try again in a few minutes. For large models (70B+), full loading may take 5-10 minutes.\n"
                    
                except Exception as e:
                    result += f"Completions error: {str(e)}\n"
                
                return result
                
            except Exception as e:
                return f"Error testing LLM API: {str(e)}"
            
        elif user_input.lower().startswith("no_llm_query"):
            # Query without using LLM for response synthesis
            # Extract the actual query
            query = user_input[len("no_llm_query"):].strip()
            if not query:
                return "Please provide a query after 'no_llm_query'"
                
            logger.info(f"Processing query without LLM: '{query}'")
            query_info = memnon._analyze_query(query, None)
            logger.info(f"Query analyzed as type: {query_info['type']}")
            
            query_results = memnon.query_memory(
                query=query,
                query_type=query_info["type"],
                filters={},
                k=5
            )
            
            # Format results directly without using LLM
            results = query_results["results"]
            if not results:
                return "No results found for your query."
            
            formatted_result = f"Found {len(results)} results for query: '{query}'\n\n"
            for i, result in enumerate(results[:5]):  # Show top 5 results
                formatted_result += f"Result {i+1} (Score: {result.get('score', 0):.4f}):\n"
                
                if result.get("type") == "narrative_chunk":
                    # For narrative chunks, show a snippet
                    content = result.get("content", "")
                    if len(content) > 300:
                        content = content[:297] + "..."
                    formatted_result += f"Content: {content}\n"
                    
                    # Add metadata
                    metadata = result.get("metadata", {})
                    formatted_result += f"Metadata: Season {metadata.get('season', 'N/A')}, "
                    formatted_result += f"Episode {metadata.get('episode', 'N/A')}, "
                    formatted_result += f"Scene {metadata.get('scene_number', 'N/A')}\n"
                    
                elif result.get("type") == "character":
                    # For character entries
                    content = result.get("content", {})
                    formatted_result += f"Character: {content.get('name', 'Unknown')}\n"
                    formatted_result += f"Summary: {content.get('summary', 'No summary available')}\n"
                    
                elif result.get("type") == "place":
                    # For place entries
                    content = result.get("content", {})
                    formatted_result += f"Place: {content.get('name', 'Unknown')}\n"
                    formatted_result += f"Summary: {content.get('summary', 'No summary available')}\n"
                
                formatted_result += "\n"
            
            return formatted_result
            
        else:
            # For natural language queries
            logger.info("Analyzing query")
            query_info = memnon._analyze_query(user_input, None)
            logger.info(f"Query analyzed as type: {query_info['type']}")
            
            logger.info("Querying memory")
            query_results = memnon.query_memory(
                query=user_input,
                query_type=query_info["type"],
                filters={},
                k=10
            )
            
            results_count = len(query_results["results"])
            logger.info(f"Got {results_count} results")
            
            if results_count == 0:
                return "No results found for your query. Try rephrasing or using different keywords."
            
            # Try to generate a response using the LLM with timeout handling
            logger.info("Synthesizing response with LLM")
            try:
                import threading
                import queue
                
                # Create a queue to hold the result
                result_queue = queue.Queue()
                
                # Define a function to call the LLM and put the result in the queue
                def call_llm():
                    try:
                        response = memnon._synthesize_response(
                            query=user_input,
                            results=query_results["results"],
                            query_type=query_results["query_type"]
                        )
                        result_queue.put(("success", response))
                    except Exception as e:
                        result_queue.put(("error", str(e)))
                
                # Start the thread
                thread = threading.Thread(target=call_llm)
                thread.daemon = True
                thread.start()
                
                # Wait for the result with a more generous timeout
                try:
                    # Using 180 seconds (3 minutes) timeout to allow for model loading
                    logger.info("Waiting for LLM response (timeout: 180 seconds)...")
                    status, result = result_queue.get(timeout=180)  # 3 minute timeout
                    if status == "success":
                        return result
                    else:
                        logger.error(f"LLM synthesis error: {result}")
                        # Fall back to basic formatting
                        return fallback_format_results(query_results, user_input)
                        
                except queue.Empty:
                    logger.error("LLM synthesis timed out after 180 seconds")
                    return fallback_format_results(query_results, user_input) + "\n\n(Note: LLM response synthesis timed out after 3 minutes. Falling back to basic results. The model may still be loading - try again or use 'no_llm_query' for faster results.)"
                    
            except Exception as e:
                logger.error(f"Error in LLM response generation: {e}")
                return fallback_format_results(query_results, user_input)
            
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        traceback.print_exc()
        return f"Error processing query: {str(e)}"


def fallback_format_results(query_results, query):
    """Format results without using LLM for synthesis"""
    results = query_results["results"]
    if not results:
        return "No results found for your query."
    
    formatted_result = f"Results for query: '{query}'\n\n"
    
    for i, result in enumerate(results[:5]):  # Show top 5 results
        formatted_result += f"Result {i+1} (Score: {result.get('score', 0):.4f}):\n"
        
        if result.get("type") == "narrative_chunk":
            # For narrative chunks, show a snippet
            content = result.get("content", "")
            if len(content) > 300:
                content = content[:297] + "..."
            formatted_result += f"Content: {content}\n"
            
            # Add metadata
            metadata = result.get("metadata", {})
            formatted_result += f"Metadata: Season {metadata.get('season', 'N/A')}, "
            formatted_result += f"Episode {metadata.get('episode', 'N/A')}, "
            formatted_result += f"Scene {metadata.get('scene_number', 'N/A')}\n"
            
        elif result.get("type") == "character":
            # For character entries
            content = result.get("content", {})
            formatted_result += f"Character: {content.get('name', 'Unknown')}\n"
            formatted_result += f"Summary: {content.get('summary', 'No summary available')}\n"
            
        elif result.get("type") == "place":
            # For place entries
            content = result.get("content", {})
            formatted_result += f"Place: {content.get('name', 'Unknown')}\n"
            formatted_result += f"Summary: {content.get('summary', 'No summary available')}\n"
        
        formatted_result += "\n"
    
    return formatted_result

def main():
    """Main function to run the MEMNON agent interactively"""
    print("\n🧠 MEMNON Interactive Memory Query Interface (Direct Mode) 🧠")
    print("==========================================================")
    
    # Check environment prerequisites
    if not check_environment():
        print("Environment check failed. Please fix the issues above and try again.")
        return
    
    # Load settings
    settings = load_settings()
    memnon_settings = settings.get("Agent Settings", {}).get("MEMNON", {})
    global_settings = settings.get("Agent Settings", {}).get("global", {})
    
    # Set debug mode
    debug = memnon_settings.get("debug", True)  # Default to True for verbose logging
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    print(f"Debug mode {'enabled' if debug else 'disabled'}")
    
    # Set database URL
    db_url = memnon_settings.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
    print(f"Using database: {db_url}")
    
    # Get model ID from global settings
    model_id = global_settings.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
    print(f"Using model: {model_id}")
    
    # Initialize MEMNON
    memnon = initialize_memnon(db_url, model_id, debug)
    
    if not memnon:
        print("Failed to initialize MEMNON. Check the logs for details.")
        return
    
    print("\nMEMNON agent initialized successfully!")
    print("\nAvailable commands:")
    print("  status           - Check MEMNON's status and database/embedding information")
    print("  process_files    - Process narrative files (optionally add pattern=PATTERN)")
    print("  test_llm         - Test LLM API connection and model loading")
    print("  no_llm_query ... - Run query without using LLM (faster, shows raw results)")
    print("  exit or quit     - Exit the program")
    print("\nOr enter any natural language query to search the narrative memory.")
    print("IMPORTANT: If queries take too long or time out, use 'no_llm_query' instead.")
    print("==========================================================\n")
    
    # Message processing loop with robust error handling
    while True:
        try:
            # Use sys.stdin.readline() instead of input() to avoid EOF errors
            print("🧠 > ", end="", flush=True)
            user_input = sys.stdin.readline().strip()
            
            if not user_input:
                continue
                
            logger.info(f"Received input: '{user_input}'")
            
            if user_input.lower() in ["exit", "quit"]:
                print("Exiting MEMNON interactive mode...")
                break
            
            # Process user query
            response = process_query(memnon, user_input)
            
            # Print the response
            print(f"\n{response}\n")
            
        except KeyboardInterrupt:
            print("\nExiting MEMNON interactive mode...")
            break
        except EOFError:
            print("\nDetected EOF. Exiting MEMNON interactive mode...")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            logger.error(f"Unexpected error in main loop: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Critical error in main: {e}")
        traceback.print_exc()
        print(f"A critical error occurred: {e}")
        print("Check memnon_direct.log for details")