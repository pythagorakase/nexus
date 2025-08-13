2025-08-12 00:27:55 [DEBUG]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f] Client created.
2025-08-12 00:27:55  [INFO]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=listDownloadedModels] Listing downloaded models
2025-08-12 00:27:55  [INFO]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=listLoaded] Listing loaded models
2025-08-12 00:27:55  [INFO]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=listLoaded] Listing loaded models
2025-08-12 00:27:55  [INFO]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=getOrLoad] Requested get or load model: openai/gpt-oss-120b
2025-08-12 00:27:55 [DEBUG]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=getOrLoad] Model not found by identifier. Trying to load.
2025-08-12 00:27:55 [DEBUG]
 [LM Studio] GPU Configuration:
  Strategy: evenly
  Priority: []
  Disabled GPUs: []
  Limit weight offload to dedicated GPU Memory: OFF
  Offload KV Cache to GPU: ON
2025-08-12 00:27:55 [DEBUG]
 [LM Studio] Live GPU memory info:
No live GPU info available
2025-08-12 00:27:55 [DEBUG]
 [LM Studio] Model load size estimate with raw num offload layers 'max' and context length '4096':
  Model: 65.25 GB
  Context: 803.12 MB
  Total: 66.05 GB
2025-08-12 00:27:55 [DEBUG]
 [LM Studio] Strict GPU VRAM cap is OFF: GPU offload layers will not be checked for adjustment
2025-08-12 00:27:55 [DEBUG]
 [LM Studio] Resolved GPU config options:
  Num Offload Layers: max
  Main GPU: 0
  Tensor Split: [0]
  Disabled GPUs: []
2025-08-12 00:27:55 [DEBUG]
 Metal : CPU : NEON = 1 | ARM_FMA = 1 | FP16_VA = 1 | DOTPROD = 1 | LLAMAFILE = 1 | ACCELERATE = 1 | REPACK = 1 |
2025-08-12 00:27:55 [DEBUG]
 llama_model_load_from_file_impl: using device Metal (Apple M4 Max) - 98303 MiB free
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: ------------------------ Adding override for key 'gpt-oss.expert_used_count'
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: additional 1 GGUFs metadata loaded.
llama_model_loader: loaded meta data with 36 key-value pairs and 687 tensors from /Users/pythagor/.lmstudio/models/lmstudio-community/gpt-oss-120b-GGUF/gpt-oss-120b-MXFP4-00001-of-00002.gguf (version GGUF V3 (latest))
llama_model_loader: Dumping metadata keys/values. Note: KV overrides do not apply in this output.
llama_model_loader: - kv   0:                       general.architecture str              = gpt-oss
llama_model_loader: - kv   1:                               general.type str              = model
llama_model_loader: - kv   2:                               general.name str              = Openai_Gpt Oss 120b
llama_model_loader: - kv   3:                           general.basename str              = openai_gpt-oss
llama_model_loader: - kv   4:                         general.size_label str              = 120B
llama_model_loader: - kv   5:                        gpt-oss.block_count u32              = 36
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: - kv   6:                     gpt-oss.context_length u32              = 131072
llama_model_loader: - kv   7:                   gpt-oss.embedding_length u32              = 2880
llama_model_loader: - kv   8:                gpt-oss.feed_forward_length u32              = 2880
llama_model_loader: - kv   9:               gpt-oss.attention.head_count u32              = 64
llama_model_loader: - kv  10:            gpt-oss.attention.head_count_kv u32              = 8
llama_model_loader: - kv  11:                     gpt-oss.rope.freq_base f32              = 150000.000000
llama_model_loader: - kv  12:   gpt-oss.attention.layer_norm_rms_epsilon f32              = 0.000010
llama_model_loader: - kv  13:                       gpt-oss.expert_count u32              = 128
llama_model_loader: - kv  14:                  gpt-oss.expert_used_count u32              = 4
llama_model_loader: - kv  15:               gpt-oss.attention.key_length u32              = 64
llama_model_loader: - kv  16:             gpt-oss.attention.value_length u32              = 64
llama_model_loader: - kv  17:           gpt-oss.attention.sliding_window u32              = 128
llama_model_loader: - kv  18:         gpt-oss.expert_feed_forward_length u32              = 2880
llama_model_loader: - kv  19:                  gpt-oss.rope.scaling.type str              = yarn
llama_model_loader: - kv  20:                gpt-oss.rope.scaling.factor f32              = 32.000000
llama_model_loader: - kv  21: gpt-oss.rope.scaling.original_context_length u32              = 4096
llama_model_loader: - kv  22:                       tokenizer.ggml.model str              = gpt2
llama_model_loader: - kv  23:                         tokenizer.ggml.pre str              = gpt-4o
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: - kv  24:                      tokenizer.ggml.tokens arr[str,201088]  = ["!", "\"", "#", "$", "%", "&", "'", ...
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: - kv  25:                  tokenizer.ggml.token_type arr[i32,201088]  = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, ...
2025-08-12 00:27:55 [DEBUG]
 llama_model_loader: - kv  26:                      tokenizer.ggml.merges arr[str,446189]  = ["Ġ Ġ", "Ġ ĠĠĠ", "ĠĠ ĠĠ", "...
llama_model_loader: - kv  27:                tokenizer.ggml.bos_token_id u32              = 199998
llama_model_loader: - kv  28:                tokenizer.ggml.eos_token_id u32              = 200002
llama_model_loader: - kv  29:            tokenizer.ggml.padding_token_id u32              = 199999
llama_model_loader: - kv  30:                    tokenizer.chat_template str              = {#-\n  In addition to the normal input...
llama_model_loader: - kv  31:               general.quantization_version u32              = 2
llama_model_loader: - kv  32:                          general.file_type u32              = 38
llama_model_loader: - kv  33:                                   split.no u16              = 0
llama_model_loader: - kv  34:                        split.tensors.count i32              = 687
llama_model_loader: - kv  35:                                split.count u16              = 2
llama_model_loader: - type  f32:  433 tensors
llama_model_loader: - type q8_0:  146 tensors
llama_model_loader: - type mxfp4:  108 tensors
print_info: file format = GGUF V3 (latest)
print_info: file type   = MXFP4 MoE
print_info: file size   = 59.02 GiB (4.34 BPW)
2025-08-12 00:27:55 [DEBUG]
 validate_override: Using metadata override (  int) 'gpt-oss.expert_used_count' = 4
load_hparams: ----------------------- n_expert_used = 4
2025-08-12 00:27:56 [DEBUG]
 load: printing all EOG tokens:
load:   - 199999 ('<|endoftext|>')
load:   - 200002 ('<|return|>')
load:   - 200007 ('<|end|>')
load:   - 200012 ('<|call|>')
load: special_eog_ids contains both '<|return|>' and '<|call|>' tokens, removing '<|end|>' token from EOG list
2025-08-12 00:27:56 [DEBUG]
 load: special tokens cache size = 21
2025-08-12 00:27:56 [DEBUG]
 load: token to piece cache size = 1.3332 MB
print_info: arch             = gpt-oss
print_info: vocab_only       = 0
print_info: n_ctx_train      = 131072
print_info: n_embd           = 2880
print_info: n_layer          = 36
print_info: n_head           = 64
print_info: n_head_kv        = 8
print_info: n_rot            = 64
print_info: n_swa            = 128
print_info: is_swa_any       = 1
print_info: n_embd_head_k    = 64
print_info: n_embd_head_v    = 64
2025-08-12 00:27:56 [DEBUG]
 print_info: n_gqa            = 8
print_info: n_embd_k_gqa     = 512
print_info: n_embd_v_gqa     = 512
print_info: f_norm_eps       = 0.0e+00
print_info: f_norm_rms_eps   = 1.0e-05
print_info: f_clamp_kqv      = 0.0e+00
print_info: f_max_alibi_bias = 0.0e+00
print_info: f_logit_scale    = 0.0e+00
print_info: f_attn_scale     = 0.0e+00
print_info: n_ff             = 2880
print_info: n_expert         = 128
print_info: n_expert_used    = 4
print_info: causal attn      = 1
print_info: pooling type     = 0
print_info: rope type        = 2
print_info: rope scaling     = yarn
print_info: freq_base_train  = 150000.0
print_info: freq_scale_train = 0.03125
print_info: n_ctx_orig_yarn  = 4096
print_info: rope_finetuned   = unknown
print_info: model type       = ?B
print_info: model params     = 116.83 B
print_info: general.name     = Openai_Gpt Oss 120b
print_info: n_ff_exp         = 2880
print_info: vocab type       = BPE
print_info: n_vocab          = 201088
print_info: n_merges         = 446189
print_info: BOS token        = 199998 '<|startoftext|>'
print_info: EOS token        = 200002 '<|return|>'
print_info: EOT token        = 200007 '<|end|>'
print_info: PAD token        = 199999 '<|endoftext|>'
print_info: LF token         = 198 'Ċ'
print_info: EOG token        = 199999 '<|endoftext|>'
print_info: EOG token        = 200002 '<|return|>'
print_info: EOG token        = 200012 '<|call|>'
print_info: max token length = 256
load_tensors: loading model tensors, this can take a while... (mmap = true)
2025-08-12 00:28:07 [DEBUG]
 load_tensors: offloading 36 repeating layers to GPU
load_tensors: offloading output layer to GPU
load_tensors: offloaded 37/37 layers to GPU
2025-08-12 00:28:07 [DEBUG]
 load_tensors: Metal_Mapped model buffer size = 37958.69 MiB
load_tensors: Metal_Mapped model buffer size = 22479.80 MiB
2025-08-12 00:28:07 [DEBUG]
 load_tensors:   CPU_Mapped model buffer size =   586.82 MiB
2025-08-12 00:28:12 [DEBUG]
 llama_context: constructing llama_context
llama_context: n_seq_max     = 1
llama_context: n_ctx         = 4096
llama_context: n_ctx_per_seq = 4096
llama_context: n_batch       = 512
llama_context: n_ubatch      = 512
llama_context: causal_attn   = 1
llama_context: flash_attn    = 0
llama_context: kv_unified    = false
llama_context: freq_base     = 150000.0
llama_context: freq_scale    = 0.03125
llama_context: n_ctx_per_seq (4096) < n_ctx_train (131072) -- the full capacity of the model will not be utilized
ggml_metal_init: allocating
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: found device: Apple M4 Max
ggml_metal_init: picking default device: Apple M4 Max
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_load_library: loading '/Users/pythagor/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-1.44.0/default.metallib'
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: GPU name:   Apple M4 Max
ggml_metal_init: GPU family: MTLGPUFamilyApple9  (1009)
ggml_metal_init: GPU family: MTLGPUFamilyCommon3 (3003)
ggml_metal_init: GPU family: MTLGPUFamilyMetal3  (5001)
ggml_metal_init: simdgroup reduction   = true
ggml_metal_init: simdgroup matrix mul. = true
ggml_metal_init: has residency sets    = false
ggml_metal_init: has bfloat            = true
ggml_metal_init: use bfloat            = false
ggml_metal_init: hasUnifiedMemory      = true
ggml_metal_init: recommendedMaxWorkingSetSize  = 103079.22 MB
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_get_rows_bf16                     (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_set_rows_bf16                     (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_mul_mv_bf16_f32                   (not supported)
ggml_metal_init: skipping kernel_mul_mv_bf16_f32_c4                (not supported)
ggml_metal_init: skipping kernel_mul_mv_bf16_f32_1row              (not supported)
ggml_metal_init: skipping kernel_mul_mv_bf16_f32_l4                (not supported)
ggml_metal_init: skipping kernel_mul_mv_bf16_bf16                  (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_mul_mv_id_bf16_f32                (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_mul_mm_bf16_f32                   (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_mul_mm_id_bf16_f16                (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h64           (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h80           (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h96           (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h112          (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h128          (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h192          (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_hk192_hv128   (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_h256          (not supported)
ggml_metal_init: skipping kernel_flash_attn_ext_bf16_hk576_hv512   (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_h64       (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_h96       (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_h128      (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_h192      (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_hk192_hv128 (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_h256      (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_flash_attn_ext_vec_bf16_hk576_hv512 (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_cpy_f32_bf16                      (not supported)
2025-08-12 00:28:12 [DEBUG]
 ggml_metal_init: skipping kernel_cpy_bf16_f32                      (not supported)
ggml_metal_init: skipping kernel_cpy_bf16_bf16                     (not supported)
2025-08-12 00:28:12 [DEBUG]
 llama_context:        CPU  output buffer size =     0.77 MiB
2025-08-12 00:28:12 [DEBUG]
 llama_kv_cache_unified_iswa: using full-size SWA cache (ref: https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)
llama_kv_cache_unified_iswa: creating non-SWA KV cache, size = 4096 cells
2025-08-12 00:28:12 [DEBUG]
 llama_kv_cache_unified:      Metal KV buffer size =   144.00 MiB
2025-08-12 00:28:12 [DEBUG]
 llama_kv_cache_unified: size =  144.00 MiB (  4096 cells,  18 layers,  1/1 seqs), K (f16):   72.00 MiB, V (f16):   72.00 MiB
llama_kv_cache_unified_iswa: creating     SWA KV cache, size = 4096 cells
2025-08-12 00:28:12 [DEBUG]
 llama_kv_cache_unified:      Metal KV buffer size =   144.00 MiB
2025-08-12 00:28:12 [DEBUG]
 llama_kv_cache_unified: size =  144.00 MiB (  4096 cells,  18 layers,  1/1 seqs), K (f16):   72.00 MiB, V (f16):   72.00 MiB
2025-08-12 00:28:12 [DEBUG]
 llama_context:      Metal compute buffer size =   819.26 MiB
llama_context:        CPU compute buffer size =    25.64 MiB
llama_context: graph nodes  = 2382
llama_context: graph splits = 2
2025-08-12 00:28:12 [DEBUG]
 common_init_from_params: added <|endoftext|> logit bias = -inf
common_init_from_params: added <|return|> logit bias = -inf
common_init_from_params: added <|call|> logit bias = -inf
common_init_from_params: setting dry_penalty_last_n to ctx_size = 4096
common_init_from_params: warming up the model with an empty run - please wait ... (--no-warmup to disable)
2025-08-12 00:28:12 [DEBUG]
 GgmlThreadpools: llama threadpool init = n_threads = 12
2025-08-12 00:28:18 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:18 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:18 [DEBUG]
 Sampling params:	repeat_last_n = 64, repeat_penalty = 1.100, frequency_penalty = 0.000, presence_penalty = 0.000
	dry_multiplier = 0.000, dry_base = 1.750, dry_allowed_length = 2, dry_penalty_last_n = -1
	top_k = 40, top_p = 0.800, min_p = 0.050, xtc_probability = 0.000, xtc_threshold = 0.100, typical_p = 1.000, top_n_sigma = -1.000, temp = 0.800
	mirostat = 0, mirostat_lr = 0.100, mirostat_ent = 5.000
2025-08-12 00:28:18 [DEBUG]
 Sampling: 
logits -> logit-bias -> penalties -> dry -> top-n-sigma -> top-k -> typical -> top-p -> min-p -> xtc -> temp-ext -> dist 
Generate: n_ctx = 4096, n_batch = 512, n_predict = 10, n_keep = 85
2025-08-12 00:28:18 [DEBUG]
 Total prompt tokens: 85
Prompt tokens to decode: 85
2025-08-12 00:28:18 [DEBUG]
 BeginProcessingPrompt
2025-08-12 00:28:18 [DEBUG]
 FinishedProcessingPrompt. Progress: 100
2025-08-12 00:28:19 [DEBUG]
 Target model llama_perf stats:
llama_perf_context_print:        load time =   16943.33 ms
llama_perf_context_print: prompt eval time =     708.96 ms /    85 tokens (    8.34 ms per token,   119.89 tokens per second)
llama_perf_context_print:        eval time =     154.39 ms /     9 runs   (   17.15 ms per token,    58.30 tokens per second)
llama_perf_context_print:       total time =     868.35 ms /    94 tokens
llama_perf_context_print:    graphs reused =          8
2025-08-12 00:28:19  [INFO]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f][Endpoint=listLoaded] Listing loaded models
2025-08-12 00:28:19 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:19 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:19 [DEBUG]
 Sampling params:	repeat_last_n = 64, repeat_penalty = 1.100, frequency_penalty = 0.000, presence_penalty = 0.000
	dry_multiplier = 0.000, dry_base = 1.750, dry_allowed_length = 2, dry_penalty_last_n = -1
	top_k = 40, top_p = 0.800, min_p = 0.050, xtc_probability = 0.000, xtc_threshold = 0.100, typical_p = 1.000, top_n_sigma = -1.000, temp = 0.300
	mirostat = 0, mirostat_lr = 0.100, mirostat_ent = 5.000
2025-08-12 00:28:19 [DEBUG]
 Sampling: 
logits -> logit-bias -> penalties -> dry -> top-n-sigma -> top-k -> typical -> top-p -> min-p -> xtc -> temp-ext -> dist 
Generate: n_ctx = 4096, n_batch = 512, n_predict = 500, n_keep = 147
2025-08-12 00:28:19 [DEBUG]
 Cache reuse summary: 69/147 of prompt (46.9388%), 69 prefix, 0 non-prefix
2025-08-12 00:28:19 [DEBUG]
 Total prompt tokens: 147
Prompt tokens to decode: 78
BeginProcessingPrompt
2025-08-12 00:28:19 [DEBUG]
 FinishedProcessingPrompt. Progress: 100
2025-08-12 00:28:20 [DEBUG]
 Target model llama_perf stats:
llama_perf_context_print:        load time =   16943.33 ms
llama_perf_context_print: prompt eval time =     335.72 ms /    78 tokens (    4.30 ms per token,   232.34 tokens per second)
llama_perf_context_print:        eval time =    1089.58 ms /    62 runs   (   17.57 ms per token,    56.90 tokens per second)
llama_perf_context_print:       total time =    1529.22 ms /   140 tokens
llama_perf_context_print:    graphs reused =         59
2025-08-12 00:28:20 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:20 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:20 [DEBUG]
 Sampling params:	repeat_last_n = 64, repeat_penalty = 1.100, frequency_penalty = 0.000, presence_penalty = 0.000
	dry_multiplier = 0.000, dry_base = 1.750, dry_allowed_length = 2, dry_penalty_last_n = -1
	top_k = 40, top_p = 0.800, min_p = 0.050, xtc_probability = 0.000, xtc_threshold = 0.100, typical_p = 1.000, top_n_sigma = -1.000, temp = 0.300
	mirostat = 0, mirostat_lr = 0.100, mirostat_ent = 5.000
2025-08-12 00:28:20 [DEBUG]
 Sampling: 
logits -> logit-bias -> penalties -> dry -> top-n-sigma -> top-k -> typical -> top-p -> min-p -> xtc -> temp-ext -> dist 
Generate: n_ctx = 4096, n_batch = 512, n_predict = 500, n_keep = 193
2025-08-12 00:28:20 [DEBUG]
 Cache reuse summary: 127/193 of prompt (65.8031%), 127 prefix, 0 non-prefix
2025-08-12 00:28:20 [DEBUG]
 Total prompt tokens: 193
Prompt tokens to decode: 66
BeginProcessingPrompt
2025-08-12 00:28:20 [DEBUG]
 FinishedProcessingPrompt. Progress: 100
2025-08-12 00:28:22 [DEBUG]
 Target model llama_perf stats:
llama_perf_context_print:        load time =   16943.33 ms
llama_perf_context_print: prompt eval time =     320.71 ms /    66 tokens (    4.86 ms per token,   205.79 tokens per second)
llama_perf_context_print:        eval time =    1777.61 ms /   103 runs   (   17.26 ms per token,    57.94 tokens per second)
llama_perf_context_print:       total time =    2139.03 ms /   169 tokens
llama_perf_context_print:    graphs reused =         99
2025-08-12 00:28:22 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:22 [DEBUG]
 Prompt successfully formatted with Harmony.
2025-08-12 00:28:22 [DEBUG]
 Sampling params:	repeat_last_n = 64, repeat_penalty = 1.100, frequency_penalty = 0.000, presence_penalty = 0.000
	dry_multiplier = 0.000, dry_base = 1.750, dry_allowed_length = 2, dry_penalty_last_n = -1
	top_k = 40, top_p = 0.800, min_p = 0.050, xtc_probability = 0.000, xtc_threshold = 0.100, typical_p = 1.000, top_n_sigma = -1.000, temp = 0.700
	mirostat = 0, mirostat_lr = 0.100, mirostat_ent = 5.000
2025-08-12 00:28:22 [DEBUG]
 Sampling: 
logits -> logit-bias -> penalties -> dry -> top-n-sigma -> top-k -> typical -> top-p -> min-p -> xtc -> temp-ext -> dist 
Generate: n_ctx = 4096, n_batch = 512, n_predict = 800, n_keep = 206
2025-08-12 00:28:22 [DEBUG]
 Cache reuse summary: 74/206 of prompt (35.9223%), 74 prefix, 0 non-prefix
2025-08-12 00:28:22 [DEBUG]
 Total prompt tokens: 206
Prompt tokens to decode: 132
BeginProcessingPrompt
2025-08-12 00:28:23 [DEBUG]
 FinishedProcessingPrompt. Progress: 100
2025-08-12 00:28:39 [DEBUG]
 Target model llama_perf stats:
llama_perf_context_print:        load time =   16943.33 ms
llama_perf_context_print: prompt eval time =     457.01 ms /   132 tokens (    3.46 ms per token,   288.84 tokens per second)
llama_perf_context_print:        eval time =   15504.95 ms /   799 runs   (   19.41 ms per token,    51.53 tokens per second)
llama_perf_context_print:       total time =   16263.67 ms /   931 tokens
llama_perf_context_print:    graphs reused =        773
2025-08-12 00:28:39 [DEBUG]
 [Client=dc47ace8-2ae1-4e92-ac64-e3dc6195158f] Client disconnected.
