The prompt-window counter loads `tokenizer_repository` with `AutoTokenizer.from_pretrained(repository, trust_remote_code=False)` in `nexus/telemetry/prompt_window.py:348-352`, without a pinned revision or `local_files_only`. This path also serves OpenRouter models whose registry entries declare a tokenizer repository.

The production artifact lock and `nexus models plan|fetch` cover only the embedder and production reranker. Decide whether the prompt-window tokenizer should join that lock and pinned fetch workflow, or remain a Hugging Face cache fetch. This issue records the choice without presuming either policy.

Refs #812

Codex — GPT-6
