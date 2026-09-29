"""Issue #812: both rerankers load exactly their configured local folder.

``CrossEncoderReranker`` used to swap the configured path for a folder of the
same name inside the checkout whenever one existed, and loaded without
``local_files_only``, so ``nexus models verify`` could pass on the configured
folder while search loaded a different, unverified one. ``Qwen3LMReranker``
loaded without ``local_files_only`` at all. These tests save tiny, randomly
initialised BERT cross-encoders and Qwen3 causal LMs to disk and load them
through the real sentence-transformers and transformers paths. Nothing is
downloaded.
"""

from __future__ import annotations

import importlib.util
import inspect
import shutil
import tomllib
from pathlib import Path
from types import ModuleType
from typing import List, Tuple

import pytest
import torch
from sentence_transformers import CrossEncoder
from transformers.models.bert.configuration_bert import BertConfig
from transformers.models.bert.modeling_bert import BertForSequenceClassification
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast
from transformers.models.qwen3.configuration_qwen3 import Qwen3Config
from transformers.models.qwen3.modeling_qwen3 import Qwen3ForCausalLM

from nexus.agents.memnon.utils import cross_encoder
from nexus.agents.memnon.utils.artifact_manifest import (
    RERANKER_ROLE,
    production_artifact_specs,
)
from nexus.agents.memnon.utils.cross_encoder import (
    EIGHT_BIT_UNSUPPORTED,
    MODEL_PATH_SETTING,
    CrossEncoderReranker,
    Qwen3LMReranker,
    cross_encoder_kwargs,
    reranker_repo_id,
)
from nexus.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
# The production reranker folder name, so the decoys below sit exactly where a
# same-named folder inside the checkout would.
PRODUCTION_BASENAME = Path(
    tomllib.loads((REPO_ROOT / "nexus.toml").read_text())["memnon"]["retrieval"][
        "cross_encoder_reranking"
    ]["model_path"]
).name


def _write_cross_encoder(root: Path, hidden_size: int) -> Path:
    """Save a tiny randomly initialised BERT cross-encoder to ``root``."""

    root.mkdir(parents=True)
    vocab_file = root / "vocab.txt"
    vocab_file.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nneedle\nhay\n")
    BertTokenizerFast(vocab_file=str(vocab_file)).save_pretrained(root)
    torch.manual_seed(0)
    config = BertConfig(
        vocab_size=7,
        hidden_size=hidden_size,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=16,
        max_position_embeddings=32,
        num_labels=1,
    )
    BertForSequenceClassification(config).save_pretrained(root)
    return root


def _checkout_with_decoys(tmp_path: Path) -> Tuple[ModuleType, List[Path]]:
    """Run the real reranker source from a temporary checkout holding decoys.

    The removed lookup derived its folder from the module's own location, so
    the source is copied into a temporary checkout layout and imported from
    there. Loadable decoy reranker folders named like the production one sit in
    both ``models/`` and ``nexus/models/`` of that checkout; the real checkout's
    folders are never touched.
    """

    checkout = tmp_path / "checkout"
    source = checkout / "nexus" / "agents" / "memnon" / "utils" / "cross_encoder.py"
    source.parent.mkdir(parents=True)
    shutil.copyfile(cross_encoder.__file__, source)
    spec = importlib.util.spec_from_file_location("checkout_cross_encoder", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    decoys = [
        _write_cross_encoder(folder / PRODUCTION_BASENAME, hidden_size=4)
        for folder in (checkout / "models", checkout / "nexus" / "models")
    ]
    return module, decoys


def _loaded_from(reranker: CrossEncoderReranker) -> str:
    """The folder the underlying transformers model was read from."""

    return str(reranker.model.model.config._name_or_path)


def test_loads_the_configured_folder_not_a_same_named_checkout_folder(
    tmp_path: Path,
) -> None:
    """The folder nexus models verify checks is the folder that loads."""

    module, decoys = _checkout_with_decoys(tmp_path)
    configured = _write_cross_encoder(
        tmp_path / "artifacts" / PRODUCTION_BASENAME, hidden_size=8
    )

    reranker = module.CrossEncoderReranker(str(configured), device="cpu")

    assert _loaded_from(reranker) == str(configured)
    assert reranker.model.model.config.hidden_size == 8
    assert all(_loaded_from(reranker) != str(decoy) for decoy in decoys)
    scores = reranker.rerank_batch("needle", ["needle hay", "hay"], batch_size=2)
    assert len(scores) == 2 and all(0.0 <= score <= 1.0 for score in scores)


def test_missing_folder_raises_instead_of_loading_a_checkout_folder(
    tmp_path: Path,
) -> None:
    """A missing configured folder is an error even when a decoy would load."""

    module, _decoys = _checkout_with_decoys(tmp_path)
    missing = tmp_path / "artifacts" / PRODUCTION_BASENAME

    with pytest.raises(RuntimeError) as raised:
        module.CrossEncoderReranker(str(missing), device="cpu")

    assert str(raised.value) == (
        f"Cross-encoder reranker is not installed: {MODEL_PATH_SETTING} "
        f"{missing} does not exist. Point {MODEL_PATH_SETTING} at the "
        "downloaded reranker folder, then run `nexus models verify`."
    )
    assert raised.value.__cause__ is None
    assert not missing.exists()


def test_missing_folder_names_the_download_command_for_its_repository(
    tmp_path: Path,
) -> None:
    """With the repository known, the remedy is the exact hf download."""

    missing = tmp_path / "artifacts" / PRODUCTION_BASENAME
    repo = "example-org/probe-reranker"

    with pytest.raises(RuntimeError) as raised:
        CrossEncoderReranker(str(missing), device="cpu", repo_id=repo)

    message = str(raised.value)
    assert f"{MODEL_PATH_SETTING} {missing} does not exist" in message
    assert f"`hf download {repo} --local-dir {missing}`" in message
    assert message.endswith("then run `nexus models verify`.")
    assert raised.value.__cause__ is None


def test_configured_path_that_is_a_file_raises(tmp_path: Path) -> None:
    """A file where the reranker folder belongs is not handed to the loader."""

    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"\x00" * 16)

    with pytest.raises(RuntimeError, match="is not a directory") as raised:
        CrossEncoderReranker(str(weights), device="cpu")

    assert MODEL_PATH_SETTING in str(raised.value)
    assert "nexus models verify" in str(raised.value)
    assert raised.value.__cause__ is None


def test_half_copied_folder_raises_with_the_underlying_error(tmp_path: Path) -> None:
    """A folder missing its weights fails loudly, chained to the load error."""

    half_copied = _write_cross_encoder(tmp_path / "artifacts" / "reranker", 8)
    (half_copied / "model.safetensors").unlink()

    with pytest.raises(RuntimeError) as raised:
        CrossEncoderReranker(str(half_copied), device="cpu", repo_id="example/probe")

    message = str(raised.value)
    assert message.startswith(
        "Cross-encoder reranker failed to load from "
        f"{MODEL_PATH_SETTING} {half_copied}: "
    )
    assert f"`hf download example/probe --local-dir {half_copied}`" in message
    assert isinstance(raised.value.__cause__, OSError)


def test_repository_is_derived_like_the_artifact_lock() -> None:
    """MEMNON names the repository nexus models lock records for the reranker."""

    settings = load_settings(REPO_ROOT / "nexus.toml")
    (locked,) = [
        spec
        for spec in production_artifact_specs(settings)
        if spec.role == RERANKER_ROLE
    ]
    # MEMNON reads its settings as this dump (see MEMNON.__init__).
    reranking = settings.memnon.model_dump(by_alias=True)["retrieval"][
        "cross_encoder_reranking"
    ]

    derived = reranker_repo_id(reranking["model_path"], reranking["candidates"])

    assert derived is not None
    assert derived == locked.repo_id
    assert reranker_repo_id("/elsewhere/reranker", reranking["candidates"]) is None


def _write_qwen3_reranker(root: Path) -> Path:
    """Save a tiny randomly initialised Qwen3 causal LM and tokenizer."""

    root.mkdir(parents=True)
    vocab_file = root / "vocab.txt"
    vocab_file.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nyes\nno\nneedle\nhay\n")
    BertTokenizerFast(vocab_file=str(vocab_file)).save_pretrained(root)
    torch.manual_seed(0)
    config = Qwen3Config(
        vocab_size=9,
        hidden_size=8,
        intermediate_size=16,
        num_hidden_layers=1,
        num_attention_heads=1,
        num_key_value_heads=1,
        head_dim=8,
        max_position_embeddings=512,
    )
    Qwen3ForCausalLM(config).save_pretrained(root)
    return root


def test_qwen3_loads_its_local_folder_and_scores(tmp_path: Path) -> None:
    """A complete local Qwen3 folder loads offline and scores every passage."""

    folder = _write_qwen3_reranker(tmp_path / "artifacts" / "Qwen3-Reranker")

    reranker = Qwen3LMReranker(str(folder), device="cpu")

    assert reranker.model.config._name_or_path == str(folder)
    scores = reranker.rerank_batch("needle", ["needle hay", "hay"], batch_size=2)
    assert len(scores) == 2 and all(0.0 <= score <= 1.0 for score in scores)


def test_qwen3_missing_folder_names_the_download_command(tmp_path: Path) -> None:
    """A missing Qwen3 folder raises before any load, naming hf download."""

    missing = tmp_path / "artifacts" / "Qwen3-Reranker-0.6B"
    repo = "example-org/probe-qwen3-reranker"

    with pytest.raises(RuntimeError) as raised:
        Qwen3LMReranker(str(missing), device="cpu", repo_id=repo)

    assert str(raised.value) == (
        f"Qwen3 reranker is not installed: {MODEL_PATH_SETTING} {missing} does "
        f"not exist. Download it with `hf download {repo} --local-dir {missing}`, "
        "then run `nexus models verify`."
    )
    assert raised.value.__cause__ is None
    assert not missing.exists()


def test_qwen3_configured_path_that_is_a_file_raises(tmp_path: Path) -> None:
    """A file where the Qwen3 folder belongs is never handed to transformers."""

    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"\x00" * 16)

    with pytest.raises(RuntimeError, match="is not a directory") as raised:
        Qwen3LMReranker(str(weights), device="cpu")

    assert str(raised.value).startswith(
        f"Qwen3 reranker {MODEL_PATH_SETTING} {weights} is not a directory."
    )
    assert "nexus models verify" in str(raised.value)
    assert raised.value.__cause__ is None


def test_qwen3_half_copied_folder_raises_with_the_underlying_error(
    tmp_path: Path,
) -> None:
    """A Qwen3 folder missing its weights fails loudly, chained to the load."""

    half_copied = _write_qwen3_reranker(tmp_path / "artifacts" / "Qwen3-Reranker")
    (half_copied / "model.safetensors").unlink()

    with pytest.raises(RuntimeError) as raised:
        Qwen3LMReranker(str(half_copied), device="cpu", repo_id="example/probe")

    message = str(raised.value)
    assert message.startswith(
        f"Qwen3 reranker failed to load from {MODEL_PATH_SETTING} {half_copied}: "
    )
    assert f"`hf download example/probe --local-dir {half_copied}`" in message
    assert isinstance(raised.value.__cause__, OSError)


def test_qwen3_install_command_reaches_the_reranker_from_rerank_results(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The repository MEMNON derives reaches the Qwen3 remedy, not only CE's."""

    missing = tmp_path / "artifacts" / "Qwen3-Reranker-4B"
    results = [{"text": "needle", "score": 0.5}]

    with caplog.at_level("ERROR", logger="nexus.memnon.cross_encoder"):
        ranked = cross_encoder.rerank_results(
            query="needle",
            results=results,
            model_path=str(missing),
            api_type="qwen3_lm",
            device="cpu",
            repo_id="example-org/probe-qwen3",
        )

    # The reranker-failure policy (issue #812, still open) keeps the original
    # results; the logged error must still carry the exact install command.
    assert ranked == results
    assert f"`hf download example-org/probe-qwen3 --local-dir {missing}`" in (
        caplog.text
    )


def test_every_cross_encoder_keyword_is_accepted_by_the_installed_library() -> None:
    """The keywords every CrossEncoder load passes exist in the locked library.

    A real check against the installed sentence-transformers, not a mock: a
    keyword the library does not accept raises TypeError before anything
    loads, which is how the old 8-bit branch failed on every CUDA host.
    """

    accepted = inspect.signature(CrossEncoder.__init__).parameters
    passed = cross_encoder_kwargs("cpu", 512)

    assert passed["local_files_only"] is True
    assert set(passed) <= set(accepted), sorted(set(passed) - set(accepted))
    assert all(
        accepted[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for name in passed
    )


def test_eight_bit_refusal_matches_the_installed_libraries() -> None:
    """The 8-bit refusal rests on library source that is still installed.

    CrossEncoder moves every model it loads with ``.to(device)``, and
    transformers raises for ``.to`` on 8-bit bitsandbytes models. When an
    upgrade changes either line, this test fails and the 8-bit path can be
    rebuilt on the library's own keywords.
    """

    from transformers import PreTrainedModel

    cross_encoder_source = inspect.getsource(CrossEncoder.__init__)
    # PreTrainedModel.to is wrapped with functools.wraps(nn.Module.to); read
    # its own code object so getsource does not follow __wrapped__.
    to_source = inspect.getsource(PreTrainedModel.to.__code__)

    assert "automodel_args" in inspect.signature(CrossEncoder.__init__).parameters
    assert "self.model.to(device)" in cross_encoder_source
    assert 'getattr(self, "is_loaded_in_8bit", False)' in to_source
    assert "`.to` is not supported for `8-bit` bitsandbytes models" in to_source


def test_eight_bit_request_is_refused_before_loading(tmp_path: Path) -> None:
    """use_8bit raises the named refusal instead of falling back or crashing."""

    folder = _write_cross_encoder(tmp_path / "artifacts" / "reranker", 8)

    with pytest.raises(RuntimeError) as raised:
        CrossEncoderReranker(str(folder), device="cpu", use_8bit=True)

    assert str(raised.value) == EIGHT_BIT_UNSUPPORTED
    assert raised.value.__cause__ is None
