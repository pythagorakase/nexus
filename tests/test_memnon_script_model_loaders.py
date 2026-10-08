"""Issue #812: operator scripts load embedders locally or fail loudly.

``scripts/import_narratives.py`` and ``scripts/query_narratives_vector.py``
fell back to ``SentenceTransformer(remote_path)`` (a Hugging Face download)
when a local folder was missing or failed to load, and
``scripts/regenerate_embeddings.py`` probed a Hub-cache snapshot and then
loaded the bare model name from the Hub. Each script now loads through the
shared local-only loader. These tests call every script's loader with a
nonexistent local path in a fresh interpreter with ``HF_HUB_OFFLINE=1`` and
``TRANSFORMERS_OFFLINE=1`` (read at import time), so any leak toward the
network fails loudly instead of downloading.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from tests.tiny_models import write_tiny_sentence_transformer

REPO_ROOT = Path(__file__).resolve().parents[1]

_PROBE = r"""
import importlib.util
import json
import sys
from pathlib import Path

script, call, missing, installed = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("probe_script", Path(script))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from nexus.agents.memnon.utils import embedding_manager as em


def entry(name, remote):
    return {"is_active": False, "local_path": missing, "remote_path": remote}


try:
    if call == "load_embedding_models":
        registry = {
            name: entry(name, f"example-org/{name}")
            for name in module.SCRIPT_EMBEDDERS
        }
        module.load_embedding_models(registry)
    elif call == "load_embedding_model":
        registry = {
            name: entry(name, f"example-org/{name}")
            for name in module.SCRIPT_EMBEDDERS
        }
        module.load_embedding_model(registry, "bge-large")
    elif call == "load_only_the_queried_model":
        # Only the queried entry is installed; the other registered embedders
        # point at missing folders and must not be loaded.
        registry = {
            name: entry(name, f"example-org/{name}")
            for name in module.SCRIPT_EMBEDDERS
        }
        registry["e5-large"]["local_path"] = installed
        model = module.load_embedding_model(registry, "e5-large")
        assert model.encode("needle hay").shape == (8,)
    elif call == "load_model":
        registry = {"probe-embedder": entry("probe-embedder", "example-org/probe")}
        module.ModelLoader.load_model("example-org/probe", registry)
    elif call == "load_unregistered":
        module.ModelLoader.load_model("example-org/unregistered", {})
    elif call == "all_models_none_active":
        # Every registered entry is inactive; --all-models has nothing to load.
        inactive = entry("probe-embedder", "example-org/probe")
        module.SETTINGS = {"models": {"probe-embedder": inactive}}
        module.regenerate_all_models(dry_run=True)
    outcome = {"type": None, "message": "", "cause": None}
except BaseException as exc:
    cause = exc.__cause__
    outcome = {
        "type": f"{type(exc).__module__}.{type(exc).__qualname__}",
        "message": str(exc),
        "cause": None if cause is None else type(cause).__qualname__,
    }
outcome["cached"] = len(em._MODEL_CACHE)
print(json.dumps(outcome))
"""


def _probe(
    script: str, call: str, tmp_path: Path, installed: Path | None = None
) -> Dict[str, Any]:
    """Call one script loader offline, from a scratch cwd, and report the error."""

    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    missing = tmp_path / "not-installed"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            str(REPO_ROOT / script),
            call,
            str(missing),
            str(installed or missing),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        # The scripts open their log files in the working directory.
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    outcome["missing"] = str(missing)
    return outcome


def _assert_missing_artifact(outcome: Dict[str, Any], name: str, repo: str) -> None:
    """The loader raised before any load, naming the folder and the restore."""

    missing = outcome["missing"]
    assert outcome["type"] == "builtins.RuntimeError", outcome
    assert outcome["message"] == (
        f"Embedding model '{name}' is not installed: local_path {missing} does "
        f"not exist. Restore it with `hf download {repo} --local-dir {missing}`, "
        "then run `nexus models verify`."
    )
    assert outcome["cause"] is None
    assert outcome["cached"] == 0


def test_import_narratives_loader_raises_for_a_missing_folder(tmp_path: Path) -> None:
    """import_narratives.py no longer downloads a missing embedder."""

    outcome = _probe("scripts/import_narratives.py", "load_embedding_models", tmp_path)

    _assert_missing_artifact(outcome, "bge-large", "example-org/bge-large")


def test_query_narratives_vector_loader_raises_for_a_missing_folder(
    tmp_path: Path,
) -> None:
    """query_narratives_vector.py no longer downloads a missing embedder."""

    outcome = _probe(
        "scripts/query_narratives_vector.py", "load_embedding_model", tmp_path
    )

    _assert_missing_artifact(outcome, "bge-large", "example-org/bge-large")


def test_query_narratives_vector_loads_only_the_queried_model(tmp_path: Path) -> None:
    """A query loads its one --model; other missing embedders do not block it."""

    installed = write_tiny_sentence_transformer(tmp_path / "installed")

    outcome = _probe(
        "scripts/query_narratives_vector.py",
        "load_only_the_queried_model",
        tmp_path,
        installed,
    )

    assert outcome["type"] is None, outcome
    assert outcome["cached"] == 1


def test_regenerate_embeddings_loader_raises_for_a_missing_folder(
    tmp_path: Path,
) -> None:
    """regenerate_embeddings.py resolves the registry entry, then fails locally."""

    outcome = _probe("scripts/regenerate_embeddings.py", "load_model", tmp_path)

    _assert_missing_artifact(outcome, "probe-embedder", "example-org/probe")


def test_regenerate_embeddings_refuses_an_unregistered_model(tmp_path: Path) -> None:
    """A model name with no registered entry is never tried on the Hub."""

    outcome = _probe("scripts/regenerate_embeddings.py", "load_unregistered", tmp_path)

    assert outcome["type"] == "builtins.RuntimeError", outcome
    assert outcome["message"].startswith(
        "Embedding model 'example-org/unregistered' is not registered in "
        "[memnon.models] or [ir_eval.embedding_candidates]"
    )
    assert outcome["cached"] == 0


def test_regenerate_all_models_refuses_a_registry_with_no_active_model(
    tmp_path: Path,
) -> None:
    """--all-models raises instead of defaulting to an unregistered Hub name."""

    outcome = _probe(
        "scripts/regenerate_embeddings.py", "all_models_none_active", tmp_path
    )

    assert outcome["type"] == "builtins.RuntimeError", outcome
    assert outcome["message"] == "No active model in [memnon.models]"
    assert outcome["cause"] is None
    assert outcome["cached"] == 0
