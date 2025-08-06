# MLX vs GGUF Performance Test Report

Generated: 2025-07-31 18:07:05

Test Run Summary:
- Total tests: 28
- Failed tests: 0
- Interrupted: No

## Executive Summary


### llama-4-scout-17b-16e-instruct

**Memory Usage:**
- GGUF: 115557.7 MB (peak)
- MLX: 78759.0 MB (peak)
- Difference: 36798.7 MB (31.8%)

**Performance:**
- GGUF tokens/sec: 18.1
- MLX tokens/sec: 40.6
- GGUF TTFT: 7.59s
- MLX TTFT: 4.98s

### llama-3.3-70b-instruct

**Memory Usage:**
- GGUF: 98684.4 MB (peak)
- MLX: 92484.4 MB (peak)
- Difference: 6200.0 MB (6.3%)

**Performance:**
- GGUF tokens/sec: 4.5
- MLX tokens/sec: 5.9
- GGUF TTFT: 11.46s
- MLX TTFT: 9.52s

### mixtral-8x22b-instruct-v0.1

**Memory Usage:**
- GGUF: 95294.7 MB (peak)
- MLX: 96807.7 MB (peak)
- Difference: -1513.1 MB (-1.6%)

**Performance:**
- GGUF tokens/sec: 17.5
- MLX tokens/sec: 20.3
- GGUF TTFT: 8.30s
- MLX TTFT: 6.97s

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
- GGUF: 17.5 tokens/sec, TTFT: 13.20s

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: 39.6 tokens/sec, TTFT: 6.64s

**llama-3.3-70b-instruct@q6_k:**
- GGUF: 3.0 tokens/sec, TTFT: 20.59s

**mlx-community/llama-3.3-70b-instruct:**
- MLX: 5.4 tokens/sec, TTFT: 16.59s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: 17.1 tokens/sec, TTFT: 14.41s

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: 19.6 tokens/sec, TTFT: 11.72s

### Memory Leak


**lmstudio-community/llama-4-scout-17b-16e-instruct:**
- GGUF: Memory growth: 579.3 MB

**mlx-community/llama-4-scout-17b-16e-instruct:**
- MLX: Memory growth: -1583.6 MB

**llama-3.3-70b-instruct@q6_k:**
- GGUF: Memory growth: -5094.2 MB

**mlx-community/llama-3.3-70b-instruct:**
- MLX: Memory growth: -47.7 MB

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**
- GGUF: Memory growth: 262.5 MB

**mlx-community/mixtral-8x22b-instruct-v0.1:**
- MLX: Memory growth: 647.3 MB

### Moe Specific


**lmstudio-community/llama-4-scout-17b-16e-instruct:**

**mlx-community/llama-4-scout-17b-16e-instruct:**

**maziyarpanahi/mixtral-8x22b-instruct-v0.1:**

**mlx-community/mixtral-8x22b-instruct-v0.1:**

## Memory Leak Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- Total memory growth: 579.3 MB
- Growth per iteration: 64.37 MB
- Leak severity: High

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- Total memory growth: -1583.6 MB
- Growth per iteration: -175.96 MB
- Leak severity: Low

**llama-3.3-70b-instruct@q6_k (GGUF):**
- Total memory growth: -5094.2 MB
- Growth per iteration: -566.02 MB
- Leak severity: Low

**mlx-community/llama-3.3-70b-instruct (MLX):**
- Total memory growth: -47.7 MB
- Growth per iteration: -5.30 MB
- Leak severity: Low

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- Total memory growth: 262.5 MB
- Growth per iteration: 29.17 MB
- Leak severity: High

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- Total memory growth: 647.3 MB
- Growth per iteration: 71.92 MB
- Leak severity: High

## MoE Expert Routing Analysis


**lmstudio-community/llama-4-scout-17b-16e-instruct (GGUF):**
- math: 15.6 tokens/sec, TTFT: 2.77s
- creative: 18.3 tokens/sec, TTFT: 2.36s
- code: 17.9 tokens/sec, TTFT: 2.60s
- factual: 17.9 tokens/sec, TTFT: 2.98s

**mlx-community/llama-4-scout-17b-16e-instruct (MLX):**
- math: 23.1 tokens/sec, TTFT: 3.82s
- creative: 23.3 tokens/sec, TTFT: 3.68s
- code: 22.9 tokens/sec, TTFT: 3.75s
- factual: 23.8 tokens/sec, TTFT: 4.21s

**maziyarpanahi/mixtral-8x22b-instruct-v0.1 (GGUF):**
- math: 10.7 tokens/sec, TTFT: 2.51s
- creative: 12.1 tokens/sec, TTFT: 2.27s
- code: 12.0 tokens/sec, TTFT: 2.21s
- factual: 11.8 tokens/sec, TTFT: 3.00s

**mlx-community/mixtral-8x22b-instruct-v0.1 (MLX):**
- math: 15.0 tokens/sec, TTFT: 3.16s
- creative: 15.7 tokens/sec, TTFT: 3.13s
- code: 16.0 tokens/sec, TTFT: 1.20s
- factual: 16.3 tokens/sec, TTFT: 3.35s

## Recommendations

- **Memory Efficiency**: MLX format shows better memory efficiency with up to 31.8% savings

### Model-Specific Recommendations:
- **llama-4-scout-17b-16e-instruct**: Recommend MLX (better memory efficiency with comparable performance)
- **llama-3.3-70b-instruct**: Recommend MLX (better memory efficiency with comparable performance)
- **mixtral-8x22b-instruct-v0.1**: Recommend Either format (similar performance, choose based on memory constraints)

### For NEXUS LORE Implementation:
- For Scout 17Bx16E: Check memory leak severity before choosing format
- Consider MLX if memory constraints are tight and context window can be limited to 40k tokens
- Use GGUF if you need the full 131k context window
- Monitor memory usage closely during extended sessions