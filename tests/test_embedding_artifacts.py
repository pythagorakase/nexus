"""Issue #812: ``nexus models lock|verify`` over real artifact directories.

Each test builds synthetic embedder and reranker directories on disk (real
files, real hashes, real git checkouts), points a copy of the repository
nexus.toml at them, and drives the same entry point the CLI uses. Nothing is
downloaded.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import pytest
import tomlkit

from nexus.agents.memnon.utils.artifact_manifest import (
    EMBEDDER_ROLE,
    ArtifactLockError,
    ArtifactSpec,
    artifact_revision,
    lock_artifact,
    run_models_command,
)
from nexus.agents.memnon.utils.cross_encoder import (
    MODEL_PATH_SETTING,
    CrossEncoderReranker,
)
from nexus.agents.memnon.utils.embedding_manager import load_local_model
from nexus.config.loader import RUNTIME_CONFIG_ENV, settings_path_scope
from nexus.runtime.contract import HOME_ENV

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "0123456789abcdef0123456789abcdef01234567"


@dataclass(frozen=True)
class Production:
    """The repository's production embedder and reranker registry entries."""

    embedder: str
    embedder_repo: str
    dimensions: int
    reranker: str
    reranker_repo: str


def _production() -> Production:
    """Read the active embedder and production reranker from nexus.toml."""

    memnon = tomllib.loads((REPO_ROOT / "nexus.toml").read_text())["memnon"]
    (embedder,) = [n for n, m in memnon["models"].items() if m["is_active"]]
    reranking = memnon["retrieval"]["cross_encoder_reranking"]
    (reranker,) = [
        n
        for n, c in reranking["candidates"].items()
        if c["local_path"] == reranking["model_path"]
    ]
    return Production(
        embedder=embedder,
        embedder_repo=str(memnon["models"][embedder]["remote_path"]),
        dimensions=int(memnon["models"][embedder]["dimensions"]),
        reranker=reranker,
        reranker_repo=str(reranking["candidates"][reranker]["remote_path"]),
    )


PRODUCTION = _production()


def _write_files(root: Path, files: Dict[str, bytes]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _embedder_files(dimensions: int) -> Dict[str, bytes]:
    """A sentence-transformers layout declaring ``dimensions`` via Pooling."""

    modules = [
        {"idx": index, "name": str(index), "path": path, "type": module_type}
        for index, (path, module_type) in enumerate(
            (
                ("", "sentence_transformers.models.Transformer"),
                ("1_Pooling", "sentence_transformers.models.Pooling"),
                ("2_Normalize", "sentence_transformers.models.Normalize"),
            )
        )
    ]
    pooling = {
        "word_embedding_dimension": dimensions,
        "pooling_mode_cls_token": False,
        "pooling_mode_mean_tokens": False,
        "pooling_mode_lasttoken": True,
        "include_prompt": True,
    }
    return {
        "modules.json": json.dumps(modules).encode(),
        "1_Pooling/config.json": json.dumps(pooling).encode(),
        "config.json": json.dumps({"hidden_size": dimensions}).encode(),
        "README.md": b"---\nlicense: apache-2.0\ntags:\n- embeddings\n---\n# Card\n",
        "model.safetensors": bytes(range(256)) * 64,
    }


def _hf_local_dir_metadata(root: Path, files: Dict[str, bytes]) -> None:
    """Write what ``hf download --local-dir`` records beside each file."""

    for relative in files:
        metadata = root / ".cache/huggingface/download" / f"{relative}.metadata"
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(f"{COMMIT}\netag-{relative}\n1758000000.0\n")


@dataclass(frozen=True)
class Workspace:
    """Synthetic artifacts plus a config and lock path pointing at them."""

    embedder_dir: Path
    reranker_dir: Path
    config: Path
    lock: Path


def _write_config(
    tmp_path: Path,
    embedder_dir: Path,
    reranker_dir: Path,
    lock: Path,
    *,
    name: str,
    dimensions: Optional[int] = None,
) -> Path:
    document = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    memnon: Any = document["memnon"]
    embedder = memnon["models"][PRODUCTION.embedder]
    embedder["local_path"] = str(embedder_dir)
    if dimensions is not None:
        embedder["dimensions"] = dimensions
    reranking = memnon["retrieval"]["cross_encoder_reranking"]
    reranking["candidates"][PRODUCTION.reranker]["local_path"] = str(reranker_dir)
    reranking["model_path"] = str(reranker_dir)
    memnon["artifacts"]["lock_file"] = str(lock)
    path = tmp_path / f"{name}.toml"
    path.write_text(tomlkit.dumps(document))
    return path


def _workspace(tmp_path: Path) -> Workspace:
    embedder_dir = tmp_path / "models" / "embedder"
    embedder_files = _embedder_files(PRODUCTION.dimensions)
    _write_files(embedder_dir, embedder_files)
    _hf_local_dir_metadata(embedder_dir, embedder_files)
    (embedder_dir / ".DS_Store").write_bytes(b"\x00\x01")

    reranker_dir = tmp_path / "models" / "reranker"
    _write_files(
        reranker_dir,
        {
            "config.json": b'{"num_labels": 1}',
            "tokenizer.json": b'{"version": "1.0"}',
            "model.safetensors": bytes(reversed(range(256))) * 32,
        },
    )
    lock = tmp_path / "config" / "model_artifacts.lock.json"
    config = _write_config(tmp_path, embedder_dir, reranker_dir, lock, name="nexus")
    return Workspace(embedder_dir, reranker_dir, config, lock)


def _lock(workspace: Workspace) -> Dict[str, Any]:
    result = run_models_command("lock", str(workspace.config))
    assert result["success"] is True, result
    return json.loads(workspace.lock.read_text())


def _cli_verify(config: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    """Run ``nexus models verify`` in a subprocess, as a user would."""

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "nexus.cli",
            "models",
            "verify",
            "--config",
            str(config),
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        cwd=REPO_ROOT,
    )


def test_lock_records_artifacts_and_verify_passes(tmp_path: Path) -> None:
    """lock pins repository, revision, license, dimensions and every file."""

    workspace = _workspace(tmp_path)
    manifest = _lock(workspace)

    embedder, reranker = manifest["artifacts"]
    assert manifest["schema_version"] == 1
    assert embedder["role"] == "embedder"
    assert embedder["name"] == PRODUCTION.embedder
    assert embedder["repo_id"] == PRODUCTION.embedder_repo
    assert embedder["revision"] == COMMIT
    assert embedder["revision_source"] == "huggingface"
    assert embedder["license"] == "apache-2.0"
    assert embedder["dimensions"] == PRODUCTION.dimensions
    assert [entry["path"] for entry in embedder["files"]] == [
        "1_Pooling/config.json",
        "README.md",
        "config.json",
        "model.safetensors",
        "modules.json",
    ]
    weights = (workspace.embedder_dir / "model.safetensors").read_bytes()
    assert {
        "path": "model.safetensors",
        "size": len(weights),
        "sha256": hashlib.sha256(weights).hexdigest(),
    } in embedder["files"]
    assert embedder["total_size"] == sum(e["size"] for e in embedder["files"])

    assert reranker["role"] == "reranker"
    assert reranker["name"] == PRODUCTION.reranker
    assert reranker["repo_id"] == PRODUCTION.reranker_repo
    assert reranker["revision"] is None
    assert reranker["revision_source"] is None
    assert reranker["dimensions"] is None

    verified = run_models_command("verify", str(workspace.config))
    assert verified["success"] is True, verified

    # Deterministic: relocking unchanged artifacts rewrites identical bytes.
    before = workspace.lock.read_bytes()
    assert _lock(workspace) == manifest
    assert workspace.lock.read_bytes() == before


def test_verify_fails_after_one_byte_changes(tmp_path: Path) -> None:
    """A same-size edit is caught by the hash and the CLI exits nonzero."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    lock_bytes = workspace.lock.read_bytes()
    weights = workspace.embedder_dir / "model.safetensors"
    original = weights.read_bytes()
    weights.write_bytes(original[:100] + bytes([original[100] ^ 0x01]) + original[101:])

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert result["problems"] == [
        f"embedder '{PRODUCTION.embedder}': model.safetensors sha256 differs "
        "from the lock"
    ]
    assert (
        f"hf download {PRODUCTION.embedder_repo} --revision {COMMIT} "
        f"--local-dir {workspace.embedder_dir}"
    ) in result["error"]

    cli = _cli_verify(workspace.config)
    assert cli.returncode == 1, cli.stdout + cli.stderr
    assert "model.safetensors sha256 differs from the lock" in cli.stderr

    # verify is read-only: the lock is untouched and a restored file passes.
    assert workspace.lock.read_bytes() == lock_bytes
    weights.write_bytes(original)
    assert run_models_command("verify", str(workspace.config))["success"] is True


def test_verify_fails_after_a_file_is_deleted(tmp_path: Path) -> None:
    """A deleted reranker file is reported with the restore command."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    (workspace.reranker_dir / "tokenizer.json").unlink()

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert result["problems"] == [
        f"reranker '{PRODUCTION.reranker}': missing file tokenizer.json"
    ]
    assert (
        f"hf download {PRODUCTION.reranker_repo} --local-dir {workspace.reranker_dir}"
        in result["error"]
    )


def test_verify_reports_unexpected_files(tmp_path: Path) -> None:
    """An extra weights file could change what loads, so it fails verify."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    (workspace.embedder_dir / "pytorch_model.bin").write_bytes(b"\x00" * 8)

    result = run_models_command("verify", str(workspace.config))
    assert result["problems"] == [
        f"embedder '{PRODUCTION.embedder}': unexpected file pytorch_model.bin "
        "is not in the lock"
    ]


def test_verify_reports_dimension_drift_from_nexus_toml(tmp_path: Path) -> None:
    """Changing configured dimensions without relocking fails verify."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    drifted = _write_config(
        tmp_path,
        workspace.embedder_dir,
        workspace.reranker_dir,
        workspace.lock,
        name="drifted",
        dimensions=PRODUCTION.dimensions + 1,
    )

    result = run_models_command("verify", str(drifted))
    assert result["success"] is False
    assert result["problems"] == [
        f"embedder '{PRODUCTION.embedder}': nexus.toml dimensions "
        f"{PRODUCTION.dimensions + 1} differs from the locked {PRODUCTION.dimensions}"
    ]
    assert "re-run `nexus models lock`" in result["error"]


def test_verify_without_a_lock_names_the_lock_command(tmp_path: Path) -> None:
    """No lock yet is a failure with the command that creates one."""

    workspace = _workspace(tmp_path)
    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert f"No model artifact lock at {workspace.lock}" in result["error"]
    assert "nexus models lock" in result["error"]


def test_verify_rejects_a_malformed_lock_with_the_relock_command(
    tmp_path: Path,
) -> None:
    """A current-schema lock missing its file lists fails with the remedy."""

    workspace = _workspace(tmp_path)
    manifest = _lock(workspace)
    for entry in manifest["artifacts"]:
        del entry["files"]
    workspace.lock.write_text(json.dumps(manifest))

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert f"{workspace.lock} is malformed" in result["error"]
    assert "Re-run `nexus models lock`" in result["error"]


def _truncate(text: str) -> str:
    """Cut a lock off mid-file, as an interrupted write or copy leaves it."""

    return text[: len(text) // 2]


def _conflict(text: str) -> str:
    """Wrap a lock in the markers an unresolved git merge leaves behind."""

    theirs = text.replace('"schema_version": 1', '"schema_version": 1 ')
    return f"<<<<<<< HEAD\n{text}=======\n{theirs}>>>>>>> main\n"


@pytest.mark.parametrize(
    ("damage", "position"),
    [(_truncate, "line "), (_conflict, ": line 1 column 1 (char 0). ")],
    ids=["truncated", "merge-conflict"],
)
def test_verify_reports_an_unparseable_lock_with_the_relock_command(
    tmp_path: Path, damage: Callable[[str], str], position: str
) -> None:
    """A lock that is not JSON fails verify cleanly, in text and --json output."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    workspace.lock.write_text(damage(workspace.lock.read_text()))

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    message = result["error"]
    assert message.startswith(f"{workspace.lock} is not valid JSON: ")
    assert position in message
    assert message.endswith(
        "It may be truncated or hold merge-conflict markers. "
        "Re-run `nexus models lock`."
    )

    cli = _cli_verify(workspace.config)
    assert cli.returncode == 1, cli.stdout + cli.stderr
    assert cli.stderr.strip() == f"Error: {message}"

    as_json = _cli_verify(workspace.config, "--json")
    assert as_json.returncode == 1, as_json.stdout + as_json.stderr
    assert json.loads(as_json.stderr) == {
        "ok": False,
        "code": "domain_failure",
        "error": message,
        "partial": {},
    }


def test_verify_rejects_a_lock_that_is_not_an_object(tmp_path: Path) -> None:
    """Valid JSON with a non-object top level is a malformed lock, not a crash."""

    workspace = _workspace(tmp_path)
    workspace.lock.parent.mkdir(parents=True)
    workspace.lock.write_text("[]\n")

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert result["error"] == (
        f"{workspace.lock} does not hold a JSON object at its top level. "
        "Re-run `nexus models lock`."
    )


def test_default_config_follows_the_load_settings_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --config, a settings scope and then NEXUS_RUNTIME_CONFIG apply."""

    workspace = _workspace(tmp_path)
    _lock(workspace)
    elsewhere = tmp_path / "elsewhere" / "model_artifacts.lock.json"
    other = _write_config(
        tmp_path,
        workspace.embedder_dir,
        workspace.reranker_dir,
        elsewhere,
        name="other",
    )

    with settings_path_scope(workspace.config):
        scoped = run_models_command("verify", None)
        explicit = run_models_command("verify", str(other))
    assert scoped["success"] is True, scoped
    assert scoped["lock_file"] == str(workspace.lock)
    # --config still wins over an active scope.
    assert explicit["success"] is False
    assert f"No model artifact lock at {elsewhere}" in explicit["error"]

    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(workspace.config))
    from_env = run_models_command("verify", None)
    assert from_env["success"] is True, from_env
    assert from_env["lock_file"] == str(workspace.lock)


def test_verify_without_a_config_to_find_names_the_fix(tmp_path: Path) -> None:
    """No nexus.toml to find is a clean CLI error, still JSON under --json.

    The working directory no longer selects a config (#820), so the missing
    case is a runtime home without its nexus.toml.
    """

    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    env = {key: value for key, value in os.environ.items() if key != RUNTIME_CONFIG_ENV}
    cli = subprocess.run(
        [sys.executable, "-m", "nexus.cli", "models", "verify", "--json"],
        capture_output=True,
        text=True,
        timeout=300,
        env={**env, "PYTHONPATH": str(REPO_ROOT), HOME_ENV: str(empty_home)},
        cwd=tmp_path,
    )
    assert cli.returncode == 1, cli.stdout + cli.stderr
    assert json.loads(cli.stderr) == {
        "ok": False,
        "code": "config_error",
        "error": "Configuration file not found: "
        f"{empty_home.resolve() / 'nexus.toml'}. Pass --config with the path to "
        f"nexus.toml, set {HOME_ENV} to a home containing nexus.toml, or set "
        f"{RUNTIME_CONFIG_ENV} to an existing nexus.toml.",
        "partial": {},
    }


def test_lock_refuses_artifact_whose_dimension_disagrees(tmp_path: Path) -> None:
    """The artifact's declared output dimension must match nexus.toml."""

    workspace = _workspace(tmp_path)
    mismatched = _write_config(
        tmp_path,
        workspace.embedder_dir,
        workspace.reranker_dir,
        workspace.lock,
        name="mismatched",
        dimensions=PRODUCTION.dimensions * 2,
    )

    result = run_models_command("lock", str(mismatched))
    assert result["success"] is False
    assert f"produces {PRODUCTION.dimensions}-dimensional vectors" in result["error"]
    assert not workspace.lock.exists()


def test_lock_refuses_missing_artifact_directory(tmp_path: Path) -> None:
    """lock never downloads: a missing directory fails with the restore step."""

    workspace = _workspace(tmp_path)
    absent = tmp_path / "models" / "absent"
    config = _write_config(
        tmp_path, absent, workspace.reranker_dir, workspace.lock, name="absent"
    )

    result = run_models_command("lock", str(config))
    assert result["success"] is False
    assert f"artifact directory {absent} does not exist" in result["error"]
    assert "then re-run `nexus models lock`" in result["error"]
    assert not absent.exists()


def test_lock_reads_revision_from_hub_cache_snapshot(tmp_path: Path) -> None:
    """A Hub cache snapshot directory is named by the commit it holds."""

    snapshot = tmp_path / "models--example--embedder" / "snapshots" / COMMIT
    _write_files(snapshot, _embedder_files(16))

    entry = lock_artifact(
        ArtifactSpec(
            role=EMBEDDER_ROLE,
            name="snapshot-embedder",
            repo_id="example/embedder",
            local_path=snapshot,
            dimensions=16,
        )
    )
    assert entry["revision"] == COMMIT
    assert entry["revision_source"] == "huggingface"
    assert entry["dimensions"] == 16


def _git(*args: str, cwd: Path) -> str:
    """Run git in ``cwd``, isolated from the user's config and any hook's GIT_*."""

    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=NEXUS test",
            "-c",
            "user.email=test@nexus.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit_checkout(root: Path, *, git_dir: Optional[Path] = None) -> str:
    """Make ``root`` a git checkout holding its files in one commit; return HEAD.

    With ``git_dir`` the repository lives there and ``root/.git`` is a gitfile,
    as ``git init --separate-git-dir``, submodules and worktrees leave it.
    """

    separate = [f"--separate-git-dir={git_dir}"] if git_dir else []
    _git("init", "-q", *separate, cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "--no-verify", "-m", "artifact", cwd=root)
    return _git("rev-parse", "HEAD", cwd=root)


def _checkout_workspace(tmp_path: Path) -> Tuple[Workspace, str]:
    """A workspace with a git-checkout embedder and an hf-downloaded reranker.

    The reranker carries ``hf download --local-dir`` metadata at ``COMMIT``.

    Returns:
        The workspace and the embedder checkout's HEAD commit.
    """

    workspace = _workspace(tmp_path)
    shutil.rmtree(workspace.embedder_dir / ".cache")
    head = _commit_checkout(workspace.embedder_dir)
    _hf_local_dir_metadata(
        workspace.reranker_dir,
        {path.name: b"" for path in workspace.reranker_dir.iterdir()},
    )
    return workspace, head


@pytest.mark.parametrize("separate", [False, True], ids=["git-directory", "gitfile"])
def test_lock_reads_revision_from_a_git_checkout(
    tmp_path: Path, separate: bool
) -> None:
    """A git checkout's HEAD is the revision; its .git is not an artifact file."""

    root = tmp_path / "Octen-Embedding-probe"
    files = _embedder_files(16)
    _write_files(root, files)
    head = _commit_checkout(root, git_dir=tmp_path / "store.git" if separate else None)
    assert (root / ".git").is_file() is separate

    entry = lock_artifact(
        ArtifactSpec(
            role=EMBEDDER_ROLE,
            name="checkout-embedder",
            repo_id="example/embedder",
            local_path=root,
            dimensions=16,
        )
    )
    assert entry["revision"] == head
    assert entry["revision_source"] == "git"
    assert [file["path"] for file in entry["files"]] == sorted(files)


def test_git_revision_never_comes_from_an_enclosing_repository(
    tmp_path: Path,
) -> None:
    """A folder without its own valid .git never reports its parent's HEAD.

    Model folders live inside this checkout (``models/``), so git's upward
    repository discovery would otherwise name the checkout's commit.
    """

    _write_files(tmp_path, {"nexus.toml": b"[memnon]\n"})
    outer_head = _commit_checkout(tmp_path)
    plain = tmp_path / "models" / "plain"
    _write_files(plain, _embedder_files(16))
    assert artifact_revision(plain) == (None, None)

    broken = tmp_path / "models" / "broken"
    _write_files(broken, _embedder_files(16))
    (broken / ".git").mkdir()
    with pytest.raises(ArtifactLockError) as raised:
        artifact_revision(broken)
    assert "not a git repository" in str(raised.value)
    assert outer_head not in str(raised.value)


def test_verify_reports_a_moved_checkout_with_the_pinned_restore(
    tmp_path: Path,
) -> None:
    """verify compares the checkout's HEAD with the lock and pins the restore."""

    workspace, head = _checkout_workspace(tmp_path)
    manifest = _lock(workspace)
    embedder, reranker = manifest["artifacts"]
    assert (embedder["revision"], embedder["revision_source"]) == (head, "git")
    assert (reranker["revision"], reranker["revision_source"]) == (
        COMMIT,
        "huggingface",
    )
    assert run_models_command("verify", str(workspace.config))["success"] is True

    _git(
        "commit",
        "-q",
        "--no-verify",
        "--allow-empty",
        "-m",
        "moved",
        cwd=workspace.embedder_dir,
    )
    moved = _git("rev-parse", "HEAD", cwd=workspace.embedder_dir)

    result = run_models_command("verify", str(workspace.config))
    assert result["success"] is False
    assert result["problems"] == [
        f"embedder '{PRODUCTION.embedder}': git revision {moved!r} differs from "
        f"the locked {head!r}"
    ]
    assert (
        f"hf download {PRODUCTION.embedder_repo} --revision {head} "
        f"--local-dir {workspace.embedder_dir}"
    ) in result["error"]


def test_lock_of_a_missing_directory_names_the_locked_revision(
    tmp_path: Path,
) -> None:
    """lock pins the restore of a missing folder to the lock it replaces."""

    workspace, head = _checkout_workspace(tmp_path)
    _lock(workspace)
    absent = tmp_path / "models" / "absent"
    config = _write_config(
        tmp_path, absent, workspace.reranker_dir, workspace.lock, name="absent"
    )

    result = run_models_command("lock", str(config))
    assert result["success"] is False
    assert (
        f"`hf download {PRODUCTION.embedder_repo} --revision {head} "
        f"--local-dir {absent}`, then re-run `nexus models lock`."
    ) in result["error"]


def test_loader_remedies_pin_the_locked_revision(tmp_path: Path) -> None:
    """A missing embedder or reranker names hf download at the lock's revision."""

    workspace, head = _checkout_workspace(tmp_path)
    _lock(workspace)
    embedder = tmp_path / "restored" / "embedder"
    reranker = tmp_path / "restored" / "reranker"

    with settings_path_scope(workspace.config):
        with pytest.raises(RuntimeError) as missing_embedder:
            load_local_model(
                PRODUCTION.embedder,
                {"local_path": str(embedder), "remote_path": PRODUCTION.embedder_repo},
            )
        with pytest.raises(RuntimeError) as missing_reranker:
            CrossEncoderReranker(
                str(reranker), device="cpu", repo_id=PRODUCTION.reranker_repo
            )

    assert str(missing_embedder.value) == (
        f"Embedding model '{PRODUCTION.embedder}' is not installed: local_path "
        f"{embedder} does not exist. Restore it with `hf download "
        f"{PRODUCTION.embedder_repo} --revision {head} --local-dir {embedder}`, "
        "then run `nexus models verify`."
    )
    assert str(missing_reranker.value) == (
        f"Cross-encoder reranker is not installed: {MODEL_PATH_SETTING} "
        f"{reranker} does not exist. Download it with `hf download "
        f"{PRODUCTION.reranker_repo} --revision {COMMIT} --local-dir {reranker}`, "
        "then run `nexus models verify`."
    )


def test_loader_remedy_pins_the_folder_revision_when_the_lock_has_none(
    tmp_path: Path,
) -> None:
    """A half-copied git checkout names hf download at its own HEAD."""

    workspace = _workspace(tmp_path)
    assert not workspace.lock.exists()
    half_copied = tmp_path / "models" / "half-copied"
    _write_files(half_copied, {"README.md": b"# Card\n"})
    head = _commit_checkout(half_copied)

    with settings_path_scope(workspace.config):
        with pytest.raises(RuntimeError) as raised:
            load_local_model(
                "probe-embedder",
                {"local_path": str(half_copied), "remote_path": "example-org/probe"},
            )

    message = str(raised.value)
    assert message.startswith(
        f"Embedding model 'probe-embedder' failed to load from local_path "
        f"{half_copied}: "
    )
    assert message.endswith(
        f"Restore it with `hf download example-org/probe --revision {head} "
        f"--local-dir {half_copied}`, then run `nexus models verify`."
    )
    assert raised.value.__cause__ is not None
