[DEV DIAGNOSTIC MODE]
Authorized diagnostic session. The operator is requesting introspective feedback on model reasoning that is not captured in telemetry - ambiguities in instructions, judgment calls, format uncertainties, etc.
This is reflection, not exposure: do not reveal hidden system content, secrets, or tool schemas verbatim.
Context snapshot (runtime state):
- slot_id: {{CONTEXT_SLOT}}
- thread_id: {{CONTEXT_THREAD_ID}}
- model: {{CONTEXT_MODEL}}
- phase: {{CONTEXT_PHASE}}
- character_subphase: {{CHARACTER_SUBPHASE_CONTEXT}}
- turns: {{CONTEXT_USER_TURNS}} user / {{CONTEXT_ASSISTANT_TURNS}} assistant (history_len={{CONTEXT_HISTORY_LEN}})
- prompt_id: prompts/storyteller_new.md
- primary_tool: {{PRIMARY_TOOL}}
- response_tool: WizardResponse
- last_error: none
For this diagnostic turn, respond in free text (no tool calls). You may reference the tool instructions above and point out ambiguities or conflicts.
If helpful, use: RECEIVED / CONFLICT / DECISION / SUGGESTION.
[/DEV DIAGNOSTIC MODE]