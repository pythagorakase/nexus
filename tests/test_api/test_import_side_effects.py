"""Regression tests for side-effect-free API imports (issue #369).

Importing ``nexus.api`` helper/schema modules — or the Orrery worker — must
not construct the Storyteller app, instantiate ChunkWorkflow, open a Postgres
pool, or run schema validation. Each test runs in a fresh subprocess pointed
at an unreachable Postgres port, so any import-time connection attempt fails
loudly (connection refused) instead of passing against a live local server.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Point libpq at a port nothing listens on. Any import-time connection
# attempt raises OperationalError immediately, failing the subprocess.
_UNREACHABLE_DB_ENV = {
    "PGHOST": "127.0.0.1",
    "PGPORT": "1",
    "PGCONNECT_TIMEOUT": "1",
    "NEXUS_SLOT": "1",
}

_FORBIDDEN_ML_IMPORT_MODULES = {
    "sentence_transformers",
    "torch",
    "transformers",
}

_FORBIDDEN_APP_IMPORT_MODULES = {
    *_FORBIDDEN_ML_IMPORT_MODULES,
    "nexus.agents.memnon.memnon",
}

_FORBIDDEN_AGENT_UTILITY_IMPORT_MODULES = {
    *_FORBIDDEN_ML_IMPORT_MODULES,
    "nexus.agents.lore.lore",
    "nexus.agents.memnon.memnon",
}


def _run_fresh_import(code: str) -> "subprocess.CompletedProcess[str]":
    env = {**os.environ, **_UNREACHABLE_DB_ENV}
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=REPO_ROOT,
    )


def _assert_clean(result: "subprocess.CompletedProcess[str]") -> None:
    assert result.returncode == 0, (
        f"import touched the database or failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.strip().endswith("OK")


def test_api_helper_imports_do_not_touch_postgres() -> None:
    """Helper/schema imports must not create a connection pool."""
    code = (
        "import nexus.api\n"
        "import nexus.api.choice_handling\n"
        "import nexus.api.new_story_schemas\n"
        "import nexus.api.chunk_workflow\n"
        "from nexus.api import db_pool\n"
        "assert db_pool._pools == {}, db_pool._pools\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))


def test_storyteller_app_export_does_not_touch_postgres() -> None:
    """Resolving nexus.api.app builds the FastAPI app without a database."""
    code = (
        "from nexus.api import app\n"
        "from nexus.api import db_pool\n"
        "assert app.title is not None\n"
        "assert db_pool._pools == {}, db_pool._pools\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))


def test_storyteller_app_export_does_not_import_ml_stack() -> None:
    """Resolving nexus.api.app must not import LORE's MEMNON/ML dependencies."""
    module_list = repr(sorted(_FORBIDDEN_APP_IMPORT_MODULES))
    code = (
        "import sys\n"
        "from nexus.api import app\n"
        f"forbidden = {module_list}\n"
        "loaded = [module for module in forbidden if module in sys.modules]\n"
        "assert app.title is not None\n"
        "assert loaded == [], loaded\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))


def test_orrery_worker_import_does_not_touch_postgres() -> None:
    """The Orrery worker module must not connect to any slot at import."""
    code = (
        "import nexus.agents.orrery.worker\n"
        "import nexus.agents.orrery.retrograde_embedding\n"
        "from nexus.api import db_pool\n"
        "assert db_pool._pools == {}, db_pool._pools\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))


def test_agent_utility_imports_do_not_import_agent_or_ml_stack() -> None:
    """Utility imports must not load LORE, MEMNON, or ML dependencies."""
    for target in [
        "nexus.agents.lore.utils.chunk_operations",
        "nexus.agents.memnon.utils.db_access",
        "nexus.agents.memnon.utils.embedding_tables",
        "nexus.agents.memnon.utils.query_analysis",
    ]:
        module_list = repr(sorted(_FORBIDDEN_AGENT_UTILITY_IMPORT_MODULES))
        code = (
            "import importlib\n"
            "import sys\n"
            f"target = {target!r}\n"
            f"forbidden = {module_list}\n"
            "importlib.import_module(target)\n"
            "loaded = [module for module in forbidden if module in sys.modules]\n"
            "assert loaded == [], {target: loaded}\n"
            "print('OK')\n"
        )
        _assert_clean(_run_fresh_import(code))


def test_agent_package_level_imports_still_work() -> None:
    """Lazy package exports must preserve the documented compatibility imports."""
    code = (
        "from nexus.agents.lore import LORE, TurnPhase\n"
        "from nexus.agents.memnon import MEMNON\n"
        "assert LORE.__name__ == 'LORE'\n"
        "assert TurnPhase.IDLE.value == 'idle'\n"
        "assert MEMNON.__name__ == 'MEMNON'\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))


def test_agent_package_dir_exports_are_unique_after_lazy_load() -> None:
    """Lazy export caching must not duplicate package names in dir()."""
    code = (
        "import importlib\n"
        "packages = {\n"
        "    'nexus.agents.lore': ('LORE', 'TurnPhase'),\n"
        "    'nexus.agents.memnon': ('MEMNON',),\n"
        "}\n"
        "for package_name, exports in packages.items():\n"
        "    package = importlib.import_module(package_name)\n"
        "    for export in exports:\n"
        "        getattr(package, export)\n"
        "    names = dir(package)\n"
        "    duplicates = [name for name in exports if names.count(name) != 1]\n"
        "    assert duplicates == [], {package_name: duplicates}\n"
        "print('OK')\n"
    )
    _assert_clean(_run_fresh_import(code))
