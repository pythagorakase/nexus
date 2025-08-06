# MLX vs GGUF Performance Test Report

Generated: 2025-07-31 13:19:45

Test Run Summary:
- Total tests: 28
- Failed tests: 0
- Interrupted: No

## Executive Summary


### llama-4-scout-17b-16e-instruct

**Memory Usage:**
- GGUF: 113669.8 MB (peak)
- MLX: 75750.6 MB (peak)
- Difference: 37919.2 MB (33.4%)

**Performance:**
- GGUF tokens/sec: 11.6
- MLX tokens/sec: 25.4
- GGUF TTFT: 8.68s
- MLX TTFT: 5.29s

### llama-3.3-70b-instruct

**Memory Usage:**
- GGUF: 91653.1 MB (peak)
- MLX: 94487.3 MB (peak)
- Difference: -2834.2 MB (-3.1%)

**Performance:**
- GGUF tokens/sec: 4.7
- MLX tokens/sec: 5.8
- GGUF TTFT: 11.44s
- MLX TTFT: 9.32s

### mixtral-8x22b-instruct-v0.1

**Memory Usage:**
- GGUF: 95657.8 MB (peak)
- MLX: 99627.3 MB (peak)
- Difference: -3969.5 MB (-4.1%)

**Performance:**
- GGUF tokens/sec: 9.1
- MLX tokens/sec: 12.9
- GGUF TTFT: 7.79s
- MLX TTFT: 8.44s

## Detailed Results by Scenario


### Cold Start


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

**llama-3.3-70b-instruct@q6_k:**

**mlx-community/llama-3.3-70b-instruct:**

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**

**mlx-community/mixtral-8x22b-instruct-v0.1:**

### Context Stress


**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: 9.5 tokens/sec, TTFT: 15.20s

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: 24.9 tokens/sec, TTFT: 7.27s

**llama-3.3-70b-instruct@q6_k:**
- GGUF: 3.7 tokens/sec, TTFT: 20.51s

**mlx-community/llama-3.3-70b-instruct:**
- MLX: 5.3 tokens/sec, TTFT: 16.17s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: 3.6 tokens/sec, TTFT: 13.22s

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: 10.0 tokens/sec, TTFT: 14.21s

### Memory Leak


**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: Memory growth: 460.0 MB

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: Memory growth: 487.9 MB

**llama-3.3-70b-instruct@q6_k:**
- GGUF: Memory growth: 1108.8 MB

**mlx-community/llama-3.3-70b-instruct:**
- MLX: Memory growth: 686.8 MB

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: Memory growth: 44.1 MB

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: Memory growth: 229.2 MB

### Moe Specific


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**

**mlx-community/mixtral-8x22b-instruct-v0.1:**

## Memory Leak Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- Total memory growth: 460.0 MB
- Growth per iteration: 51.12 MB
- Leak severity: High

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- Total memory growth: 487.9 MB
- Growth per iteration: 54.21 MB
- Leak severity: High

**llama-3.3-70b-instruct@q6_k (GGUF):**
- Total memory growth: 1108.8 MB
- Growth per iteration: 123.20 MB
- Leak severity: High

**mlx-community/llama-3.3-70b-instruct (MLX):**
- Total memory growth: 686.8 MB
- Growth per iteration: 76.31 MB
- Leak severity: High

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- Total memory growth: 44.1 MB
- Growth per iteration: 4.90 MB
- Leak severity: Low

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- Total memory growth: 229.2 MB
- Growth per iteration: 25.47 MB
- Leak severity: High

## MoE Expert Routing Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- math: 16.5 tokens/sec, TTFT: 2.83s
- creative: 14.7 tokens/sec, TTFT: 2.37s
- code: 15.0 tokens/sec, TTFT: 2.66s
- factual: No performance metrics available

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- math: 26.4 tokens/sec, TTFT: 3.81s
- creative: 25.7 tokens/sec, TTFT: 3.76s
- code: 26.6 tokens/sec, TTFT: 3.84s
- factual: 26.3 tokens/sec, TTFT: 3.91s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- math: 11.6 tokens/sec, TTFT: 2.29s
- creative: 12.2 tokens/sec, TTFT: 2.28s
- code: 12.2 tokens/sec, TTFT: 2.41s
- factual: 12.1 tokens/sec, TTFT: 2.41s

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- math: 13.3 tokens/sec, TTFT: 3.20s
- creative: 13.5 tokens/sec, TTFT: 3.59s
- code: 13.7 tokens/sec, TTFT: 3.48s
- factual: 13.7 tokens/sec, TTFT: 3.41s

## Recommendations

- **Memory Efficiency**: MLX format shows better memory efficiency with up to 33.4% savings

### Model-Specific Recommendations:
- **llama-4-scout-17b-16e-instruct**: Recommend MLX (better memory efficiency with comparable performance)
- **llama-3.3-70b-instruct**: Recommend Either format (similar performance, choose based on memory constraints)
- **mixtral-8x22b-instruct-v0.1**: Recommend Either format (similar performance, choose based on memory constraints)

### For NEXUS LORE Implementation:
- For Scout 17Bx16E: Check memory leak severity before choosing format
- Consider MLX if memory constraints are tight and context window can be limited to 40k tokens
- Use GGUF if you need the full 131k context window
- Monitor memory usage closely during extended sessions