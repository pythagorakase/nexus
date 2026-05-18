"""
LORE Q&A Retrofuturistic TUI.

Run:
  python nexus/agents/lore/lore_qa_tui.py

The legacy Q&A helper now returns direct MEMNON retrieval context rather than a
local-model synthesized answer.
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


def format_retrieval_context(result: Dict[str, Any]) -> str:
    """Format direct MEMNON retrieval results for human-facing displays."""

    answer = str(result.get("answer", "")).strip()
    if answer:
        return answer

    directives = result.get("directives") or {}
    if not isinstance(directives, dict):
        return "No relevant information found in the available story data."

    parts: list[str] = []
    for directive, payload in directives.items():
        if not isinstance(payload, dict):
            continue
        context = str(payload.get("retrieved_context", "")).strip()
        if context:
            parts.append(f"{directive}\n\n{context}")

    return (
        "\n\n---\n\n".join(parts)
        or "No relevant information found in the available story data."
    )


def collect_directive_field(result: Dict[str, Any], field_name: str) -> List[Any]:
    """Collect per-directive retrieval metadata into one flat list."""

    collected: List[Any] = []
    directives = result.get("directives") or {}
    if not isinstance(directives, dict):
        return collected

    for payload in directives.values():
        if not isinstance(payload, dict):
            continue
        value = payload.get(field_name)
        if isinstance(value, list):
            collected.extend(value)
        elif value:
            collected.append(value)
    return collected


class StatusBar(Static):
    """Header status bar showing product, retrieval mode, db, and hints."""

    retrieval_mode: reactive[str] = reactive("(retrieval: direct)")
    db_health: reactive[str] = reactive("DB: ?")
    latency_ms: reactive[str] = reactive("— ms")
    token_info: reactive[str] = reactive("tokens: —")
    hint_text: reactive[str] = reactive(
        "Ctrl+Q: Quit  Ctrl+C: Clear  Ctrl+S: Save  ↑/↓: History"
    )

    def render(self) -> str:
        left = f"LORE Q&A  {self.retrieval_mode}  {self.db_health}  {self.token_info}"
        right = f"⏱ {self.latency_ms}   {self.hint_text}"
        # Simple two-column feel by padding; Textual's Static render returns str
        return (
            f"[bold {COLOR_SYSTEM}]{left}[/]"
            + " " * 4
            + f"[bold {COLOR_SYSTEM}]{right}[/]"
        )


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
    """Direct retrieval trace."""

    def on_mount(self) -> None:  # type: ignore[override]
        self.write(f"[bold {COLOR_SYSTEM}]Retrieval trace initialized...[/]")


class QueryList(DataTable):
    """Retrieval queries table."""

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
        yield Static(f"[bold {COLOR_SYSTEM}]Retrieval Queries[/]")
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
        status.retrieval_mode = "(retrieval: direct)"
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
        self.query_one(ConversationView).add_lore(
            "[save placeholder] Transcript saving will be implemented in a later stage."
        )

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
        self.query_one(ReasoningLog).write(
            f"[dim]{time.strftime('%H:%M:%S')}[/] [bold {COLOR_SYSTEM}]queued[/] {question}"
        )

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
            status.retrieval_mode = "(retrieval: direct)"
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
            self.query_one(ConversationView).add_error(
                f"Failed to initialize LORE: {e}"
            )
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

            # Populate conversation with direct retrieval context.
            conversation.add_lore(format_retrieval_context(result))

            # Citations
            sources = result.get("sources") or []
            if sources:
                conversation.write("[dim]citations:[/]")
                for cid in sources[:10]:
                    conversation.write(f"  [dim]- chunk_id:{cid}[/]")

            # Reasoning
            reasoning.clear()
            reasoning_items = collect_directive_field(result, "reasoning")
            if reasoning_items:
                for item in reasoning_items:
                    reasoning.write(str(item))
            elif result.get("reasoning"):
                reasoning.write(str(result["reasoning"]))  # type: ignore[index]
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
            sp = result.get("search_progress") or collect_directive_field(
                result, "search_progress"
            )
            for idx, item in enumerate(sp, start=1):
                if isinstance(item, dict):
                    q = str(item.get("query", ""))
                    cnt = str(item.get("result_count", ""))
                    notes = ""
                    progress_table.add_row(str(idx), cnt, notes)

            # SQL attempts
            sql_table.clear(columns=False)
            attempts = result.get("sql_attempts") or collect_directive_field(
                result, "sql_attempts"
            )
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
    parser.add_argument(
        "--qa", help="Run headless Q&A with the given question (no TUI)"
    )
    parser.add_argument(
        "--repl", action="store_true", help="Run interactive headless CLI (no TUI)"
    )
    parser.add_argument(
        "--settings",
        default="settings.json",
        help="Path to settings.json for LORE (default: settings.json)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging for headless mode"
    )
    parser.add_argument(
        "--save-json", help="Path to save JSON transcript (headless mode)"
    )
    parser.add_argument(
        "--save-md", help="Path to save Markdown summary (headless mode)"
    )

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

                print("LORE Q&A CLI — type 'exit' or Ctrl+D to quit.\n")
                # Best-effort status line
                try:
                    status = lore.get_status()  # type: ignore[attr-defined]
                    comps = (
                        status.get("components", {}) if isinstance(status, dict) else {}
                    )
                    db = "ok" if comps.get("memnon") else "unavailable"
                    print(f"Status: retrieval=direct; db={db}\n")
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
                    print(f"\nRetrieved context:\n{format_retrieval_context(result)}\n")

                    sources = result.get("sources") or []
                    if sources:
                        print("Citations:")
                        for cid in sources[:10]:
                            print(f"- chunk_id:{cid}")
                        print()

                    reasoning_items = collect_directive_field(result, "reasoning")
                    reasoning_text = str(result.get("reasoning", "")).strip()
                    if reasoning_items or reasoning_text:
                        print("Reasoning:")
                        if reasoning_items:
                            for item in reasoning_items:
                                print(item)
                        else:
                            print(reasoning_text)
                        print()

                    queries = result.get("queries") or []
                    if queries:
                        print("Retrieval queries:")
                        for i, q in enumerate(queries, start=1):
                            q_text = str(q)
                            print(f" {i}. {q_text}")
                        print()

                    attempts = result.get("sql_attempts") or collect_directive_field(
                        result, "sql_attempts"
                    )
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
                            f"Retrieved context:\n\n{format_retrieval_context(result)}\n\n",
                            "Citations:\n"
                            + "\n".join(
                                [
                                    f"- chunk_id:{cid}"
                                    for cid in (result.get("sources") or [])
                                ]
                            ),
                            "\n\nReasoning:\n\n" + str(result.get("reasoning", "")),
                            f"\n\nElapsed: {int(elapsed*1000)} ms\n",
                        ]
                        out_md.write_text("".join(lines))
                    except Exception:
                        pass
                # Print to stdout
                print(json.dumps(result, indent=2))
                return 0
            except Exception as e:
                print(json.dumps({"error": str(e)}))
                return 1

        raise SystemExit(asyncio.run(_run_headless()))
    else:
        LoreQATerminal().run()
