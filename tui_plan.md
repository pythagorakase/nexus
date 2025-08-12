## LORE Q&A Retrofuturistic TUI — Detailed Build Plan

### Purpose
Deliver a Textual-based retrofuturistic terminal UI for LORE’s Q&A “vibe check” mode that visibly streams the agent’s reasoning, retrieval progression, SQL steps, and final answer with narrative citations. Align with the color scheme and aesthetic from the original prompt while integrating the current backend (agentic SQL + hybrid retrieval + synthesis).

### References and Requirements
- From `prompt.md`:
  - Aesthetic: 1980s cyberpunk terminal (black bg, console greens for LORE, violet/magenta for user, cyan for system, hot pink/orange for errors)
  - Features: status bar (LM Studio + model), scrollable conversation, real-time reasoning/queries/search progress, final answer with citations
  - Keybindings: Ctrl+C (clear), Ctrl+Q (quit), Ctrl+S (save), Up/Down (history)
  - Rich markdown rendering, async updates, loading spinners, token counts/utilization
- From `plan.md`:
  - TUI file: `nexus/agents/lore/lore_qa_tui.py`
  - Use `LORE.answer_question()` as backend call
  - Provide CLI `poetry run python nexus/agents/lore/lore_qa_tui.py`
- Current backend status:
  - `LORE.answer_question(question)` implements:
    - Agentic SQL (structured planning with few-shot examples, duplicate-SQL guard)
    - Hybrid retrieval (multi-model vectors; text leg adjustable; k≈8 per query)
    - Minimal query generator (verbatim user question + entity tokens; deduped)
    - Spot-reading (neighbors around best chunk)
    - Output: `answer`, `sources` (chunk_ids), `structured_sources`, `queries`, `reasoning`, `search_progress`, `sql_attempts`
  - LM Studio model ensuring via `ModelManager`; `--keep-model` CLI; structured output via `LocalLLMManager`
  - System prompt updated to document tools and flow

### High-Level UX
Screen split into four regions:
1) Header status bar (fixed)
   - Left: LORE Q&A; LM Studio connection/model; DB health; token usage
   - Right: clock; last latency; keybinding hints
2) Conversation pane (left, scrollable)
   - Alternating user/LORE messages; Rich markdown; color-coded
3) Live telemetry pane (right)
   - Reasoning stream (LLM trace)
   - Generated queries
   - Search progress (per-query counts)
   - SQL attempts (step order)
4) Footer input line
   - Prompt input; spinner during processing

### Color/Style Map
- Background: #000000
- LORE responses: #41FF00 / #33FF33 / #39FF14
- User input: #9933FF or #CC66FF
- System/status: #00FFFF
- Errors: #FF33FF or #FF6633

### Widgets and Layout (Textual)
- `QAScreen` (Screen)
  - Header: `StatusBar`
  - Body: Horizontal split
    - Left: `ConversationView` (scrollable + Rich)
    - Right: `TelemetryPanel` (sections): `ReasoningLog`, `QueryList`, `SearchProgress`, `SQLAttempts`
  - Footer: `InputBar` (input widget with hints)

### Data Flow and Async Model
- On Enter: dispatch `run_qa(question)` in background
- Append user message → disable input → show spinner
- Await `LORE.answer_question` → populate panels:
  - Conversation: `answer` + citations
  - Reasoning: `reasoning`
  - Queries: `queries`
  - Progress: `search_progress`
  - SQL: `sql_attempts`
  - Structured: `structured_sources`
  - Status: elapsed time; token usage (placeholder)
- Errors: render in telemetry + header

### Keybindings
- Ctrl+Q: Quit
- Ctrl+C: Clear conversation + telemetry
- Ctrl+S: Save transcript (JSON/Markdown)
- Up/Down: Input history

### Token/Latency Telemetry
- Initial: elapsed seconds per op; simple counters
- Later: integrate with `TokenBudgetManager`

### Theming and Rendering
- Rich markdown for answers; citations as code-fenced list
- Tables for queries/search/SQL with cyan borders
- Truncate long SQL; expand on selection/copy

### File Structure
- `nexus/agents/lore/lore_qa_tui.py`
  - Textual app + widgets + styles
  - `run_qa` coroutine wiring to `LORE`
  - CLI entry

### Integration Points
- LM Studio status via `LocalLLMManager`
- DB reachability via MEMNON methods
- Use `LORE.answer_question()` payload

### Error Handling
- Hard fail surfaces; show fatal message
- Empty results → “No evidence” state

### Performance Targets
- Keep UI responsive; background tasks; target ~5s typical

### Save/Load Transcript
- Save JSON with: question, answer, sources, structured_sources, queries, reasoning, search_progress, sql_attempts, timings
- Optionally save Markdown summary

### Testing Checklist
- Ask example questions; verify:
  - Status/model
  - Reasoning and SQL attempts stream
  - Queries/search counts
  - Citations and structured sources
  - Keybindings and transcript

### Implementation Steps
1) Scaffold `lore_qa_tui.py` with app/screen/layout/theme
2) Input handling + background `run_qa`
3) Populate panels from payload; spinners
4) Keybindings + transcript save
5) Polish visuals
6) Manual test with provided prompts

### Risks / Notes
- SQL logs can be long; sensible truncation
- Token reporting approximate initially
- LM Studio unload warnings benign; `--keep-model` available


