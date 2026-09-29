"""The readiness contract (issue #803): one registry, one schema, three roles.

Checks run against real temporary configs copied from the checkout's
nexus.toml, real directories, real executables on a controlled PATH, and a
real HTTP listener standing in for the remote runtime. None of these tests
opens a PostgreSQL connection; tests/test_runtime/test_readiness_pg.py covers
the database checks behind the PostgreSQL gate.
"""

from __future__ import annotations

from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import threading
from typing import Any, Callable

import pytest
import tomlkit

from nexus import cli
from nexus.api.secrets_endpoints import required_secret_accounts
from nexus.config import load_settings
from nexus.runtime.contract import (
    GATEWAY_PORT_ENV,
    HOME_ENV,
    NEXUS_AUTH_HEADER,
    RUNTIME_CONFIG_ENV,
    RUNTIME_STATUS_PATH,
)
from nexus.runtime.readiness import (
    REGISTRY,
    REQUIRED_EXTENSIONS,
    TARGETS,
    CheckResult,
    CheckSpec,
    Outcome,
    ReadinessContext,
    ReadinessReport,
    find_postgres_tool,
    render_report,
    run_readiness,
    runtime_version,
    validate_registry,
)
from nexus.util.secret_manager import InMemorySecretBackend, get_secret, set_secret

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
CHECK_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# The stable contract: renaming, re-scoping or re-wiring a check is a
# deliberate change to this table (and, for field changes, the schema version).
EXPECTED_REGISTRY = [
    ("config.valid", ["owner-host", "owner-client", "ci-runner"], []),
    ("postgres.reachable", ["owner-host"], ["config.valid"]),
    ("postgres.extensions", ["owner-host"], ["postgres.reachable"]),
    ("template.present", ["owner-host"], ["postgres.reachable"]),
    ("template.migrations_current", ["owner-host"], ["template.present"]),
    ("slots.migrations_current", ["owner-host"], ["template.present"]),
    ("template.idf_analyzer_current", ["owner-host"], ["template.present"]),
    ("slots.idf_analyzer_current", ["owner-host"], ["template.present"]),
    ("tools.pg_dump", ["owner-host"], ["config.valid"]),
    ("ui.bundle", ["owner-host"], []),
    ("secrets.seat_providers", ["owner-host"], ["config.valid"]),
    ("gateway.reachable", ["owner-client"], ["config.valid"]),
    ("gateway.version", ["owner-client"], ["gateway.reachable"]),
    ("reachability.gate", ["ci-runner"], ["config.valid"]),
]


@pytest.fixture(autouse=True)
def _developer_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Resolve the checkout config, the configured gateway port, fresh secrets."""
    for name in (HOME_ENV, RUNTIME_CONFIG_ENV, GATEWAY_PORT_ENV, "NEXUS_AUTH"):
        monkeypatch.delenv(name, raising=False)
    get_secret.cache_clear()
    yield
    get_secret.cache_clear()


def _write_config(
    tmp_path: Path, edit: Callable[[Any], None] = lambda document: None
) -> Path:
    """Write a real copy of the checkout's nexus.toml, edited by ``edit``."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    edit(document)
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _by_id(report: ReadinessReport) -> dict[str, CheckResult]:
    return {check.id: check for check in report.checks}


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *args: str,
) -> tuple[int, str, str]:
    """Run the real ``nexus`` entry point and capture its streams."""
    monkeypatch.setattr(sys, "argv", ["nexus", *args])
    exit_code = cli.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Registry and schema
# ---------------------------------------------------------------------------


def test_registry_ids_are_unique_stable_and_scoped() -> None:
    """Every check has one stable dotted ID, known roles, and prior dependencies."""
    assert [
        (spec.id, list(spec.targets), list(spec.depends_on)) for spec in REGISTRY
    ] == EXPECTED_REGISTRY
    assert all(CHECK_ID.match(spec.id) for spec in REGISTRY)
    assert TARGETS == ("owner-host", "owner-client", "ci-runner")
    validate_registry(REGISTRY)
    assert [spec.id for spec in REGISTRY if spec.gateway_evaluable] == [
        "config.valid",
        "tools.pg_dump",
        "ui.bundle",
    ]


def _spec(
    check_id: str,
    depends_on: tuple[str, ...] = (),
    *,
    targets: tuple[Any, ...] = ("owner-host",),
    gateway: bool = False,
    run: Callable[[ReadinessContext], Outcome] = lambda ctx: Outcome(True, "ok"),
) -> CheckSpec:
    return CheckSpec(check_id, targets, depends_on, run, gateway_evaluable=gateway)


@pytest.mark.parametrize(
    ("registry", "message"),
    (
        pytest.param(
            (_spec("a.one"), _spec("a.one")), "Duplicate readiness check ID", id="dup"
        ),
        pytest.param(
            (_spec("a.two", ("a.one",)), _spec("a.one")),
            "not registered before it",
            id="forward",
        ),
        pytest.param(
            (
                _spec("a.one"),
                _spec("a.two", ("a.one",), targets=("owner-host", "ci-runner")),
            ),
            "serves a target its dependency a.one does not serve",
            id="scope",
        ),
        pytest.param(
            (_spec("a.one"), _spec("a.two", ("a.one",), gateway=True)),
            "gateway-evaluable but a.one is not",
            id="gateway",
        ),
        pytest.param(
            (_spec("a.one", targets=("guest-ready-host",)),),
            "invalid targets",
            id="unknown-target",
        ),
    ),
)
def test_registry_validation_rejects_unevaluable_wiring(
    registry: tuple[CheckSpec, ...], message: str
) -> None:
    """A registry that could not run as written fails loudly, before any check."""
    with pytest.raises(ValueError, match=message):
        validate_registry(registry)


def test_check_schema_is_stable() -> None:
    """Python, Tauri and CI read one schema; field changes bump the version."""
    check = CheckResult.model_json_schema()
    assert set(check["properties"]) == {
        "id",
        "targets",
        "status",
        "observed",
        "depends_on",
        "remediation",
    }
    assert set(check["required"]) == set(check["properties"])
    assert check["properties"]["status"]["enum"] == ["pass", "fail", "skip"]
    assert check["properties"]["targets"]["items"]["enum"] == list(TARGETS)
    assert check["additionalProperties"] is False

    report = ReadinessReport.model_json_schema()
    assert set(report["properties"]) == {
        "schema_version",
        "target",
        "ok",
        "checks",
        "omitted",
    }
    assert report["properties"]["schema_version"]["const"] == 1


def test_required_extensions_match_the_migrations() -> None:
    """postgres.extensions asks for exactly the extensions migrations create."""
    created = {
        name.lower()
        for path in (REPO_ROOT / "migrations").iterdir()
        if path.suffix in {".sql", ".py"}
        for name in re.findall(
            r"CREATE EXTENSION IF NOT EXISTS\s+\"?(\w+)", path.read_text(), re.I
        )
    }
    assert created == set(REQUIRED_EXTENSIONS)


# ---------------------------------------------------------------------------
# Runner semantics on real checks
# ---------------------------------------------------------------------------


def test_config_valid_passes_on_the_checkout_config() -> None:
    """The active nexus.toml resolves through the runtime-home rule and loads."""
    ctx = ReadinessContext()
    report = run_readiness("owner-host", ctx, gateway_only=True)

    config = _by_id(report)["config.valid"]
    assert config.status == "pass"
    assert config.observed == f"{REPO_CONFIG} (checkout)"
    assert config.remediation is None
    assert ctx.settings is not None
    assert ctx.settings.runtime is not None
    assert ctx.settings.runtime.readiness.slots == [1, 2, 3, 4, 5]


def test_invalid_config_fails_and_skips_every_dependent_by_root_cause(
    tmp_path: Path,
) -> None:
    """A failed dependency skips its whole chain, each naming the root failure."""

    def break_slots(document: Any) -> None:
        document["runtime"]["readiness"]["slots"] = [0, 2]

    config = _write_config(tmp_path, break_slots)
    report = run_readiness("owner-host", ReadinessContext(config_path=config))
    checks = _by_id(report)

    assert report.ok is False
    assert checks["config.valid"].status == "fail"
    assert "runtime.readiness.slots" in checks["config.valid"].observed
    assert "slots must be between 1 and 5, got [0]" in checks["config.valid"].observed
    assert str(config) in (checks["config.valid"].remediation or "")
    # Direct dependents and transitive ones (postgres.extensions depends on
    # postgres.reachable) all name config.valid; nothing reached PostgreSQL.
    for check_id in (
        "postgres.reachable",
        "postgres.extensions",
        "template.present",
        "template.migrations_current",
        "slots.migrations_current",
        "template.idf_analyzer_current",
        "slots.idf_analyzer_current",
        "tools.pg_dump",
        "secrets.seat_providers",
    ):
        assert checks[check_id].status == "skip", check_id
        assert checks[check_id].observed == "config.valid failed"
        assert checks[check_id].remediation == "Resolve config.valid first."
    # A check without that dependency still runs.
    assert checks["ui.bundle"].status in {"pass", "fail"}


def test_config_valid_refuses_two_active_configurations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXUS_HOME and an explicit --config naming another file is a failure."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv(HOME_ENV, str(home))
    report = run_readiness(
        "ci-runner", ReadinessContext(config_path=_write_config(tmp_path))
    )
    config = _by_id(report)["config.valid"]
    assert config.status == "fail"
    assert "Two active configurations are not allowed" in config.observed
    assert _by_id(report)["reachability.gate"].status == "skip"


def test_runner_skips_a_dependent_of_a_skipped_check_by_root_cause() -> None:
    """A three-link chain names the failed root, not the skipped middle link."""
    calls: list[str] = []

    def failing(ctx: ReadinessContext) -> Outcome:
        calls.append("root")
        return Outcome(False, "down", "bring it up")

    def unreachable(ctx: ReadinessContext) -> Outcome:
        raise AssertionError("a skipped check must never run")

    registry = (
        _spec("chain.root", run=failing),
        _spec("chain.middle", ("chain.root",), run=unreachable),
        _spec("chain.leaf", ("chain.middle",), run=unreachable),
        _spec("chain.free"),
    )
    report = run_readiness("owner-host", ReadinessContext(), registry=registry)

    assert calls == ["root"]
    assert [(c.id, c.status, c.observed) for c in report.checks] == [
        ("chain.root", "fail", "down"),
        ("chain.middle", "skip", "chain.root failed"),
        ("chain.leaf", "skip", "chain.root failed"),
        ("chain.free", "pass", "ok"),
    ]
    assert report.ok is False
    assert render_report(report) == [
        "fail  chain.root    down  -> bring it up",
        "skip  chain.middle  chain.root failed",
        "skip  chain.leaf    chain.root failed",
        "pass  chain.free    ok",
    ]


def test_ui_bundle_reads_the_build_directory(tmp_path: Path) -> None:
    """ui.bundle passes only once the build's index.html exists."""
    dist = tmp_path / "dist" / "public"
    ctx = ReadinessContext(ui_dist_dir=dist)
    missing = _by_id(run_readiness("owner-host", ctx, gateway_only=True))["ui.bundle"]
    assert missing.status == "fail"
    assert missing.observed == f"{dist / 'index.html'} missing"
    assert missing.remediation == "Build it: npm --prefix ui run build"

    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    ctx = ReadinessContext(ui_dist_dir=dist)
    built = _by_id(run_readiness("owner-host", ctx, gateway_only=True))["ui.bundle"]
    assert (built.status, built.observed) == ("pass", str(dist))


def _executable(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    tool = directory / name
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    return tool


def test_pg_dump_resolves_from_path_then_tool_search_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PATH wins; tool_search_paths supplements it; neither is a failure."""
    on_path = _executable(tmp_path / "path-bin", "pg_dump")
    extra = _executable(tmp_path / "app-bin", "pg_dump")
    empty = tmp_path / "empty-bin"
    empty.mkdir()

    monkeypatch.setenv("PATH", str(on_path.parent))
    assert find_postgres_tool("pg_dump", [str(extra.parent)]) == (str(on_path), "PATH")

    monkeypatch.setenv("PATH", str(empty))
    assert find_postgres_tool("pg_dump", [str(extra.parent)]) == (
        str(extra),
        "[api.database].tool_search_paths",
    )

    def search(paths: list[str]) -> Callable[[Any], None]:
        def edit(document: Any) -> None:
            document["api"]["database"]["tool_search_paths"] = paths

        return edit

    found = run_readiness(
        "owner-host",
        ReadinessContext(
            config_path=_write_config(tmp_path, search([str(extra.parent)]))
        ),
        gateway_only=True,
    )
    tool = _by_id(found)["tools.pg_dump"]
    assert tool.status == "pass"
    assert tool.observed == f"{extra} (via [api.database].tool_search_paths)"

    absent = run_readiness(
        "owner-host",
        ReadinessContext(config_path=_write_config(tmp_path, search([str(empty)]))),
        gateway_only=True,
    )
    tool = _by_id(absent)["tools.pg_dump"]
    assert tool.status == "fail"
    assert "pg_dump not found on PATH and [api.database].tool_search_paths" in (
        tool.observed
    )
    assert "tool_search_paths" in (tool.remediation or "")


def _seat_accounts() -> list[str]:
    return sorted(required_secret_accounts(load_settings(REPO_CONFIG)))


# The registered specs themselves, narrowed to checks that open no database.
SECRETS_ONLY = [
    spec for spec in REGISTRY if spec.id in {"config.valid", "secrets.seat_providers"}
]


def _secrets_check() -> CheckResult:
    report = run_readiness("owner-host", ReadinessContext(), registry=SECRETS_ONLY)
    return _by_id(report)["secrets.seat_providers"]


def test_seat_secrets_report_presence_and_never_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment-only mode: a present key is named, its value never appears."""
    accounts = _seat_accounts()
    assert accounts, "the checkout's seats read at least one stored key"
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    for account in accounts:
        monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)

    secrets = _secrets_check()
    assert secrets.status == "fail"
    assert secrets.observed.startswith("missing: ")
    assert secrets.observed.endswith("[environment only, NEXUS_KEYRING_DISABLE=1]")
    assert secrets.remediation == (
        "Export "
        + ", ".join(f"{account.upper()}_API_KEY" for account in accounts)
        + ", or unset NEXUS_KEYRING_DISABLE to read the platform store."
    )

    sentinel = "sk-readiness-sentinel-9f3c7a"
    for account in accounts:
        monkeypatch.setenv(f"{account.upper()}_API_KEY", sentinel)
    get_secret.cache_clear()
    report = run_readiness("owner-host", ReadinessContext(), registry=SECRETS_ONLY)
    secrets = _by_id(report)["secrets.seat_providers"]
    assert secrets.status == "pass"
    assert secrets.observed.startswith("present: ")
    assert all(account in secrets.observed for account in accounts)
    dumped = json.dumps(report.model_dump(mode="json")) + "\n".join(
        render_report(report)
    )
    assert sentinel not in dumped
    assert sentinel[-4:] not in dumped


def test_seat_secrets_read_the_platform_store_path(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the store enabled, presence comes from the active secret backend."""
    accounts = _seat_accounts()
    for account in accounts:
        monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    secrets = _secrets_check()
    assert secrets.status == "fail"
    assert secrets.observed.endswith("[platform secret store]")
    assert "API KEYS card" in (secrets.remediation or "")

    for account in accounts:
        set_secret(account, "store-held-value-5521")
    secrets = _secrets_check()
    assert secrets.status == "pass"
    assert "5521" not in secrets.observed
    assert in_memory_secret_store.accounts() == frozenset(accounts)


# ---------------------------------------------------------------------------
# Owner client against a real HTTP listener
# ---------------------------------------------------------------------------


class _RuntimeEndpoint:
    """A loopback HTTP server that answers /runtime/status like a gateway."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[dict[str, str]] = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                endpoint.requests.append(
                    {"path": self.path, **{k: v for k, v in self.headers.items()}}
                )
                body = json.dumps(endpoint.payload).encode()
                self.send_response(200 if self.path == RUNTIME_STATUS_PATH else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "_RuntimeEndpoint":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


def _external_config(tmp_path: Path, gateway_url: str) -> Path:
    def attach(document: Any) -> None:
        document["runtime"]["profile"] = "external"
        external = tomlkit.table()
        external["gateway_url"] = gateway_url
        document["runtime"]["external"] = external

    return _write_config(tmp_path, attach)


def test_doctor_owner_client_reaches_the_runtime_with_its_auth_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real entry point probes /runtime/status and matches the version."""
    payload = {"ok": True, "profile": "local", "version": runtime_version()}
    with _RuntimeEndpoint(payload) as endpoint:
        config = _external_config(tmp_path, endpoint.url)
        exit_code, out, err = _run_cli(
            monkeypatch,
            capsys,
            "doctor",
            "--target",
            "owner-client",
            "--config",
            str(config),
            "--json",
        )

    assert (exit_code, err) == (0, "")
    report = json.loads(out)
    assert report["target"] == "owner-client"
    assert report["ok"] is True
    assert [(c["id"], c["status"]) for c in report["checks"]] == [
        ("config.valid", "pass"),
        ("gateway.reachable", "pass"),
        ("gateway.version", "pass"),
    ]
    assert report["checks"][1]["observed"] == (
        f"{endpoint.url}{RUNTIME_STATUS_PATH} answered (profile local, runtime ok)"
    )
    assert [request["path"] for request in endpoint.requests] == [RUNTIME_STATUS_PATH]
    assert endpoint.requests[0][NEXUS_AUTH_HEADER] == ""


def test_doctor_owner_client_fails_on_a_version_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A runtime on another version fails gateway.version and exits 1."""
    payload = {"ok": False, "profile": "local", "version": "0.0.0-other"}
    with _RuntimeEndpoint(payload) as endpoint:
        config = _external_config(tmp_path, endpoint.url)
        exit_code, out, err = _run_cli(
            monkeypatch,
            capsys,
            "doctor",
            "--target",
            "owner-client",
            "--config",
            str(config),
        )

    assert (exit_code, err) == (1, "")
    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[1].startswith("pass  gateway.reachable  ")
    assert lines[1].endswith("answered (profile local, runtime not ok)")
    assert lines[2] == (
        f"fail  gateway.version    client {runtime_version()}, runtime 0.0.0-other"
        "  -> Update the older side (git pull, poetry install), then restart the "
        "runtime with nexus restart."
    )


def test_doctor_owner_client_reports_an_unreachable_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A closed port fails gateway.reachable and skips the version check."""
    with _RuntimeEndpoint({}) as endpoint:
        closed = endpoint.url
    config = _external_config(tmp_path, closed)
    exit_code, out, _ = _run_cli(
        monkeypatch,
        capsys,
        "doctor",
        "--target",
        "owner-client",
        "--config",
        str(config),
        "--json",
    )

    assert exit_code == 1
    checks = {check["id"]: check for check in json.loads(out)["checks"]}
    assert checks["gateway.reachable"]["status"] == "fail"
    assert "Connection refused" in checks["gateway.reachable"]["observed"]
    assert checks["gateway.reachable"]["remediation"] == (
        "Start the gateway [runtime.external].gateway_url names."
    )
    assert checks["gateway.version"]["status"] == "skip"


# ---------------------------------------------------------------------------
# CI runner through the real entry point
# ---------------------------------------------------------------------------


def test_doctor_ci_runner_passes_on_this_checkout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ci-runner role runs the real reachability gate and exits 0."""
    exit_code, out, err = _run_cli(
        monkeypatch, capsys, "--json", "doctor", "--target", "ci-runner"
    )

    assert (exit_code, err) == (0, "")
    report = json.loads(out)
    assert report["schema_version"] == 1
    assert report["ok"] is True
    assert report["omitted"] == []
    gate = report["checks"][1]
    assert (gate["id"], gate["status"]) == ("reachability.gate", "pass")
    assert gate["observed"].endswith("production modules reachable, no findings")


def test_doctor_exits_one_on_an_invalid_config_and_prints_one_line_per_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Any failed check exits 1; text output is one line per check."""
    config = tmp_path / "nexus.toml"
    config.write_text("[runtime\n", encoding="utf-8")
    exit_code, out, _ = _run_cli(
        monkeypatch, capsys, "doctor", "--target", "ci-runner", "--config", str(config)
    )

    assert exit_code == 1
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"fail  config.valid       {config}: ")
    assert lines[1] == "skip  reachability.gate  config.valid failed"


def test_doctor_parser_defaults_to_owner_host_and_rejects_other_roles() -> None:
    """doctor is a registered subcommand whose targets are the registry's roles."""
    parser = cli.build_parser()
    namespace = parser.parse_args(["doctor"])
    assert (namespace.command, namespace.target, namespace.config) == (
        "doctor",
        "owner-host",
        None,
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["doctor", "--target", "guest-ready-host"])
