#!/bin/zsh
set -eu
cd /Users/pythagor/.codex/worktrees/resume-shell-ui/nexus
STATE_SURFACES_SCRATCH='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/batch-1' \
STATE_SURFACES_CONDITION='w1101-1279/pointer=fine/reduce,w1-639/pointer=fine/reduce,w1-639/pointer=coarse/reduce,w640-760/pointer=coarse/reduce' \
STATE_SURFACES_OUTPUT='/tmp/nexus-777-shell-ui-4ae8b8d2/capture-v2/shards/batch-1.json' \
nice -n 15 npm --prefix ui run resolve-state-surfaces
