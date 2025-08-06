#!/usr/bin/env python3
"""Test script to verify accurate token counting."""

import json
from src.lmstudio_sdk_client_v2 import LMStudioSDKClient

def test_token_counting():
    """Test token counting with a simple generation."""
    # First ensure a model is loaded
    import lmstudio as lms
    lms_client = lms.Client(api_host='localhost:1234')
    loaded = lms_client.list_loaded_models()
    
    if not loaded:
        print("No models loaded. Please load a model in LM Studio first.")
        return
        
    model = loaded[0]
    model_id = model.identifier
    print(f"Testing with model: {model_id}")
    print(f"Model path: {model.get_info().path}")
    
    # Now use our client for testing
    client = LMStudioSDKClient()
    
    # Test with streaming (most common in the test suite)
    print("\n--- Testing Streaming Mode ---")
    result = client.generate(
        model=model_id,
        prompt="Write exactly 10 words about artificial intelligence.",
        max_tokens=50,
        temperature=0.7,
        stream=True
    )
    
    # Debug: Check if we got an error
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    
    print(f"Content: {result['content']}")
    print(f"Tokens generated: {result['tokens_generated']}")
    print(f"Tokens per second: {result['tokens_per_second']:.2f}")
    print(f"TTFT: {result['ttft']:.3f}s" if result['ttft'] else "TTFT: N/A")
    print(f"Prompt tokens: {result['prompt_tokens']}")
    print(f"Total tokens: {result['total_tokens']}")
    
    # Test with sync mode
    print("\n--- Testing Sync Mode ---")
    result = client.generate(
        model=model_id,
        prompt="Count from 1 to 5.",
        max_tokens=20,
        temperature=0.7,
        stream=False
    )
    
    print(f"Content: {result['content']}")
    print(f"Tokens generated: {result['tokens_generated']}")
    print(f"Tokens per second: {result['tokens_per_second']:.2f}")
    print(f"Prompt tokens: {result['prompt_tokens']}")
    print(f"Total tokens: {result['total_tokens']}")
    
    # Compare with LM Studio's reported speed
    print("\n✓ Token counting should now match LM Studio's reported speeds!")
    print("Compare these numbers with what LM Studio shows in its UI.")

if __name__ == "__main__":
    test_token_counting()