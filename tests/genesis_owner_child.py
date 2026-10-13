"""A genesis owner process that a 776-S1b PostgreSQL proof kills mid-run.

Run as ``python -m tests.genesis_owner_child <capture.json>`` with
``NEXUS_ROUTED_SLOT`` and ``NEXUS_ROUTED_SLOT_DATABASE`` naming the disposable
clone (``tests.pg_fixtures.routed_slot_environment``). The child routes the
slot before anything else, stages the fixture world, confirms both phases and
runs the transition route. Its derivation, packet and seed boundaries return
the real captured outputs; its expansion boundary sleeps, so the parent can
SIGKILL it while its run is still ``running`` with its expansion row open.

``capture_boundaries`` is shared with the parent tests, which replay the same
capture through the same boundary shapes.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from tests.pg_fixtures import connect, route_slot_from_environment

# Production call sites of the four provider boundaries a genesis run crosses.
BOUNDARY_TARGETS = {
    "derivation": "nexus.api.trait_input_derivation.ensure_trait_compile_inputs",
    "packet": "nexus.agents.orrery.retrograde_packet.build_retrograde_dry_run_packet",
    "seed_candidates": "nexus.agents.orrery.retrograde_seed_candidates.run_seed_stage",
    "expansion": (
        "nexus.agents.orrery.retrograde_expansion.generate_expansion_with_skald"
    ),
}
# How long the child's expansion boundary holds its run open; the parent
# kills the child long before this ends.
EXPANSION_HOLD_SECONDS = 600


def capture_boundaries(capture: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    """Return boundary replacements that answer with the captured outputs."""
    outputs = capture["outputs"]

    def derive(transition_data: Any, **_kwargs: Any) -> Any:
        from nexus.api.trait_compiler_schemas import TraitCompileInputs

        saved = outputs["derivation"]
        raw = saved["trait_compile_inputs"]
        transition_data.character.trait_compile_inputs = (
            None if raw is None else TraitCompileInputs.model_validate(raw)
        )
        return copy.deepcopy(saved["outcome"])

    def packet(**_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(outputs["packet"])

    def seed(**_kwargs: Any) -> dict[str, Any]:
        return {
            "model": capture["model"],
            "seed_candidate_response": copy.deepcopy(outputs["seed_candidates"]),
        }

    def expansion(**_kwargs: Any) -> dict[str, Any]:
        return {"retrograde_expansion_plan": copy.deepcopy(outputs["expansion"])}

    return {
        "derivation": derive,
        "packet": packet,
        "seed_candidates": seed,
        "expansion": expansion,
    }


def _install(target: str, replacement: Callable[..., Any]) -> None:
    module_name, attribute = target.rsplit(".", 1)
    module = __import__(module_name, fromlist=[attribute])
    setattr(module, attribute, replacement)


def main() -> None:
    """Stage, confirm and run the route; hold expansion until killed."""
    slot, dbname = route_slot_from_environment()
    capture = json.loads(Path(sys.argv[1]).read_text())

    from nexus.api.narrative_schemas import TransitionRequest
    from nexus.api.wizard_chat import transition_to_narrative_endpoint
    from tests.test_orrery.test_retrograde_wizard_live import stage_fixture_world

    stage_fixture_world(dbname)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.new_story_creator SET "
            "setting_confirmed = TRUE, character_confirmed = TRUE"
        )

    def hold(**_kwargs: Any) -> None:
        time.sleep(EXPANSION_HOLD_SECONDS)
        raise RuntimeError("genesis owner child was not killed")

    boundaries: dict[str, Callable[..., Any]] = {
        **capture_boundaries(capture),
        "expansion": hold,
    }
    for stage, target in BOUNDARY_TARGETS.items():
        _install(target, boundaries[stage])
    asyncio.run(transition_to_narrative_endpoint(TransitionRequest(slot=slot)))


if __name__ == "__main__":
    main()
