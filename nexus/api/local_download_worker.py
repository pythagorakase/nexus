"""Detached worker for downloading curated local-model GGUF files."""

from __future__ import annotations

import argparse
import sys

from huggingface_hub import hf_hub_download


def main() -> int:
    """Download each requested catalog file into its managed local directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--local-dir", required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    arguments = parser.parse_args()

    try:
        for filename in arguments.files:
            hf_hub_download(
                repo_id=arguments.repo_id,
                filename=filename,
                local_dir=arguments.local_dir,
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
