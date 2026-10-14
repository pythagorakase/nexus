#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-3' \
STATE_SURFACES_CONDITION='w640-760/pointer=fine/reduce,w640-760/pointer=fine/motion/start,w640-760/pointer=fine/motion/trough,w640-760/pointer=coarse/motion/start' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-3.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
