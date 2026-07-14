"""Pre-commit gate for configuration integrity.

Model-roster edits are routine and accelerating; this hook makes their
failure modes fail AT COMMIT TIME instead of at the next boot or on a
teammate's machine:

1. nexus.toml loads through the full Pydantic model — a removed model id
   with a dangling @provider.role reference (or any other registry
   violation) aborts the commit with the validator's message.
2. The dev-dashboard ship-off invariant: committed [orrery.dashboard]
   enabled must be false (no-auth gateway on 0.0.0.0). Local dashboard
   work uses NEXUS_DEV_DASHBOARD=1 instead of editing the file.
3. scripts/check_model_drift.py — literal model ids in source that no
   longer match the registry (and lack a "# pin: <reason>" comment).

pre-commit stashes unstaged changes before running hooks, so reading the
working tree here reads exactly what is being committed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []

    # The override must not mask what the committed file actually says.
    os.environ.pop("NEXUS_DEV_DASHBOARD", None)

    from nexus.config import load_settings

    try:
        load_settings(str(REPO_ROOT / "nexus.toml"))
    except Exception as exc:  # noqa: BLE001 — report, then block the commit
        failures.append(f"nexus.toml failed validation:\n{exc}")

    data = tomllib.loads((REPO_ROOT / "nexus.toml").read_text())
    if data["orrery"]["dashboard"]["enabled"] is not False:
        failures.append(
            "[orrery.dashboard] enabled must ship false (no-auth gateway on "
            "0.0.0.0). Unstage this change and use NEXUS_DEV_DASHBOARD=1 for "
            "local dashboard work."
        )

    drift = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_model_drift.py")],
        capture_output=True,
        text=True,
    )
    if drift.returncode != 0:
        failures.append(
            "Model-ID drift detected (add the id to the registry, route "
            "through @provider.role, or mark '# pin: <reason>'):\n"
            + drift.stdout.strip()
        )

    if failures:
        for failure in failures:
            print(f"\n✗ {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
