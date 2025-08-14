## LORE Q&A Mode and Retrofuturistic TUI — Implementation Plan

### Goals
- Add a non-narrative Q&A mode to `LORE` that answers questions about the existing narrative.
- Provide a retrofuturistic Textual-based TUI for interactive Q&A with live reasoning and retrieval telemetry.
- Ensure strict semantic/mechanical separation and hard-fail behavior when LM Studio is unavailable.

### Constraints
- All semantic understanding must go through `LocalLLMManager`.
- Fail hard if LM Studio is unavailable (no fallbacks).
- Q&A responses must cite concrete narrative `chunk_id` sources.
- Keep responses informational, not narrative prose.
- Keep edits scoped only to files listed below.

---

### Stage 0 — Grounding (No code changes)
- Review existing components:
  - `nexus/agents/lore/lore.py` (turn cycle, CLI entry)
  - `nexus/agents/lore/utils/local_llm.py` (availability, query, analysis, query generation)
  - `nexus/agents/memnon/memnon.py` and `utils/search.py` (hybrid/vector search, returning chunk IDs)
  - Tests under `tests/test_lore/` to mirror logging/reasoning capture patterns

Deliverable: This plan document.

---

### Stage 1 — Backend Q&A Mode (Minimal edits to `lore.py`)
Edits:
- Add `async def answer_question(self, question: str) -> Dict[str, Any]` to `nexus/agents/lore/lore.py` implementing:
  1) Availability check via `LocalLLMManager.is_available()` and hard-fail.
  2) Use `LocalLLMManager` to analyze the question and generate natural-language retrieval queries.
  3) Execute each query via `MEMNON.query_memory(..., use_hybrid=True)` to retrieve chunks.
  4) Synthesize a concise, factual answer via `LocalLLMManager.query(...)`, passing retrieved snippets and metadata.
  5) Return `{ answer, sources, queries, reasoning }` with `sources` as a unique list of `chunk_id`s actually used.

- Extend CLI in `lore.py` main to support:
  - `--qa "<question>"` → run `answer_question` once and print structured JSON (answer + sources + queries + timing + token usage when available).

Acceptance checks:
- Hard fails if LM Studio down.
- Returns chunk IDs in `sources`.
- No narrative generation; answer is informational.

---

### Stage 2 — Retrofuturistic TUI (`nexus/agents/lore/lore_qa_tui.py`)
New file:
- Build a Textual app with:
  - Status bar: LM Studio connection, model name, token usage.
  - Scrollable conversation history with color scheme:
    - LORE: greens (#41FF00, #33FF33, #39FF14)
    - User: violet/magenta (#9933FF / #CC66FF)
    - System/status: cyan (#00FFFF)
    - Errors: hot pink/orange (#FF33FF / #FF6633)
    - Background: black (#000000)
  - Real-time panels:
    - Reasoning stream (LLM trace emitted via incremental logs)
    - Generated queries panel
    - Search progress with live counts
    - Final answer with source citations (rich markdown)
  - Shortcuts: Ctrl+C (clear), Ctrl+Q (quit), Ctrl+S (save transcript), Up/Down (history)
  - Async tasks with spinners during processing

Integration:
- Import and use `LORE.answer_question()` for back-end calls.
- Provide `poetry run python nexus/agents/lore/lore_qa_tui.py` entry.

Acceptance checks:
- Visuals match palette and vibe.
- Live updates for reasoning, queries, and retrieval counts.

---

### Stage 3 — Tests (`tests/test_lore/test_qa_mode.py`)
New file tests covering:
- Question analysis and query generation (mocks/stubs for LM Studio if needed; prefer real availability check path but mark as skip if unavailable).
- Response synthesis from multiple sources.
- Source citation accuracy (ensure returned `sources` are actual `chunk_id`s).
- "I don't know" behavior when insufficient evidence.

Also add example questions per prompt:
- "What is Victor's relationship to Dynacorp?"
- "Describe the neural interface technology"
- "Who are Alex's allies?"
- "What happened in the Badlands?"

Acceptance checks:
- All tests pass locally via `poetry run pytest tests/test_lore/test_qa_mode.py -xvs`.

---

### Stage 4 — Docs
- Add `docs/lore_qa.md`: brief component overview, CLI usage, TUI controls, failure modes, performance notes.

---

### Stage 5 — Wiring and Commands
- Ensure `poetry run python -m nexus.agents.lore.lore --qa "..."` works.
- Ensure `poetry run python nexus/agents/lore/lore_qa_tui.py` launches the TUI.

---

### Non-Goals / Risks
- No fallback to remote LLMs; if LM Studio is down, we error fast.
- TUI token counters may report approximate values initially; refine later.

---

### Deliverables Checklist
- [ ] `lore.py` — `answer_question` method + `--qa` CLI
- [ ] `lore_qa_tui.py` — Textual TUI
- [ ] `tests/test_lore/test_qa_mode.py`
- [ ] `docs/lore_qa.md`

---

### Execution Notes
- Keep files concise (<300 LOC each where reasonable).
- Reuse existing `LocalLLMManager` and `MEMNON` APIs; avoid duplicating retrieval logic.
- Log via `logger = logging.getLogger("nexus.lore.qa")` for Q&A flow.

---

Please review and approve. Upon approval, I will implement Stage 1 and pause for review before proceeding to the TUI and tests.


