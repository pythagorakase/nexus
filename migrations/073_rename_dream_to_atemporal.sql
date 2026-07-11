-- 073_rename_dream_to_atemporal.sql
--
-- Rename the dream layer to reflect its clock semantics: the in-world clock
-- does not apply to dreams, hallucinations, or time-abnormal realms.

ALTER TYPE world_layer_type RENAME VALUE 'dream' TO 'atemporal';
