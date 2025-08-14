"""
NEXUS TUI — Retrofuturistic Terminal UI

Run:
  poetry run python tui.py

Headless REPL:
  poetry run python tui.py --repl

One-shot headless:
  poetry run python tui.py --qa "your question"
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse the existing Textual app from LORE TUI for now
# This centralizes the UI entrypoint at project root while we generalize modules later
from nexus.agents.lore.lore_qa_tui import LoreQATerminal  # type: ignore


async def _run_headless(args) -> int:
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
        result: Dict[str, Any] = await lore.answer_question(args.qa)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NEXUS TUI or headless CLI")
    parser.add_argument("--qa", help="Run headless Q&A with the given question (no TUI)")
    parser.add_argument("--repl", action="store_true", help="Run interactive headless CLI (no TUI)")
    parser.add_argument("--agentic-sql", action="store_true", help="Enable agentic SQL (default: ON via settings.json)")
    parser.add_argument("--settings", default="settings.json", help="Path to settings.json (default: settings.json)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging for headless mode")
    parser.add_argument("--save-json", help="Path to save JSON transcript (headless mode)")
    parser.add_argument("--save-md", help="Path to save Markdown summary (headless mode)")
    parser.add_argument("--keep-model", action="store_true", help="Keep LM Studio model loaded (headless mode)")

    args = parser.parse_args()

    if args.qa:
        raise SystemExit(asyncio.run(_run_headless(args)))
    elif args.repl:
        # For now, defer to the LORE TUI's REPL path by invoking it directly
        LoreQATerminal().run()
    else:
        LoreQATerminal().run()
