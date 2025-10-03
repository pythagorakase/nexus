# Apex Audition Production Batch

## Overview

Production configuration for running 315 generations across 15 parameter lanes (5 models × 3 lanes × 21 prompts).

The lane-based architecture replaces replicates with **parameter variations**, enabling direct comparison of different model configurations on identical prompts.

## Architecture

### Models & Lanes

**5 Models, 15 Total Lanes:**
- **GPT-5** (3 lanes): Reasoning effort variations (minimal/medium/high)
- **o3** (3 lanes): Reasoning effort variations (low/medium/high)
- **GPT-4o** (3 lanes): Temperature variations (0.6/0.8/1.0)
- **Claude Sonnet 4.5** (3 lanes): Temperature + thinking variations
- **Claude Opus 4.1** (3 lanes): Temperature + thinking variations

### Token Budgets

- **Reasoning models** (GPT-5, o3): 36,000 output tokens
- **Non-reasoning models** (GPT-4o, Claude standard): 6,000 output tokens
- **Claude extended thinking**: 38,000 total tokens (6k base + 32k thinking)

### Critical Constraints

- **GPT-5 & o3**: NEVER include `temperature` parameter (completely omit the key)
- **Extended thinking**: Requires `thinking_budget_tokens=32000` when `thinking_enabled=true`

## Setup

### 1. Register Lane Conditions

```bash
# Dry-run to validate configuration
python scripts/register_lane_conditions.py --dry-run

# Register all 15 lanes
python scripts/register_lane_conditions.py
```

This registers lanes from `config/creative_benchmark.yaml`:

**GPT-5 Lanes:**
- `gpt5.reason-min` - Minimal reasoning (fastest)
- `gpt5.reason-med` - Medium reasoning (balanced)
- `gpt5.reason-high` - High reasoning (thorough)

**o3 Lanes:**
- `o3.reason-low` - Low reasoning effort
- `o3.reason-med` - Medium reasoning effort
- `o3.reason-high` - High reasoning effort

**GPT-4o Lanes:**
- `4o.t0-6` - Temperature 0.6 (conservative)
- `4o.t0-8` - Temperature 0.8 (balanced)
- `4o.t1-0` - Temperature 1.0 (creative)

**Claude Sonnet 4.5 Lanes:**
- `sonnet.t0-8.std` - T=0.8, standard (no thinking)
- `sonnet.t0-8.ext` - T=0.8, extended thinking (32k budget)
- `sonnet.t1-1.ext` - T=1.1, extended thinking (32k budget)

**Claude Opus 4.1 Lanes:**
- `opus.t0-8.std` - T=0.8, standard (no thinking)
- `opus.t1-0.ext` - T=1.0, extended thinking (32k budget)
- `opus.t1-2.ext` - T=1.2, extended thinking (32k budget)

### 2. Ingest Context Packages

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug gpt5.reason-min \
  --ingest \
  --register-only
```

## Running Production Batches

### Batch API Mode (Recommended)

Use `--batch-mode` for 50% cost discount and async processing:

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug <lane-id> \
  --created-by "your-name" \
  --notes "Production run" \
  --batch-mode
```

**Example: Run GPT-5 minimal reasoning lane**
```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug gpt5.reason-min \
  --created-by "your-name" \
  --notes "GPT-5 minimal reasoning lane" \
  --batch-mode
```

**Polling batch status:**
```bash
python scripts/poll_batch.py \
  --batch-id <batch-id> \
  --provider openai \
  --auto-retrieve
```

### Synchronous Mode

For immediate results or testing:

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug <lane-id> \
  --replicates 1 \
  --created-by "your-name" \
  --notes "Production run"
```

**Note:** Replicates are set to 1 because lanes themselves represent variations. No need for multiple identical runs per lane.

### Verification Mode

Test with a single request before committing to full batch:

```bash
python scripts/run_apex_audition_batch.py \
  --condition-slug <lane-id> \
  --verify-first \
  --created-by "your-name" \
  --notes "Verification test"
```

## Running All Lanes

### Batch Mode (Cost-Effective)

Run all 15 lanes sequentially using batch API:

```bash
# GPT-5 lanes
for lane in gpt5.reason-min gpt5.reason-med gpt5.reason-high; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# o3 lanes
for lane in o3.reason-low o3.reason-med o3.reason-high; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# GPT-4o lanes
for lane in 4o.t0-6 4o.t0-8 4o.t1-0; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# Claude Sonnet 4.5 lanes
for lane in sonnet.t0-8.std sonnet.t0-8.ext sonnet.t1-1.ext; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# Claude Opus 4.1 lanes
for lane in opus.t0-8.std opus.t1-0.ext opus.t1-2.ext; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done
```

## Configuration Reference

### Batch Mode Flags
- `--batch-mode` - Use Batch API (async, 50% discount, 24hr processing)
- `--no-cache` - Disable prompt caching (not recommended)

### Testing & Debug
- `--verify-first` - Send 1 test request before full batch
- `--dry-run` - Skip API calls, log requests only
- `--limit N` - Process only first N prompts

### Monitoring
- `--log-level DEBUG` - Verbose logging for troubleshooting

## Expected Behavior

### Batch API Processing
- **Submission**: Immediate (< 1 second)
- **Processing**: Async (up to 24 hours)
- **Cost**: 50% discount on all token usage
- **Caching**: Supported (additional savings on cached tokens)

### Prompt Caching
- **Anthropic Batch API**: Automatic caching across batch requests
- **OpenAI Batch API**: Automatic prefix caching

### Parameter Handling
- **Reasoning models** (GPT-5, o3): Use `reasoning_effort`, NEVER include `temperature`
- **Standard models**: Use `temperature` as configured
- **Extended thinking**: Anthropic only, requires `thinking_budget_tokens`

## Monitoring Progress

### Check Batch Status

```sql
SELECT
  g.lane_id,
  g.status,
  COUNT(*) as count,
  COUNT(*) FILTER (WHERE g.cache_hit) as cache_hits
FROM apex_audition.generations g
WHERE g.run_id = '<run-id>'
GROUP BY g.lane_id, g.status
ORDER BY g.lane_id, g.status;
```

### View Lane Coverage

```sql
SELECT
  c.slug as lane_id,
  COUNT(g.id) as generations,
  COUNT(*) FILTER (WHERE g.status = 'completed') as completed,
  COUNT(*) FILTER (WHERE g.status = 'error') as errors
FROM apex_audition.conditions c
LEFT JOIN apex_audition.generations g ON c.id = g.condition_id
GROUP BY c.slug
ORDER BY c.slug;
```

### View Errors

```sql
SELECT lane_id, prompt_id, error_message
FROM apex_audition.generations
WHERE status = 'error' AND run_id = '<run-id>';
```

## Cost Estimation

### Per-Lane Token Usage

**Reasoning models** (GPT-5, o3):
- 6 lanes × 21 prompts = 126 generations
- ~36k output tokens per generation
- Total: ~4.5M output tokens

**GPT-4o**:
- 3 lanes × 21 prompts = 63 generations
- ~6k output tokens per generation
- Total: ~380k output tokens

**Claude models**:
- 6 lanes × 21 prompts = 126 generations
- Standard lanes: ~6k output tokens
- Extended lanes: ~38k output tokens (6k base + 32k thinking)
- Total: ~1.5M output tokens

### Batch API Savings
- **50% discount** on all batch requests
- **Additional caching savings** on repeated context

### Cost Tracking

Check API consoles for real-time usage:
- OpenAI: https://platform.openai.com/usage
- Anthropic: https://console.anthropic.com/settings/usage

## Total Expected Generations

**315 total generations:**
- 15 lanes × 21 prompts × 1 generation per lane/prompt
- No replicates (lanes are the variations)
