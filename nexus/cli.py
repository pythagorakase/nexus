"""CLI entry point for NEXUS headless workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.api.narrative import (
    ApproveNarrativeRequest,
    ChatRequest,
    ContinueNarrativeRequest,
    TransitionRequest,
    approve_narrative,
    generate_narrative_async,
    get_db_connection,
    get_narrative_status,
    get_new_story_model,
    new_story_chat_endpoint,
    transition_to_narrative_endpoint,
)
from nexus.config import load_settings_as_dict


def load_settings_data(settings_path: Path) -> Dict[str, Any]:
    """Load settings.json from the provided path."""
    return load_settings_as_dict(str(settings_path))


def parse_optional_json(value: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse a JSON string into a dictionary when provided."""
    if value is None:
        return None
    return json.loads(value)


def load_json_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Load JSON content from a file path if provided."""
    if path is None:
        return None
    return json.loads(Path(path).read_text())


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    """Format datetime objects as ISO strings for JSON output."""
    if value is None:
        return None
    return value.isoformat()


def emit_output(payload: Dict[str, Any], as_json: bool) -> None:
    """Emit payload to stdout in JSON or human-readable format."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    message = payload.get("message")
    if message:
        print(message)

    if "choices" in payload:
        print("Choices:")
        for idx, choice in enumerate(payload["choices"], start=1):
            print(f"  {idx}. {choice}")

    if "storyteller_text" in payload and payload["storyteller_text"]:
        print(payload["storyteller_text"])

    if "status" in payload and payload.get("status") not in {"ok", None}:
        print(f"Status: {payload['status']}")


def emit_error(message: str, as_json: bool) -> None:
    """Emit error output to stderr."""
    if as_json:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def fetch_incubator_payload(
    session_id: str, slot: Optional[int]
) -> Optional[Dict[str, Any]]:
    """Fetch incubator data for a given session if present."""
    conn = get_db_connection(slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM incubator WHERE session_id = %s", (session_id,))
            result = cur.fetchone()
        if result:
            return dict(result)
        return None
    finally:
        conn.close()


async def run_wizard_chat(args: argparse.Namespace) -> Dict[str, Any]:
    """Run a wizard chat step using the existing new story flow."""
    context_data = parse_optional_json(args.context_json) or load_json_file(
        args.context_file
    )
    request = ChatRequest(
        slot=args.slot,
        thread_id=args.thread_id,
        message=args.message,
        model=args.model,
        current_phase=args.phase,
        context_data=context_data,
        accept_fate=args.accept_fate,
    )
    response = await new_story_chat_endpoint(request)
    return response


async def run_wizard_transition(args: argparse.Namespace) -> Dict[str, Any]:
    """Transition wizard state into narrative mode."""
    request = TransitionRequest(slot=args.slot)
    response = await transition_to_narrative_endpoint(request)
    return response.model_dump()


async def run_narrative_generate(args: argparse.Namespace) -> Dict[str, Any]:
    """Generate narrative for a bootstrap or continuation step."""
    session_id = str(uuid.uuid4())
    request = ContinueNarrativeRequest(
        chunk_id=args.chunk_id,
        user_text=args.user_text,
        test_mode=args.test_mode,
        slot=args.slot,
    )
    await generate_narrative_async(
        session_id=session_id,
        parent_chunk_id=request.chunk_id or 0,
        user_text=request.user_text,
        test_mode=request.test_mode,
        slot=request.slot,
    )
    status = await get_narrative_status(session_id, slot=args.slot)
    incubator_data = fetch_incubator_payload(session_id, args.slot)
    response: Dict[str, Any] = {
        "session_id": session_id,
        "status": status.status,
        "chunk_id": status.chunk_id,
        "parent_chunk_id": status.parent_chunk_id,
        "created_at": format_datetime(status.created_at),
        "error": status.error,
    }
    if incubator_data:
        response.update(
            {
                "storyteller_text": incubator_data.get("storyteller_text"),
                "choice_object": incubator_data.get("choice_object"),
            }
        )
    return response


async def run_narrative_status(args: argparse.Namespace) -> Dict[str, Any]:
    """Fetch narrative generation status by session ID."""
    status = await get_narrative_status(args.session_id, slot=args.slot)
    return {
        "session_id": status.session_id,
        "status": status.status,
        "chunk_id": status.chunk_id,
        "parent_chunk_id": status.parent_chunk_id,
        "created_at": format_datetime(status.created_at),
        "error": status.error,
    }


async def run_narrative_approve(args: argparse.Namespace) -> Dict[str, Any]:
    """Approve or commit a narrative session."""
    request = ApproveNarrativeRequest(
        session_id=args.session_id,
        commit=args.commit,
    )
    response = await approve_narrative(
        session_id=args.session_id, request=request, slot=args.slot
    )
    return response


def build_parser(settings: Dict[str, Any], settings_path: str) -> argparse.ArgumentParser:
    """Build CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(description="NEXUS CLI")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--settings",
        default=settings_path,
        help="Path to settings.json (default: settings.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    wizard_parser = subparsers.add_parser("wizard", help="Wizard flow commands")
    wizard_sub = wizard_parser.add_subparsers(dest="wizard_command", required=True)

    wizard_chat = wizard_sub.add_parser("chat", help="Send wizard chat message")
    wizard_chat.add_argument("--slot", type=int, required=True)
    wizard_chat.add_argument("--thread-id", required=True)
    wizard_chat.add_argument("--message", required=True)
    wizard_chat.add_argument(
        "--phase",
        choices=["setting", "character", "seed"],
        required=True,
    )
    wizard_chat.add_argument(
        "--model",
        default=settings.get("API Settings", {})
        .get("new_story", {})
        .get("model", get_new_story_model()),
    )
    wizard_chat.add_argument(
        "--context-json",
        help="Inline JSON for context_data",
    )
    wizard_chat.add_argument(
        "--context-file",
        help="Path to JSON file for context_data",
    )
    wizard_chat.add_argument(
        "--accept-fate",
        action="store_true",
        help="Force tool call to advance wizard artifacts",
    )

    wizard_transition = wizard_sub.add_parser(
        "transition", help="Transition wizard to narrative mode"
    )
    wizard_transition.add_argument("--slot", type=int, required=True)

    narrative_parser = subparsers.add_parser(
        "narrative", help="Narrative generation commands"
    )
    narrative_sub = narrative_parser.add_subparsers(
        dest="narrative_command", required=True
    )

    narrative_generate = narrative_sub.add_parser(
        "generate", help="Generate narrative for a chunk"
    )
    narrative_generate.add_argument("--slot", type=int, required=True)
    narrative_generate.add_argument(
        "--chunk-id",
        type=int,
        default=0,
        help="Parent chunk id (0 for bootstrap)",
    )
    narrative_generate.add_argument("--user-text", required=True)
    narrative_generate.add_argument(
        "--test-mode",
        action="store_true",
        default=settings.get("Agent Settings", {})
        .get("global", {})
        .get("narrative", {})
        .get("use_mock_mode", False),
        help="Use mock narrative generation",
    )

    narrative_status = narrative_sub.add_parser(
        "status", help="Check narrative session status"
    )
    narrative_status.add_argument("--session-id", required=True)
    narrative_status.add_argument("--slot", type=int, required=True)

    narrative_approve = narrative_sub.add_parser(
        "approve", help="Approve or commit narrative session"
    )
    narrative_approve.add_argument("--session-id", required=True)
    narrative_approve.add_argument("--slot", type=int, required=True)
    narrative_approve.add_argument(
        "--commit",
        action="store_true",
        default=True,
        help="Commit the incubator entry",
    )
    narrative_approve.add_argument(
        "--no-commit",
        action="store_false",
        dest="commit",
        help="Mark as reviewed without commit",
    )

    return parser


def main() -> int:
    """Entry point for the NEXUS CLI."""
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--settings", default="settings.json")
    pre_args, _ = pre_parser.parse_known_args()

    settings_path = Path(pre_args.settings)
    settings = load_settings_data(settings_path)
    parser = build_parser(settings, pre_args.settings)
    args = parser.parse_args()

    try:
        if args.command == "wizard" and args.wizard_command == "chat":
            result = asyncio.run(run_wizard_chat(args))
        elif args.command == "wizard" and args.wizard_command == "transition":
            result = asyncio.run(run_wizard_transition(args))
        elif args.command == "narrative" and args.narrative_command == "generate":
            result = asyncio.run(run_narrative_generate(args))
        elif args.command == "narrative" and args.narrative_command == "status":
            result = asyncio.run(run_narrative_status(args))
        elif args.command == "narrative" and args.narrative_command == "approve":
            result = asyncio.run(run_narrative_approve(args))
        else:
            emit_error("Unknown command", args.json)
            return 2
    except (ValueError, KeyError, psycopg2.Error) as exc:
        emit_error(str(exc), args.json)
        return 1
    except Exception as exc:
        emit_error(str(exc), args.json)
        return 1

    emit_output(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
