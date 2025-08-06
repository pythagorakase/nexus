#!/usr/bin/env python3
"""
Test Q4_K_XL model with various context sizes
"""

from llama_cpp import Llama
import time
import psutil
import sys

model_path = "models/llama-4-scout/Q4_K_XL/Llama-4-Scout-17B-16E-Instruct-UD-Q4_K_XL-merged.gguf"

# Test a specific context size if provided as argument
if len(sys.argv) > 1:
    context_sizes = [int(sys.argv[1])]
else:
    # Test progressively larger contexts
    context_sizes = [32768, 65536, 131072, 200000]

print("Testing Llama 4.0 Scout Q4_K_XL...\n")

for n_ctx in context_sizes:
    print(f"\n{'='*60}")
    print(f"Testing with {n_ctx:,} context tokens ({n_ctx/1024:.0f}K)")
    print('='*60)
    
    try:
        # Get initial memory
        process = psutil.Process()
        initial_mem = process.memory_info().rss / (1024**3)
        
        start = time.time()
        print(f"Loading model...", end="", flush=True)
        
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=12,
            n_gpu_layers=-1,  # All layers on GPU
            verbose=False,
            n_batch=512,
            seed=42,
            f16_kv=True,
            use_mmap=True,  # Memory-mapped files for efficiency
            use_mlock=False  # Don't lock in RAM
        )
        
        load_time = time.time() - start
        current_mem = process.memory_info().rss / (1024**3)
        mem_increase = current_mem - initial_mem
        
        print(f" ✓ ({load_time:.1f}s)")
        print(f"Memory usage: {current_mem:.1f} GB (+{mem_increase:.1f} GB)")
        
        # Quick inference test
        print("Testing inference...", end="", flush=True)
        prompt = "The meaning of life is"
        
        start = time.time()
        response = llm(prompt, max_tokens=20, temperature=0.7, echo=False)
        inference_time = time.time() - start
        
        text = response['choices'][0]['text'].strip()
        print(f" ✓ ({inference_time:.1f}s)")
        print(f"Response: '{text}'")
        
        # Clean up
        del llm
        
        # Give it a moment to release memory
        time.sleep(2)
        
    except Exception as e:
        print(f" ✗")
        print(f"Error: {str(e)[:200]}...")
        if "decode returned" in str(e):
            print("Note: This appears to be a memory/decode issue")
        continue

# Final system check
vm = psutil.virtual_memory()
print(f"\n{'='*60}")
print(f"System memory: {vm.total / (1024**3):.1f} GB total, {vm.available / (1024**3):.1f} GB available")
print('='*60)