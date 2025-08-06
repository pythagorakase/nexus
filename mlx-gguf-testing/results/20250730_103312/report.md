# MLX vs GGUF Performance Test Report

Generated: 2025-07-30 10:33:12

Test Run Summary:
- Total tests: 28
- Failed tests: 1
- Interrupted: No

## Executive Summary


### llama-3.3-70b-instruct

**Memory Usage:**
- GGUF: 89886.3 MB (peak)
- MLX: 94365.0 MB (peak)
- Difference: -4478.7 MB (-5.0%)

**Performance:**
- GGUF tokens/sec: 4.1
- MLX tokens/sec: 4.2
- GGUF TTFT: 23.61s
- MLX TTFT: 23.03s

### llama-4-scout-17b-16e-instruct

**Memory Usage:**
- GGUF: 122507.8 MB (peak)
- MLX: 114705.4 MB (peak)
- Difference: 7802.3 MB (6.4%)

### mixtral-8x22b-instruct-v0.1

**Memory Usage:**
- GGUF: 87684.0 MB (peak)
- MLX: 90711.8 MB (peak)
- Difference: -3027.8 MB (-3.5%)

**Performance:**
- GGUF tokens/sec: 5.7
- MLX tokens/sec: 8.5
- GGUF TTFT: 30.52s
- MLX TTFT: 22.48s

## Detailed Results by Scenario


### Cold Start


**llama-3.3-70b-instruct@q6_k:**

**mlx-community/llama-3.3-70b-instruct:**

**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**

**mlx-community/mixtral-8x22b-instruct-v0.1:**

### Context Stress


**llama-3.3-70b-instruct@q6_k:**
- GGUF: 4.5 tokens/sec, TTFT: 19.62s

**mlx-community/llama-3.3-70b-instruct:**
- MLX: 4.8 tokens/sec, TTFT: 17.29s

**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: No performance metrics available

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: 25.5 tokens/sec, TTFT: 6.32s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: 7.5 tokens/sec, TTFT: 15.27s

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: 11.6 tokens/sec, TTFT: 12.73s

### Memory Leak


**llama-3.3-70b-instruct@q6_k:**
- GGUF: Memory growth: -40.5 MB

**mlx-community/llama-3.3-70b-instruct:**
- MLX: Memory growth: 594.9 MB

**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: Failed - Prompt 0: 400 Bad Request: Unknown error, Prompt 1: 400 Bad Request: Unknown error, Prompt 2: 400 Bad Request: Unknown error, Prompt 3: 400 Bad Request: Unknown error, Prompt 4: 400 Bad Request: Unknown error, Prompt 5: 400 Bad Request: Unknown error, Prompt 6: 400 Bad Request: Unknown error, Prompt 7: 400 Bad Request: Unknown error, Prompt 8: 400 Bad Request: Unknown error, Prompt 9: 400 Bad Request: Unknown error

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: Memory growth: 896.3 MB

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: Memory growth: 328.6 MB

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: Memory growth: -2437.2 MB

### Moe Specific


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**

**mlx-community/mixtral-8x22b-instruct-v0.1:**

## Memory Leak Analysis


**llama-3.3-70b-instruct@q6_k (GGUF):**
- Total memory growth: -40.5 MB
- Growth per iteration: -4.49 MB
- Leak severity: Low

**mlx-community/llama-3.3-70b-instruct (MLX):**
- Total memory growth: 594.9 MB
- Growth per iteration: 66.10 MB
- Leak severity: High

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- Total memory growth: 896.3 MB
- Growth per iteration: 99.59 MB
- Leak severity: High

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- Total memory growth: 328.6 MB
- Growth per iteration: 36.52 MB
- Leak severity: High

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- Total memory growth: -2437.2 MB
- Growth per iteration: -270.80 MB
- Leak severity: Low

## MoE Expert Routing Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- math: No performance metrics available
- creative: No performance metrics available
- code: No performance metrics available
- factual: No performance metrics available

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- math: 27.5 tokens/sec, TTFT: 3.56s
- creative: 26.7 tokens/sec, TTFT: 3.43s
- code: 28.3 tokens/sec, TTFT: 3.43s
- factual: 27.6 tokens/sec, TTFT: 3.51s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- math: 10.7 tokens/sec, TTFT: 2.82s
- creative: 11.6 tokens/sec, TTFT: 2.35s
- code: 11.8 tokens/sec, TTFT: 2.33s
- factual: 11.7 tokens/sec, TTFT: 2.59s

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- math: 16.5 tokens/sec, TTFT: 2.66s
- creative: 16.9 tokens/sec, TTFT: 2.65s
- code: 16.9 tokens/sec, TTFT: 2.57s
- factual: 16.9 tokens/sec, TTFT: 2.81s

## Recommendations

- **Memory Efficiency**: MLX format shows better memory efficiency with up to 6.4% savings

### Model-Specific Recommendations:
- **llama-3.3-70b-instruct**: Recommend Either format (similar performance, choose based on memory constraints)
- **mixtral-8x22b-instruct-v0.1**: Recommend Either format (similar performance, choose based on memory constraints)

### For NEXUS LORE Implementation:
- For Scout 17Bx16E: Check memory leak severity before choosing format
- Consider MLX if memory constraints are tight and context window can be limited to 40k tokens
- Use GGUF if you need the full 131k context window
- Monitor memory usage closely during extended sessions