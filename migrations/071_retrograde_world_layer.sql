-- 071_retrograde_world_layer.sql
--
-- First-class identity for Retrograde chunks (issue #442 structural
-- follow-up): generated-history chunks were world_layer='primary',
-- distinguishable only by S00E00 slugs and buried authorial_directives
-- markers — which is why they read as fake narrative. The chunks (the
-- synthetic retrieval/anchor artifacts) get their own layer; the
-- world_events rows they document remain primary-layer canon.
--
-- NOTE: ALTER TYPE ... ADD VALUE cannot run inside a transaction block
-- on older Postgres; the runner executes files as single transactions,
-- so use the IF NOT EXISTS form which is transaction-safe on PG12+.

ALTER TYPE world_layer_type ADD VALUE IF NOT EXISTS 'retrograde';
