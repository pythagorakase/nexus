"""The NEXUS CLI command contract: transports, exit codes, and JSON envelopes.

Transport Rule
--------------
Every command ``nexus.cli.build_parser()`` registers declares, in
:data:`COMMAND_TRANSPORTS`, the most privileged resource its handler opens:

- ``http``: the handler reaches story state only through the NEXUS API at
  ``get_api_url()`` (the remote profile's base URL, ``NEXUS_API_URL``, or the
  local gateway). Reading the active ``nexus.toml`` does not count.
- ``operator_api``: the handler reads operator-plane routes
  (``nexus/api/route_capabilities.py``) of the NEXUS API at ``get_api_url()``.
  The ``http`` commands that already call operator routes (``clear``,
  ``lock``, ``unlock``, ``model --set``/``--clear``) stay ``http`` until issue
  #824 splits the listeners.
- ``database``: the handler connects to a slot database itself
  (``psycopg2``, ``nexus.api.db_pool``, or a reader built on them, such as the
  wizard cache and story-settings readers), whatever else it also does.
- ``local_operator``: the handler opens no slot database but acts on this
  machine: supervised processes and pidfiles, captured logs, the runtime home,
  the usage ledger, model artifacts, local packet and manifest files, or
  provider calls made with this machine's secrets.

A nested command is keyed by its full path (``"models lock"``). A command
whose flags choose the resource it opens lists them in :data:`FLAG_TRANSPORTS`;
a local-operator command whose handler serves the remote profile over HTTP
itself lists that in :data:`REMOTE_PROFILE_TRANSPORTS`. Commands whose
``--config`` selects the runtime configuration are in
:data:`RUNTIME_CONFIG_COMMANDS`, so the remote check reads that file.
``docs/cli_reference.md`` is rendered from ``build_parser()`` and these tables
by ``scripts/render_cli_reference.py``.

Remote Refusal
--------------
The runtime is remote when the active configuration's ``[runtime] profile`` is
``"remote"`` or ``NEXUS_API_URL`` names a host that is not loopback. Under a
remote runtime, ``database``, ``local_operator`` and ``operator_api`` commands
are refused before dispatch with ``transport_refused`` (exit 3), so they never read this
machine's slot databases or runtime files in place of the remote runtime's,
and never reach a remote runtime's operator routes.
``doctor``, ``init`` and ``receipts`` are the self-diagnostic commands
(:data:`SELF_DIAGNOSTIC_COMMANDS`): they evaluate this machine's configuration
and runtime themselves, so they are dispatched without the configuration load
or the remote refusal. An invalid configuration is a ``config.valid`` finding
for ``doctor`` and ``init``, and the client machine of a remote runtime runs
``doctor --target owner-client``; ``receipts`` reads this machine's failure
receipts when no configuration loads.

Exit Codes and Envelopes
------------------------
:class:`ExitCode` is stable: 0 ok, 1 domain failure, 2 usage, 3 transport
refused, 4 API unreachable. Every ``--json`` failure prints
:func:`error_envelope` on stderr, argparse's rejection of the command line
included (``nexus.cli.CliArgumentParser``): ``ok`` false, a stable ``code``
from :data:`ERROR_CODES`, the ``error`` message string earlier releases
printed, and ``partial``, every non-empty field of the failed result. A
refused connection, a timeout, an unusable API URL, and a missing or refused
runtime credential propagate from the HTTP handlers to ``nexus.cli.main()``,
so every HTTP command reports them alike. An API answer the command cannot
use propagates to ``main()`` from the play and slot handlers (``load``,
``continue``, ``retry``, ``accept``, ``undo``, ``regenerate``, ``clear``, ``lock``,
``unlock``, ``model --set``/``--clear``) and the ``inspect`` verbs, which
report it alike: a non-2xx answer is ``api_error`` (``inspect`` reports a 404
as ``not_found``), a 401, 403 or redirect that is not followed is
``config_error`` (the gateway itself answers none of them, so an edge in front
of it such as Cloudflare Access rejected the request), and a 2xx body that is
not a JSON object is ``invalid_response``. ``model`` reports
a slot database it cannot read as ``database_error``. Only a command that
already saved work (a confirmed artifact, a saved seed, a scheduled turn)
reports a later failed request itself, with a ``partial`` that keeps that
work and its recovery command: as ``api_unreachable`` when the gateway
refused or dropped the connection (``nexus.cli.wait_for_session`` never
retries a failed status read), as ``api_error`` for a non-2xx answer, as
``config_error`` for an access rejection, otherwise as a domain failure. JSON-first
commands (:data:`ENVELOPE_COMMANDS`) print :func:`success_envelope` on stdout;
other commands keep their established success payloads. One exception is
kept for existing consumers: a policy gate (``trait-audit
--fail-on-remainders``) prints its full success-shaped report, with
``failed_policy`` true, and exits 1. Expected failures (unreachable API,
refusals, bad arguments, missing or invalid configuration, domain errors) are
reported through the envelope; a traceback means a programming fault.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import IntEnum
import ipaddress
from types import MappingProxyType
from typing import Any, Dict, FrozenSet, Iterator, Literal, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from nexus.config.settings_models import RuntimeSettings

Transport = Literal["http", "operator_api", "local_operator", "database"]

API_URL_ENV = "NEXUS_API_URL"

COMMAND_TRANSPORTS: Mapping[str, Transport] = MappingProxyType(
    {
        # Managed runtime: supervisor processes, pidfiles, captured logs, and
        # the runtime-home plan.
        "up": "local_operator",
        "down": "local_operator",
        "restart": "local_operator",
        "status": "local_operator",
        "logs": "local_operator",
        "home": "local_operator",
        "doctor": "local_operator",
        "init": "local_operator",
        "receipts": "local_operator",
        # Local ledgers and model artifacts.
        "usage": "local_operator",
        "window-replay": "local_operator",
        "models lock": "local_operator",
        "models verify": "local_operator",
        "models plan": "local_operator",
        "models fetch": "local_operator",
        # Play and slot administration over the NEXUS API.
        "load": "http",
        "continue": "http",
        "retry": "http",
        "accept": "http",
        "undo": "http",
        "regenerate": "http",
        "clear": "http",
        "lock": "http",
        "unlock": "http",
        "inspect slot": "http",
        "inspect chunks": "http",
        "inspect chunk": "http",
        "inspect incubator": "http",
        "inspect characters": "http",
        "inspect places": "http",
        "inspect factions": "http",
        # Operator-plane reads; refused while the runtime is remote (815-Q3).
        "inspect settings": "operator_api",
        "inspect secrets": "operator_api",
        # Reading seat identities opens the slot database; see FLAG_TRANSPORTS.
        "model": "database",
        # Direct slot-database readers and writers.
        "jobs": "database",
        "inspect-turn": "database",
        "prune-manifests": "database",
        "trait-audit": "database",
        "retrograde-packet": "database",
        "retrograde-apply-expansion": "database",
        "retrograde-embed-history": "database",
        "record-revelation": "database",
        "faction-audit": "database",
        "faction-manifest": "database",
        "faction-apply": "database",
        "character-manifest": "database",
        "character-apply": "database",
        "place-manifest": "database",
        "place-apply": "database",
        # Read-only; --all also reads NEXUS_template.
        "tags audit": "database",
        # Local packet and manifest files, and provider calls made with this
        # machine's secrets; --slot also opens the slot database.
        "retrograde-seed-candidates": "local_operator",
        "retrograde-expand-seeds": "local_operator",
        "backfill-review-packet": "local_operator",
    }
)

# The first listed flag that is set (not None or False) selects the transport.
FLAG_TRANSPORTS: Mapping[str, Tuple[Tuple[str, Transport], ...]] = MappingProxyType(
    {
        "model": (("list", "local_operator"), ("set", "http"), ("clear", "http")),
        "retrograde-seed-candidates": (("slot", "database"),),
    }
)

# Under the remote profile the supervisor answers these by probing the hosted
# runtime's /runtime/status over HTTP; it spawns and reads nothing locally.
REMOTE_PROFILE_TRANSPORTS: Mapping[str, Transport] = MappingProxyType(
    {"up": "http", "status": "http"}
)

RUNTIME_CONFIG_COMMANDS: FrozenSet[str] = frozenset(
    {
        "up",
        "down",
        "restart",
        "status",
        "logs",
        "models lock",
        "models verify",
        "models plan",
        "models fetch",
    }
)

# Commands whose --json success output is success_envelope(data).
ENVELOPE_COMMANDS: FrozenSet[str] = frozenset(
    {
        "inspect slot",
        "inspect chunks",
        "inspect chunk",
        "inspect incubator",
        "inspect characters",
        "inspect places",
        "inspect factions",
        "inspect settings",
        "inspect secrets",
        "tags audit",
    }
)

# Commands that diagnose this machine's configuration and role themselves:
# main() dispatches them without loading the configuration or applying the
# remote refusal, so a broken nexus.toml never stops them before they run.
SELF_DIAGNOSTIC_COMMANDS: FrozenSet[str] = frozenset({"doctor", "init", "receipts"})

REFUSED_REMOTE_TRANSPORTS: FrozenSet[Transport] = frozenset(
    {"database", "local_operator", "operator_api"}
)

# What each transport opens, in the order the generated reference lists them.
TRANSPORT_OPENS: Mapping[Transport, str] = MappingProxyType(
    {
        "http": "The NEXUS API only",
        "operator_api": "The NEXUS API's operator routes on this machine",
        "database": "A slot database directly",
        "local_operator": (
            "This machine's processes, logs, runtime home, usage ledger, model "
            "artifacts, local files, or provider credentials"
        ),
    }
)


class ExitCode(IntEnum):
    """Stable process exit codes of the NEXUS CLI."""

    OK = 0
    DOMAIN_FAILURE = 1
    USAGE = 2
    TRANSPORT_REFUSED = 3
    UNREACHABLE = 4


ERROR_CODES: Mapping[str, ExitCode] = MappingProxyType(
    {
        "domain_failure": ExitCode.DOMAIN_FAILURE,
        "config_error": ExitCode.DOMAIN_FAILURE,
        "not_found": ExitCode.DOMAIN_FAILURE,
        "api_error": ExitCode.DOMAIN_FAILURE,
        "invalid_response": ExitCode.DOMAIN_FAILURE,
        "database_error": ExitCode.DOMAIN_FAILURE,
        "usage_error": ExitCode.USAGE,
        "transport_refused": ExitCode.TRANSPORT_REFUSED,
        "api_unreachable": ExitCode.UNREACHABLE,
    }
)

# Result keys that describe the failure itself rather than preserved work.
_STATUS_KEYS = frozenset({"success", "error", "code"})


def exit_code_for(code: str) -> ExitCode:
    """Map a stable error code to its exit code; unknown codes are faults."""
    try:
        return ERROR_CODES[code]
    except KeyError:
        raise ValueError(f"Unregistered CLI error code: {code!r}") from None


def _is_empty(value: Any) -> bool:
    """Whether a result field holds nothing worth preserving."""
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, dict, set, frozenset)):
        return len(value) == 0
    return False


def partial_fields(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Every non-empty field of a failed result other than its status keys."""
    return {
        key: value
        for key, value in result.items()
        if key not in _STATUS_KEYS and not _is_empty(value)
    }


def error_envelope(
    code: str, message: str, partial: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build the one ``--json`` failure envelope printed on stderr.

    ``error`` stays the message string earlier releases printed, so callers
    that read it keep working; ``code`` is the stable machine-readable class.
    """
    exit_code_for(code)
    return {"ok": False, "code": code, "error": message, "partial": dict(partial)}


def success_envelope(data: Any) -> Dict[str, Any]:
    """Build the ``--json`` success envelope of a JSON-first command."""
    return {"ok": True, "data": data}


def _subparsers(parser: argparse.ArgumentParser) -> Optional[argparse.Action]:
    """The parser's subcommand action, if it has one."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def iter_command_parsers(
    parser: argparse.ArgumentParser,
) -> Iterator[Tuple[str, argparse.ArgumentParser, Optional[str]]]:
    """Yield every registered subparser as (full path, parser, one-line help).

    The walk is depth-first in registration order, so a group precedes its
    verbs. The help is the ``help`` of the parent's choice action for that
    name (argparse keeps it there, not on the child parser), or None.
    """

    def walk(
        node: argparse.ArgumentParser, prefix: Tuple[str, ...]
    ) -> Iterator[Tuple[str, argparse.ArgumentParser, Optional[str]]]:
        action = _subparsers(node)
        if action is None:
            return
        assert isinstance(action, argparse._SubParsersAction)
        assert isinstance(action.choices, dict)
        helps = {choice.dest: choice.help for choice in action._choices_actions}
        for name, child in action.choices.items():
            path = (*prefix, name)
            yield " ".join(path), child, helps.get(name)
            yield from walk(child, path)

    if _subparsers(parser) is None:
        raise ValueError("The CLI parser registers no subcommands")
    yield from walk(parser, ())


def iter_command_paths(parser: argparse.ArgumentParser) -> Iterator[str]:
    """Yield the full path of every leaf command the parser registers."""
    for path, child, _help in iter_command_parsers(parser):
        if _subparsers(child) is None:
            yield path


def command_path(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    """Return the full path of the command ``args`` selected (``models lock``)."""
    parts = []
    node = parser
    while (action := _subparsers(node)) is not None:
        name = getattr(args, action.dest)
        parts.append(name)
        assert isinstance(action.choices, dict)
        node = action.choices[name]
    return " ".join(parts)


@dataclass(frozen=True)
class RemoteRuntime:
    """Why the CLI's effective runtime is remote.

    Attributes:
        reason: Human-readable cause, naming the profile or the API host.
        profile: True when the active config's ``[runtime] profile`` is
            ``remote`` (the supervisor then serves up and status over HTTP).
    """

    reason: str
    profile: bool


def is_loopback_url(url: str) -> bool:
    """Whether an API URL names this machine (localhost or a loopback IP)."""
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"{API_URL_ENV} has no host: {url!r}")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def detect_remote_runtime(
    runtime: Optional[RuntimeSettings], api_url_override: Optional[str]
) -> Optional[RemoteRuntime]:
    """Return why the runtime is remote, or None when it is this machine."""
    if runtime is not None and runtime.profile == "remote":
        if runtime.remote is None:  # guarded by RuntimeSettings validation
            raise ValueError("Remote runtime profile has no remote configuration")
        return RemoteRuntime(
            reason=f"[runtime] profile is 'remote' at {runtime.remote.base_url}",
            profile=True,
        )
    if api_url_override and not is_loopback_url(api_url_override):
        return RemoteRuntime(
            reason=f"{API_URL_ENV} targets {api_url_override}", profile=False
        )
    return None


def resolve_transport(
    command: str, args: argparse.Namespace, remote: Optional[RemoteRuntime]
) -> Transport:
    """The transport one invocation of ``command`` uses under ``remote``."""
    if remote is not None and remote.profile:
        profile_transport = REMOTE_PROFILE_TRANSPORTS.get(command)
        if profile_transport is not None:
            return profile_transport
    for flag, transport in FLAG_TRANSPORTS.get(command, ()):
        if getattr(args, flag, None) not in (None, False):
            return transport
    return COMMAND_TRANSPORTS[command]


def transport_refusal(
    command: str, args: argparse.Namespace, remote: Optional[RemoteRuntime]
) -> Optional[str]:
    """Return why ``command`` is refused under ``remote``, or None to run it."""
    if remote is None:
        return None
    transport = resolve_transport(command, args, remote)
    if transport not in REFUSED_REMOTE_TRANSPORTS:
        return None
    return (
        f"'nexus {command}' uses the {transport} transport, which is refused "
        f"while the runtime is remote ({remote.reason}); run it on the "
        "runtime host."
    )
