-- 092_claim_distortion_depth.sql
--
-- Authored account variants may opt into deterministic hop-depth selection.
-- Propagation never invents or mutates account content.

ALTER TABLE claims
    ADD COLUMN distortion_min_depth integer,
    ADD CONSTRAINT claims_distortion_min_depth_check
        CHECK (distortion_min_depth >= 1);

COMMENT ON COLUMN claims.distortion_min_depth IS
    'NULL means this account is never auto-selected by propagation distortion (canonical accounts and manually granted variants); an integer d means propagation delivers this account instead of the scheduling account to listeners reached at hop depth >= d. Among qualifying sibling variants the largest distortion_min_depth wins, with ties resolved by lowest claim id.';
COMMENT ON CONSTRAINT claims_distortion_min_depth_check ON claims IS
    'Authored propagation-distortion thresholds begin at hop depth 1.';

-- No partial unique index is intentional: multiple authored variants may share
-- a threshold, and propagation resolves that ambiguity by lowest claim id.
