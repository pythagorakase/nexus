"""Live and pure-boundary tests for hosted-runtime authentication."""

from __future__ import annotations

from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from typing import Iterator, Optional

import pytest
import tomlkit

from nexus import cli
from nexus.config import load_settings
from nexus.config.settings_models import RuntimeRemoteSettings
from nexus.runtime import remote_auth
from nexus.runtime.contract import (
    CF_ACCESS_CLIENT_ID_HEADER,
    CF_ACCESS_CLIENT_SECRET_HEADER,
    NEXUS_AUTH_HEADER,
    RUNTIME_CONFIG_ENV,
)
from nexus.runtime.supervisor import Supervisor
from nexus.util.secret_manager import MissingSecretError

CLIENT_ID_ACCOUNT = "cloudflare_access_client_id"
CLIENT_SECRET_ACCOUNT = "cloudflare_access_client_secret"
CLIENT_ID_ENV = "CLOUDFLARE_ACCESS_CLIENT_ID_API_KEY"
CLIENT_SECRET_ENV = "CLOUDFLARE_ACCESS_CLIENT_SECRET_API_KEY"


def _access_remote() -> RuntimeRemoteSettings:
    return RuntimeRemoteSettings(
        base_url="https://nexus.example.com",
        cloudflare_access={
            "client_id_secret": CLIENT_ID_ACCOUNT,
            "client_secret_secret": CLIENT_SECRET_ACCOUNT,
        },
    )


@pytest.fixture(autouse=True)
def _clear_secret_cache() -> Iterator[None]:
    """Keep environment-backed secret reads isolated between tests."""
    remote_auth.get_secret.cache_clear()
    yield
    remote_auth.get_secret.cache_clear()


@pytest.fixture()
def runtime_http_server() -> Iterator[tuple[str, list[dict[str, Optional[str]]]]]:
    """Run a real loopback HTTP runtime and record received auth headers."""
    records: list[dict[str, Optional[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            records.append(
                {
                    "path": self.path,
                    "nexus_auth": self.headers.get(NEXUS_AUTH_HEADER),
                    "access_id": self.headers.get(CF_ACCESS_CLIENT_ID_HEADER),
                    "access_secret": self.headers.get(CF_ACCESS_CLIENT_SECRET_HEADER),
                }
            )
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.end_headers()
                return

            payload = (
                {
                    "is_empty": False,
                    "is_wizard_mode": False,
                    "storyteller_text": "Remote story state.",
                }
                if self.path == "/api/slot/5/state"
                else {"ok": True}
            )
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_access_headers_resolve_for_exact_remote_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured origin receives both environment-store Access values."""
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.setenv(CLIENT_ID_ENV, "client-id-value")
    monkeypatch.setenv(CLIENT_SECRET_ENV, "client-secret-value")
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    auth = remote_auth.build_runtime_request_auth(
        "https://NEXUS.example.com:443/api/slot/5/state",
        _access_remote(),
    )

    assert auth.headers == {
        NEXUS_AUTH_HEADER: "runtime-token",
        CF_ACCESS_CLIENT_ID_HEADER: "client-id-value",
        CF_ACCESS_CLIENT_SECRET_HEADER: "client-secret-value",
    }
    assert auth.allow_redirects is False


@pytest.mark.parametrize(
    "target",
    [
        "http://nexus.example.com/api/slot/5/state",
        "https://nexus.example.com:444/api/slot/5/state",
        "https://attacker.example/api/slot/5/state",
    ],
)
def test_access_headers_never_leave_configured_origin(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Origin drift suppresses Access secret resolution entirely."""
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.delenv(CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(CLIENT_SECRET_ENV, raising=False)
    monkeypatch.delenv("NEXUS_AUTH", raising=False)

    auth = remote_auth.build_runtime_request_auth(target, _access_remote())

    assert auth.headers == {NEXUS_AUTH_HEADER: ""}
    assert auth.allow_redirects is True


def test_unconfigured_access_preserves_runtime_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordinary local and remote clients keep the existing header contract."""
    monkeypatch.delenv("NEXUS_AUTH", raising=False)
    remote = RuntimeRemoteSettings(base_url="https://nexus.example.com")

    auth = remote_auth.build_runtime_request_auth(
        "https://nexus.example.com/runtime/status", remote
    )

    assert auth.headers == {NEXUS_AUTH_HEADER: ""}
    assert auth.allow_redirects is True


def test_nonempty_runtime_token_disables_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The application credential cannot cross an HTTP redirect either."""
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    auth = remote_auth.build_runtime_request_auth(
        "https://nexus.example.com/runtime/status"
    )

    assert auth.headers == {NEXUS_AUTH_HEADER: "runtime-token"}
    assert auth.allow_redirects is False


@pytest.mark.parametrize(
    "target", ["http://example.com/status", "http://192.168.1.20/status"]
)
def test_runtime_token_rejects_plaintext_non_loopback(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runtime credential is never sent in cleartext across the network."""
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    with pytest.raises(ValueError, match="plaintext.*non-loopback"):
        remote_auth.build_runtime_request_auth(target)


@pytest.mark.parametrize(
    "target",
    [
        "http://localhost:8002/status",
        "http://127.0.0.1:8002/status",
        "http://[::1]:8002/status",
    ],
)
def test_runtime_token_allows_plaintext_loopback(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local development keeps its loopback HTTP credential seam."""
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    auth = remote_auth.build_runtime_request_auth(target)

    assert auth.headers == {NEXUS_AUTH_HEADER: "runtime-token"}
    assert auth.allow_redirects is False


def test_missing_access_secret_fails_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing configured credential is a visible error, never a fallback."""
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.delenv(CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(CLIENT_SECRET_ENV, raising=False)

    with pytest.raises(MissingSecretError, match=CLIENT_ID_ENV):
        remote_auth.build_runtime_request_auth(
            "https://nexus.example.com/runtime/status", _access_remote()
        )


def test_cli_request_reaches_live_loopback_with_runtime_auth(
    runtime_http_server: tuple[str, list[dict[str, Optional[str]]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed story CLI sends auth through a real HTTP socket."""
    base_url, records = runtime_http_server
    monkeypatch.setenv("NEXUS_API_URL", base_url)
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    result = cli.run_load(Namespace(slot=5))

    assert result["success"] is True
    assert records == [
        {
            "path": "/api/slot/5/state",
            "nexus_auth": "runtime-token",
            "access_id": None,
            "access_secret": None,
        }
    ]


def test_cli_credential_request_does_not_follow_live_redirect(
    runtime_http_server: tuple[str, list[dict[str, Optional[str]]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect suppression is verified against a real redirect response."""
    base_url, records = runtime_http_server
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    response = cli._api_get(f"{base_url}/redirect", timeout=2)

    assert response.status_code == 302
    assert [record["path"] for record in records] == ["/redirect"]


def test_supervisor_remote_probe_reaches_live_runtime(
    runtime_http_server: tuple[str, list[dict[str, Optional[str]]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor probe sends shared auth through a real HTTP socket."""
    base_url, records = runtime_http_server
    settings = load_settings("nexus.toml")
    runtime = settings.runtime.model_copy(
        update={
            "profile": "remote",
            "remote": RuntimeRemoteSettings(base_url=base_url),
        }
    )
    settings = settings.model_copy(update={"runtime": runtime})
    supervisor = Supervisor(settings, Path("nexus.toml"))
    monkeypatch.setenv("NEXUS_AUTH", "runtime-token")

    result = supervisor._check_remote()

    assert result["runtime"] == {"ok": True}
    assert records == [
        {
            "path": "/runtime/status",
            "nexus_auth": "runtime-token",
            "access_id": None,
            "access_secret": None,
        }
    ]


def test_cli_uses_remote_profile_from_explicit_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story commands inherit base_url from NEXUS_RUNTIME_CONFIG."""
    document = tomlkit.parse(Path("nexus.toml").read_text(encoding="utf-8"))
    document["runtime"]["profile"] = "remote"
    config = tmp_path / "remote.toml"
    config.write_text(tomlkit.dumps(document), encoding="utf-8")
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(config))
    monkeypatch.delenv("NEXUS_API_URL", raising=False)

    assert cli.get_api_url() == "https://nexus.pythagora.net"


def test_cli_outside_checkout_preserves_local_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed CLI outside the checkout does not require a cwd config."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(RUNTIME_CONFIG_ENV, raising=False)
    monkeypatch.delenv("NEXUS_API_URL", raising=False)

    assert cli.get_api_url() == cli.DEFAULT_API_URL
