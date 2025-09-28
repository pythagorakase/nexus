#!/usr/bin/env python3
"""Regenerate every Apex audition context package using LORE."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from generate_apex_audition_contexts import ContextSeedBuilder, SCENES


LOGGER = logging.getLogger("apex_audition.batch")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    builder = ContextSeedBuilder(use_lore=True)

    total = len(SCENES)
    output_paths: list[Path] = []

    LOGGER.info("Regenerating %s audition packages with LORE inference", total)

    for index, config in enumerate(SCENES.values(), start=1):
        start = time.perf_counter()
        LOGGER.info("[%s/%s] Chunk %s (%s)", index, total, config.chunk_id, config.label)
        package = builder.build_scene_package(config)
        path = builder.save_package(package)
        output_paths.append(path)
        duration = time.perf_counter() - start
        LOGGER.info("Saved %s (%.1fs)", path, duration)

    LOGGER.info("Completed batch regeneration. %s packages updated:", len(output_paths))
    for path in output_paths:
        LOGGER.info("- %s", path)


if __name__ == "__main__":
    main()

