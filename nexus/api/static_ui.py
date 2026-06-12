"""Static serving for the built PWA and runtime image uploads.

The FastAPI gateway is the single origin (issue #396): it serves the built
client bundle (``ui/dist/public``, produced by ``npm --prefix ui run
build``) with SPA fallback routing, plus the runtime upload directories
(``/character_portraits``, ``/place_images``) straight from
``ui/client/public`` so files uploaded after the build still resolve.

Cache policy: hashed bundle assets (``assets/``) are immutable; the app
shell (``index.html``), the service worker, and the manifest are always
revalidated so deploys take effect on next load.

Dev mode note: the Vite dev server (``npm --prefix ui run dev``) serves the
client itself and proxies /api, /ws, and the upload routes here — so a
missing ``ui/dist/public`` build is only an error when someone actually
requests the app shell from the gateway, not at startup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

logger = logging.getLogger("nexus.api.static_ui")

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_PUBLIC_DIR = REPO_ROOT / "ui" / "client" / "public"
UI_DIST_DIR = REPO_ROOT / "ui" / "dist" / "public"

# Paths that must never fall back to index.html: a 404 on these is a real
# 404 (a missing API route masquerading as the app shell is a debugging trap).
NO_SPA_FALLBACK_PREFIXES = ("api/", "ws/")

# App-shell files that must always be revalidated (service worker update
# flow depends on sw.js never being served stale).
NO_CACHE_FILES = {
    "index.html",
    "sw.js",
    "registerSW.js",
    "manifest.json",
    "manifest.webmanifest",
}


class SpaStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback and PWA-appropriate cache headers."""

    async def get_response(self, path: str, scope) -> Response:
        served_path = path
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith(NO_SPA_FALLBACK_PREFIXES):
                raise
            # Client-side route (e.g. /reader): serve the app shell.
            served_path = "index.html"
            response = await super().get_response("index.html", scope)
        self._apply_cache_policy(served_path, response)
        return response

    @staticmethod
    def _apply_cache_policy(path: str, response: Response) -> None:
        name = Path(path).name
        if path in ("", ".") or name in NO_CACHE_FILES:
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/"):
            # Vite emits content-hashed filenames under assets/.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"


def mount_ui(app: FastAPI) -> None:
    """Mount upload directories and the built PWA on the gateway app.

    Must be called after every API route is registered: the dist mount at
    ``/`` is a catch-all and Starlette matches routes in registration order.
    """
    # Runtime upload directories (created on demand; uploads also mkdir).
    for route, subdir in (
        ("/character_portraits", "character_portraits"),
        ("/place_images", "place_images"),
    ):
        directory = UI_PUBLIC_DIR / subdir
        directory.mkdir(parents=True, exist_ok=True)
        app.mount(route, StaticFiles(directory=directory), name=subdir)

    if UI_DIST_DIR.is_dir():
        app.mount("/", SpaStaticFiles(directory=UI_DIST_DIR, html=True), name="ui")
        logger.info("Serving built PWA from %s", UI_DIST_DIR)
    else:
        logger.warning(
            "UI build not found at %s - the gateway will serve APIs only. "
            "Run `npm --prefix ui run build` (or use the Vite dev server).",
            UI_DIST_DIR,
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def ui_build_missing(full_path: str) -> PlainTextResponse:
            return PlainTextResponse(
                "NEXUS UI build not found. Run `npm --prefix ui run build`, "
                "or use the Vite dev server (`npm --prefix ui run dev`).",
                status_code=503,
            )
