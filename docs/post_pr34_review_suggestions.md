# Post-PR #34 Actionable Follow-Up Items

This document captures concrete remediation tasks identified during the comprehensive review of commits `6570d46^..a8976bd` (October 5–7, 2025). Items are grouped by domain so that teams can triage and schedule work.

## 1. MEMNON Agent & Hybrid Search
- [ ] Document the contamination-prevention workflow, including the trust boundaries, failure modes, and recovery steps. Publish alongside `nexus/agents/memnon/` README.
- [ ] Introduce configuration flags for rare-keyword boosting so different agents can dial weights without code changes. Ensure defaults match the current behaviour.
- [ ] Add regression benchmarks that compare pre/post hybrid-search latency and relevance. Track at least three corpora sizes (small, medium, large).

## 2. Apex Audition Backend Enhancements
- [ ] Produce a lightweight migration guide that maps new condition-note fields and export formats for existing deployments.
- [ ] Extend FastAPI tests to cover export responses, including CSV encoding, authorization, and large dataset streaming.
- [ ] Stress-test the context-generation script with production-scale data and document runtime expectations.

## 3. Progressive Web App Rollout
- [ ] Document cache strategy (offline vs. network-first) and service-worker update flow in the frontend README.
- [ ] Add automated or scripted smoke tests for iOS Safari and Android Chrome to verify PWA install/offline behaviour.
- [ ] Establish icon-asset guidelines (dimensions, file size limits) and confirm Git LFS usage expectations for designers.

## 4. Image Gallery & Asset Pipeline
- [ ] Implement server-side validation for uploaded images (MIME/type sniffing, file-size caps, dimension limits) and expand API tests to cover failure paths.
- [ ] Provide an operational playbook for filesystem storage: directory quotas, monitoring hooks, and cleanup automation.
- [ ] Evaluate S3-compatible object storage integration and prepare a migration plan that preserves existing file paths.

## 5. Database Schema & Migrations
- [ ] Align image-table migrations with the project’s migration tooling (Drizzle/SQL) and supply rollback scripts.
- [ ] Clarify boolean fields that currently use integer flags (e.g., `is_main`) and convert them where possible.
- [ ] Index new GeoJSON geometry fields and document their TypeScript bindings to prevent runtime parsing issues.

## 6. Security & Access Controls
- [ ] Audit image CRUD endpoints for role-based access, ensuring upload/delete operations respect entity ownership.
- [ ] Add rate limiting or throttling for bulk uploads to mitigate abuse vectors.
- [ ] Verify contamination-prevention logic includes logging and alerting for suspected incidents.

## 7. Developer Experience
- [ ] Update onboarding docs with Git LFS setup, the PostgreSQL default URL change, and any new environment variables.
- [ ] Make browser auto-open behaviour in the Iris launcher configurable (CLI flag or env variable) and document usage.
- [ ] Capture troubleshooting steps for service-worker cache busting when frontend deployments roll out new bundles.

---
These items should be reviewed, prioritized, and tracked in the project’s issue management system so they can be executed in upcoming sprints.
