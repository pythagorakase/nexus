ALTER TABLE global_variables ADD COLUMN gaia_model text;
ALTER TABLE global_variables ADD COLUMN apex_context_window integer;

COMMENT ON COLUMN global_variables.gaia_model IS
    'World State model registry ID for this story; NULL follows the story Skald model.';
COMMENT ON COLUMN global_variables.apex_context_window IS
    'Story context window in tokens; NULL uses the nexus.toml default.';
