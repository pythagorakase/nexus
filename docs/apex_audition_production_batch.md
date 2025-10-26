# Apex Audition Production Batch

## Overview

The Apex Audition system uses **database-managed conditions** as the single source of truth. Conditions define specific model configurations (provider, model, parameters) called "lanes" that are tested against prompts to compare performance.

**Current Configuration**: 26 active lanes across 7 models and 5 providers.

## Architecture

### Database as Source of Truth

All condition management happens in the `apex_audition.conditions` table:
- **Runtime**: All scripts query the database directly
- **UI Management**: Toggle `is_active` and `is_visible` flags via Manage Contenders dialog
- **No Config Files**: Database is the only source of truth (eliminates drift)

### Current Lanes (26 Total)

**OpenAI - GPT-5** (3 lanes):
- `gpt5.reason-min` - Minimal reasoning (fastest)
- `gpt5.reason-med` - Medium reasoning (balanced)
- `gpt5.reason-high` - High reasoning (thorough)

**OpenAI - o3** (3 lanes):
- `o3.reason-low` - Low reasoning effort
- `o3.reason-med` - Medium reasoning effort
- `o3.reason-high` - High reasoning effort

**OpenAI - GPT-4o** (3 lanes):
- `4o.t0-7` - Temperature 0.7
- `4o.t1-0` - Temperature 1.0
- `4o.t1-1` - Temperature 1.1

**Anthropic - Claude Sonnet 4.5** (3 lanes):
- `sonnet.t0-7.std` - T=0.7, standard (no extended thinking)
- `sonnet.t1-0.std` - T=1.0, standard
- `sonnet.t1-0.ext` - T=1.0, extended thinking (28k budget)

**Anthropic - Claude Opus 4.1** (2 lanes):
- `opus.t0-7.std` - T=0.7, standard
- `opus.t1-0.std` - T=1.0, standard

**DeepSeek** (3 lanes):
- `deepseek-v3.2-exp-t1.0` - Temperature 1.0
- `deepseek-v3.2-exp-t1.3` - Temperature 1.3
- `deepseek-v3.2-exp-t1.5` - Temperature 1.5

**Moonshot - Kimi K2** (4 lanes):
- `kimi.t0-60` - Temperature 0.6 baseline
- `kimi.t0-75.tp0-95.fp0-2` - T=0.75, top_p=0.95, frequency_penalty=0.2
- `kimi.t0-80.tp0-95.fp0-3` - T=0.80, top_p=0.95, frequency_penalty=0.3
- `kimi.t0-90.tp0-90.fp0-5.pp0-3.rp1-1` - Hot lane with multiple penalties

**Nous Research - Hermes 4 405B** (5 lanes):
- `hermes.t0-9.min0-05.rp1-10` - T=0.9, min_p=0.05, repetition_penalty=1.1
- `hermes.t1-1.min0-08.tp0-92.rp1-15` - T=1.1, min_p=0.08, top_p=0.92, repetition_penalty=1.15
- `hermes.t1-3.min0-10.tp0-88.rp1-20` - T=1.3, min_p=0.10, top_p=0.88, repetition_penalty=1.2
- `hermes.t1-5.min0-12.tp0-85.rp1-25.pp0-2` - T=1.5 with presence dampening
- `hermes.t1-7.min0-15.tp0-82.rp1-30.pp0-3` - T=1.7 hottest lane

### Token Budgets

- **Reasoning models** (GPT-5, o3): 36,000 output tokens
- **Standard models**: 2,048 - 6,000 output tokens
- **Extended thinking**: 36,000 total (varies by thinking budget)

### Critical Constraints

- **GPT-5 & o3**: NEVER include `temperature` parameter (use `reasoning_effort` instead)
- **Anthropic temperature**: Valid range 0.0 - 1.0 only
- **Anthropic extended thinking**: Cannot be combined with temperature parameter
- **Extended thinking**: Requires `thinking_budget_tokens` when `thinking_enabled=true`

## Managing Conditions

### Option 1: UI-Based Management (Recommended)

Use the **Manage Contenders** dialog in the Audition tab:
- Toggle `is_active` - Controls whether lane can run new generations
- Toggle `is_visible` - Controls whether lane appears in leaderboards/comparisons
- Real-time updates with automatic query invalidation

### Option 2: SQL-Based Management

#### View All Conditions

```sql
SELECT
    id, slug, provider, model_name, label,
    temperature, top_p, min_p,
    frequency_penalty, presence_penalty, repetition_penalty,
    reasoning_effort, thinking_enabled,
    max_output_tokens, thinking_budget_tokens,
    is_active, is_visible
FROM apex_audition.conditions
ORDER BY provider, model_name, id;
```

#### Add New Lane

```sql
INSERT INTO apex_audition.conditions (
    slug, provider, model_name, label,
    temperature, max_output_tokens,
    is_active, is_visible
) VALUES (
    '4o.t0-9',
    'openai',
    'gpt-4o',
    'GPT-4o T=0.9',
    0.9,
    6000,
    true,
    true
);
```

#### Update Lane Parameters

```sql
UPDATE apex_audition.conditions
SET temperature = 0.85,
    max_output_tokens = 8000
WHERE slug = '4o.t0-9';
```

#### Soft Delete (Recommended)

```sql
-- Disable lane without losing generation data
UPDATE apex_audition.conditions
SET is_active = false,
    is_visible = false
WHERE slug = 'deprecated-lane';
```

#### Hard Delete (DANGEROUS)

```sql
-- WARNING: Cascades to delete ALL generations and comparisons!
-- Check for generations first:
SELECT COUNT(*) FROM apex_audition.generations WHERE condition_id = 25;

-- If count > 0, use soft delete instead. Hard delete only if count = 0:
DELETE FROM apex_audition.conditions WHERE id = 25;
```

### Safety Notes

⚠️ **CASCADE DELETION WARNING**

The conditions table uses `ON DELETE CASCADE`:
- Deleting a condition **permanently deletes** all its generations
- Deleting generations **permanently deletes** all their comparisons
- This cannot be undone - expensive API data will be lost

**Best Practices:**
1. **Always soft-delete** by setting `is_active = false` and `is_visible = false`
2. **Only hard-delete** conditions with zero generations
3. **Check generation count** before any DELETE operation
4. **Use slug, not ID** when identifying conditions (IDs can change during migrations)

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

**Note:** Replicates are set to 1 because lanes themselves represent variations.

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

Run multiple lanes sequentially using batch API:

```bash
# OpenAI lanes
for lane in gpt5.reason-min gpt5.reason-med gpt5.reason-high \
            o3.reason-low o3.reason-med o3.reason-high \
            4o.t0-7 4o.t1-0 4o.t1-1; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# Anthropic lanes
for lane in sonnet.t0-7.std sonnet.t1-0.std sonnet.t1-0.ext \
            opus.t0-7.std opus.t1-0.std; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# DeepSeek lanes
for lane in deepseek-v3.2-exp-t1.0 deepseek-v3.2-exp-t1.3 deepseek-v3.2-exp-t1.5; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# Moonshot Kimi lanes
for lane in kimi.t0-60 kimi.t0-75.tp0-95.fp0-2 \
            kimi.t0-80.tp0-95.fp0-3 kimi.t0-90.tp0-90.fp0-5.pp0-3.rp1-1; do
  python scripts/run_apex_audition_batch.py \
    --condition-slug $lane \
    --created-by "your-name" \
    --notes "Production: $lane" \
    --batch-mode
  sleep 2
done

# Hermes lanes
for lane in hermes.t0-9.min0-05.rp1-10 \
            hermes.t1-1.min0-08.tp0-92.rp1-15 \
            hermes.t1-3.min0-10.tp0-88.rp1-20 \
            hermes.t1-5.min0-12.tp0-85.rp1-25.pp0-2 \
            hermes.t1-7.min0-15.tp0-82.rp1-30.pp0-3; do
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
- **Processing**: Async (typically 24 hours, may extend to 7 days during high load)
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
  g.condition_id,
  c.slug as lane_id,
  g.status,
  COUNT(*) as count,
  COUNT(*) FILTER (WHERE g.cache_hit) as cache_hits
FROM apex_audition.generations g
JOIN apex_audition.conditions c ON c.id = g.condition_id
WHERE g.run_id = '<run-id>'
GROUP BY g.condition_id, c.slug, g.status
ORDER BY c.slug, g.status;
```

### View Lane Coverage

```sql
SELECT
  c.slug as lane_id,
  c.is_active,
  c.is_visible,
  COUNT(g.id) as total_generations,
  COUNT(*) FILTER (WHERE g.status = 'completed') as completed,
  COUNT(*) FILTER (WHERE g.status = 'error') as errors,
  COUNT(*) FILTER (WHERE g.status = 'pending') as pending
FROM apex_audition.conditions c
LEFT JOIN apex_audition.generations g ON c.id = g.condition_id
GROUP BY c.id, c.slug, c.is_active, c.is_visible
ORDER BY c.slug;
```

### View Errors

```sql
SELECT
  c.slug as lane_id,
  g.prompt_id,
  g.error_message,
  g.created_at
FROM apex_audition.generations g
JOIN apex_audition.conditions c ON c.id = g.condition_id
WHERE g.status = 'error'
ORDER BY g.created_at DESC
LIMIT 20;
```

### Check for Generations Before Deletion

```sql
-- ALWAYS run this before deleting a condition
SELECT
  c.slug,
  COUNT(g.id) as generation_count,
  MIN(g.created_at) as first_generation,
  MAX(g.created_at) as last_generation
FROM apex_audition.conditions c
LEFT JOIN apex_audition.generations g ON c.id = g.condition_id
WHERE c.slug = 'lane-to-delete'
GROUP BY c.slug;
```

## Cost Tracking

Check API consoles for real-time usage:
- OpenAI: https://platform.openai.com/usage
- Anthropic: https://console.anthropic.com/settings/usage
