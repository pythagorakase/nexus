#!/usr/bin/env python3
"""
Simple test for Llama 4.0 Scout with different context sizes
"""

from llama_cpp import Llama
import time

model_path = "models/llama-4-scout/Q5_K_XL/Llama-4-Scout-17B-16E-Instruct-UD-Q5_K_XL-merged.gguf"

# Test different context sizes - go bigger!
context_sizes = [16384, 32768, 65536, 131072, 262144]

print("Testing Llama 4.0 Scout with different context sizes...\n")

for n_ctx in context_sizes:
    print(f"Testing with n_ctx={n_ctx}...")
    
    try:
        # Load model
        start = time.time()
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=12,
            n_gpu_layers=-1,  # All layers on GPU
            verbose=False,
            n_batch=512,  # Smaller batch size
            seed=-1,
            f16_kv=True
        )
        load_time = time.time() - start
        print(f"  ✓ Model loaded in {load_time:.2f}s")
        
        # Test inference
        prompt = "Write a single word response: What is the capital of France?"
        start = time.time()
        response = llm(prompt, max_tokens=20, temperature=0.1, echo=False)
        inference_time = time.time() - start
        
        text = response['choices'][0]['text'].strip()
        print(f"  ✓ Inference successful in {inference_time:.2f}s")
        print(f"  Response: {text}")
        print()
        
        # Clean up
        del llm
        
    except Exception as e:
        print(f"  ✗ Failed: {str(e)[:100]}...")
        print()
        continue

print("\nTesting memory info...")
import psutil
process = psutil.Process()
memory_info = process.memory_info()
print(f"Current process memory: {memory_info.rss / (1024**3):.2f} GB")

# Check system memory
vm = psutil.virtual_memory()
print(f"System memory: {vm.total / (1024**3):.1f} GB total, {vm.available / (1024**3):.1f} GB available")