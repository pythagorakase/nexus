#!/usr/bin/env python3
"""
Interactive runner for MEMNON agent.
This script provides a simple command-line interface for interacting with MEMNON.
"""

'''
=============================================================================
MEMNON INTERACTIVE INTERFACE
=============================================================================

This script provides an interactive command-line interface for MEMNON, allowing
you to test the hybrid search functionality and explore narrative memory.

USAGE:
------
    ./run_memnon_interactive.py [options]

COMMAND-LINE OPTIONS:
--------------------
    --raw-results    Start with raw search results mode enabled
                     (Shows detailed search info and scoring)
    
    --db-url URL     Specify a database URL different from settings.json
                     Example: --db-url "postgresql://user:pass@localhost/db"
    
    --debug          Enable debug mode (more verbose logging)

INTERACTIVE COMMANDS:
--------------------
    status           Show MEMNON status, including database stats and
                     hybrid search configuration
    
    test hybrid search    Run the hybrid search test suite with default
                          test queries
    
    test hybrid search queries: ["Query 1", "Query 2"]
                          Run hybrid search tests with custom queries
    
    raw              Toggle between showing raw search results 
                     (with scoring details) and LLM-synthesized responses
    
    exit, quit       Exit the interactive mode

EXAMPLE USAGE:
-------------
    # See hybrid search configuration
    > status
    
    # Compare hybrid vs vector search performance
    > test hybrid search
    
    # Test with custom queries
    > test hybrid search queries: ["Neural implant malfunction", "Corporate district meeting"]
    
    # Toggle raw mode to see detailed scoring
    > raw
    
    # Run a query with hybrid search (when enabled)
    > What happened between Alex and Emilia in the corporate district?
    
    # See vector and text component scores (when in raw mode)
    > Who has a neural implant?

NOTE: When in raw mode, you'll see both the detailed search results with
      component scores AND the LLM's synthesized answer.
=============================================================================
'''

import os
import sys
import json
import argparse
from typing import List, Dict, Any, Optional

# Import MEMNON agent
from nexus.agents.memnon.memnon import MEMNON

class SimpleInterface:
    """A simple interface for running MEMNON interactively"""
    
    def __init__(self):
        self.history = []
        
    def user_message(self, text: str):
        """Process a user message (just stores it for now)"""
        self.history.append({"role": "user", "content": text})
        return text
        
    def assistant_message(self, text: str):
        """Display assistant message"""
        self.history.append({"role": "assistant", "content": text})
        # Print with formatting
        print("\n\033[1;34mMEMNON:\033[0m", end=" ")
        print(text)
        return text

class Message:
    """Simple message class to mimic the legacy Letta Message structure"""
    
    def __init__(self, role, content):
        self.role = role
        self.content = [SimpleContent(content)]
        
class SimpleContent:
    """Simple content class to mimic the legacy Letta content structure"""
    
    def __init__(self, text):
        self.text = text

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Run MEMNON in interactive mode")
    parser.add_argument(
        "--raw-results", 
        action="store_true", 
        help="Show raw search results without LLM synthesis"
    )
    parser.add_argument(
        "--db-url", 
        type=str, 
        help="PostgreSQL database URL (default: from settings.json)"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug mode"
    )
    return parser.parse_args()

def main():
    """Main function to run the interactive interface"""
    args = parse_arguments()
    
    print("\n\033[1;32m=== MEMNON Interactive Mode ===\033[0m")
    print("Type 'exit' or 'quit' to end the session")
    print("Special commands:")
    print("  - 'status': Display MEMNON status")
    print("  - 'test hybrid search': Test hybrid search functionality")
    print("  - 'raw': Toggle showing raw search results")
    print("\033[1;32m==============================\033[0m\n")
    
    # Initialize the interface
    interface = SimpleInterface()
    
    # Print startup message
    interface.assistant_message("MEMNON initialized. What would you like to know?")
    
    # Initialize MEMNON with the interface
    memnon = MEMNON(
        interface=interface, 
        db_url=args.db_url, 
        debug=args.debug
    )
    
    # Set raw results flag
    show_raw = args.raw_results
    
    # Main loop
    while True:
        # Get user input
        try:
            user_input = input("\n\033[1;33mYou:\033[0m ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break
            
        # Check for exit command
        if user_input.lower() in ["exit", "quit"]:
            print("Exiting...")
            break
            
        # Check for toggle raw results
        if user_input.lower() == "raw":
            show_raw = not show_raw
            print(f"Raw results: {'ON' if show_raw else 'OFF'}")
            continue
            
        # Process the query
        interface.user_message(user_input)
        
        # Create a Message object that mimics what legacy Letta would provide
        message = Message("user", user_input)
        
        # Process the message with MEMNON
        try:
            # First parse command to see if we should show raw results
            command = memnon._parse_command(message)
            
            if command.get("action") == "status" or "test" in user_input.lower():
                # For status and test commands, just pass through to step
                response = memnon.step([message])
                if isinstance(response, str):
                    interface.assistant_message(response)
                else:
                    interface.assistant_message(json.dumps(response, indent=2))
            else:
                # For search queries, we may want to show raw results
                if show_raw:
                    # Get query results without LLM synthesis
                    query_results = memnon.query_memory(
                        query=user_input,
                        query_type=None,
                        filters={},
                        k=5
                    )
                    
                    # Print query type and search plan
                    print(f"\n\033[1;36mQuery Type:\033[0m {query_results['query_type']}")
                    print(f"\033[1;36mSearch Plan:\033[0m {query_results['metadata']['search_plan']}")
                    
                    # Print strategies used
                    strategies = query_results['metadata']['search_stats']['strategies_executed']
                    print(f"\033[1;36mStrategies Used:\033[0m {', '.join(strategies)}")
                    
                    # Print results
                    print("\n\033[1;36mResults:\033[0m")
                    for i, result in enumerate(query_results['results'][:5]):
                        score = result.get('score', 0.0)
                        source = result.get('source', 'unknown')
                        
                        # Check if it's a hybrid result
                        if 'vector_score' in result and 'text_score' in result:
                            score_info = f"Score: {score:.4f} (V: {result['vector_score']:.4f}, T: {result['text_score']:.4f})"
                        else:
                            score_info = f"Score: {score:.4f}"
                            
                        # Get metadata
                        metadata = result.get('metadata', {})
                        meta_str = ""
                        if metadata:
                            if 'season' in metadata and 'episode' in metadata:
                                meta_str += f" S{metadata['season']}E{metadata['episode']}"
                            if 'scene_number' in metadata:
                                meta_str += f" Scene {metadata['scene_number']}"
                        
                        # Print header for this result
                        print(f"\n\033[1;33mResult {i+1}\033[0m ({source}{meta_str}) - {score_info}")
                        
                        # Print text (truncated if too long)
                        text = result.get('text', '')
                        max_len = 500
                        if len(text) > max_len:
                            text = text[:max_len] + "..."
                        print(text)
                    
                    # Also pass to synthesize_response to get the LLM's answer
                    response = memnon._synthesize_response(
                        query=user_input,
                        results=query_results['results'],
                        query_type=query_results['query_type']
                    )
                    interface.assistant_message(response)
                else:
                    # Regular processing with LLM synthesis
                    response = memnon.step([message])
                    if isinstance(response, str):
                        interface.assistant_message(response)
                    else:
                        interface.assistant_message(json.dumps(response, indent=2))
                        
        except Exception as e:
            print(f"\n\033[1;31mError:\033[0m {str(e)}")
            import traceback
            print(traceback.format_exc())

if __name__ == "__main__":
    main() 