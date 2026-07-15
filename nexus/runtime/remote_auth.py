"""Origin-scoped authentication for outbound runtime HTTP requests.

Cloudflare Access is an edge boundary in front of a hosted NEXUS runtime.
The application remains auth-less behind it: remote clients resolve a service
token from the platform secret store and attach its two headers only when the
request target exactly matches the configured remote origin.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

from nexus.config.settings_models import RuntimeRemoteSettings
from nexus.runtime.contract import (
    CF_ACCESS_CLIENT_ID_HEADER,
    CF_ACCESS_CLIENT_SECRET_HEADER,
    NEXUS_AUTH_HEADER,
)
from nexus.util.secret_manager import get_secret


@dataclass(frozen=True)
class RuntimeRequestAuth:
    """Headers and redirect policy for one outbound runtime request."""

    headers: Dict[str, str]
    allow_redirects: bool


def _normalized_origin(url: str) -> Optional[Tuple[str, str, int]]:
    """Return a comparable HTTP(S) origin with default ports expanded."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    if scheme not in {"http", "https"} or hostname is None:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, hostname.lower(), port


def _same_origin(left: str, right: str) -> bool:
    """Return whether two URLs have the same scheme, host, and effective port."""
    left_origin = _normalized_origin(left)
    return left_origin is not None and left_origin == _normalized_origin(right)


def _credential_transport_is_safe(url: str) -> bool:
    """Allow credentials over HTTPS, or HTTP only to genuine loopback."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() == "https":
        return True
    if parsed.scheme.lower() != "http" or parsed.hostname is None:
        return False
    hostname = parsed.hostname.lower()
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def build_runtime_request_auth(
    target_url: str,
    remote: Optional[RuntimeRemoteSettings] = None,
) -> RuntimeRequestAuth:
    """Build safe headers for a runtime request.

    ``X-Nexus-Auth`` remains part of every client request. Cloudflare Access
    credentials are resolved only for the configured remote origin. Requests
    carrying any credential never follow redirects because ``requests``
    otherwise preserves arbitrary custom headers across cross-origin redirects.
    A non-empty application credential also requires HTTPS except on loopback.
    """
    nexus_auth = os.environ.get("NEXUS_AUTH", "")
    if nexus_auth and not _credential_transport_is_safe(target_url):
        raise ValueError(
            "Refusing to send NEXUS_AUTH over plaintext to a non-loopback target"
        )
    headers = {NEXUS_AUTH_HEADER: nexus_auth}
    allow_redirects = not bool(nexus_auth)
    if remote is None or remote.cloudflare_access is None:
        return RuntimeRequestAuth(headers=headers, allow_redirects=allow_redirects)
    if not _same_origin(target_url, remote.base_url):
        return RuntimeRequestAuth(headers=headers, allow_redirects=allow_redirects)

    access = remote.cloudflare_access
    headers[CF_ACCESS_CLIENT_ID_HEADER] = get_secret(access.client_id_secret)
    headers[CF_ACCESS_CLIENT_SECRET_HEADER] = get_secret(access.client_secret_secret)
    return RuntimeRequestAuth(headers=headers, allow_redirects=False)
