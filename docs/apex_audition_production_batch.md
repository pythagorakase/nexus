# Apex Audition Production Batch

## Overview

Production configuration for running 252 generations (4 conditions × 21 contexts × 3 replicates).

## Setup

### 1. Register Production Conditions

```bash
./scripts/register_production_conditions.sh
```

This registers 4 conditions:
- `prod-gpt5` - GPT-5 (T=0.7, max_tokens=2048)
- `prod-gpt4o` - GPT-4o (T=0.7, max_tokens=2048)
- `prod-sonnet45` - Claude Sonnet 4.5 (T=0.7, max_tokens=2048)
- `prod-opus41` - Claude Opus 4.1 (T=0.7, max_tokens=2048)

### 2. Ingest Context Packages

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt5 \
  --ingest \
  --register-only
```

## Running Production Batches

### Verification Mode (Recommended)

Test with a single request before committing to the full batch:

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt5 \
  --replicates 3 \
  --verify-first \
  --created-by "your-name" \
  --notes "Production batch: GPT-5"
```

### Full Batch Commands

**GPT-5** (63 generations: 21 contexts × 3 replicates)
```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt5 \
  --replicates 3 \
  --created-by "your-name" \
  --notes "Production batch: GPT-5"
```

**GPT-4o** (63 generations: 21 contexts × 3 replicates)
```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt4o \
  --replicates 3 \
  --created-by "your-name" \
  --notes "Production batch: GPT-4o"
```

**Claude Sonnet 4.5** (63 generations: 21 contexts × 3 replicates)
```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-sonnet45 \
  --replicates 3 \
  --created-by "your-name" \
  --notes "Production batch: Sonnet 4.5"
```

**Claude Opus 4.1** (63 generations: 21 contexts × 3 replicates)
```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-opus41 \
  --replicates 3 \
  --created-by "your-name" \
  --notes "Production batch: Opus 4.1"
```

## Configuration Flags

### Caching & Rate Limiting
- `--no-cache` - Disable prompt caching (not recommended for production)
- `--no-rate-limiting` - Disable rate limit enforcement (use with caution)
- `--max-retries 3` - Retry failed requests (default: 3)

### Testing & Debug
- `--verify-first` - Send 1 test request before full batch
- `--dry-run` - Skip API calls, log requests only
- `--limit N` - Process only first N contexts

### Monitoring
- `--log-level DEBUG` - Verbose logging for troubleshooting

## Expected Behavior

### Prompt Caching
- **Anthropic**: First request warms cache, subsequent requests hit cache within 5-minute window
- **OpenAI**: Automatic prefix caching with 5-10 minute TTL

### Context-Sequential Processing
- All 3 replicates for context #1 → All 3 replicates for context #2 → ...
- Maximizes cache hit rate within TTL window

### Rate Limiting
- Enforced based on `docs/api_limits.md`
- Automatic throttling with sliding window tracking
- No manual delays needed

### Auto-Retry
- 3 retry attempts with exponential backoff (1s, 2s, 4s)
- Handles transient failures automatically
- Failed requests after max retries recorded as "error" status

## Monitoring Progress

Check batch progress:
```sql
SELECT
  status,
  COUNT(*) as count,
  COUNT(*) FILTER (WHERE cache_hit) as cache_hits
FROM apex_audition.generations
WHERE run_id = '<run-id>'
GROUP BY status;
```

View errors:
```sql
SELECT prompt_id, replicate_index, error_message
FROM apex_audition.generations
WHERE status = 'error' AND run_id = '<run-id>';
```

## Cost Estimation

Check API console for real-time cost tracking:
- OpenAI: https://platform.openai.com/usage
- Anthropic: https://console.anthropic.com/settings/usage

Expected savings with caching:
- First request per context: Full cost (128K input tokens)
- Subsequent 2 replicates: ~90% discount on cached portion
