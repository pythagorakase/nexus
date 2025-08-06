# MLX vs GGUF Performance Test Report

Generated: 2025-07-31 17:02:44

Test Run Summary:
- Total tests: 10
- Failed tests: 0
- Interrupted: Yes

## Executive Summary


### llama-4-scout-17b-16e-instruct

**Memory Usage:**
- GGUF: 115722.5 MB (peak)
- MLX: 79526.2 MB (peak)
- Difference: 36196.3 MB (31.3%)

**Performance:**
- GGUF tokens/sec: 18.7
- MLX tokens/sec: 40.5
- GGUF TTFT: 7.34s
- MLX TTFT: 4.93s

## Detailed Results by Scenario


### Cold Start


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

### Context Stress


**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: 17.9 tokens/sec, TTFT: 12.61s

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: 39.6 tokens/sec, TTFT: 6.60s

### Memory Leak


**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: Memory growth: -282.3 MB

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: Memory growth: -783.5 MB

### Moe Specific


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

## Memory Leak Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- Total memory growth: -282.3 MB
- Growth per iteration: -31.37 MB
- Leak severity: Low

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- Total memory growth: -783.5 MB
- Growth per iteration: -87.05 MB
- Leak severity: Low

## MoE Expert Routing Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- math: 19.4 tokens/sec, TTFT: 2.73s
- creative: 18.3 tokens/sec, TTFT: 2.32s
- code: 17.7 tokens/sec, TTFT: 2.51s
- factual: No performance metrics available

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- math: 41.6 tokens/sec, TTFT: 3.79s
- creative: 41.5 tokens/sec, TTFT: 3.69s
- code: 40.7 tokens/sec, TTFT: 3.79s
- factual: 31.7 tokens/sec, TTFT: 3.88s

## Recommendations

- **Memory Efficiency**: MLX format shows better memory efficiency with up to 31.3% savings

### Model-Specific Recommendations:
- **llama-4-scout-17b-16e-instruct**: Recommend MLX (better memory efficiency with comparable performance)

### For NEXUS LORE Implementation:
- For Scout 17Bx16E: Check memory leak severity before choosing format
- Consider MLX if memory constraints are tight and context window can be limited to 40k tokens
- Use GGUF if you need the full 131k context window
- Monitor memory usage closely during extended sessions