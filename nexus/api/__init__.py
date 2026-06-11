"""API package exports.

Importing ``nexus.api`` (or any helper/schema submodule) must stay free of
runtime side effects: no FastAPI app construction, no database pools, and no
schema checks. The Storyteller app is exposed lazily via PEP 562 so that
``nexus.api.app`` still resolves for callers that ask for it explicitly.
See issue #369.
"""

from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from .storyteller import app

        return app
    raise AttributeError(f"module 'nexus.api' has no attribute {name!r}")
