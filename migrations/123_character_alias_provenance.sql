-- Preserve authored aliases while rebuilding deterministic collision-free forms.
ALTER TABLE character_aliases ADD COLUMN provenance text NOT NULL DEFAULT 'authored';
COMMENT ON COLUMN character_aliases.provenance IS 'Alias origin: authored or generated deterministic collision-free generation.';
