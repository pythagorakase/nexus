#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-7' \
STATE_SURFACES_CONDITION='w1280/pointer=fine/reduce,w1280/pointer=fine/motion/start,w1280/pointer=fine/motion/trough,w1281-1535/pointer=fine/reduce' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-7.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
