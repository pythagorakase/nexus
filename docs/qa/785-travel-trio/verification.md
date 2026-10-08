# Resumed travel trio verification

Part A reproduces native ETA-independent arrival; Part B refuses unroutable
choices and explicit journeys; Part C updates only source-supported defaults.
No elapsed-time arrival fix, new route charting, migration or UI change is in
this slice. Owner gateways remain stopped; a restart is owed when resumed.

- [Parts A/B proof](parts-a-b.md): identical seeded fast/slow native travel
  sequences, sync/async routing and rollback checks, mutation control, static
  delta, read-only fleet survey and independent corpus review.
- [Calibration proof](calibration.md): source/retention decisions, before/after
  samples, read-only geodesic calculations and corpus exclusions.
- Calibration and configured-override tests:22 passed. Black, flake8 and mypy
  passed both changed C test files. Document freshness:42 passed, guard active.
- Complete combined PostgreSQL gate and PR review are coordinator work;
  these focused results do not claim the full gate.

Codex — GPT-6
