---
status: canonical
sources:
  - scripts/check_reachability.py
verified_commit: "55ab85a4468f0a46b5cbe7b0daacf66d8a890709"
---

# 0075: A Behavior-Preserving Reachability Index

**Kind:** decision
**Links:** #1129, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1129#issuecomment-6423094037.

> - **1129-D1.** Where does the repeatable synthetic scaling benchmark live: as a `scripts/` tool, as a pytest test, or as a `docs/qa` probe? Decision: The repeatable scaling benchmark is a stdlib-only probe at `docs/qa/1129-reachability-namespace-index/scaling_benchmark.py` that takes the gate script's path as an argument (loaded with `importlib.util.spec_from_file_location`) so one benchmark times both the c7ae2988 copy and the branch. It is formatted, typed and lint-clean because `docs/qa` is inside the repository's black, flake8 and mypy scope. Basis: The critique showed that a benchmark without a script-path argument reports only "after" numbers, and that `docs/qa` probes remain inside the black, flake8 and mypy scope. Reversal cost: Delete the probe.
> - **1129-D2.** When an import is alias-rewritten and still does not resolve, the namespace check at `scripts/check_reachability.py:423` tests the original, un-aliased name; should the optimization keep that behavior or also change it? Decision: The optimization is behavior-preserving only. The alias-rewritten namespace check keeps its current semantics. A test pins the current behavior. The PR's Deferred section names it as a latent misclassification, and the coordinator files it as a follow-up issue at landing. Basis: The scope of #1129 is performance, and the critique asked that the pinning test be framed as a record of current behavior rather than a contract. Reversal cost: A later slice changes the semantics with its own test.
> - **1129-D3.** Should the optimization also cover the AST parse cost, or change `[runtime.readiness].reachability_timeout_seconds`? Decision: No change to the AST parse path or to `[runtime.readiness].reachability_timeout_seconds`. Basis: Least change. Reversal cost: None.
> - **1129-D4.** How is the byte-identical `--report` proof taken, given that the branch's new tests change the gate's own inventory? Decision: The byte-identical `--report` proof runs both script versions (origin/main's copy and the branch's) against the same tree, never across different trees. Basis: The critique showed that across different trees the check cannot pass, because each new test becomes a report root. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
