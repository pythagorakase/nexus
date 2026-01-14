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
import logging
import sys
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("nexus.cli")

# Default API server URL (narrative API handles wizard + story endpoints)
DEFAULT_API_URL = "http://localhost:8002"


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
                "success": True,
                "message": f"Slot {args.slot} is empty. Use 'nexus continue --slot {args.slot}' to initialize.",
                "is_empty": True,
            }

        if data.get("is_wizard_mode"):
            return {
                "success": True,
                "message": f"Slot {args.slot} is in wizard mode.",
                "phase": data.get("phase"),
                "choices": [],
            }

        # Narrative mode
        return {
            "success": True,
            "message": data.get("storyteller_text") or "No narrative text available.",
            "choices": data.get("choices", []),
            "chunk_id": data.get("current_chunk_id"),
            "has_pending": data.get("has_pending"),
        }

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_continue(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Advance the story (wizard or narrative).

    Determines mode from slot state and calls the appropriate unified endpoint:
    - Wizard mode: /api/story/new/chat
    - Narrative mode: /api/narrative/continue
    """
    try:
        # First, get slot state to determine mode
        state_url = f"{get_api_url()}/api/slot/{args.slot}/state"
        state_response = requests.get(state_url, timeout=30)
        state_response.raise_for_status()
        state = state_response.json()

        if state.get("is_empty"):
            # Initialize via setup/start endpoint, then call wizard chat
            # Pass model from slot state (e.g., TEST mode)
            setup_url = f"{get_api_url()}/api/story/new/setup/start"
            setup_payload = {"slot": args.slot}
            if state.get("model"):
                setup_payload["model"] = state["model"]
            setup_response = requests.post(
                setup_url,
                json=setup_payload,
                timeout=30
            )
            if not setup_response.ok:
                return {"success": False, "error": f"Failed to initialize wizard: {setup_response.text}"}

            return {
                "success": True,
                "message": f"Wizard initialized for slot {args.slot}. Ready to begin story creation.",
                "phase": "setting",
            }

        if state.get("is_wizard_mode"):
            # Check if wizard is ready for transition to narrative
            if state.get("phase") == "ready":
                # Call transition endpoint, then bootstrap
                transition_url = f"{get_api_url()}/api/story/new/transition"
                transition_response = requests.post(
                    transition_url,
                    json={"slot": args.slot},
                    timeout=60
                )
                if not transition_response.ok:
                    return {"success": False, "error": f"Transition failed: {transition_response.text}"}

                # Transition complete - refresh state and continue to narrative
                state_response = requests.get(state_url, timeout=30)
                state = state_response.json()

                if state.get("is_wizard_mode"):
                    return {"success": False, "error": "Transition completed but still in wizard mode"}

                # Continue to narrative mode handling below (don't return here)
            else:
                # Call wizard chat directly
                url = f"{get_api_url()}/api/story/new/chat"
                # Use CLI override or slot's configured model (e.g., TEST mode)
                model_to_use = args.model or state.get("model")
                payload = {
                    "slot": args.slot,
                    "message": args.user_text or "",
                    "accept_fate": args.accept_fate,
                    # thread_id and current_phase resolved by backend
                }
                if model_to_use:
                    payload["model"] = model_to_use

                response = requests.post(url, json=payload, timeout=120)
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "message": data.get("message"),
                    "choices": data.get("choices", []),
                    "phase": data.get("phase"),
                }

        # Narrative mode - call continue directly
        # (Also reached after wizard transition above)
        if not state.get("is_wizard_mode"):
            # Narrative mode - call continue directly
            # Resolve choice to user_text if provided
            user_text = args.user_text or ""
            if args.choice is not None and state.get("choices"):
                choices = state.get("choices", [])
                if 1 <= args.choice <= len(choices):
                    user_text = choices[args.choice - 1]
                else:
                    return {"success": False, "error": f"Choice {args.choice} out of range (1-{len(choices)})"}

            # Approve pending content if exists
            if state.get("has_pending"):
                approve_url = f"{get_api_url()}/api/narrative/approve"
                approve_response = requests.post(
                    approve_url,
                    json={"slot": args.slot, "commit": True},
                    timeout=30
                )
                if not approve_response.ok:
                    logger.warning("Auto-approve failed: %s", approve_response.text)

            url = f"{get_api_url()}/api/narrative/continue"
            payload = {
                "slot": args.slot,
                "user_text": user_text,
                # chunk_id resolved by backend
            }

            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            # Wait for generation to complete and fetch result
            session_id = data.get("session_id")
            if session_id:
                # Poll for completion (simplified - real implementation would use websocket)
                for _ in range(60):  # Max 60 seconds
                    status_url = f"{get_api_url()}/api/narrative/status/{session_id}"
                    status_response = requests.get(status_url, params={"slot": args.slot}, timeout=30)
                    if status_response.ok:
                        status = status_response.json()
                        if status.get("status") == "completed":
                            # Fetch incubator for result
                            load_result = run_load(args)
                            return {
                                "success": True,
                                "message": load_result.get("message"),
                                "choices": load_result.get("choices", []),
                                "chunk_id": status.get("chunk_id"),
                            }
                        elif status.get("status") == "error":
                            return {"success": False, "error": status.get("error", "Generation failed")}
                    time.sleep(1)
                return {"success": False, "error": "Generation timed out"}

            return {
                "success": True,
                "message": data.get("message"),
                "session_id": session_id,
            }

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
            "success": data.get("success", True),
            "message": data.get("message"),
        }

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_model(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Get or set the model for a slot.

    Calls GET or POST /api/slot/{slot}/model.
    """
    try:
        if args.list:
            # List available models from config (no slot required)
            try:
                from nexus.config.loader import load_settings_as_dict

                settings = load_settings_as_dict()
                models = settings.get("global", {}).get("model", {}).get(
                    "available_models", ["gpt-5.1", "TEST", "claude"]
                )
            except Exception:
                # Fallback to hardcoded defaults if config unavailable
                models = ["gpt-5.1", "TEST", "claude"]
            return {
                "success": True,
                "message": f"Available models: {', '.join(models)}",
                "available_models": models,
            }

        # Slot is required for get/set operations
        base_url = f"{get_api_url()}/api/slot/{args.slot}/model"

        if args.set:
            # Set the model
            response = requests.post(base_url, json={"model": args.set}, timeout=30)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
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
            "success": True,
            "message": f"Current model: {current}\nAvailable: {', '.join(available)}",
            "model": data.get("model"),
            "available_models": available,
        }

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_clear(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Clear a slot (reset wizard state).

    Calls POST /api/story/new/setup/reset.
    """
    try:
        url = f"{get_api_url()}/api/story/new/setup/reset"
        response = requests.post(url, json={"slot": args.slot}, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} cleared",
        }
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_lock(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Lock a slot to prevent modifications.

    Calls POST /api/slot/{slot}/lock.
    """
    try:
        url = f"{get_api_url()}/api/slot/{args.slot}/lock"
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} locked",
        }
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_unlock(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Unlock a slot to allow modifications.

    Calls POST /api/slot/{slot}/unlock.
    """
    try:
        url = f"{get_api_url()}/api/slot/{args.slot}/unlock"
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} unlocked",
        }
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Cannot connect to API server at {get_api_url()}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
  nexus clear --slot 5          Clear slot (reset wizard state)
  nexus lock --slot 1           Lock slot to prevent modifications
  nexus unlock --slot 2         Unlock slot to allow modifications
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

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear a slot (reset wizard state)")
    clear_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")

    # lock command
    lock_parser = subparsers.add_parser("lock", help="Lock a slot to prevent modifications")
    lock_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")

    # unlock command
    unlock_parser = subparsers.add_parser("unlock", help="Unlock a slot to allow modifications")
    unlock_parser.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")

    return parser


def main() -> int:
    """Entry point for the NEXUS CLI."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate slot for commands that require it
    if args.command in ("load", "continue", "undo", "clear", "lock", "unlock"):
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
    elif args.command == "clear":
        result = run_clear(args)
    elif args.command == "lock":
        result = run_lock(args)
    elif args.command == "unlock":
        result = run_unlock(args)
    else:
        emit_error(f"Unknown command: {args.command}", args.json)
        return 2

    # Check for errors (consistent format: success=False with error message)
    if not result.get("success", True) or result.get("error"):
        emit_error(result.get("error", "Unknown error"), args.json)
        return 1

    emit_output(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
