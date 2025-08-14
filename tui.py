"""
NEXUS TUI — Retrofuturistic Terminal UI

Run:
  poetry run python tui.py

Headless retrieval:
  poetry run python tui.py "<directive 1>" "<directive 2>" --chunk <id>

Interactive UI (default):
  poetry run python tui.py
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Input, Static, Log

# Command registry for CLI-like UX
AVAILABLE_COMMANDS: List[Dict[str, str]] = [
    {"name": "read", "usage": "/read s03e05[c004]|<chunk_id>", "description": "View scene (or by chunk id) with surrounding chunks"},
    {"name": "chunk", "usage": "/chunk <id>", "description": "Set target narrative chunk id"},
    {"name": "help", "usage": "/help [command]", "description": "Show available commands or details"},
    {"name": "status", "usage": "/status", "description": "Show component status"},
    {"name": "clear", "usage": "/clear", "description": "Clear conversation and telemetry"},
    {"name": "keep-model", "usage": "/keep-model on|off", "description": "Keep/unload LM Studio model after runs"},
]

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
    model_name: reactive[str] = reactive("(model: unknown)")
    db_health: reactive[str] = reactive("DB: ?")
    latency_ms: reactive[str] = reactive("— ms")
    token_info: reactive[str] = reactive("tokens: —")
    hint_text: reactive[str] = reactive("Ctrl+Q: Quit  Ctrl+C: Clear  Ctrl+S: Save  ↑/↓: History")

    def render(self) -> str:  # type: ignore[override]
        left = f"NEXUS TUI  {self.model_name}  {self.db_health}  {self.token_info}"
        right = f"⏱ {self.latency_ms}   {self.hint_text}"
        return f"[bold {COLOR_SYSTEM}]{left}[/]" + " " * 4 + f"[bold {COLOR_SYSTEM}]{right}[/]"


class ConversationView(Log):
    def on_mount(self) -> None:  # type: ignore[override]
        self.clear()
        self.write(f"[bold {COLOR_SYSTEM}]Welcome to NEXUS TUI. Type /help for commands.[/]")

    def add_user(self, text: str) -> None:
        self.write(f"[bold {COLOR_USER}](you)[/] {text}")

    def add_lore(self, text: str) -> None:
        self.write(f"[bold {COLOR_LORE_PRIMARY}](NEXUS)[/] {text}")

    def add_error(self, text: str) -> None:
        self.write(f"[bold {COLOR_ERROR}]✖ {text}[/]")


class ReasoningLog(Log):
    def on_mount(self) -> None:  # type: ignore[override]
        self.write(f"[bold {COLOR_SYSTEM}]Reasoning stream initialized…[/]")


class QueryList(DataTable):
    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("#", "Query")


class SearchProgress(DataTable):
    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("Query #", "Results", "Notes")


class SQLAttempts(DataTable):
    def on_mount(self) -> None:  # type: ignore[override]
        self.cursor_type = "row"
        self.add_columns("Step", "SQL (truncated)")


class TelemetryPanel(Vertical):
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
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Input(placeholder="Enter directive or /read …", id="prompt")
        yield Static(f"[dim]{StatusBar().hint_text}[/]", id="hints")


class CommandSuggestions(Static):
    entries: List[Dict[str, str]]

    def on_mount(self) -> None:  # type: ignore[override]
        self.entries = []
        self.display = False
        self.update("")

    def show_matches(self, query: str) -> None:
        prefix = query.lower().lstrip(":/").strip()
        if not prefix:
            matches = AVAILABLE_COMMANDS
        else:
            matches = [c for c in AVAILABLE_COMMANDS if c["name"].startswith(prefix)]
        self.entries = matches[:6]
        if not self.entries:
            self.display = False
            self.update("")
            return
        lines = [f"[bold {COLOR_SYSTEM}]/{e['name']}[/] [dim]{e['description']}[/]" for e in self.entries]
        self.update("\n".join(lines))
        self.display = True

    def hide(self) -> None:
        self.display = False
        self.update("")


class NexusTUI(App[None]):
    CSS = f"""
    Screen {{
        background: {COLOR_BG};
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
        height: 5;
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

    CommandSuggestions {{
        height: 2;
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
    current_chunk: Optional[int]

    def __init__(self) -> None:
        super().__init__()
        self.input_history = []
        self.history_index = -1
        self.lore = None
        self.current_chunk = None

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield StatusBar(id="status")
        with Horizontal(id="body"):
            yield ConversationView(id="conversation")
            yield TelemetryPanel(id="telemetry")
        yield InputBar(id="inputbar")
        yield CommandSuggestions(id="suggestions")
        yield Footer()

    def on_mount(self) -> None:  # type: ignore[override]
        status = self.query_one(StatusBar)
        status.model_name = "(model: pending)"
        status.db_health = "DB: pending"
        status.latency_ms = "—"
        status.token_info = "tokens: —"

        self.query_one(QueryList).add_row("1", "—")
        self.query_one(SearchProgress).add_row("1", "0", "—")
        self.query_one(SQLAttempts).add_row("1", "—")

    def action_clear_all(self) -> None:
        self.query_one(ConversationView).clear()
        self.query_one(ReasoningLog).clear()
        self.query_one(QueryList).clear(columns=False)
        self.query_one(SearchProgress).clear(columns=False)
        self.query_one(SQLAttempts).clear(columns=False)
        self.query_one(QueryList).add_row("1", "—")
        self.query_one(SearchProgress).add_row("1", "0", "—")
        self.query_one(SQLAttempts).add_row("1", "—")

    def action_save_transcript(self) -> None:
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
        raw = (event.value or "").strip()
        if not raw:
            return

        try:
            if raw.startswith(":") or raw.startswith("/"):
                self.query_one(CommandSuggestions).show_matches(raw)
            else:
                self.query_one(CommandSuggestions).hide()
        except Exception:
            pass

        # /read s03e05[c004] | /read <chunk_id>
        if raw.lower().startswith("/read"):
            arg = raw[5:].strip()
            try:
                await self._ensure_lore()
            except Exception as e:
                self.query_one(ConversationView).add_error(str(e))
                event.input.value = ""
                self.query_one(CommandSuggestions).hide()
                return

            if arg.isdigit():
                await self._display_chunk_and_neighbors(int(arg))
                event.input.value = ""
                self.query_one(CommandSuggestions).hide()
                return

            import re
            m = re.match(r"s(\d{1,2})e(\d{1,2})(?:c(\d{1,3}))?", arg, flags=re.IGNORECASE)
            if not m:
                self.query_one(ConversationView).add_error("Usage: /read s03e05[c004] or /read <chunk_id>")
                event.input.value = ""
                self.query_one(CommandSuggestions).hide()
                return
            season = int(m.group(1))
            episode = int(m.group(2))
            scene = int(m.group(3)) if m.group(3) else 1
            try:
                memnon = getattr(self.lore, "memnon", None)
                if not memnon:
                    raise RuntimeError("MEMNON unavailable")
                from sqlalchemy import text as _sqltext  # type: ignore
                with memnon.Session() as session:  # type: ignore[attr-defined]
                    row = session.execute(
                        _sqltext(
                            """
                            SELECT nc.id
                            FROM narrative_chunks nc
                            JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                            WHERE cm.season = :s AND cm.episode = :e AND cm.scene = :c
                            ORDER BY nc.id ASC
                            LIMIT 1
                            """
                        ),
                        {"s": season, "e": episode, "c": scene},
                    ).fetchone()
                if not row:
                    self.query_one(ConversationView).add_error("No chunk found for that S/E/Scene")
                else:
                    await self._display_chunk_and_neighbors(int(row[0]))
            except Exception as e:
                self.query_one(ConversationView).add_error(str(e))
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # /chunk <id> (alias for setting current_chunk)
        if raw.lower().startswith("/chunk") or raw.lower().startswith(":chunk"):
            parts = raw.split()
            if len(parts) >= 2 and parts[1].isdigit():
                self.current_chunk = int(parts[1])
                self.query_one(ConversationView).add_lore(f"[system] Target chunk set to {self.current_chunk}")
            else:
                self.query_one(ConversationView).add_error("Usage: /chunk <id>")
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # /status
        if raw.lower().startswith("/status") or raw.lower().startswith(":status"):
            try:
                await self._ensure_lore()
                s = self.lore.get_status() if self.lore else {}
                self.query_one(ConversationView).add_lore("[system] Status:")
                self.query_one(ConversationView).write(json.dumps(s, indent=2))
            except Exception as e:
                self.query_one(ConversationView).add_error(str(e))
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # /clear
        if raw.lower().startswith("/clear") or raw.lower().startswith(":clear"):
            self.action_clear_all()
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # /help [name]
        if raw.lower().startswith("/help") or raw.lower().startswith(":help"):
            parts = raw.split()
            if len(parts) == 1:
                lines = [f"/{c['name']} — {c['description']} (usage: {c['usage']})" for c in AVAILABLE_COMMANDS]
                self.query_one(ConversationView).add_lore("[system] Commands:\n" + "\n".join(lines))
            else:
                name = parts[1].lstrip("/:")
                found = next((c for c in AVAILABLE_COMMANDS if c["name"] == name), None)
                if found:
                    self.query_one(ConversationView).add_lore(
                        f"[system] /{found['name']} — {found['description']}\nusage: {found['usage']}"
                    )
                else:
                    self.query_one(ConversationView).add_error(f"No such command: {name}")
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # /keep-model on|off
        if raw.lower().startswith("/keep-model") or raw.lower().startswith(":keep-model"):
            parts = raw.split()
            if len(parts) >= 2:
                flag = parts[1].lower()
                try:
                    await self._ensure_lore()
                    if self.lore and getattr(self.lore, "llm_manager", None):
                        if flag == "on":
                            self.lore.llm_manager.unload_on_exit = False  # type: ignore[attr-defined]
                            self.query_one(ConversationView).add_lore("[system] keep-model: ON")
                        elif flag == "off":
                            self.lore.llm_manager.unload_on_exit = True  # type: ignore[attr-defined]
                            self.query_one(ConversationView).add_lore("[system] keep-model: OFF")
                        else:
                            self.query_one(ConversationView).add_error("Usage: /keep-model on|off")
                except Exception as e:
                    self.query_one(ConversationView).add_error(str(e))
            else:
                self.query_one(ConversationView).add_error("Usage: /keep-model on|off")
            event.input.value = ""
            self.query_one(CommandSuggestions).hide()
            return

        # Treat as a retrieval directive; require a target chunk set
        directive = raw
        if self.current_chunk is None:
            self.query_one(ConversationView).add_error("No target chunk set. Use /chunk <id> or /read … first.")
            event.input.value = ""
            return

        # Update conversation and UI state
        conversation = self.query_one(ConversationView)
        conversation.add_user(directive)
        self.input_history.append(directive)
        self.history_index = len(self.input_history)

        input_widget = self.query_one(Input)
        input_widget.value = ""
        input_widget.disabled = True
        self._set_status_busy()

        self.query_one(ReasoningLog).write(
            f"[dim]{time.strftime('%H:%M:%S')}[/] [bold {COLOR_SYSTEM}]queued[/] {directive}"
        )

        asyncio.create_task(self._run_retrieval_flow([directive], self.current_chunk))

    def _set_status_busy(self) -> None:
        self.query_one(StatusBar).latency_ms = "…"

    def _set_status_ready(self, elapsed_s: float) -> None:
        self.query_one(StatusBar).latency_ms = f"{int(elapsed_s * 1000)} ms"

    async def _display_chunk_and_neighbors(self, chunk_id: int, window: int = 2) -> None:
        try:
            await self._ensure_lore()
            memnon = getattr(self.lore, "memnon", None)
            if not memnon:
                raise RuntimeError("MEMNON unavailable")
            target = memnon.get_chunk_by_id(chunk_id)
            if not target:
                self.query_one(ConversationView).add_error(f"Chunk {chunk_id} not found")
                return
            self.current_chunk = chunk_id
            ids = list(range(max(1, chunk_id - window), chunk_id + window + 1))
            rendered: List[str] = []
            for cid in ids:
                data = memnon.get_chunk_by_id(cid)
                if not data:
                    continue
                header = data.get("header", f"(chunk {cid})")
                body = data.get("text", "")
                colored_lines = []
                for line in body.splitlines():
                    if line.strip().lower().startswith(("you ", "you\t", "you,")) or " you " in line.lower():
                        colored_lines.append(f"[bold {COLOR_USER_ALT}]{line}[/]")
                    else:
                        colored_lines.append(f"[bold {COLOR_LORE_PRIMARY}]{line}[/]")
                rendered.append(f"[dim]{header}[/]\n" + "\n".join(colored_lines))
            convo = self.query_one(ConversationView)
            convo.add_lore(f"[system] Target chunk set to {chunk_id}; showing ±{window}")
            for block in rendered:
                convo.write(block)
        except Exception as e:
            self.query_one(ConversationView).add_error(str(e))

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

    async def _run_retrieval_flow(self, directives: List[str], chunk_id: int) -> None:
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

            result: Dict[str, Any] = await lore.retrieve_context(directives, chunk_id=chunk_id)  # type: ignore[attr-defined]

            directives_map = result.get("directives") or {}
            for directive in directives:
                directive_data = directives_map.get(directive) if isinstance(directives_map, dict) else None
                if not directive_data and isinstance(directives_map, dict) and directives_map:
                    directive_data = list(directives_map.values())[0]

                synthesis = str((directive_data or {}).get("retrieved_context", "")).strip()
                conversation.add_lore(synthesis or "No context retrieved.")

                sources = (directive_data or {}).get("sources") or []
                if sources:
                    conversation.write("[dim]citations:[/]")
                    for cid in sources[:10]:
                        conversation.write(f"  [dim]- chunk_id:{cid}[/]")

                reasoning.clear()
                dir_reason = (directive_data or {}).get("reasoning")
                if isinstance(dir_reason, dict):
                    reasoning.write("[dim]structured reasoning:[/]")
                    try:
                        reasoning.write(json.dumps(dir_reason, indent=2))
                    except Exception:
                        reasoning.write(str(dir_reason))
                elif dir_reason:
                    reasoning.write(str(dir_reason))
                else:
                    reasoning.write("[dim]No reasoning provided.[/]")

                queries_table.clear(columns=False)
                for i, q in enumerate(result.get("queries") or [], start=1):
                    q_text = str(q)
                    q_text = q_text if len(q_text) <= 160 else q_text[:157] + "…"
                    queries_table.add_row(str(i), q_text)

                progress_table.clear(columns=False)
                sp = (directive_data or {}).get("search_progress") or []
                for idx, item in enumerate(sp, start=1):
                    if isinstance(item, dict):
                        cnt = str(item.get("result_count", ""))
                        notes = ""
                        progress_table.add_row(str(idx), cnt, notes)

                sql_table.clear(columns=False)
                attempts = (directive_data or {}).get("sql_attempts") or []
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
            try:
                input_widget.disabled = False
                input_widget.focus()
            except Exception:
                pass


async def _run_headless(directives: List[str], chunk_id: int, *, settings: str, agentic_sql: bool, keep_model: bool, debug: bool, save_json: Optional[str], save_md: Optional[str]) -> int:
    try:
        from nexus.agents.lore.lore import LORE
        lore = LORE(settings_path=settings, debug=debug)
        if agentic_sql:
            lore.settings.setdefault("Agent Settings", {}).setdefault("LORE", {}).setdefault("agentic_sql", True)
        if keep_model and getattr(lore, "llm_manager", None):
            try:
                lore.llm_manager.unload_on_exit = False  # type: ignore[attr-defined]
            except Exception:
                pass
        start = time.time()
        result: Dict[str, Any] = await lore.retrieve_context(directives, chunk_id=chunk_id)
        elapsed = time.time() - start
        if save_json:
            out_path = Path(save_json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"directives": directives, "chunk_id": chunk_id, "timings": {"elapsed_s": elapsed}, **result}
            out_path.write_text(json.dumps(payload, indent=2))
        if save_md:
            out_md = Path(save_md)
            out_md.parent.mkdir(parents=True, exist_ok=True)
            blocks = []
            for d, ddata in (result.get("directives") or {}).items():
                blocks.append(f"## {d}\n\n{ddata.get('retrieved_context','')}\n")
            out_md.write_text("\n".join(blocks))
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NEXUS TUI or headless retrieval CLI")
    parser.add_argument("directives", nargs="*", help="One or more retrieval directives (requires --chunk)")
    parser.add_argument("--chunk", type=int, help="Target narrative chunk id for retrieval (required with directives)")
    parser.add_argument("--repl", action="store_true", help="Run the Textual UI (default if no directives)")
    parser.add_argument("--agentic-sql", action="store_true", help="Enable agentic SQL (default: ON via settings.json)")
    parser.add_argument("--settings", default="settings.json", help="Path to settings.json (default: settings.json)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging for headless mode")
    parser.add_argument("--save-json", help="Path to save JSON transcript (headless mode)")
    parser.add_argument("--save-md", help="Path to save Markdown summary (headless mode)")
    parser.add_argument("--keep-model", action="store_true", help="Keep LM Studio model loaded (headless mode)")

    args = parser.parse_args()

    if args.directives:
        if not args.chunk:
            print(json.dumps({"error": "--chunk is required when providing directives"}))
            raise SystemExit(2)
        raise SystemExit(
            asyncio.run(
                _run_headless(
                    args.directives,
                    args.chunk,
                    settings=args.settings,
                    agentic_sql=args.agentic_sql,
                    keep_model=args.keep_model,
                    debug=args.debug,
                    save_json=args.save_json,
                    save_md=args.save_md,
                )
            )
        )
    else:
        NexusTUI().run()
