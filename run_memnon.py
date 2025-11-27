#!/usr/bin/env python3
"""
Simple MEMNON Runner Script

A simplified script to run the MEMNON agent for interactive queries.
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("memnon.log"), logging.StreamHandler()]
)
logger = logging.getLogger("memnon-runner")

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class SimpleInterface:
    """Simple output interface for MEMNON."""
    def assistant_message(self, message):
        print(f"\n{message}\n")


def main():
    """Run MEMNON in a simple interactive mode."""
    print("\n===== MEMNON Interactive Memory System =====")
    
    # Import MEMNON class here to avoid circular import issues
    try:
        from nexus.agents.memnon.memnon import MEMNON, MEMNON_SETTINGS
        logger.info("Successfully imported MEMNON")
    except ImportError as e:
        print(f"Error importing MEMNON: {e}")
        return 1
    
    # Get database URL using slot-aware resolution
    from nexus.api.slot_utils import get_slot_db_url
    db_url = get_slot_db_url()
    logger.info(f"Using slot database: {db_url}")
    
    # Get model from global settings
    from nexus.agents.memnon.memnon import GLOBAL_SETTINGS
    model_id = GLOBAL_SETTINGS.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
    
    # Initialize MEMNON
    try:
        print("Initializing MEMNON (this might take a moment)...")
        memnon = MEMNON(
            interface=SimpleInterface(),
            agent_state=None,  # Direct mode - no legacy Letta framework needed
            user=None,
            db_url=db_url,
            model_id=model_id,
            debug=True
        )
        print("MEMNON initialized successfully.")
    except Exception as e:
        print(f"Error initializing MEMNON: {e}")
        traceback.print_exc()
        return 1
    
    # Print status after initialization
    print("\nMEMNON Status:")
    status = memnon._get_status()
    print(status)
    
    # Print available commands
    print("\nAvailable commands:")
    print("  status           - Show current MEMNON status")
    print("  exit/quit        - Exit the program")
    print("  raw <query>      - Query without LLM response synthesis (fast)")
    print("  test_llm         - Test LLM API connection")
    print("  Any other text   - Natural language query to MEMNON")
    
    # Main command loop
    while True:
        try:
            print("\n> ", end="", flush=True)
            sys.stdout.flush()  # Force flush
            
            # Read directly from sys.stdin to avoid EOF errors in some environments
            command_line = sys.stdin.readline()
            if not command_line:
                print("\nDetected EOF, exiting...")
                break
                
            command = command_line.strip()
                
            if not command:
                continue
                
            if command.lower() in ("exit", "quit"):
                print("Exiting MEMNON")
                break
                
            elif command.lower() == "status":
                # Get MEMNON status
                print(memnon._get_status())
                
            elif command.lower().startswith("raw "):
                # Run query without LLM synthesis
                query = command[4:].strip()
                if not query:
                    print("Please specify a query after 'raw'")
                    continue
                    
                print(f"Running raw query: '{query}'")
                
                # Analyze query
                query_info = memnon._analyze_query(query, None)
                query_type = query_info["type"]
                print(f"Query type: {query_type}")
                
                # Get results from memory
                results = memnon.query_memory(
                    query=query,
                    query_type=query_type,
                    k=5
                )
                
                # Format results
                if not results["results"]:
                    print("No results found.")
                else:
                    print(f"Found {len(results['results'])} matching items:")
                    for i, item in enumerate(results['results'][:5]):
                        print(f"\n---- Result {i+1} ----")
                        source_type = item.get("source", item.get("type", "unknown"))
                        print(f"Type: {source_type} (Score: {item['score']:.2f})")
                        
                        # Get content - handle both content and text fields
                        content = item.get("content", item.get("text", ""))
                        if len(content) > 200:
                            content = content[:197] + "..."
                        print(f"Content: {content}")
                        
                        # Print metadata
                        meta = item.get("metadata", {})
                        print(f"Season: {meta.get('season', 'N/A')}, Episode: {meta.get('episode', 'N/A')}, Scene: {meta.get('scene_number', 'N/A')}")
                        
                        # If content is a dictionary (structured data), show key fields
                        if isinstance(content, dict):
                            for k, v in content.items():
                                if k in ["name", "summary"]:
                                    print(f"{k.capitalize()}: {v}")
            
            elif command.lower() == "test_llm":
                # Test LLM API connection
                import requests
                
                api_base = MEMNON_SETTINGS.get("llm", {}).get("api_base", "http://localhost:1234")
                print(f"Testing LLM API connection to {api_base}")
                
                # Test models endpoint
                try:
                    print("Testing models endpoint...", end="", flush=True)
                    response = requests.get(f"{api_base}/v1/models", timeout=5)
                    if response.status_code == 200:
                        models = response.json()
                        model_ids = [model["id"] for model in models.get("data", [])]
                        print("Success!")
                        print(f"Available models: {', '.join(model_ids)}")
                        print(f"Current model: {model_id}")
                    else:
                        print(f"Failed with status {response.status_code}")
                except Exception as e:
                    print(f"Error: {e}")
                
                # Test completions endpoint
                try:
                    print("\nTesting completions endpoint...")
                    print(f"(This may take a while if the model {model_id} is still loading into memory)")
                    
                    repeat_penalty = MEMNON_SETTINGS.get("llm", {}).get("repeat_penalty", 1.3)
                    presence_penalty = MEMNON_SETTINGS.get("llm", {}).get("presence_penalty", 0.5)
                    frequency_penalty = MEMNON_SETTINGS.get("llm", {}).get("frequency_penalty", 0.5)
                    
                    payload = {
                        "model": model_id,
                        "prompt": "Hello, how are you?",
                        "temperature": 0.2,
                        "max_tokens": 20,
                        "repeat_penalty": repeat_penalty,
                        "presence_penalty": presence_penalty,
                        "frequency_penalty": frequency_penalty,
                        "stream": False
                    }
                    
                    print("Sending request...")
                    start_time = time.time()
                    response = requests.post(
                        f"{api_base}/v1/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=MEMNON_SETTINGS.get("llm", {}).get("timeout", 300)  # Use setting
                    )
                    
                    elapsed = time.time() - start_time
                    print(f"Response received in {elapsed:.2f} seconds")
                    
                    if response.status_code == 200:
                        print("Success!")
                        data = response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            text = data["choices"][0].get("text", "")
                            print(f"Response: {text}")
                        else:
                            print("No text in response")
                    else:
                        print(f"Failed with status {response.status_code}")
                        print(f"Error: {response.text}")
                        
                except requests.exceptions.Timeout:
                    llm_timeout = MEMNON_SETTINGS.get("llm", {}).get("timeout", 300)
                    print(f"Request timed out after {llm_timeout} seconds")
                    print("The model is likely still loading. Try again later.")
                except Exception as e:
                    print(f"Error: {e}")
                    
            else:
                # Regular query with LLM synthesis
                query = command
                print(f"Processing query: '{query}'")
                
                try:
                    # Start timer
                    start_time = time.time()
                    
                    # First determine query type
                    query_info = memnon._analyze_query(query, None)
                    query_type = query_info["type"]
                    print(f"Query type: {query_type} (determined in {time.time()-start_time:.2f}s)")
                    
                    # Get results using LLM-directed search
                    phase_start = time.time()
                    results = memnon.query_memory(
                        query=query,
                        query_type=query_type,
                        k=10
                    )
                    search_time = time.time() - phase_start
                    
                    # Print search metadata
                    search_plan = results.get("metadata", {}).get("search_plan", "Default search strategy")
                    strategies = results.get("metadata", {}).get("strategies_executed", [])
                    print(f"Search plan: {search_plan}")
                    print(f"Strategies used: {', '.join(strategies)}")
                    print(f"Found {len(results['results'])} results in {search_time:.2f}s")
                    
                    if not results["results"]:
                        print("No results found for your query.")
                        continue
                    
                    # Generate response with LLM
                    print("Generating response with LLM (may take a while)...")
                    phase_start = time.time()
                    
                    # Try running in a thread with a timeout
                    import threading
                    import queue
                    
                    def synth_thread():
                        try:
                            response = memnon._synthesize_response(
                                query=query,
                                results=results["results"],
                                query_type=results["query_type"]
                            )
                            result_queue.put(("success", response))
                        except Exception as e:
                            result_queue.put(("error", str(e)))
                    
                    # Create queue and thread
                    result_queue = queue.Queue()
                    thread = threading.Thread(target=synth_thread)
                    thread.daemon = True
                    thread.start()
                    
                    # Get timeout from settings
                    llm_timeout = MEMNON_SETTINGS.get("llm", {}).get("timeout", 300)  # Default 5 minutes
                    
                    # Wait with timeout
                    try:
                        print(f"Waiting for LLM response (timeout: {llm_timeout}s)...")
                        status, result = result_queue.get(timeout=llm_timeout)
                        if status == "success":
                            print(f"Response generated in {time.time()-phase_start:.2f}s")
                            print(f"\n{result}\n")
                        else:
                            print(f"Error generating response: {result}")
                            print("Showing top results instead:")
                            
                            # Show top results as fallback
                            for i, item in enumerate(results['results'][:3]):
                                try:
                                    print(f"\n---- Result {i+1} ----")
                                    
                                    # Get source type and score
                                    source_type = item.get("source", "unknown")
                                    score = item.get("score", 0)
                                    print(f"Source: {source_type}, Score: {score:.2f}")
                                    
                                    # Get content (text field has priority)
                                    if "text" in item and item["text"]:
                                        content = item["text"]
                                        if len(content) > 200:
                                            content = content[:197] + "..."
                                        print(f"Content: {content}")
                                    
                                    # Show metadata in compact form
                                    if "metadata" in item and item["metadata"]:
                                        print("Metadata:")
                                        for k, v in item["metadata"].items():
                                            if k in ["season", "episode", "scene_number"]:
                                                print(f"  {k}: {v}")
                                    
                                    # Show relevance info if available
                                    if "relevance" in item:
                                        matches = item["relevance"].get("matches", [])
                                        if matches:
                                            print(f"Matches: {', '.join(matches[:5])}")
                                except Exception as display_error:
                                    print(f"Error displaying result: {display_error}")
                    except queue.Empty:
                        print(f"Response generation timed out after {llm_timeout} seconds")
                        print("The LLM is likely still loading or processing.")
                        print("Try using 'raw' queries while LM Studio loads the model.")
                
                except Exception as e:
                    print(f"Error processing query: {e}")
                    traceback.print_exc()
        
        except KeyboardInterrupt:
            print("\nOperation interrupted by user. Enter 'exit' to quit.")
        except Exception as e:
            print(f"Unexpected error: {e}")
            logger.error(f"Unexpected error: {e}")
            logger.error(traceback.format_exc())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nExiting MEMNON...")
        sys.exit(0)
    except Exception as e:
        print(f"Critical error: {e}")
        traceback.print_exc()
        sys.exit(1)