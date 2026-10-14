#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-2' \
STATE_SURFACES_CONDITION='w1-639/pointer=fine/motion/start,w1-639/pointer=fine/motion/trough,w1-639/pointer=coarse/motion/start,w1-639/pointer=coarse/motion/trough' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-2.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
