"""Time ``analyze_repository`` from a given reachability gate script (#1129).

The probe loads the gate script named on the command line, so one benchmark
times both the c7ae2988 copy and the branch's copy. It uses the standard
library only and imports nothing from ``tests/``.

Synthetic mode (no ``--repo``) builds, for each module count N, the nine files
of the ``static_repo`` fixture plus N trivial modules under ``pkg/`` and one
``pkg/importer.py`` with M external imports, then times only
``analyze_repository``. Repo mode (``--repo ROOT``) times ``analyze_repository``
on a checkout with its own ``config/reachability.toml``.

Run it as ``python -S scaling_benchmark.py <script> [options]``. It prints one
JSON object and exits 0.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import statistics
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

FIXTURE_SOURCES = {
    "pyproject.toml": '[project.scripts]\ndemo = "pkg.cli:main"\n',
    "nexus.toml": (
        "[runtime.services.gateway]\n"
        'command = ["{python}", "-m", "uvicorn", "pkg.api:app"]\n'
    ),
    "pytest.ini": "[pytest]\ntestpaths = tests\nnorecursedirs = archive\n",
    "pkg/__init__.py": 'raise RuntimeError("APPLICATION MUST NOT BE IMPORTED")\n',
    "pkg/cli.py": "def main():\n    from . import helper\n",
    "pkg/api.py": "app = object()\n",
    "pkg/helper.py": "value = 1\n",
    "scripts/migrate.py": (
        'SCRIPT_ONLY_MIGRATIONS = ["008"]\ndef load(path):\n    pass\n'
    ),
    "tests/test_example.py": "def test_example():\n    import pkg.helper\n",
}


def fixture_config() -> dict[str, Any]:
    """Return the ``static_repo`` fixture's reachability config."""
    return {
        "version": 1,
        "maintained": ["pkg/**/*.py", "scripts/**/*.py", "migrations/*.py"],
        "baseline": "baseline.json",
        "production": {
            "project_config": "pyproject.toml",
            "runtime_config": "nexus.toml",
        },
        "pytest": {"config": "pytest.ini"},
        "migrations": {
            "loader": "scripts/migrate.py:load",
            "pattern": "migrations/[0-9][0-9][0-9]_*.py",
            "symbol": "run",
            "script_only_versions": ["008"],
            "reason": "Registered migration loader",
        },
    }


def load_gate(script: Path) -> ModuleType:
    """Load a ``check_reachability.py`` copy from its file path."""
    spec = importlib.util.spec_from_file_location("qa1129_gate", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load a module spec from {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["qa1129_gate"] = module
    spec.loader.exec_module(module)
    return module


def write_tree(root: Path, modules: int, imports: int) -> None:
    """Write the fixture files, N trivial modules and one external importer."""
    sources = dict(FIXTURE_SOURCES)
    for index in range(modules):
        sources[f"pkg/mod_{index:05d}.py"] = "value = 0\n"
    sources["pkg/importer.py"] = (
        "".join(f"import qa1129_external_{index:05d}\n" for index in range(imports))
        + "def main():\n    pass\n"
    )
    for path, source in sources.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source)


def time_calls(call: Callable[[], Any], repeat: int) -> tuple[list[float], Any]:
    """Run ``call`` ``repeat`` times; return each wall time and the last result."""
    durations: list[float] = []
    result: Any = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = call()
        durations.append(time.perf_counter() - start)
    return durations, result


def summary(modules: int, durations: list[float]) -> dict[str, Any]:
    """Summarize one timing series."""
    return {
        "modules": modules,
        "median_s": statistics.median(durations),
        "min_s": min(durations),
        "max_s": max(durations),
    }


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the benchmark and print one JSON object."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path, help="Path to a check_reachability.py")
    parser.add_argument("--modules", default="250,500,1000,2000")
    parser.add_argument("--imports", type=int, default=2000)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--repo", type=Path, help="Time this checkout instead")
    args = parser.parse_args(argv)
    gate = load_gate(args.script)
    results: list[dict[str, Any]] = []
    if args.repo is not None:
        root = args.repo
        config = tomllib.loads((root / "config/reachability.toml").read_text())
        durations, report = time_calls(
            lambda: gate.analyze_repository(root, config), args.repeat
        )
        results.append(summary(len(report["maintained_modules"]), durations))
    else:
        for modules in (int(item) for item in args.modules.split(",")):
            with tempfile.TemporaryDirectory() as directory:
                tree = Path(directory)
                write_tree(tree, modules, args.imports)
                config = fixture_config()
                durations, _ = time_calls(
                    lambda: gate.analyze_repository(tree, config), args.repeat
                )
            results.append(summary(modules, durations))
    print(
        json.dumps(
            {
                "script": str(args.script),
                "python": platform.python_version(),
                "mode": "synthetic" if args.repo is None else "repo",
                "imports": args.imports,
                "repeat": args.repeat,
                "results": results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
