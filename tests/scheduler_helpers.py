"""Real scheduler proof configuration using the registered TEST provider."""

from pathlib import Path
from urllib.parse import urlsplit

import tomlkit


def test_provider_config(tmp_path, base_url, monkeypatch):
    """Route every provider consumer to TEST in a private config file."""
    doc = tomlkit.parse(Path("nexus.toml").read_text())
    providers = doc["global"]["model"]["api_models"]
    uses = []
    for provider in providers.values():
        for model in provider["models"]:
            model_uses = model.pop("uses", [])
            uses.extend(use for use in model_uses if use != "local_models.model")
            if "local_models.model" in model_uses:
                model["uses"] = ["local_models.model"]
    providers["test"]["models"][0]["uses"] = uses
    providers["test"]["base_url"] = base_url
    doc["runtime"]["services"]["mock_openai"]["port"] = urlsplit(base_url).port
    doc["runtime"]["state_dir"] = str(tmp_path / "runtime")
    doc["wizard"]["max_retries"] = 0
    doc["runtime"]["scheduler"].update(
        poll_interval_seconds=0.05,
        generation_wait_seconds=0.01,
        heartbeat_interval_seconds=0.1,
        lease_duration_seconds=3,
        compaction_retry_delay_seconds=0.1,
        error_backoff_seconds=0.1,
    )
    path = tmp_path / "scheduler.toml"
    path.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path
