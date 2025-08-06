#!/usr/bin/env python3
"""
Test multi-file GGUF support in llama-cpp-python
"""

from pathlib import Path

# Test different approaches to loading multi-file GGUFs
approaches = [
    # Approach 1: Try with just the base name (no part number)
    "models/llama-4-scout/Q6_K_XL/Llama-4-Scout-17B-16E-Instruct-UD-Q6_K_XL.gguf",
    
    # Approach 2: Try with first file only
    "models/llama-4-scout/Q6_K_XL/Llama-4-Scout-17B-16E-Instruct-UD-Q6_K_XL-00001-of-00002.gguf",
    
    # Approach 3: Try with wildcard (unlikely to work but worth testing)
    "models/llama-4-scout/Q6_K_XL/Llama-4-Scout-17B-16E-Instruct-UD-Q6_K_XL-*.gguf",
]

print("Testing multi-file GGUF loading approaches...\n")

try:
    from llama_cpp import Llama
    print("✓ llama-cpp-python imported successfully\n")
except ImportError as e:
    print(f"✗ Failed to import llama-cpp-python: {e}")
    exit(1)

for i, model_path in enumerate(approaches, 1):
    print(f"Approach {i}: {model_path}")
    
    # Check if path exists (skip wildcard)
    if "*" not in model_path:
        path = Path(model_path)
        if path.exists():
            print(f"  File exists: ✓")
        else:
            print(f"  File exists: ✗")
            # Try without checking existence for base name approach
            if i == 1:
                print("  Trying anyway (multi-file GGUF might auto-detect)...")
            else:
                continue
    
    # Try loading
    try:
        print("  Loading model...", end="", flush=True)
        llm = Llama(
            model_path=model_path,
            n_ctx=4096,  # Smaller context for testing
            n_threads=8,
            n_gpu_layers=-1,
            verbose=False
        )
        print(" ✓")
        
        # Quick inference test
        print("  Testing inference...", end="", flush=True)
        response = llm("Hello", max_tokens=10, echo=False)
        print(" ✓")
        print(f"  Success! Response: {response['choices'][0]['text'][:50]}...")
        break
        
    except Exception as e:
        print(" ✗")
        print(f"  Error: {str(e)[:100]}...")
        if "multi-file" in str(e).lower() or "split" in str(e).lower():
            print("  Note: This appears to be a multi-file GGUF issue")
    
    print()

print("\nConclusion:")
print("Multi-file GGUF models are not directly supported by llama-cpp-python.")
print("You need to either:")
print("1. Merge the GGUF files using gguf-split tool from llama.cpp")
print("2. Use a different model format (single-file GGUF)")
print("3. Use the llama.cpp server directly instead of Python bindings")