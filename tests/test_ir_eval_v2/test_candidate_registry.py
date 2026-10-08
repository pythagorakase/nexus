"""Issue #812 (812-S4a): the runtime holds one embedder; candidates are offline.

``[memnon.models]`` declares exactly one runtime embedder. The offline
embedding candidates live in ``[ir_eval.embedding_candidates]`` and the
offline reranker candidates in ``[ir_eval.reranker_candidates]``; only an
ir_eval run selects them. Every config here is a ``tomlkit`` copy of the real
``nexus.toml`` under ``tmp_path``, loaded through ``load_settings``.
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest
import tomlkit
from pydantic import ValidationError

from ir_eval.engine.run_executor import RunExecutor
from ir_eval.engine.storage import EvaluationStore
from ir_eval.models.schemas import EvalModelConfig, EvalRunConfig
from nexus.config import load_settings, load_settings_as_dict
from nexus.database import database_url

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = "Octen-Embedding-4B"
EMBEDDING_CANDIDATES = {
    "bge-large",
    "e5-large",
    "bge-small-custom",
    "inf-retriever-v1-1.5b",
    "Octen-Embedding-0.6B",
    "Octen-Embedding-4B-INT8",
    "Octen-Embedding-8B",
    "Octen-Embedding-8B-INT8",
}
RERANKER_CANDIDATES = {"qwen3-reranker-0.6b", "qwen3-reranker-4b", "mxbai-rerank-large"}


def _config(tmp_path: Path, edit: Callable[[Any], None] | None = None) -> Path:
    """Write a tomlkit copy of the real nexus.toml, edited, under tmp_path."""

    document: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    if edit is not None:
        edit(document)
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(document))
    return path


def _raw() -> Dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "nexus.toml").read_text())


def test_committed_runtime_holds_one_embedder(tmp_path: Path) -> None:
    """One runtime embedder; the eight embedders and three rerankers moved."""

    path = _config(tmp_path)
    settings = load_settings(path)

    assert set(settings.memnon.models) == {PRODUCTION}
    assert settings.ir_eval is not None
    assert set(settings.ir_eval.embedding_candidates) == EMBEDDING_CANDIDATES
    assert set(settings.ir_eval.reranker_candidates) == RERANKER_CANDIDATES
    facade = load_settings_as_dict(path)["Agent Settings"]["MEMNON"]
    assert "candidates" not in facade["retrieval"]["cross_encoder_reranking"]


@pytest.mark.parametrize("is_active", (False, True))
def test_settings_reject_a_second_runtime_embedder(
    tmp_path: Path, is_active: bool
) -> None:
    """A second runtime entry fails at load, active or not."""

    def edit(document: Any) -> None:
        candidate = document["ir_eval"]["embedding_candidates"].pop(
            "Octen-Embedding-8B"
        )
        entry = tomlkit.table()
        entry["is_active"] = is_active
        for key, value in candidate.items():
            entry[key] = value
        entry["weight"] = 0.0
        document["memnon"]["models"]["Octen-Embedding-8B"] = entry

    with pytest.raises(ValidationError) as raised:
        load_settings(_config(tmp_path, edit))
    message = str(raised.value)
    assert "exactly one runtime embedder" in message
    assert PRODUCTION in message and "Octen-Embedding-8B" in message


def test_settings_reject_an_inactive_sole_embedder(tmp_path: Path) -> None:
    """The one runtime entry is the production embedder, so it is active."""

    def edit(document: Any) -> None:
        document["memnon"]["models"][PRODUCTION]["is_active"] = False

    with pytest.raises(ValidationError) as raised:
        load_settings(_config(tmp_path, edit))
    assert (
        f"[memnon.models].{PRODUCTION} must set is_active = true "
        "(the production embedder)."
    ) in str(raised.value)


@pytest.mark.parametrize(("key", "value"), (("is_active", True), ("weight", 0.5)))
def test_candidates_reject_runtime_switches(
    tmp_path: Path, key: str, value: Any
) -> None:
    """A candidate carries no is_active or weight; the run supplies both."""

    def edit(document: Any) -> None:
        document["ir_eval"]["embedding_candidates"]["bge-large"][key] = value

    with pytest.raises(ValidationError) as raised:
        load_settings(_config(tmp_path, edit))
    errors = [(error["loc"], error["type"]) for error in raised.value.errors()]
    assert errors == [
        (("ir_eval", "embedding_candidates", "bge-large", key), "extra_forbidden")
    ]


def _shadow_name(document: Any) -> None:
    production = document["memnon"]["models"][PRODUCTION]
    entry = tomlkit.table()
    entry["local_path"] = str(production["local_path"]) + "-copy"
    entry["dimensions"] = int(production["dimensions"])
    document["ir_eval"]["embedding_candidates"][PRODUCTION] = entry


def _shadow_embedder_path(document: Any) -> None:
    production = document["memnon"]["models"][PRODUCTION]
    # A trailing slash names the same directory.
    document["ir_eval"]["embedding_candidates"]["bge-large"]["local_path"] = (
        str(production["local_path"]) + "/"
    )


def _shadow_reranker_path(document: Any) -> None:
    reranking = document["memnon"]["retrieval"]["cross_encoder_reranking"]
    document["ir_eval"]["reranker_candidates"]["qwen3-reranker-0.6b"]["local_path"] = (
        str(reranking["model_path"])
    )


@pytest.mark.parametrize(
    ("edit", "expected"),
    (
        (
            _shadow_name,
            f"[ir_eval.embedding_candidates].{PRODUCTION} repeats the name of "
            "the production [memnon.models] entry",
        ),
        (
            _shadow_embedder_path,
            "[ir_eval.embedding_candidates].bge-large.local_path",
        ),
        (
            _shadow_reranker_path,
            "[ir_eval.reranker_candidates].qwen3-reranker-0.6b.local_path",
        ),
    ),
    ids=("embedder-name", "embedder-path", "reranker-path"),
)
def test_candidates_cannot_shadow_production(
    tmp_path: Path, edit: Callable[[Any], None], expected: str
) -> None:
    """A candidate never names or points at a production artifact."""

    with pytest.raises(ValidationError) as raised:
        load_settings(_config(tmp_path, edit))
    message = str(raised.value)
    assert expected in message
    if edit is _shadow_embedder_path:
        assert f"production [memnon.models].{PRODUCTION}.local_path" in message
    if edit is _shadow_reranker_path:
        assert (
            "production [memnon.retrieval.cross_encoder_reranking].model_path"
            in message
        )


def test_embedder_registry_unions_production_and_candidates(tmp_path: Path) -> None:
    """The offline scripts' registry is the production entry plus candidates."""

    registry = load_settings(_config(tmp_path)).embedder_registry()
    raw = _raw()

    assert set(registry) == {PRODUCTION} | EMBEDDING_CANDIDATES
    assert registry[PRODUCTION] == raw["memnon"]["models"][PRODUCTION]
    for name in EMBEDDING_CANDIDATES:
        assert registry[name] == raw["ir_eval"]["embedding_candidates"][name], name


def _executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunExecutor:
    """Build a RunExecutor on a real config copy; nothing connects."""

    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(_config(tmp_path)))
    url = database_url("qa640_812s4a_offline")
    return RunExecutor(EvaluationStore(url), db_url=url)


def _run_config(models: List[EvalModelConfig]) -> EvalRunConfig:
    return EvalRunConfig(name="812-s4a", embedding_models=models)


def test_run_settings_activate_exactly_the_selected_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every snapshot model runs at its normalized weight; extras are refused."""

    executor = _executor(tmp_path, monkeypatch)
    config = _run_config(
        [
            EvalModelConfig(model=PRODUCTION, weight=0.2),
            EvalModelConfig(model="Octen-Embedding-8B", weight=0.6),
        ]
    )
    snapshot = copy.deepcopy(executor.base_memnon_settings)
    snapshot["models"] = {
        model.model: executor._resolve_embedding_model(model.model)
        for model in config.embedding_models
    }

    run_settings, weights = executor._build_run_memnon_settings(
        config, base_settings=snapshot
    )

    models = run_settings["models"]
    assert set(models) == {PRODUCTION, "Octen-Embedding-8B"}
    assert all(model["is_active"] is True for model in models.values())
    assert models[PRODUCTION]["weight"] == pytest.approx(0.25)
    assert models["Octen-Embedding-8B"]["weight"] == pytest.approx(0.75)
    assert sum(model["weight"] for model in models.values()) == pytest.approx(1.0)
    assert weights == {
        PRODUCTION: pytest.approx(0.25),
        "Octen-Embedding-8B": pytest.approx(0.75),
    }

    extra = copy.deepcopy(snapshot)
    extra["models"]["bge-large"] = executor._resolve_embedding_model("bge-large")
    with pytest.raises(ValueError, match="differ from the selected models"):
        executor._build_run_memnon_settings(config, base_settings=extra)
