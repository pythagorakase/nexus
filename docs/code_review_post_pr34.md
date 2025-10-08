# Post-PR #34 Actionable Suggestions

This document captures concrete follow-up work identified while reviewing the
changes merged after PR #34 (commit range `6570d46^..a8976bd`, October 5–7,
2025). Each item is phrased so it can be scheduled as a ticket or follow-up PR.

## 1. Security & Data Integrity

- **Harden image upload endpoints**: Enforce strict MIME/type checks (PNG,
  JPEG, JPG), apply upload size limits, and sanitize filenames to block path
  traversal before persisting to `character_portraits/` and `place_images/`.
- **Document and enforce authorization rules**: Clarify which roles may create
  or delete images, and ensure backend routes verify ownership/permissions for
  every CRUD action.
- **Explain MEMNON contamination prevention**: Add developer-facing docs that
  define "contamination," outline mitigation logic, and call out known
  edge-cases so the feature can be audited.

## 2. Reliability & Performance

- **Add automated coverage for new workflows**: Write tests that exercise image
  uploads, deletion, and GeoJSON parsing (including malformed payloads) as well
  as MEMNON rare-keyword retrieval paths and Apex audition exports.
- **Benchmark MEMNON search adjustments**: Produce before/after latency and
  relevance measurements to validate the new IDF weighting and rare-term boost.
- **Validate PWA caching strategy**: Explicitly define which assets use
  cache-first vs. network-first policies and add regression tests (or manual
  checklists) for offline/online transitions across Chrome and Safari.

## 3. Operations & Tooling

- **Publish migration guide**: Provide step-by-step instructions for creating
  the new `assets` schema, running manual SQL, and enabling Git LFS so existing
  deployments can upgrade safely.
- **Monitor storage usage**: Add alerts or dashboards that track disk
  consumption for filesystem-stored images and outline contingency plans for
  disk exhaustion.
- **Clarify developer setup changes**: Update onboarding docs to reflect the
  new PostgreSQL defaults in the `iris` launcher and highlight any required
  environment variable tweaks.

## 4. Future Enhancements (Schedule Next Sprint)

- **Implement image processing pipeline**: Introduce server-side resizing or
  compression plus thumbnail generation to improve load times and reduce
  storage footprint.
- **Explore object storage migration**: Evaluate S3-compatible backends for the
  growing image corpus, including cost estimates and CDN integration options.
- **Enhance admin tooling**: Design UI for bulk image management and consider
  quotas or cleanup jobs to manage large libraries.

