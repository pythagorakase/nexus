#!/usr/bin/env python3
"""
Remove storyteller_chunk contamination from apex audition context packages.

This script removes the 'storyteller_chunk' field that was accidentally included
in context packages, which showed the AI the exact canonical answer it was
supposed to generate.
"""

import json
from pathlib import Path
from typing import List


def clean_package(package_path: Path) -> bool:
    """
    Remove storyteller_chunk from a context package.

    Args:
        package_path: Path to the context package JSON file

    Returns:
        True if storyteller_chunk was found and removed, False otherwise
    """
    with package_path.open("r", encoding="utf-8") as f:
        package = json.load(f)

    # Check if contamination exists
    had_contamination = "storyteller_chunk" in package

    if had_contamination:
        # Remove the contamination
        del package["storyteller_chunk"]

        # Save cleaned package
        with package_path.open("w", encoding="utf-8") as f:
            json.dump(package, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return had_contamination


def main() -> None:
    """Clean all context packages in the apex_audition directory."""
    packages_dir = Path(__file__).parent.parent / "context_packages" / "apex_audition"

    if not packages_dir.exists():
        print(f"Error: Directory not found: {packages_dir}")
        return

    # Find all JSON files
    package_files = sorted(packages_dir.glob("chunk_*.json"))

    if not package_files:
        print(f"No context packages found in {packages_dir}")
        return

    print(f"Found {len(package_files)} context packages")
    print(f"Scanning for contamination...\n")

    cleaned_count = 0
    clean_count = 0

    for package_path in package_files:
        was_contaminated = clean_package(package_path)

        if was_contaminated:
            print(f"✓ Cleaned: {package_path.name}")
            cleaned_count += 1
        else:
            print(f"  Already clean: {package_path.name}")
            clean_count += 1

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Cleaned: {cleaned_count}")
    print(f"  Already clean: {clean_count}")
    print(f"  Total: {len(package_files)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
