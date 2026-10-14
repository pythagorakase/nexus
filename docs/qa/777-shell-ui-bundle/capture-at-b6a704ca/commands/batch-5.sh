#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-5' \
STATE_SURFACES_CONDITION='w768-1023/pointer=fine/reduce,w768-1023/pointer=fine/motion/start,w768-1023/pointer=fine/motion/trough,w1024-1100/pointer=fine/reduce' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-5.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
