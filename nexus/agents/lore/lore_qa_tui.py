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

from typing import List

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

    def __init__(self) -> None:
        super().__init__()
        self.input_history = []
        self.history_index = -1

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


if __name__ == "__main__":
    LoreQATerminal().run()


