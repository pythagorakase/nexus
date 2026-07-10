"""Deprecated migration shim for copying 1Password keys into NEXUS storage.

The settings-pane API KEYS card is the supported set and rotation path. This
personal migration shim remains only for owners with legacy 1Password entries;
1Password is not a NEXUS runtime or canonical-storage dependency.

Reads provider -> 1Password-reference mappings from ``nexus.toml``'s
``[secrets.providers]`` table. Each entry uses one of two schemes:

* ``op-item:<item-id>:<field-name>``  -> uses ``op item get``
* ``op-read:<secret-reference>``      -> uses ``op read``

Usage::

    python scripts/sync_secrets.py                    # sync all providers
    python scripts/sync_secrets.py --provider openai  # sync a single provider
    python scripts/sync_secrets.py --verify           # read back from secret store
    python scripts/sync_secrets.py --dry-run          # show what would happen
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

from nexus.util.secret_manager import get_secret, set_secret

NEXUS_ROOT = Path(__file__).resolve().parent.parent
NEXUS_TOML = NEXUS_ROOT / "nexus.toml"


def load_provider_refs() -> dict[str, str]:
    with NEXUS_TOML.open("rb") as fh:
        config = tomllib.load(fh)
    section = config.get("secrets", {}).get("providers")
    if not section:
        sys.exit(
            "ERROR: [secrets.providers] table missing from nexus.toml. "
            "Add provider -> 1Password reference mappings before running sync."
        )
    return section


def fetch_from_1password(reference: str, provider: str) -> str:
    if reference.startswith("op-item:"):
        rest = reference[len("op-item:") :]
        item_id, _, field = rest.partition(":")
        if not item_id or not field:
            sys.exit(
                f"ERROR: malformed op-item reference for '{provider}': "
                f"{reference!r}. Expected 'op-item:<item-id>:<field-name>'."
            )
        cmd = ["op", "item", "get", item_id, "--fields", field, "--reveal"]
    elif reference.startswith("op-read:"):
        ref = reference[len("op-read:") :]
        cmd = ["op", "read", ref]
    else:
        sys.exit(
            f"ERROR: unknown reference scheme for '{provider}': {reference!r}. "
            f"Use 'op-item:...' or 'op-read:...'."
        )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("ERROR: 1Password CLI (op) not found in PATH.")
    except subprocess.CalledProcessError as exc:
        sys.exit(
            f"ERROR: op invocation failed for '{provider}'. "
            f"If your CLI session has expired, run `op signin`.\n"
            f"stderr: {exc.stderr.strip()}"
        )

    key = result.stdout.strip()
    if not key:
        sys.exit(f"ERROR: empty key returned from 1Password for '{provider}'.")
    return key


def write_to_keychain(provider: str, key: str) -> None:
    """Deprecated compatibility wrapper around the canonical writer."""
    set_secret(provider, key)


def verify(provider: str) -> bool:
    """Print credential presence without key material. Return success."""
    try:
        get_secret(provider)
    except Exception as exc:  # noqa: BLE001 - diagnostic only
        print(f"  [FAIL] {provider}: {exc}")
        return False
    print(f"  [ OK ] {provider}: present")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="sync only this provider")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="read back from the secret store (does not call 1Password)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without invoking op or security",
    )
    args = parser.parse_args()

    refs = load_provider_refs()

    if args.provider and args.provider not in refs:
        sys.exit(
            f"ERROR: provider '{args.provider}' not in [secrets.providers]. "
            f"Known: {sorted(refs)}"
        )

    targets = {args.provider: refs[args.provider]} if args.provider else refs

    if args.verify:
        print("Verifying secret-store entries:")
        results = [verify(provider) for provider in targets]
        return 0 if all(results) else 1

    for provider, reference in targets.items():
        print(f"Syncing {provider} from the legacy migration source ...")
        if args.dry_run:
            print(f"  [dry-run] would invoke op + the secret writer for '{provider}'")
            continue
        key = fetch_from_1password(reference, provider)
        write_to_keychain(provider, key)
        print(f"  stored {provider} in the platform secret store")

    if args.dry_run:
        return 0

    print("\nVerifying:")
    results = [verify(provider) for provider in targets]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
