-- Resolver occurrence stamping and the legacy non-Retrograde NULL backfill.
-- Fail before changing any row when its exact tick-chunk clock is unavailable.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.world_events AS we
        LEFT JOIN public.chunk_metadata AS cm ON cm.chunk_id = we.tick_chunk_id
        WHERE we.world_time IS NULL
          AND we.source IS DISTINCT FROM 'retrograde'
          AND cm.world_time IS NULL
    ) THEN
        RAISE EXCEPTION 'Migration 142: non-Retrograde event has no exact tick-chunk world clock';
    END IF;
END;
$$;

UPDATE public.world_events AS we SET world_time = cm.world_time FROM public.chunk_metadata AS cm WHERE we.world_time IS NULL AND we.source IS DISTINCT FROM 'retrograde' AND cm.chunk_id = we.tick_chunk_id;

COMMENT ON COLUMN public.world_events.world_time IS
    'Exact diegetic occurrence time, separate from database recording time. Resolver deeds and their detected signals use the tick chunk''s canonical chunk_metadata.world_time unless the caller supplies an explicit instant. System events may retain a scheduled instant before their committing chunk. tick_chunk_id records ordering and replay, not occurrence time. Migration 142 fills only legacy NULL non-Retrograde rows from their tick chunk''s canonical clock. Undated Retrograde history remains NULL pending its own chronology contract.';
