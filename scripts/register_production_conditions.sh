#!/bin/bash
# Register all production conditions for Apex Audition
# 4 conditions testing frontier models with consistent parameters

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Registering production conditions for Apex Audition..."
echo

# Condition 1: GPT-5
echo "1/4: Registering GPT-5..."
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt5 \
  --provider openai \
  --model gpt-5 \
  --temperature 0.7 \
  --max-tokens 2048 \
  --label "Production: GPT-5" \
  --description "GPT-5 baseline with T=0.7" \
  --register-only

# Condition 2: GPT-4o
echo "2/4: Registering GPT-4o..."
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-gpt4o \
  --provider openai \
  --model gpt-4o \
  --temperature 0.7 \
  --max-tokens 2048 \
  --label "Production: GPT-4o" \
  --description "GPT-4o comparison with T=0.7" \
  --register-only

# Condition 3: Claude Sonnet 4.5
echo "3/4: Registering Claude Sonnet 4.5..."
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-sonnet45 \
  --provider anthropic \
  --model claude-sonnet-4-5-20250929 \
  --temperature 0.7 \
  --max-tokens 2048 \
  --label "Production: Sonnet 4.5" \
  --description "Claude Sonnet 4.5 with T=0.7" \
  --register-only

# Condition 4: Claude Opus 4.1
echo "4/4: Registering Claude Opus 4.1..."
python scripts/run_apex_audition_batch.py \
  --condition-slug prod-opus41 \
  --provider anthropic \
  --model claude-opus-4-1-20250514 \
  --temperature 0.7 \
  --max-tokens 2048 \
  --label "Production: Opus 4.1" \
  --description "Claude Opus 4.1 with T=0.7" \
  --register-only

echo
echo "✓ All production conditions registered!"
echo
echo "To run the full production batch (252 generations = 4 conditions × 21 contexts × 3 replicates):"
echo "  python scripts/run_apex_audition_batch.py --condition-slug <slug> --replicates 3 --verify-first"
