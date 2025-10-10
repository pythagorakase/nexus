-- Create global settings table for apex_audition
CREATE TABLE IF NOT EXISTS apex_audition.global_settings (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id = TRUE), -- Ensures only one row
    replicate_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert the single settings row
INSERT INTO apex_audition.global_settings (id, replicate_count)
VALUES (TRUE, 1)
ON CONFLICT (id) DO NOTHING;

-- Create trigger to update updated_at
CREATE OR REPLACE FUNCTION apex_audition.update_global_settings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_global_settings_timestamp
BEFORE UPDATE ON apex_audition.global_settings
FOR EACH ROW
EXECUTE FUNCTION apex_audition.update_global_settings_timestamp();
