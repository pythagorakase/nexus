-- 067_rename_orrery_templates.sql
--
-- Rename two orrery template ids so package names are self-evident:
--
--   reach_out_to_kin  -> reach_out     (gate widened beyond kin to friend/
--                                       companion ties; the old name would
--                                       misdescribe what fires)
--   pursue_ghost_lead -> uncover_past  (genre-neutral rewrite of the
--                                       buried-identity project arc)
--
-- template_id is denormalized onto six base tables (entity_tags_current is
-- a view over entity_tags and needs no update). Historical rows are
-- rewritten so provenance joins against the current catalog stay whole.

UPDATE entity_tags SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';
UPDATE entity_pair_tags SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';
UPDATE orrery_resolutions SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';
UPDATE orrery_adjudication_log SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';
UPDATE orrery_scene_pressures SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';
UPDATE orrery_prompt_exposures SET template_id = 'reach_out'
    WHERE template_id = 'reach_out_to_kin';

UPDATE entity_tags SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
UPDATE entity_pair_tags SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
UPDATE orrery_resolutions SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
UPDATE orrery_adjudication_log SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
UPDATE orrery_scene_pressures SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
UPDATE orrery_prompt_exposures SET template_id = 'uncover_past'
    WHERE template_id = 'pursue_ghost_lead';
