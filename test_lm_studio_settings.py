#!/usr/bin/env python3
"""
Test Q4_K_M model with settings that mirror LM Studio's successful configuration
"""

from llama_cpp import Llama
import time
import psutil
import gc

model_path = "models/llama-4-scout/Q4_K_M/Llama-4-Scout-17B-16E-Instruct-Q4_K_M-merged.gguf"

print("Testing Llama 4.0 Scout Q4_K_M with LM Studio-like settings\n")
print("=" * 60)

# Get system memory info
vm = psutil.virtual_memory()
print(f"System memory: {vm.total / (1024**3):.1f} GB total, {vm.available / (1024**3):.1f} GB available")
print("=" * 60)

# Test with 128K context as suggested
test_context = 131072  # 128K tokens

print(f"\nLoading model with {test_context:,} context tokens...")
print("Settings based on LM Studio configuration:")
print("- GPU layers: 44/48 (leaving some for system)")
print("- CPU threads: 12")
print("- Batch size: 512") 
print("- Memory mapping: enabled")
print("- KV cache on GPU: enabled (f16)")
print("=" * 60)

try:
    start = time.time()
    
    llm = Llama(
        model_path=model_path,
        n_ctx=test_context,
        n_threads=12,  # Match LM Studio
        n_gpu_layers=44,  # 44/48 layers on GPU like LM Studio
        verbose=False,
        n_batch=512,  # Match LM Studio eval batch size
        seed=-1,  # Random seed
        f16_kv=True,  # KV cache in f16 (offloaded to GPU)
        use_mmap=True,  # Memory mapping enabled
        use_mlock=False,  # Don't lock pages in RAM
        # Note: llama-cpp-python handles RoPE automatically
    )
    
    load_time = time.time() - start
    print(f"\n✓ Model loaded successfully in {load_time:.1f}s")
    
    # Check memory usage
    process = psutil.Process()
    mem_info = process.memory_info()
    print(f"Process memory usage: {mem_info.rss / (1024**3):.1f} GB")
    
    # Get updated system memory
    vm = psutil.virtual_memory()
    print(f"System memory available: {vm.available / (1024**3):.1f} GB")
    
    # Test inference
    print("\n" + "-" * 60)
    print("Testing inference capabilities...")
    
    # Test 1: Simple generation
    prompt1 = "The key advantages of the Llama 4 Scout model are"
    print(f"\nPrompt 1: '{prompt1}'")
    
    start = time.time()
    response1 = llm(prompt1, max_tokens=50, temperature=0.7, echo=False)
    time1 = time.time() - start
    
    text1 = response1['choices'][0]['text'].strip()
    print(f"Response ({time1:.1f}s): {text1}")
    
    # Test 2: Longer context utilization
    print("\n" + "-" * 60)
    long_context = """
    In the year 2157, humanity had finally achieved faster-than-light travel through the invention of the Alcubierre-Chen drive. 
    The first colony ships departed Earth, carrying millions of settlers to distant star systems. 
    Among these pioneers was Dr. Elena Rodriguez, a xenobiologist who would make the discovery that changed everything.
    
    On the planet Kepler-442b, Dr. Rodriguez encountered something unprecedented: a form of life that existed partially in our 
    dimension and partially in what she termed 'cognitive space' - a realm where thought and reality intersected.
    
    Question: Based on this narrative, what might Dr. Rodriguez have discovered about the nature of consciousness?
    """
    
    print(f"Testing with longer context ({len(long_context)} chars)...")
    
    start = time.time()
    response2 = llm(long_context, max_tokens=100, temperature=0.8, echo=False)
    time2 = time.time() - start
    
    text2 = response2['choices'][0]['text'].strip()
    print(f"\nResponse ({time2:.1f}s): {text2}")
    
    # Performance summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Model load time: {load_time:.1f}s")
    print(f"Simple prompt inference: {time1:.1f}s ({len(text1.split())} words)")
    print(f"Context-heavy inference: {time2:.1f}s ({len(text2.split())} words)")
    print(f"Tokens/second (approx): {(len(text1.split()) + len(text2.split())) / (time1 + time2):.1f}")
    
    # Final memory check
    mem_info = process.memory_info()
    print(f"\nFinal process memory: {mem_info.rss / (1024**3):.1f} GB")
    
    print("\n✅ SUCCESS! Model is working with 128K context.")
    print("\nNext steps:")
    print("1. Update LORE settings to use these parameters")
    print("2. Consider testing with 200K context if memory permits")
    print("3. Implement dynamic context sizing based on need")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting:")
    print("1. Reduce n_gpu_layers to 40 or lower")
    print("2. Try smaller context (65536)")
    print("3. Close other applications to free memory")
    
finally:
    # Cleanup
    if 'llm' in locals():
        print("\nCleaning up...")
        del llm
    gc.collect()