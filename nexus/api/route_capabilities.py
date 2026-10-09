"""Authoritative player/operator route-capability registry (issue #824).

Every HTTP route, websocket, and static mount the gateway registers is
classified in :data:`ROUTE_CAPABILITIES`, keyed the way Starlette dispatches
it: ``(method, path template)`` for HTTP routes, ``("WS", path)`` for
websockets, and ``("MOUNT", path)`` for mounts. Handlers are not decorated;
this table is the single source of truth, and an unclassified route fails
the gateway import (:func:`require_classified`).

Two planes project from the one shared app:

- **player** — what the remote tunnel may reach: reading and play
  (narrative turns, undo, the new-story wizard, preferences, static images,
  and the app shell). The wizard can overwrite an unlocked occupied slot,
  so its start and transition routes are marked destructive.
- **operator** — the whole runtime, player routes included, for loopback:
  secrets, settings, local models, diagnostics, slot administration, resets,
  and asset management.

:func:`build_player_app` and :func:`build_operator_app` construct those
projections over the same route objects, lifespan, middleware, and exception
handlers. Binding each projection to its own listener is a later slice.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Any,
    AsyncIterator,
    Callable,
    FrozenSet,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
)

from fastapi import FastAPI
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute

Plane = Literal["player", "operator"]
SlotMode = Literal["none", "read", "write"]
RouteKey = Tuple[str, str]


@dataclass(frozen=True)
class RouteCapability:
    """What one gateway route may do, and which plane serves it.

    Attributes:
        plane: ``player`` routes are served by both projections; ``operator``
            routes only by the operator projection.
        capability: Dotted capability group (``narrative.play``,
            ``secrets``, ...), shared by routes that stand or fall together.
        slot_mode: Whether the route touches a save slot's database:
            ``none``, ``read``, or ``write``.
        provider_effect: True when the request can start model-provider
            work: a remote model call (inference, provider-hosted wizard
            transcripts, credential verification), directly, in a background
            task, or by waking the deferred-work loop; or the local inference
            server's lifecycle.
        destructive: True when the route can irreversibly wipe a story, an
            in-progress wizard, uploaded images, a stored credential, or a
            downloaded model. Discarding a pending turn or the latest wizard
            draft is bounded play, not destruction.
    """

    plane: Plane
    capability: str
    slot_mode: SlotMode
    provider_effect: bool
    destructive: bool


class RouteCapabilityError(RuntimeError):
    """A route's classification cannot be projected onto one plane."""


class UnclassifiedRouteError(RouteCapabilityError):
    """One or more registered routes have no registry entry."""

    def __init__(self, keys: List[RouteKey]) -> None:
        self.keys = keys
        listed = ", ".join(f"{method} {path}" for method, path in keys)
        super().__init__(
            "Unclassified gateway routes: "
            f"{listed}. Add each to ROUTE_CAPABILITIES in "
            "nexus/api/route_capabilities.py before registering it."
        )


def _player(
    capability: str,
    slot_mode: SlotMode = "none",
    *,
    provider_effect: bool = False,
    destructive: bool = False,
) -> RouteCapability:
    return RouteCapability(
        "player", capability, slot_mode, provider_effect, destructive
    )


def _operator(
    capability: str,
    slot_mode: SlotMode = "none",
    *,
    provider_effect: bool = False,
    destructive: bool = False,
) -> RouteCapability:
    return RouteCapability(
        "operator", capability, slot_mode, provider_effect, destructive
    )


_HEALTH = _player("health")
_NARRATIVE_READ = _player("narrative.read", "read")
_NARRATIVE_TURN = _player("narrative.play", "write", provider_effect=True)
_NARRATIVE_EDIT = _player("narrative.play", "write")
_WIZARD_TURN = _player("wizard.play", "write", provider_effect=True)
_WIZARD_EDIT = _player("wizard.play", "write")
_WIZARD_OVERWRITE = _player(
    "wizard.play", "write", provider_effect=True, destructive=True
)
_ASSETS_READ = _player("assets.read", "read")
_ASSETS_FILES = _player("assets.read")
_UI_SHELL = _player("ui.shell")
_API_DOCS = _operator("diagnostics.api_docs")
_ORRERY_DEV_READ = _operator("diagnostics.orrery", "read")
_LOCAL_MODELS = _operator("local_models")
_LOCAL_MODELS_RUNTIME = _operator("local_models", provider_effect=True)
_ASSETS_WRITE = _operator("assets.manage", "write")
_ASSETS_DELETE = _operator("assets.manage", "write", destructive=True)

ROUTE_CAPABILITIES: Mapping[RouteKey, RouteCapability] = MappingProxyType(
    {
        # FastAPI's generated schema and docs describe the serving app's
        # routes; projections regenerate them rather than share them.
        ("GET", "/openapi.json"): _API_DOCS,
        ("HEAD", "/openapi.json"): _API_DOCS,
        ("GET", "/docs"): _API_DOCS,
        ("HEAD", "/docs"): _API_DOCS,
        ("GET", "/docs/oauth2-redirect"): _API_DOCS,
        ("HEAD", "/docs/oauth2-redirect"): _API_DOCS,
        ("GET", "/redoc"): _API_DOCS,
        ("HEAD", "/redoc"): _API_DOCS,
        # settings_endpoints: raw nexus.toml and registry metadata.
        ("HEAD", "/api/settings"): _operator("settings.read"),
        ("GET", "/api/settings"): _operator("settings.read"),
        # preferences_endpoints: theme, fonts, next-story model.
        ("GET", "/api/preferences"): _player("preferences"),
        ("PATCH", "/api/preferences"): _player("preferences"),
        # secrets_endpoints
        ("GET", "/api/secrets/status"): _operator("secrets"),
        ("PUT", "/api/secrets/{provider}"): _operator("secrets", destructive=True),
        ("POST", "/api/secrets/{provider}/verify"): _operator(
            "secrets", provider_effect=True
        ),
        # slot_endpoints
        ("GET", "/api/slot/{slot}/state"): _player(
            "slot.read", "read", provider_effect=True
        ),
        ("POST", "/api/slot/{slot}/undo"): _NARRATIVE_EDIT,
        ("GET", "/api/slot/{slot}/settings"): _player("slot.read", "read"),
        ("PATCH", "/api/slot/{slot}/settings"): _operator("slot.pins", "write"),
        ("POST", "/api/slot/{slot}/lock"): _operator("slot.lock", "write"),
        ("POST", "/api/slot/{slot}/unlock"): _operator("slot.lock", "write"),
        # setup_endpoints. The wizard admits any unlocked slot, occupied or
        # not; the slot lock is the only guard. Starting it discards the
        # slot's in-progress wizard and trait selections and persists the
        # resolved wizard model as the slot's Skald pin, so a request's model
        # override replaces an operator-set pin.
        ("POST", "/api/story/new/setup/start"): _WIZARD_OVERWRITE,
        ("GET", "/api/story/new/setup/resume"): _player(
            "wizard.read", "read", provider_effect=True
        ),
        ("POST", "/api/story/new/setup/confirm"): _WIZARD_EDIT,
        ("POST", "/api/story/new/setup/character/revise"): _WIZARD_EDIT,
        ("POST", "/api/story/new/setup/record"): _WIZARD_EDIT,
        ("POST", "/api/story/new/setup/reset"): _operator(
            "slot.reset", "write", destructive=True
        ),
        # A nonmutating compatibility activation with no live player client.
        ("POST", "/api/story/new/slot/select"): _operator("slot.select"),
        ("GET", "/api/story/new/slots"): _player("slot.read", "read"),
        # wizard_chat
        ("POST", "/api/story/new/chat"): _WIZARD_TURN,
        # Records the genesis strangeness selection on the wizard cache.
        ("PUT", "/api/story/new/weird"): _WIZARD_EDIT,
        # Deletes the slot's existing world and restarts its id sequences.
        ("POST", "/api/story/new/transition"): _WIZARD_OVERWRITE,
        ("GET", "/api/story/new/retrograde/status"): _player("wizard.read"),
        # reader_endpoints
        ("GET", "/status"): _HEALTH,
        ("GET", "/api/narrative/seasons"): _NARRATIVE_READ,
        ("GET", "/api/narrative/episodes/{season_id}"): _NARRATIVE_READ,
        ("GET", "/api/narrative/latest-chunk"): _NARRATIVE_READ,
        ("GET", "/api/narrative/feed"): _NARRATIVE_READ,
        ("GET", "/api/narrative/chunks"): _NARRATIVE_READ,
        ("GET", "/api/narrative/outline"): _NARRATIVE_READ,
        ("GET", "/api/narrative/recap"): _NARRATIVE_READ,
        ("GET", "/api/narrative/chunks/{chunk_id}/adjacent"): _NARRATIVE_READ,
        ("GET", "/api/narrative/chunks/{chunk_id}/context"): _NARRATIVE_READ,
        ("GET", "/api/narrative/chunks/{season_id}/{episode_id}"): _NARRATIVE_READ,
        ("GET", "/api/narrative/chunks/{chunk_id}"): _NARRATIVE_READ,
        ("GET", "/api/characters"): _NARRATIVE_READ,
        ("GET", "/api/characters/{character_id}/relationships"): _NARRATIVE_READ,
        ("GET", "/api/places"): _NARRATIVE_READ,
        ("GET", "/api/current-place"): _NARRATIVE_READ,
        ("GET", "/api/zones"): _NARRATIVE_READ,
        ("GET", "/api/factions"): _NARRATIVE_READ,
        # asset_endpoints
        ("GET", "/api/characters/{character_id}/images"): _ASSETS_READ,
        ("POST", "/api/characters/{character_id}/images"): _ASSETS_WRITE,
        ("PUT", "/api/characters/{character_id}/images/{image_id}/main"): (
            _ASSETS_WRITE
        ),
        ("DELETE", "/api/characters/{character_id}/images/{image_id}"): (
            _ASSETS_DELETE
        ),
        ("GET", "/api/places/{place_id}/images"): _ASSETS_READ,
        ("POST", "/api/places/{place_id}/images"): _ASSETS_WRITE,
        ("PUT", "/api/places/{place_id}/images/{image_id}/main"): _ASSETS_WRITE,
        ("DELETE", "/api/places/{place_id}/images/{image_id}"): _ASSETS_DELETE,
        # local_models_endpoints
        ("GET", "/api/local-models/status"): _LOCAL_MODELS,
        ("POST", "/api/local-models/activate"): _LOCAL_MODELS_RUNTIME,
        ("POST", "/api/local-models/deactivate"): _LOCAL_MODELS_RUNTIME,
        ("POST", "/api/local-models/download"): _LOCAL_MODELS,
        ("GET", "/api/local-models/download"): _LOCAL_MODELS,
        ("POST", "/api/local-models/download/cancel"): _LOCAL_MODELS,
        ("POST", "/api/local-models/delete"): _operator(
            "local_models", destructive=True
        ),
        ("GET", "/api/local-models/browse"): _LOCAL_MODELS,
        ("POST", "/api/local-models/register"): _LOCAL_MODELS,
        # orrery_dev_endpoints and backstage_endpoints ([orrery.dashboard]).
        ("GET", "/api/dev/orrery/catalog"): _operator("diagnostics.orrery"),
        ("POST", "/api/dev/orrery/resolve"): _ORRERY_DEV_READ,
        ("POST", "/api/dev/orrery/context/entities"): _ORRERY_DEV_READ,
        ("POST", "/api/dev/orrery/cognition/trace"): _ORRERY_DEV_READ,
        ("POST", "/api/dev/orrery/coverage"): _ORRERY_DEV_READ,
        ("GET", "/api/dev/orrery/history/adjudications"): _ORRERY_DEV_READ,
        ("GET", "/api/dev/orrery/vocab"): _ORRERY_DEV_READ,
        ("GET", "/api/dev/backstage/health"): _operator("diagnostics.backstage"),
        ("GET", "/api/dev/backstage/{slot}/turn"): _operator(
            "diagnostics.backstage", "read"
        ),
        # narrative.py
        ("GET", "/health"): _HEALTH,
        ("GET", "/api/config/models"): _player("models.catalog"),
        ("POST", "/api/narrative/continue"): _NARRATIVE_TURN,
        ("POST", "/api/narrative/retry"): _NARRATIVE_TURN,
        ("GET", "/api/narrative/active"): _NARRATIVE_READ,
        ("GET", "/api/narrative/status/{session_id}"): _NARRATIVE_READ,
        ("POST", "/api/narrative/regenerate"): _NARRATIVE_TURN,
        # Committing wakes the deferred-work loop (summaries, embeddings).
        ("POST", "/api/narrative/approve"): _NARRATIVE_TURN,
        ("POST", "/api/narrative/approve/{session_id}"): _NARRATIVE_TURN,
        ("POST", "/api/narrative/select-choice"): _NARRATIVE_EDIT,
        ("WS", "/ws/narrative"): _player("narrative.progress"),
        ("GET", "/api/narrative/incubator"): _NARRATIVE_READ,
        ("DELETE", "/api/narrative/incubator"): _NARRATIVE_EDIT,
        ("GET", "/api/user-character"): _NARRATIVE_READ,
        # runtime_status
        ("GET", "/runtime/status"): _operator("diagnostics.runtime", "read"),
        # static_ui: upload directories, then the SPA (one of the two).
        ("MOUNT", "/character_portraits"): _ASSETS_FILES,
        ("MOUNT", "/place_images"): _ASSETS_FILES,
        ("MOUNT", "/"): _UI_SHELL,
        ("GET", "/{full_path:path}"): _UI_SHELL,
    }
)

_PROJECTION_PLANES: Mapping[Plane, FrozenSet[Plane]] = MappingProxyType(
    {
        "player": frozenset({"player"}),
        "operator": frozenset({"player", "operator"}),
    }
)

# Set on the source app's state while a projection runs its lifespan.
_ACTIVE_PROJECTION_ATTR = "route_projection_lifespan"


def route_keys(route: BaseRoute) -> Tuple[RouteKey, ...]:
    """Return the registry keys Starlette dispatches ``route`` under.

    An HTTP route yields one key per method; a route that accepts any
    method yields ``("*", path)``. Route types the registry does not know
    yield a key naming their class, which no entry matches.
    """
    if isinstance(route, WebSocketRoute):
        return (("WS", route.path),)
    if isinstance(route, Mount):
        return (("MOUNT", route.path or "/"),)
    if isinstance(route, Route):
        if route.methods is None:
            return (("*", route.path),)
        return tuple((method, route.path) for method in sorted(route.methods))
    return ((type(route).__name__.upper(), str(getattr(route, "path", route))),)


def classify_app(app: FastAPI) -> List[RouteKey]:
    """Return the keys of every route on ``app`` that the registry lacks."""
    return [
        key
        for route in app.routes
        for key in route_keys(route)
        if key not in ROUTE_CAPABILITIES
    ]


def route_plane(route: BaseRoute) -> Plane:
    """Return the one plane that serves ``route``.

    Raises:
        UnclassifiedRouteError: A key of the route has no registry entry.
        RouteCapabilityError: The route's methods span both planes, so no
            projection could serve it whole.
    """
    keys = route_keys(route)
    missing = [key for key in keys if key not in ROUTE_CAPABILITIES]
    if missing:
        raise UnclassifiedRouteError(missing)
    planes = {ROUTE_CAPABILITIES[key].plane for key in keys}
    if len(planes) != 1:
        listed = ", ".join(f"{method} {path}" for method, path in keys)
        raise RouteCapabilityError(f"Route {listed} spans planes {sorted(planes)}")
    return planes.pop()


def require_classified(app: FastAPI) -> None:
    """Fail loudly unless every route on ``app`` projects onto one plane."""
    unclassified = classify_app(app)
    if unclassified:
        raise UnclassifiedRouteError(unclassified)
    for route in app.routes:
        route_plane(route)
    _require_ui_shell_last(app)


def _require_ui_shell_last(app: FastAPI) -> None:
    """Reject routes registered after the SPA catch-all; none can match."""
    shell_seen = False
    for route in app.routes:
        is_shell = all(
            ROUTE_CAPABILITIES[key].capability == "ui.shell"
            for key in route_keys(route)
        )
        if shell_seen and not is_shell:
            listed = ", ".join(f"{m} {p}" for m, p in route_keys(route))
            raise RouteCapabilityError(
                f"Route {listed} is registered after the app-shell catch-all"
            )
        shell_seen = shell_seen or is_shell


def _framework_paths(app: FastAPI) -> FrozenSet[str]:
    """Paths of the schema and docs routes FastAPI generated for ``app``."""
    if not app.openapi_url:
        return frozenset()
    paths = {app.openapi_url}
    if app.docs_url:
        paths.add(app.docs_url)
        if app.swagger_ui_oauth2_redirect_url:
            paths.add(app.swagger_ui_oauth2_redirect_url)
    if app.redoc_url:
        paths.add(app.redoc_url)
    return frozenset(paths)


def _is_framework_route(route: BaseRoute, framework_paths: FrozenSet[str]) -> bool:
    # FastAPI adds these as plain Starlette routes whose handlers close over
    # the source app, so a copy would serve the source's full schema.
    return type(route) is Route and route.path in framework_paths


def _shared_lifespan(source_app: FastAPI, plane: Plane) -> Callable[[FastAPI], Any]:
    """Run the source app's lifespan against the source app itself.

    Shared handlers read ``source_app.state`` (the slot scheduler), so the
    lifespan must populate that state, not the projection's. Two
    projections entering the same lifespan at once would start two
    schedulers for one slot, so the second fails loudly.
    """

    @asynccontextmanager
    async def lifespan(_projection: FastAPI) -> AsyncIterator[Optional[Any]]:
        active = getattr(source_app.state, _ACTIVE_PROJECTION_ATTR, None)
        if active is not None:
            raise RouteCapabilityError(
                f"The {active} projection is already running this app's "
                f"lifespan; the {plane} projection cannot run it again"
            )
        setattr(source_app.state, _ACTIVE_PROJECTION_ATTR, plane)
        try:
            async with source_app.router.lifespan_context(source_app) as state:
                yield state
        finally:
            setattr(source_app.state, _ACTIVE_PROJECTION_ATTR, None)

    return lifespan


def _build_projection(source_app: FastAPI, plane: Plane) -> FastAPI:
    """Construct the ``plane`` projection of ``source_app``."""
    require_classified(source_app)
    admitted = _PROJECTION_PLANES[plane]
    framework_paths = _framework_paths(source_app)
    framework_planes = {
        route_plane(route)
        for route in source_app.routes
        if _is_framework_route(route, framework_paths)
    }
    if len(framework_planes) > 1:
        raise RouteCapabilityError(
            "FastAPI schema and docs routes must share one plane, "
            f"got {sorted(framework_planes)}"
        )
    serve_docs = bool(framework_planes) and framework_planes <= admitted
    projection = FastAPI(
        debug=source_app.debug,
        title=source_app.title,
        description=source_app.description,
        version=source_app.version,
        openapi_tags=source_app.openapi_tags,
        root_path=source_app.root_path,
        lifespan=_shared_lifespan(source_app, plane),
        exception_handlers=dict(source_app.exception_handlers),
        middleware=list(source_app.user_middleware),
        openapi_url=source_app.openapi_url if serve_docs else None,
        docs_url=source_app.docs_url if serve_docs else None,
        redoc_url=source_app.redoc_url if serve_docs else None,
        swagger_ui_oauth2_redirect_url=(
            source_app.swagger_ui_oauth2_redirect_url if serve_docs else None
        ),
    )
    for route in source_app.routes:
        if _is_framework_route(route, framework_paths):
            continue
        if route_plane(route) in admitted:
            projection.router.routes.append(route)
    return projection


def build_player_app(source_app: FastAPI) -> FastAPI:
    """Project the player plane of ``source_app`` into a new app.

    The projection shares ``source_app``'s route objects (in registration
    order, the SPA catch-all last), lifespan, middleware, and exception
    handlers, and serves only player-plane routes.

    Raises:
        UnclassifiedRouteError: A source route has no registry entry.
        RouteCapabilityError: A source route cannot be projected.
    """
    return _build_projection(source_app, "player")


def build_operator_app(source_app: FastAPI) -> FastAPI:
    """Project the operator plane of ``source_app`` into a new app.

    The operator plane is the whole runtime: player routes plus operator
    routes, so a loopback shell plays and administers through one origin.
    It shares ``source_app``'s route objects, lifespan, middleware, and
    exception handlers.

    Raises:
        UnclassifiedRouteError: A source route has no registry entry.
        RouteCapabilityError: A source route cannot be projected.
    """
    return _build_projection(source_app, "operator")
