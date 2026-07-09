---
name: codex-first
description: "Route implementation work to Codex CLI; Claude specs, reviews, verifies. Use when a task is a buildable work order: implementation from a frozen spec, refactors, mechanical migrations, bug fixes with known repro, test writing, bulk exploration."
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Codex First

Claude Code sessions only. Codex/other harnesses: skip; never self-delegate.

Rationale: Claude (Fable/Opus) tokens metered + expensive; Codex flat-rate. GPT-5.5+ is usually the better and faster model at writing/implementing code; Claude wins at ergonomics — judgment, design, spec-writing, review, orchestration. So Codex types, Claude thinks and verifies.

## Route

Delegate to Codex (default for hands-on work):

- implementation from a frozen spec; refactors; mechanical migrations
- bug fixes with known repro; test writing; coverage fills
- CI fixes, dependency bumps, scripts/tooling
- bulk codebase exploration where raw reading ≫ the answer

Keep in Claude:

- design, API design, architecture, naming, UX judgment
- tasks where writing the spec IS the work (ambiguity = design)
- tiny edits (~<20 lines, single obvious change) — delegation overhead loses
- anything needing session tools: MCP (browser/computer-use), Keychain secrets
- destructive/irreversible ops, releases, pushes, GitHub mutations — Claude-side per git rules
- review of Codex output — never delegated, never skipped

Mixed task: Claude designs first, freezes spec, delegates build-out.
Heuristic: prompt reads as a work order → delegate; writing it forces decisions → design, Claude.

## Invoke

Prompt via temp file, never inline quoting:

```bash
P=$(mktemp); O=$(mktemp); cat >"$P" <<'EOF'
<goal, repo + key paths, constraints ("don't touch X"), non-goals, proof expected, output shape>
EOF
command codex exec --yolo -C <repo> \
  -c model_reasoning_effort="high" \
  -o "$O" - <"$P" 2>/dev/null
```

- `--yolo` is the house default; Codex may run commands/tests freely. Keep prompts scoped to the target repo.
- `command codex` bypasses any interactive shell wrapper (binary: `/opt/homebrew/bin/codex`)
- stderr suppressed (thinking noise bloats context); drop `2>/dev/null` only to debug a failing run
- read the `-o` file (`$O`) for the result; don't parse the JSONL stream
- long runs: Bash run_in_background, read the `-o` file on exit; don't kill quiet runs <30 min
- parallel independent tasks OK: separate repos/dirs, and mint a distinct `$O` per task — a shared fixed path silently clobbers one run's result with another's
- outside a git repo add `--skip-git-repo-check`

Follow-up fixes — cheaper than fresh runs, keeps context. `resume` has no `-C`/`--yolo`: run from the repo dir, spell the long flag. The `cd` is load-bearing, not stylistic — `resume --last` matches sessions by cwd, so launching from the wrong directory silently resumes an unrelated session (possibly a human's) and operates on the wrong tree:

```bash
(cd <repo> && command codex exec resume --last \
  --dangerously-bypass-approvals-and-sandbox \
  -o "$O2" - <"$P2" 2>/dev/null)
```

## Prompt Contract

Codex starts with zero session context. Every prompt: goal, exact repo/paths, constraints, non-goals, proof expected (exact test command), output shape ("report files changed + test output"). Spec quality decides success.

## Verify (Claude, Always)

- `git status -sb` + read the full diff; judge like a contributor PR
- run focused tests yourself or demand proof output; Codex claims are advisory
- iterate via resume; after 2 failed rounds, take over and do it directly
- normal closeout still applies: the `docs/agent_workflow.md` branch → PR → review → merge flow before ship

## Economics

Win = generation + exploration tokens moved to Codex; Claude spends only on spec + diff review. Don't ping-pong trivia through delegation; don't re-read what Codex already summarized.

## NEXUS Adaptations

Local deltas from the upstream skill (steipete/agent-scripts `codex-first`, imported 2026-07-09):

- **Model** comes from `~/.codex/config.toml` (`model = "gpt-5.5"` as of import; flip to `gpt-5.6` when live — the alias routes to `gpt-5.6-sol`). Don't pin `-m` in delegation runs; the config line is the single switch.
- **Reasoning effort**: config default is `xhigh`; the invocation template's `-c model_reasoning_effort="high"` deliberately overrides per-run (work orders rarely need `xhigh`). GPT-5.6 widens the ladder to `none`…`max`; OpenAI migration guidance is keep the current baseline, then trial one level lower.
- **`--yolo`** is a hidden alias for `--dangerously-bypass-approvals-and-sandbox` in codex-cli ≥0.143 (absent from `--help`, verified working).
- **Brew lags releases**: if the API rejects the configured model with "requires a newer version of Codex" and `brew upgrade codex` says up to date, the desktop app's auto-updated bundled binary at `/Applications/Codex.app/Contents/Resources/codex` works immediately — substitute it for `command codex` until the formula catches up (this is how gpt-5.6-sol day-one runs worked, 2026-07-09).
- **Repo conventions ride along free**: Codex reads `AGENTS.md` at the repo root automatically, so specs need only task-specific constraints — but NEXUS user directives that shape a spec's *acceptance criteria* still belong in the prompt when relevant: live tests over mocks, tunables in `nexus.toml` not hardcoded, loud errors over fallbacks, prompts under `prompts/` never in Python.
- Upstream references to `$maintainer-orchestrator` (multi-repo portfolio work) and `$autoreview` (his closeout) don't exist here; NEXUS is single-repo and closeout is `docs/agent_workflow.md`.
