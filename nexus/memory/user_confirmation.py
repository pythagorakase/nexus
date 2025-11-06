"""User confirmation utilities for fallback scenarios."""

import sys
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

# Global hook registry for UI integration
_confirmation_hooks: Dict[str, Callable] = {}
_input_hooks: Dict[str, Callable] = {}


def register_confirmation_hook(hook_type: str, callback: Callable[[str, Optional[str]], bool]) -> None:
    """Register a custom confirmation handler for UI integration.

    Args:
        hook_type: Type of confirmation (e.g., 'fallback', 'missing_file')
        callback: Function that takes (message, details) and returns bool
    """
    _confirmation_hooks[hook_type] = callback
    logger.info(f"Registered confirmation hook for '{hook_type}'")


def register_input_hook(hook_type: str, callback: Callable[[str, Optional[Callable]], Optional[str]]) -> None:
    """Register a custom input handler for UI integration.

    Args:
        hook_type: Type of input (e.g., 'file_path', 'config_value')
        callback: Function that takes (prompt, validation_func) and returns str or None
    """
    _input_hooks[hook_type] = callback
    logger.info(f"Registered input hook for '{hook_type}'")


def clear_hooks() -> None:
    """Clear all registered hooks (useful for testing)."""
    _confirmation_hooks.clear()
    _input_hooks.clear()


def confirm_fallback(message: str, details: Optional[str] = None, hook_type: str = "fallback") -> bool:
    """Prompt user to confirm fallback operation.

    Args:
        message: Main confirmation message
        details: Optional additional details
        hook_type: Type of confirmation for hook lookup (default: "fallback")

    Returns:
        True if user confirms, False otherwise
    """
    # Check if there's a registered hook for this type
    if hook_type in _confirmation_hooks:
        logger.debug(f"Using registered hook for confirmation type: {hook_type}")
        return _confirmation_hooks[hook_type](message, details)

    # Fall back to console interaction
    print("\n" + "=" * 80, file=sys.stderr)
    print("⚠️  FALLBACK CONFIRMATION REQUIRED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"\n{message}", file=sys.stderr)

    if details:
        print(f"\nDetails: {details}", file=sys.stderr)

    print("\nProceed with fallback? (Y/N): ", end="", file=sys.stderr)
    sys.stderr.flush()

    try:
        response = input().strip().upper()
        confirmed = response in ['Y', 'YES']

        if confirmed:
            logger.info("User confirmed fallback operation")
        else:
            logger.warning("User declined fallback operation")

        return confirmed
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled", file=sys.stderr)
        return False


def request_input(prompt: str, validation_func=None, hook_type: str = "input") -> Optional[str]:
    """Request input from user with optional validation.

    Args:
        prompt: Prompt message to display
        validation_func: Optional function to validate input
        hook_type: Type of input for hook lookup (default: "input")

    Returns:
        User input if valid, None if cancelled
    """
    # Check if there's a registered hook for this type
    if hook_type in _input_hooks:
        logger.debug(f"Using registered hook for input type: {hook_type}")
        return _input_hooks[hook_type](prompt, validation_func)

    # Fall back to console interaction
    print("\n" + "=" * 80, file=sys.stderr)
    print("📝 USER INPUT REQUIRED", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"\n{prompt}", file=sys.stderr)
    print("\nEnter value (or Ctrl+C to cancel): ", end="", file=sys.stderr)
    sys.stderr.flush()

    try:
        user_input = input().strip()

        if validation_func:
            if not validation_func(user_input):
                print("❌ Invalid input", file=sys.stderr)
                return None

        logger.info(f"User provided input: {user_input[:50]}...")
        return user_input
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled", file=sys.stderr)
        return None


def is_interactive() -> bool:
    """Check if running in interactive mode (TTY attached).

    Returns:
        True if interactive, False if running in CI/batch mode
    """
    return sys.stdin.isatty() and sys.stdout.isatty()