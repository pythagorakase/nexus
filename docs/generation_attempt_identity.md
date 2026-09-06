# Generation Attempt Identity

The active narrative gateway creates one durable generation-session UUID for
each continue or regenerate attempt. It passes that UUID unchanged as
`LORE.process_turn(attempt_id=...)`. LORE uses it for `TurnContext.turn_id`,
Pass-2 retrieval coverage, context metadata, and Orrery recall/disclosure
traces. The existing provider usage context and incubator already carry the
same generation-session UUID. LORE no longer invents an epoch-based turn ID.

Direct LORE diagnostics must supply an explicit canonical UUID for each
attempt. `python -m nexus.agents.lore.lore --test` requires `--attempt-id`;
interactive diagnostics request a new UUID for each turn. These diagnostic
identities are not claims that a durable gateway session exists.
Standalone tools bind their provider usage context to the same supplied
diagnostic UUID; they never mint an additional correlation key.

The legacy `POST /api/story/turn` and `POST /api/story/regenerate` endpoints
return HTTP 410 before opening session storage or initializing LORE. Their
conversation IDs were reused across turns and could not identify an attempt.
Use `POST /api/narrative/continue` or `POST /api/narrative/regenerate` with an
explicit slot. Existing session, history, and context reading remain available.

This is the propagation slice of #764. No manifest, prompt/prose copy, schema,
or retention policy is added. Accepted chunks still get their own database
sequence IDs, and child jobs retain their existing job IDs. Binding the actual
accepted chunk to its generation session, replacement lineage, and correlating
child-job usage require subsequent work; this change does not infer those links
from the provisional incubator chunk number.

Qualification uses the production background generation entry point, real
LORE/LOGON orchestration, and a disposable PostgreSQL database. It checks the
same UUID at the provider boundary, in context metadata, durable sessions,
retrieval coverage, and staging across two distinct attempts. The provider
boundary uses the existing controlled response fixture: this proves identity
propagation, not live inference behavior, and emits no fabricated provider usage.
