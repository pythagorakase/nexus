---
description: Preflight check - audit docs, commit changes, and create PR
---

You are about to complete a full preflight workflow: audit documentation for accuracy, commit all changes to a feature branch, and create a pull request.

## Your Process

### Step 1: Review Recent Changes

Use `git status` and `git diff` to see what has changed since the last commit. Focus on understanding:
- Which files have been modified
- What functionality has changed
- What new code has been added
- What was removed or refactored

### Step 2: Documentation Audit

Use the Task tool to launch the scribe agent with a prompt that:
- Summarizes the code changes you identified
- Asks scribe to audit existing documentation (README.md, CLAUDE.md, relevant docstrings) for accuracy
- Requests specific findings about what is outdated (if anything)
- Asks for updates to any documentation that has become inaccurate

**Important**: Focus ONLY on existing documentation - don't create new docs. Check accuracy, not completeness.

### Step 3: Wait for Scribe Completion

After scribe completes, provide a brief summary to the user:
- If documentation is current: confirm that no updates were needed
- If updates were made: list which files were updated and why

### Step 4: Commit and Create PR

Once the documentation audit is complete (with any necessary updates made), proceed with the commit and PR workflow:

**Commit all your changes to the feature branch, or create a feature branch if we're currently on main. Submit this commit as a PR, including any immediately preceding commits that were not included in the last PR.**

Follow your standard commit and PR creation process, ensuring:
- All changes are staged (including any documentation updates from scribe)
- A descriptive commit message is generated based on the full scope of changes
- A feature branch is created if currently on main
- A pull request is created with appropriate title and description summarizing the changes

Proceed with the full preflight workflow now.
