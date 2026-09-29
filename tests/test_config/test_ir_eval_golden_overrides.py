"""The checked-in IR-evaluation overrides name only settings the schema knows.

``ir_eval/ir_eval.py`` (the V1 evaluation CLI) merges the ``settings`` block of
``ir_eval/golden_queries.json`` into the control MEMNON settings with
``create_temp_settings_file``, and the settings models reject unknown keys.
PR #1010 retired ``hybrid_search.target_model`` and
``cross_encoder_reranking.use_8bit``, so the golden overrides must not carry
them. The CLI runs in a fresh interpreter because its module-level
``from scripts.auto_judge import AIJudge`` resolves against the repository's
own ``scripts`` package once the suite has imported it.

Two older failures on this path are not this test's subject, so it asserts
that the merge adds no field-level error instead of full validation: the
legacy ``.json`` loader never supplies the required
``[storyteller.correspondence]`` section (so the merged MEMNON section is
validated inside canonical ``nexus.toml``), and the golden ``models`` block
marks three ensemble-era embedders active against the model-level
single-active-embedder invariant.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nexus.config.settings_models import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_QUERIES = REPO_ROOT / "ir_eval" / "golden_queries.json"
_THIS_MODULE = ".".join(
    Path(__file__).resolve().relative_to(REPO_ROOT).with_suffix("").parts
)
_CHILD = (
    f"import sys; from {_THIS_MODULE} import _merge_golden_overrides; "
    "_merge_golden_overrides(sys.argv[1])"
)


def _merge_golden_overrides(control_path: str) -> None:
    """Print the settings file the CLI's default experiment would evaluate.

    ``IREvalPGCLI.__init__`` opens PostgreSQL connections, so the probe skips
    it; ``reload_settings`` only reads the control and golden-query files.
    """
    spec = importlib.util.spec_from_file_location(
        "ir_eval_cli", REPO_ROOT / "ir_eval" / "ir_eval.py"
    )
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    probe = object.__new__(cli.IREvalPGCLI)
    probe.settings_path = control_path
    probe.golden_queries_path = cli.DEFAULT_GOLDEN_QUERIES_PATH
    probe.reload_settings()
    print(cli.create_temp_settings_file(probe.settings, probe.experimental_settings))


def _contains(merged: Any, override: Any) -> bool:
    """Return whether every key and value of ``override`` appears in ``merged``."""
    if isinstance(override, dict):
        return isinstance(merged, dict) and all(
            key in merged and _contains(merged[key], value)
            for key, value in override.items()
        )
    return bool(merged == override)


def test_golden_query_overrides_merge_without_field_errors(tmp_path: Path) -> None:
    """The CLI's default experiment merges into MEMNON without an unknown key."""
    canonical = tomllib.loads((REPO_ROOT / "nexus.toml").read_text())
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"Agent Settings": {"MEMNON": canonical["memnon"]}}))

    result = subprocess.run(
        [sys.executable, "-c", _CHILD, str(control)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "TMPDIR": str(tmp_path), "PYTHONPATH": str(REPO_ROOT)},
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    produced = Path(result.stdout.strip().splitlines()[-1])
    assert produced.parent == tmp_path

    memnon = json.loads(produced.read_text())["Agent Settings"]["MEMNON"]
    golden = json.loads(GOLDEN_QUERIES.read_text())["settings"]
    assert _contains(memnon, {"retrieval": golden["retrieval"]})

    canonical["memnon"] = memnon
    try:
        Settings(**canonical)
    except ValidationError as exc:
        field_errors = [
            (error["loc"], error["type"]) for error in exc.errors() if error["loc"]
        ]
        assert field_errors == []
