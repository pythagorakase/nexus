"""Issue #812: one production embedder, loaded only from its local artifact.

The EmbeddingManager used to fall back to a Hugging Face download when an
active model's ``local_path`` was missing, then to hardcoded default models,
and finished with zero models and a log line when all of that failed. These
tests pin the fail-loud contract: a missing, non-directory or unloadable
artifact raises a RuntimeError naming the model, the path and the corrective
command, without any network load; and the committed configuration names
exactly one active embedder.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, List

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[1]

# Runs in a fresh interpreter so HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE are set
# before huggingface_hub and transformers read them at import time.
_OFFLINE_PROBE = r"""
import json
import sys

from nexus.agents.memnon.utils import embedding_manager as em


def probe(local_path):
    settings = {
        "models": {
            "probe-embedder": {
                "is_active": True,
                "local_path": local_path,
                "remote_path": "example-org/probe-embedder",
                "dimensions": 8,
                "weight": 1.0,
            }
        }
    }
    try:
        em.EmbeddingManager(settings=settings)
    except BaseException as exc:
        cause = exc.__cause__
        return {
            "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
            "message": str(exc),
            "cause": None if cause is None else type(cause).__qualname__,
            "cached": len(em._MODEL_CACHE),
        }
    return {"type": None, "message": "", "cause": None, "cached": len(em._MODEL_CACHE)}


print(json.dumps({"missing": probe(sys.argv[1]), "unloadable": probe(sys.argv[2])}))
"""


def _probe_offline(missing: Path, unloadable: Path) -> Dict[str, Dict[str, Any]]:
    """Construct EmbeddingManagers in an offline interpreter and report errors."""

    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", _OFFLINE_PROBE, str(missing), str(unloadable)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_missing_or_unloadable_local_artifact_raises_without_network(
    tmp_path: Path,
) -> None:
    """No remote download, no default model: the load fails with a remedy."""

    missing = tmp_path / "not-installed"
    unloadable = tmp_path / "empty-artifact"
    unloadable.mkdir()

    outcome = _probe_offline(missing, unloadable)

    absent = outcome["missing"]
    assert absent["type"] == "builtins.RuntimeError", absent
    assert "probe-embedder" in absent["message"]
    assert f"{missing} does not exist" in absent["message"]
    assert (
        f"hf download example-org/probe-embedder --local-dir {missing}"
        in absent["message"]
    )
    assert "nexus models verify" in absent["message"]
    # Raised before any load was attempted, local or remote.
    assert absent["cause"] is None
    assert absent["cached"] == 0

    broken = outcome["unloadable"]
    assert broken["type"] == "builtins.RuntimeError", broken
    assert f"failed to load from local_path {unloadable}" in broken["message"]
    assert "nexus models verify" in broken["message"]
    assert broken["cause"] is not None
    assert broken["cached"] == 0


def _manager_settings(**model: Any) -> Dict[str, Any]:
    return {"models": {"probe-embedder": {"weight": 1.0, "dimensions": 8, **model}}}


def test_local_path_that_is_a_file_raises(tmp_path: Path) -> None:
    """A file where the artifact directory belongs is not loaded."""

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager

    artifact = tmp_path / "model.safetensors"
    artifact.write_bytes(b"\x00" * 16)

    with pytest.raises(RuntimeError, match="is not a directory") as raised:
        EmbeddingManager(
            settings=_manager_settings(is_active=True, local_path=str(artifact))
        )
    assert "probe-embedder" in str(raised.value)
    assert "nexus models verify" in str(raised.value)


def test_is_active_is_required(tmp_path: Path) -> None:
    """A model entry without is_active is no longer treated as active."""

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager

    with pytest.raises(ValueError, match="probe-embedder.*must declare is_active"):
        EmbeddingManager(settings=_manager_settings(local_path=str(tmp_path)))


def test_no_active_embedder_raises_instead_of_loading_defaults(
    tmp_path: Path,
) -> None:
    """Zero active models used to trigger hardcoded default downloads."""

    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager

    with pytest.raises(RuntimeError, match="No embedding model .* is_active"):
        EmbeddingManager(
            settings=_manager_settings(is_active=False, local_path=str(tmp_path))
        )


def _config_with_active(tmp_path: Path, active: List[str]) -> Path:
    document = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    memnon: Any = document["memnon"]
    for name, model in memnon["models"].items():
        model["is_active"] = name in active
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(document))
    return path


def _registered_embedders() -> List[str]:
    document = tomllib.loads((REPO_ROOT / "nexus.toml").read_text())
    return list(document["memnon"]["models"])


def test_repository_config_declares_one_active_embedder() -> None:
    """The committed nexus.toml satisfies the single-embedder contract."""

    models = load_settings(REPO_ROOT / "nexus.toml").memnon.models
    assert sum(model.is_active for model in models.values()) == 1


def test_settings_reject_zero_active_embedders(tmp_path: Path) -> None:
    """A config with no production embedder fails at load, not at first query."""

    with pytest.raises(ValidationError, match="exactly one embedder.*none is active"):
        load_settings(_config_with_active(tmp_path, []))


def test_settings_reject_two_active_embedders_and_name_them(tmp_path: Path) -> None:
    """An accidental ensemble names both offending entries."""

    first, second = _registered_embedders()[:2]
    with pytest.raises(ValidationError) as raised:
        load_settings(_config_with_active(tmp_path, [first, second]))
    message = str(raised.value)
    assert "exactly one embedder" in message
    assert "2 are active" in message
    assert first in message and second in message


def test_lore_startup_surfaces_the_embedder_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LORE fails startup with the embedder's `hf download` remedy, not a guess.

    MEMNON connects to PostgreSQL before it builds its EmbeddingManager, so
    this stand-in keeps only that step: the real EmbeddingManager raises for
    the repository's active embedder pointed at a missing directory. The same
    construction against a real database is in
    tests/test_lore/test_runtime_config.py.
    """

    from nexus.agents.lore.lore import LORE
    from nexus.agents.memnon import memnon as memnon_module
    from nexus.agents.memnon.utils.embedding_manager import EmbeddingManager

    config = REPO_ROOT / "nexus.toml"
    settings = load_settings(config).memnon.model_dump(by_alias=True)
    (active,) = [
        name for name, model in settings["models"].items() if model["is_active"]
    ]
    missing = tmp_path / "not-installed"
    settings["models"][active]["local_path"] = str(missing)
    remedy = (
        f"hf download {settings['models'][active]['remote_path']} --local-dir {missing}"
    )

    def memnon_without_database(**_kwargs: Any) -> EmbeddingManager:
        return EmbeddingManager(settings=settings)

    monkeypatch.setattr(memnon_module, "MEMNON", memnon_without_database)

    with pytest.raises(RuntimeError) as raised:
        LORE(settings_path=str(config), enable_logon=False, dbname="save_05")

    message = str(raised.value)
    assert message.startswith("FATAL: MEMNON initialization failed:")
    assert remedy in message
    assert "Check database connection" not in message
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert remedy in str(raised.value.__cause__)
