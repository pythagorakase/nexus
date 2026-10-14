#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-8' \
STATE_SURFACES_CONDITION='w1281-1535/pointer=fine/motion/start,w1281-1535/pointer=fine/motion/trough,w1536+/pointer=fine/reduce,w1536+/pointer=fine/motion/start' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-8.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
