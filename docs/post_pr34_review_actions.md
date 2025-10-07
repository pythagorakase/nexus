# Post-PR #34 Comprehensive Review Actions

## Overview
This document captures actionable follow-up work identified during the comprehensive review of commits `6570d46^..a8976bd` (October 5–7, 2025). Items are grouped by priority and mapped to responsible areas so they can be scheduled and tracked.

## Must-Address Before Merging to `main`
1. **Document MEMNON contamination safeguards**  
   - Add an architecture note explaining how contamination is detected and blocked.  
   - Include operational guidance for configuring thresholds or overrides.  
   - Owners: MEMNON maintainers (`nexus/agents/memnon`).
2. **Harden image upload endpoints**  
   - Enforce MIME type and extension validation for PNG/JPEG files.  
   - Impose explicit file size limits and return descriptive errors.  
   - Sanitize filenames to prevent traversal and ensure predictable storage paths.  
   - Owners: Full-stack image gallery team (`ui/server`, `nexus/api`).
3. **Author migration guidance for new database objects**  
   - Provide SQL migration steps for `assets.character_images`, `assets.place_images`, and GeoJSON changes.  
   - Clarify rollback options and deployment order.  
   - Owners: Database/infra maintainers.
4. **Publish PWA behavior documentation**  
   - Describe offline capabilities, cache strategy, and update flow for the service worker.  
   - Call out browser limitations (especially iOS Safari).  
   - Owners: Frontend team (`ui/client`, `ui/server`).

## High-Priority (Next Sprint)
1. **Add automated tests for image workflows**  
   - Cover upload, main-image selection, deletion, and authorization.  
   - Include negative cases (oversized files, invalid types).  
   - Owners: Full-stack image gallery team.
2. **Benchmark MEMNON hybrid search tuning**  
   - Compare rare-keyword weighting against previous implementation using representative corpora.  
   - Document impact on latency and relevance metrics.  
   - Owners: MEMNON maintainers.
3. **Cross-browser PWA validation**  
   - Test install/offline flows on Android Chrome, iOS Safari, and desktop browsers.  
   - Capture issues and update documentation.  
   - Owners: Frontend QA.
4. **Define storage monitoring and quotas**  
   - Establish alerting for filesystem usage by uploaded images.  
   - Propose per-entity or per-user limits to prevent runaway growth.  
   - Owners: Operations/infra team.

## Medium-Term Enhancements
1. **Introduce image compression & thumbnails**  
   - Generate optimized derivatives for gallery and card views.  
   - Reduce bandwidth and improve load times.  
   - Owners: Full-stack image gallery team.
2. **Evaluate object storage migration path**  
   - Assess S3-compatible storage for scalability and redundancy.  
   - Outline migration tooling and CDN integration.  
   - Owners: Operations/infra team.
3. **Expand GeoJSON handling tests**  
   - Add coverage for invalid geometries, null coordinates, and alternative feature types.  
   - Owners: Backend mapping team.
4. **Enhance MEMNON configurability**  
   - Expose rare keyword boosting weights and contamination controls via settings.  
   - Ensure defaults remain backwards compatible.  
   - Owners: MEMNON maintainers.

## Open Questions Requiring Clarification
- What user roles are permitted to upload or delete gallery images?  
- How will service worker cache invalidation be coordinated with API changes?  
- Do we need an admin UI for bulk asset cleanup prior to shipping?

## Tracking & Next Steps
- Create tasks in the project tracker referencing this document.  
- Assign owners and due dates aligned with release planning.  
- Revisit during the next release readiness review to confirm completion status.
