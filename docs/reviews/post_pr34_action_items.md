# Post-PR #34 Review Action Items

This document captures actionable follow-ups for the changes merged since PR #34 (commit range `6570d46^..a8976bd`). Tasks are grouped by area, with suggested owners and priorities to accelerate sign-off.

## 1. MEMNON Agent & Hybrid Search

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| High | Document contamination-prevention flow in `docs/` and add integration test covering an edge case (contaminated vs. clean context) | MEMNON team | Clarify triggering conditions and expected mitigation steps. |
| High | Capture before/after latency and relevance metrics for hybrid search updates | MEMNON team | Use existing retrieval benchmarks; share in team wiki. |
| Medium | Expose rare keyword weighting via configuration with sane defaults | MEMNON team | Allows tuning per-agent without code change. |
| Medium | Assess IDF dictionary memory footprint at current corpus size and plan caching strategy | MEMNON team | Include growth projections and eviction policy. |

## 2. Apex Audition Enhancements

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| High | Write migration guide for the new condition notes field and export flow | Backend | Cover schema adjustments and data backfill. |
| Medium | Add FastAPI tests for CSV export to ensure correct filtering and authorization | Backend QA | Guard against PII leakage in exports. |
| Medium | Profile `generate_apex_audition_contexts.py` on a full production dataset | Backend | Document runtime and memory requirements. |

## 3. Image Gallery System

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| High | Implement MIME/type and filesize validation plus filename sanitization for uploads | Backend Security | Reject unsupported or oversized files before disk write. |
| High | Produce database migration script (SQL or Drizzle) for new `assets` schema | Backend | Include rollback or cleanup instructions. |
| High | Add API authorization checks ensuring only permitted users can create/update/delete images | Backend | Confirm ownership validation in both routes and services. |
| Medium | Add automated tests covering upload → set main → delete lifecycle | Backend QA | Run against temporary storage to avoid residue. |
| Medium | Monitor disk usage and define alert thresholds for filesystem storage | DevOps | Consider migration path to object storage. |
| Low | Evaluate automatic thumbnail generation/compression pipeline | Backend | Preemptively address performance concerns. |

## 4. PWA & Frontend Updates

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| High | Document service worker caching strategy and update cadence | Frontend | Include guidance for clearing stale caches. |
| High | Validate PWA install/offline flows on Chrome (Android) and Safari (iOS) | QA | Record device/OS matrix and results. |
| Medium | Define cache invalidation policy for API schema changes | Frontend & Backend | Coordinate versioning between clients and API. |
| Low | Measure bundle size/regressions post-PWA work and plan optimizations if necessary | Frontend | Capture baseline metrics for future monitoring. |

## 5. Git LFS & Repository Hygiene

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| Medium | Publish contributor guide for Git LFS setup and usage | Dev Experience | Include troubleshooting for existing clones. |
| Medium | Estimate projected LFS storage growth and costs | DevOps | Share with leadership for budgeting. |
| Low | Audit `.gitignore` for image-related patterns and update as needed | Dev Experience | Ensure redundant or missing entries are addressed. |

## 6. Iris Launcher & Environment Defaults

| Priority | Task | Owner | Notes |
| --- | --- | --- | --- |
| Medium | Add documentation for new PostgreSQL defaults and how to override locally | Dev Experience | Update onboarding checklist. |
| Low | Provide configuration flag for auto-opening browser on demand | Dev Experience | Maintain previous workflow option. |

---

**Tracking:** Add these items to the shared engineering tracker and reference this document in the retrospective agenda.
