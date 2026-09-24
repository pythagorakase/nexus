"""The managed llama-server's configured and reported context capacity."""

from typing import Any, Mapping, Sequence


def serving_context_window(command: Sequence[str]) -> int:
    """Read the explicit serving window from the supervisor's actual argv."""
    values = []
    for index, argument in enumerate(command):
        if argument in {"--ctx-size", "-c"}:
            values.append(command[index + 1] if index + 1 < len(command) else "")
        elif argument.startswith("--ctx-size="):
            values.append(argument.split("=", 1)[1])
    if len(values) != 1 or not values[0].isdigit() or int(values[0]) <= 0:
        raise ValueError(
            "llama_server.command requires one explicit positive --ctx-size"
        )
    return int(values[0])


def local_context_window(settings: Mapping[str, Any]) -> int:
    """Resolve the same window the supervisor passes to llama-server."""
    return serving_context_window(
        settings["runtime"]["services"]["llama_server"]["command"]
    )


def validate_reported_context(props: Mapping[str, Any], expected: int) -> None:
    """Refuse an unavailable or mismatched per-slot context from GET /props."""
    actual = props.get("default_generation_settings", {}).get("n_ctx")
    if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected:
        raise ValueError(
            f"llama-server reports n_ctx={actual!r}; configured serving context_window={expected}"
        )


def verify_local_context(provider: Any, settings: Mapping[str, Any]) -> None:
    """Check a provider instance on first use, before any local generation."""
    import httpx

    expected = local_context_window(settings)
    base_url = settings["global"]["model"]["api_models"]["local"]["base_url"]
    url = base_url.removesuffix("/").removesuffix("/v1") + "/props"
    key = (url, expected)
    if getattr(provider, "_verified_local_context", None) == key:
        return
    response = httpx.get(url, timeout=provider.client.timeout)
    response.raise_for_status()
    validate_reported_context(response.json(), expected)
    provider._verified_local_context = key
