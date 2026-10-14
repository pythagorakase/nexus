#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-4' \
STATE_SURFACES_CONDITION='w640-760/pointer=coarse/motion/trough,w761-767/pointer=fine/reduce,w761-767/pointer=fine/motion/start,w761-767/pointer=fine/motion/trough' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-4.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
