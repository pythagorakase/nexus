"""
LORE Q&A Retrofuturistic TUI (Scaffold)

Stage 1: App/screen/layout/theme only, no backend wiring yet.

Run:
  python nexus/agents/lore/lore_qa_tui.py

Planned wiring in next stages:
  - On submit, dispatch background `run_qa(question)`
  - Populate telemetry and conversation from LORE.answer_question payload
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Input, Static, Log


# Color/Style Map (1980s cyberpunk terminal)
COLOR_BG = "#000000"
COLOR_LORE_PRIMARY = "#41FF00"
COLOR_LORE_SECONDARY = "#33FF33"
COLOR_LORE_ALT = "#39FF14"
COLOR_USER = "#9933FF"
COLOR_USER_ALT = "#CC66FF"
COLOR_SYSTEM = "#00FFFF"
COLOR_ERROR = "#FF33FF"
COLOR_ERROR_ALT = "#FF6633"


class StatusBar(Static):
    """Header status bar showing product, model, db, and hints."""

    model_name: reactive[str] = reactive("(model: unknown)")
    db_health: reactive[str] = reactive("DB: ?")
    latency_ms: reactive[str] = reactive("— ms")
    token_info: reactive[str] = reactive("tokens: —")
    hint_text: reactive[str] = reactive("Ctrl+Q: Quit  Ctrl+C: Clear  Ctrl+S: Save  ↑/↓: History")

    def render(self) -> str:
        left = f"LORE Q&A  {self.model_name}  {self.db_health}  {self.token_info}"
        right = f"⏱ {self.latency_ms}   {self.hint_text}"
        # Simple two-column feel by padding; Textual's Static render returns str
        return f"[bold {COLOR_SYSTEM}]{left}[/]" + " " * 4 + f"[bold {COLOR_SYSTEM}]{right}[/]"


class ConversationView(Log):
    """Scrollable conversation pane with markdown-ish rendering."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.clear()
        self.write(
            f"[bold {COLOR_SYSTEM}]Welcome to LORE Q&A TUI (scaffold). Submit a question to begin.[/]"
        )

    def add_user(self, text: str) -> None:
        self.write(f"[bold {COLOR_USER}](you)[/] {text}")

    def add_lore(self, text: str) -> None:
        self.write(f"[bold {COLOR_LORE_PRIMARY}](LORE)[/] {text}")

    def add_error(self, text: str) -> None:
        self.write(f"[bold {COLOR_ERROR}]✖ {text}[/]")


class ReasoningLog(Log):
    """Live reasoning stream (LLM trace)."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.write(f"[bold {COLOR_SYSTEM}]Reasoning stream initialized…[/]")


class QueryList(DataTable):
    """Generated queries table."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("#", "Query")


class SearchProgress(DataTable):
    """Search progress table (per-query counts)."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("Query #", "Results", "Notes")


class SQLAttempts(DataTable):
    """SQL attempts table (step order)."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("Step", "SQL (truncated)")


class TelemetryPanel(Vertical):
    """Right side telemetry panel composed of multiple sections."""

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Static(f"[bold {COLOR_SYSTEM}]Reasoning[/]")
        yield ReasoningLog(id="reasoning")
        yield Static(f"[bold {COLOR_SYSTEM}]Generated Queries[/]")
        yield QueryList(id="queries")
        yield Static(f"[bold {COLOR_SYSTEM}]Search Progress[/]")
        yield SearchProgress(id="progress")
        yield Static(f"[bold {COLOR_SYSTEM}]SQL Attempts[/]")
        yield SQLAttempts(id="sql")


class InputBar(Container):
    """Footer input line with hint."""

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Input(placeholder="Ask LORE a question…", id="prompt")
        yield Static(f"[dim]{StatusBar().hint_text}[/]", id="hints")


class LoreQATerminal(App[None]):
    CSS = f"""
    Screen {{
        background: {COLOR_BG};
    }}

    .title {{
        color: {COLOR_SYSTEM};
    }}

    StatusBar {{
        dock: top;
        height: 1;
        color: {COLOR_SYSTEM};
        background: {COLOR_BG};
        content-align: left middle;
        padding: 0 1;
    }}

    InputBar {{
        dock: bottom;
        height: 3;
        background: {COLOR_BG};
        padding: 0 1;
    }}
    InputBar > Input#prompt {{
        border: tall {COLOR_USER_ALT};
    }}
    InputBar > Static#hints {{
        color: {COLOR_SYSTEM};
        padding-left: 1;
    }}

    #body {{
        height: 1fr;
    }}

    ConversationView {{
        border: round {COLOR_LORE_SECONDARY};
        color: {COLOR_LORE_ALT};
    }}

    TelemetryPanel {{
        border: round {COLOR_SYSTEM};
    }}
    TelemetryPanel > Static {{
        padding-left: 1;
    }}

    ReasoningLog, QueryList, SearchProgress, SQLAttempts {{
        height: auto;
        min-height: 5;
        border: tall {COLOR_SYSTEM};
    }}
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "clear_all", "Clear"),
        Binding("ctrl+s", "save_transcript", "Save"),
        Binding("up", "history_up", "History Up"),
        Binding("down", "history_down", "History Down"),
    ]

    input_history: List[str]
    history_index: int
    lore: Optional[object]

    def __init__(self) -> None:
        super().__init__()
        self.input_history = []
        self.history_index = -1
        self.lore = None

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield StatusBar(id="status")
        with Horizontal(id="body"):
            yield ConversationView(id="conversation")
            yield TelemetryPanel(id="telemetry")
        yield InputBar(id="inputbar")
        yield Footer()

    def on_mount(self) -> None:  # type: ignore[override]
        # Seed placeholder values in the header
        status = self.query_one(StatusBar)
        status.model_name = "(model: pending)"
        status.db_health = "DB: pending"
        status.latency_ms = "—"
        status.token_info = "tokens: —"

        # Seed telemetry placeholders
        queries = self.query_one(QueryList)
        queries.add_row("1", "—")
        progress = self.query_one(SearchProgress)
        progress.add_row("1", "0", "—")
        sql = self.query_one(SQLAttempts)
        sql.add_row("1", "—")

    def action_clear_all(self) -> None:
        self.query_one(ConversationView).clear()
        self.query_one(ReasoningLog).clear()
        self.query_one(QueryList).clear(columns=False)
        self.query_one(SearchProgress).clear(columns=False)
        self.query_one(SQLAttempts).clear(columns=False)
        # Re-add table headers since clear(columns=False) leaves them; if not, reinitialize
        # Ensure at least one empty row for visual structure
        self.query_one(QueryList).add_row("1", "—")
        self.query_one(SearchProgress).add_row("1", "0", "—")
        self.query_one(SQLAttempts).add_row("1", "—")

    def action_save_transcript(self) -> None:
        # Placeholder: stage 4 will implement save/load
        self.query_one(ConversationView).add_lore("[save placeholder] Transcript saving will be implemented in a later stage.")

    def action_history_up(self) -> None:
        if not self.input_history:
            return
        self.history_index = max(0, self.history_index - 1)
        self.query_one(Input).value = self.input_history[self.history_index]

    def action_history_down(self) -> None:
        if not self.input_history:
            return
        self.history_index = min(len(self.input_history) - 1, self.history_index + 1)
        self.query_one(Input).value = self.input_history[self.history_index]


    async def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        question = (event.value or "").strip()
        if not question:
            return

        # Update conversation and UI state
        conversation = self.query_one(ConversationView)
        conversation.add_user(question)
        self.input_history.append(question)
        self.history_index = len(self.input_history)

        input_widget = event.input
        input_widget.value = ""
        input_widget.disabled = True
        self._set_status_busy()

        # Give immediate feedback
        self.query_one(ReasoningLog).write(f"[dim]{time.strftime('%H:%M:%S')}[/] [bold {COLOR_SYSTEM}]queued[/] {question}")

        # Run in background to keep UI responsive
        asyncio.create_task(self._run_qa_flow(question))

    def _set_status_busy(self) -> None:
        status = self.query_one(StatusBar)
        status.latency_ms = "…"

    def _set_status_ready(self, elapsed_s: float) -> None:
        status = self.query_one(StatusBar)
        status.latency_ms = f"{int(elapsed_s * 1000)} ms"

    def _populate_status_from_lore(self) -> None:
        try:
            lore = self.lore
            if lore is None:
                return
            status = self.query_one(StatusBar)
            s = lore.get_status()  # type: ignore[attr-defined]
            comp = s.get("components", {}) if isinstance(s, dict) else {}
            status.model_name = "(model: local)" if comp.get("local_llm") else "(model: unavailable)"
            status.db_health = "DB: ok" if comp.get("memnon") else "DB: unavailable"
        except Exception:
            pass

    async def _ensure_lore(self) -> None:
        if self.lore is not None:
            return
        try:
            from nexus.agents.lore.lore import LORE  # Lazy import
            self.lore = LORE()
        except Exception as e:
            self.query_one(ConversationView).add_error(f"Failed to initialize LORE: {e}")
            raise

    async def _run_qa_flow(self, question: str) -> None:
        start = time.time()
        conversation = self.query_one(ConversationView)
        reasoning = self.query_one(ReasoningLog)
        queries_table = self.query_one(QueryList)
        progress_table = self.query_one(SearchProgress)
        sql_table = self.query_one(SQLAttempts)
        input_widget = self.query_one(Input)

        try:
            await self._ensure_lore()
            self._populate_status_from_lore()

            lore = self.lore
            assert lore is not None

            # Call backend
            result: Dict[str, Any] = await lore.answer_question(question)  # type: ignore[attr-defined]

            # Populate conversation
            answer = str(result.get("answer", "")).strip()
            conversation.add_lore(answer or "I don't know based on the available story data.")

            # Citations
            sources = result.get("sources") or []
            if sources:
                conversation.write("[dim]citations:[/]")
                for cid in sources[:10]:
                    conversation.write(f"  [dim]- chunk_id:{cid}[/]")

            # Reasoning
            reasoning.clear()
            if result.get("reasoning"):
                reasoning.write(result["reasoning"])  # type: ignore[index]
            else:
                reasoning.write("[dim]No reasoning trace provided.[/]")

            # Queries
            queries_table.clear(columns=False)
            queries = result.get("queries") or []
            for i, q in enumerate(queries, start=1):
                q_text = str(q)
                q_text = q_text if len(q_text) <= 160 else q_text[:157] + "…"
                queries_table.add_row(str(i), q_text)

            # Search progress
            progress_table.clear(columns=False)
            sp = result.get("search_progress") or []
            for idx, item in enumerate(sp, start=1):
                if isinstance(item, dict):
                    q = str(item.get("query", ""))
                    cnt = str(item.get("result_count", ""))
                    notes = ""
                    progress_table.add_row(str(idx), cnt, notes)

            # SQL attempts
            sql_table.clear(columns=False)
            attempts = result.get("sql_attempts") or []
            for i, att in enumerate(attempts, start=1):
                if isinstance(att, dict):
                    sql = str(att.get("sql", "")).replace("\n", " ")
                    if len(sql) > 120:
                        sql = sql[:117] + "…"
                    sql_table.add_row(str(i), sql or "—")

            elapsed = time.time() - start
            self._set_status_ready(elapsed)
        except Exception as e:
            conversation.add_error(str(e))
        finally:
            # Re-enable input
            try:
                input_widget.disabled = False
                input_widget.focus()
            except Exception:
                pass

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LORE Q&A TUI or headless CLI")
    parser.add_argument("--qa", help="Run headless Q&A with the given question (no TUI)")
    parser.add_argument("--repl", action="store_true", help="Run interactive headless CLI (no TUI)")
    parser.add_argument("--agentic-sql", action="store_true", help="Enable agentic SQL during headless Q&A")
    parser.add_argument("--settings", help="Path to settings.json for LORE")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging for headless mode")
    parser.add_argument("--save-json", help="Path to save JSON transcript (headless mode)")
    parser.add_argument("--save-md", help="Path to save Markdown summary (headless mode)")
    parser.add_argument("--keep-model", action="store_true", help="Keep LM Studio model loaded (headless mode)")

    args = parser.parse_args()

    if args.repl:
        async def _run_repl() -> int:
            """Run an interactive headless REPL for LORE Q&A.

            This mode avoids the Textual TUI and keeps interaction strictly in the terminal.
            It prints the answer and optional telemetry after each question.
            """
            try:
                from nexus.agents.lore.lore import LORE

                lore = LORE(settings_path=args.settings, debug=args.debug)
                if args.agentic_sql:
                    lore.settings.setdefault("Agent Settings", {}).setdefault("LORE", {}).setdefault("agentic_sql", True)
                if args.keep_model and getattr(lore, "llm_manager", None):
                    try:
                        lore.llm_manager.unload_on_exit = False  # type: ignore[attr-defined]
                    except Exception:
                        pass

                print("LORE Q&A CLI — type 'exit' or Ctrl+D to quit.\n")
                # Best-effort status line
                try:
                    status = lore.get_status()  # type: ignore[attr-defined]
                    comps = status.get("components", {}) if isinstance(status, dict) else {}
                    model = "local" if comps.get("local_llm") else "unavailable"
                    db = "ok" if comps.get("memnon") else "unavailable"
                    print(f"Status: model={model}; db={db}\n")
                except Exception:
                    pass

                while True:
                    try:
                        question = input("LORE> ").strip()
                    except EOFError:
                        print()
                        break
                    if not question:
                        continue
                    if question.lower() in {"exit", "quit", ":q", ":q!"}:
                        break

                    start = time.time()
                    try:
                        result: Dict[str, Any] = await lore.answer_question(question)  # type: ignore[attr-defined]
                    except Exception as e:
                        print(f"[error] {e}")
                        continue

                    elapsed_ms = int((time.time() - start) * 1000)
                    answer = str(result.get("answer", "")).strip()
                    print(f"\nAnswer:\n{answer}\n")

                    sources = result.get("sources") or []
                    if sources:
                        print("Citations:")
                        for cid in sources[:10]:
                            print(f"- chunk_id:{cid}")
                        print()

                    reasoning_text = str(result.get("reasoning", "")).strip()
                    if reasoning_text:
                        print("Reasoning:")
                        print(reasoning_text)
                        print()

                    queries = result.get("queries") or []
                    if queries:
                        print("Generated queries:")
                        for i, q in enumerate(queries, start=1):
                            q_text = str(q)
                            print(f" {i}. {q_text}")
                        print()

                    attempts = result.get("sql_attempts") or []
                    if attempts:
                        print("SQL attempts:")
                        for i, att in enumerate(attempts, start=1):
                            if isinstance(att, dict):
                                sql = str(att.get("sql", "")).replace("\n", " ")
                                if len(sql) > 200:
                                    sql = sql[:197] + "…"
                                print(f" {i}. {sql}")
                        print()

                    print(f"Elapsed: {elapsed_ms} ms\n")

                return 0
            except Exception as e:
                print(json.dumps({"error": str(e)}))
                return 1

        raise SystemExit(asyncio.run(_run_repl()))
    elif args.qa:
        async def _run_headless() -> int:
            try:
                from nexus.agents.lore.lore import LORE
                lore = LORE(settings_path=args.settings, debug=args.debug)
                if args.agentic_sql:
                    lore.settings.setdefault("Agent Settings", {}).setdefault("LORE", {}).setdefault("agentic_sql", True)
                start = time.time()
                result: Dict[str, Any] = await lore.answer_question(args.qa)
                elapsed = time.time() - start
                # Save outputs if requested
                if args.save_json:
                    try:
                        out_path = Path(args.save_json)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        payload = {
                            "question": args.qa,
                            "timings": {"elapsed_s": elapsed},
                            **result,
                        }
                        out_path.write_text(json.dumps(payload, indent=2))
                    except Exception:
                        pass
                if args.save_md:
                    try:
                        out_md = Path(args.save_md)
                        out_md.parent.mkdir(parents=True, exist_ok=True)
                        lines = [
                            f"# LORE Q&A\n",
                            f"Question: {args.qa}\n\n",
                            f"Answer:\n\n{result.get('answer','')}\n\n",
                            "Citations:\n" + "\n".join([f"- chunk_id:{cid}" for cid in (result.get('sources') or [])]),
                            "\n\nReasoning:\n\n" + str(result.get("reasoning", "")),
                            f"\n\nElapsed: {int(elapsed*1000)} ms\n",
                        ]
                        out_md.write_text("".join(lines))
                    except Exception:
                        pass
                # Print to stdout
                print(json.dumps(result, indent=2))
                if args.keep_model and getattr(lore, "llm_manager", None):
                    try:
                        lore.llm_manager.unload_on_exit = False  # type: ignore[attr-defined]
                    except Exception:
                        pass
                return 0
            except Exception as e:
                print(json.dumps({"error": str(e)}))
                return 1

        raise SystemExit(asyncio.run(_run_headless()))
    else:
        LoreQATerminal().run()


