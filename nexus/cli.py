"""
NEXUS CLI - Simplified command-line interface for story management.

Commands:
    nexus load --slot N         Display current slot state
    nexus continue --slot N     Advance the story (wizard or narrative)
    nexus undo --slot N         Revert the last action
    nexus model --slot N        Get or set the model for a slot

The CLI is slot-centric: only --slot N is required. The backend resolves
all other state (wizard phase, current chunk, thread ID) automatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

import requests

# Default API server URL
DEFAULT_API_URL = "http://localhost:8000"


def get_api_url() -> str:
    """Get the API server URL from environment or default."""
    import os

    return os.environ.get("NEXUS_API_URL", DEFAULT_API_URL)


def emit_output(payload: Dict[str, Any], as_json: bool) -> None:
    """Emit payload to stdout in JSON or human-readable format."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Human-readable output
    if payload.get("error"):
        print(f"Error: {payload['error']}")
        return

    # Display message/storyteller text
    message = payload.get("message") or payload.get("storyteller_text")
    if message:
        print(message)
        print()

    # Display choices if available
    choices = payload.get("choices", [])
    if choices:
        print("Choices:")
        for idx, choice in enumerate(choices, start=1):
            print(f"  {idx}. {choice}")
        print()

    # Display phase if in wizard mode
    phase = payload.get("phase")
    if phase:
        print(f"[Wizard Phase: {phase}]")

    # Display chunk ID if in narrative mode
    chunk_id = payload.get("chunk_id") or payload.get("current_chunk_id")
    if chunk_id:
        print(f"[Chunk: {chunk_id}]")


def emit_error(message: str, as_json: bool) -> None:
    """Emit error output to stderr."""
    if as_json:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def run_load(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Display current slot state.

    Calls GET /api/slot/{slot}/state to get the current state.
    If the slot is empty, offers to initialize it.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/state"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("is_empty"):
            return {
                "message": f"Slot {args.slot} is empty. Use 'nexus continue --slot {args.slot}' to initialize.",
                "is_empty": True,
            }

        if data.get("is_wizard_mode"):
            return {
                "message": f"Slot {args.slot} is in wizard mode.",
                "phase": data.get("phase"),
                "choices": [],
            }

        # Narrative mode
        return {
            "message": data.get("storyteller_text") or "No narrative text available.",
            "choices": data.get("choices", []),
            "chunk_id": data.get("current_chunk_id"),
            "has_pending": data.get("has_pending"),
        }

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


def run_continue(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Advance the story (wizard or narrative).

    Calls POST /api/slot/{slot}/continue with the appropriate parameters.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/continue"

    payload = {
        "accept_fate": args.accept_fate,
    }

    if args.choice is not None:
        payload["choice"] = args.choice
    if args.user_text is not None:
        payload["user_text"] = args.user_text
    if args.model is not None:
        payload["model"] = args.model

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return {"error": data.get("error", "Unknown error")}

        result = {
            "message": data.get("message"),
            "choices": data.get("choices", []),
        }

        if data.get("phase"):
            result["phase"] = data["phase"]
        if data.get("chunk_id"):
            result["chunk_id"] = data["chunk_id"]

        return result

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


def run_undo(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Undo the last action.

    Calls POST /api/slot/{slot}/undo.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/undo"

    try:
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        return {
            "message": data.get("message"),
            "success": data.get("success"),
        }

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


def run_model(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Get or set the model for a slot.

    Calls GET or POST /api/slot/{slot}/model.
    """
    base_url = f"{get_api_url()}/api/slot/{args.slot}/model"

    try:
        if args.list:
            # Just list available models
            response = requests.get(base_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            models = data.get("available_models", [])
            return {
                "message": f"Available models: {', '.join(models)}",
                "available_models": models,
            }

        if args.set:
            # Set the model
            response = requests.post(base_url, json={"model": args.set}, timeout=30)
            response.raise_for_status()
            data = response.json()
            return {
                "message": f"Model changed to {data.get('model')}",
                "model": data.get("model"),
            }

        # Get current model
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        current = data.get("model") or "(default)"
        available = data.get("available_models", [])
        return {
            "message": f"Current model: {current}\nAvailable: {', '.join(available)}",
            "model": data.get("model"),
            "available_models": available,
        }

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="NEXUS CLI - Story management command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus load --slot 5           Show current state of slot 5
  nexus continue --slot 5       Advance the story
  nexus continue --slot 5 --choice 1   Select choice #1
  nexus continue --slot 5 --user-text "I approach carefully"
  nexus continue --slot 5 --accept-fate   Auto-advance
  nexus undo --slot 5           Revert last action
  nexus model --slot 5          Show current model
  nexus model --slot 5 --set TEST   Change to TEST model
  nexus model --list            List available models
""",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # load command
    load_parser = subparsers.add_parser("load", help="Display current slot state")
    load_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")

    # continue command
    continue_parser = subparsers.add_parser("continue", help="Advance the story")
    continue_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")
    continue_parser.add_argument(
        "--choice",
        type=int,
        help="Select structured choice by number (1-indexed)",
    )
    continue_parser.add_argument(
        "--user-text",
        help="Freeform user input",
    )
    continue_parser.add_argument(
        "--accept-fate",
        action="store_true",
        help="Auto-advance (select first choice or trigger auto-generate)",
    )
    continue_parser.add_argument(
        "--model",
        help="Override model for this request (e.g., gpt-5.1, TEST, claude)",
    )

    # undo command
    undo_parser = subparsers.add_parser("undo", help="Revert last action")
    undo_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")

    # model command
    model_parser = subparsers.add_parser("model", help="Get or set model for a slot")
    model_parser.add_argument("--slot", type=int, help="Slot number (1-5)")
    model_parser.add_argument("--set", help="Set the model (e.g., gpt-5.1, TEST, claude)")
    model_parser.add_argument("--list", action="store_true", help="List available models")

    return parser


def main() -> int:
    """Entry point for the NEXUS CLI."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate slot for commands that require it
    if args.command in ("load", "continue", "undo"):
        if args.slot < 1 or args.slot > 5:
            emit_error("Slot must be between 1 and 5", args.json)
            return 1

    if args.command == "model":
        if args.slot is not None and (args.slot < 1 or args.slot > 5):
            emit_error("Slot must be between 1 and 5", args.json)
            return 1
        if not args.list and args.slot is None:
            emit_error("--slot is required unless using --list", args.json)
            return 1

    # Execute command
    if args.command == "load":
        result = run_load(args)
    elif args.command == "continue":
        result = run_continue(args)
    elif args.command == "undo":
        result = run_undo(args)
    elif args.command == "model":
        result = run_model(args)
    else:
        emit_error(f"Unknown command: {args.command}", args.json)
        return 2

    # Check for errors
    if result.get("error"):
        emit_error(result["error"], args.json)
        return 1

    emit_output(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
