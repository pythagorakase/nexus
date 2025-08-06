#!/usr/bin/env python3
"""
Safe test for Q4_K_M model with progressive context loading
"""

from llama_cpp import Llama
import time
import psutil
import gc

model_path = "models/llama-4-scout/Q4_K_M/Llama-4-Scout-17B-16E-Instruct-Q4_K_M-merged.gguf"

print("Safe Llama 4.0 Scout Q4_K_M Test\n")
print("=" * 60)

# Get system memory info
vm = psutil.virtual_memory()
print(f"System memory: {vm.total / (1024**3):.1f} GB total, {vm.available / (1024**3):.1f} GB available")
print("=" * 60)

# Start with a very safe context size
test_context = 65536  # 64K to start

print(f"\nTesting with {test_context:,} context tokens...")

try:
    # More conservative settings
    print("Loading model with conservative settings...")
    start = time.time()
    
    llm = Llama(
        model_path=model_path,
        n_ctx=test_context,
        n_threads=8,  # Fewer threads
        n_gpu_layers=100,  # Not all layers on GPU to save VRAM
        verbose=False,
        n_batch=256,  # Smaller batch
        seed=42,
        f16_kv=False,  # Use f32 for stability
        use_mmap=True,
        use_mlock=False,
        low_vram=True  # Enable low VRAM mode if available
    )
    
    load_time = time.time() - start
    print(f"✓ Model loaded in {load_time:.1f}s")
    
    # Check memory
    process = psutil.Process()
    mem_info = process.memory_info()
    print(f"Process memory: {mem_info.rss / (1024**3):.1f} GB")
    
    # Simple test
    print("\nTesting basic inference...")
    prompt = "Hello, world! The weather today is"
    
    start = time.time()
    response = llm(prompt, max_tokens=20, temperature=0.7, echo=False, stop=["\n"])
    inference_time = time.time() - start
    
    text = response['choices'][0]['text'].strip()
    print(f"✓ Inference successful in {inference_time:.1f}s")
    print(f"Response: '{text}'")
    
    # If successful, provide guidance
    print("\n" + "=" * 60)
    print("SUCCESS! The model loads and runs with 64K context.")
    print("\nTo test larger contexts, you can:")
    print("1. Gradually increase n_ctx (e.g., 131072, 200000)")
    print("2. Monitor memory usage carefully")
    print("3. Consider using n_gpu_layers < 100 to balance GPU/CPU memory")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    print("\nTroubleshooting suggestions:")
    print("1. Try reducing n_gpu_layers (e.g., 50)")
    print("2. Try a smaller n_ctx (e.g., 32768)")
    print("3. Ensure no other memory-intensive apps are running")
finally:
    # Force cleanup
    if 'llm' in locals():
        del llm
    gc.collect()