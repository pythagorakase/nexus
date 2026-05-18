# Agent Workflow

This repository favors autonomous, end-to-end agent work once the task scope is
clear. Use this workflow for normal implementation tasks unless the user gives
more specific instructions.

## Branches, Commits, and PRs

- Create a feature branch for implementation work unless the user explicitly
  asks for a direct commit to `main`.
- Commit intentionally as useful work lands. Do not leave completed changes
  unstaged when pausing or handing off.
- Open a ready-for-review PR autonomously when the branch is validated. Use a
  draft PR only when the user explicitly asks for one.
- Include a concise PR summary, validation commands, and any schema,
  configuration, or data-impact notes.

## Review Orchestration

- After opening a PR, create a heartbeat to check agent review orchestration,
  review comments, failed checks, or merge readiness.
- Verify review-ready markers only after the downstream Claude workflow
  succeeds.
- If initial Codex or Claude feedback is present, address actionable items,
  validate locally, push fixes, and merge/prune when required checks pass.
- Do not wait for or expect re-reviews after follow-up commits unless there is
  explicit evidence of another required review cycle.
- Delete obsolete heartbeats after the PR is merged, closed, or no longer worth
  checking.

## When to Pause

Pause and ask the user before merging only when:

- review feedback conflicts or would cause a behavioral regression;
- required checks fail in a non-obvious way;
- the change has destructive data or migration implications;
- the remaining decision is genuinely a product, story, or design choice.

Otherwise, keep the fix, validate, merge, and prune loop moving.
