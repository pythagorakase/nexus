"""Read-only replay of the #1007 target-ref boundary. No model calls.

Adapted from the QA night's ``contract_target_ref.py``. Run from the
repository root with ``PYTHONPATH=$PWD``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from pydantic import ValidationError

from nexus.agents.orrery.retrograde_expansion import validate_expansion_plan
from nexus.agents.orrery.retrograde_seed_candidates import (
    RetrogradeSeedCandidateValidationError,
    validate_seed_candidate_response,
)
from nexus.api.native_structured_output import structured_output_error_text

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests" / "test_orrery" / "test_retrograde_expansion.py"

spec = importlib.util.spec_from_file_location("qa_expansion_fixture", FIXTURE_PATH)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

import nexus  # noqa: E402

print(json.dumps({"nexus_module": nexus.__file__}))

v = m._expansion_test_vocabulary()
packet = m._packet(v)
seed = m._seed_response(v)
seed["candidates"][0]["project_intent"] = {
    "project_type": "court_patron",
    "target_ref": "character:Vale",
    "rationale": "The old debt can become patronage.",
}

# Step 1: the seed stage now rejects the kind-prefixed target.
try:
    validate_seed_candidate_response(
        payload=seed,
        seed_generation_request=packet["seed_generation_request"],
        vocabulary=v,
    )
except (ValidationError, RetrogradeSeedCandidateValidationError) as exc:
    print(
        json.dumps(
            {
                "step": 1,
                "candidate_target": "character:Vale",
                "rejected_by": type(exc).__name__,
                "error": structured_output_error_text(exc),
            }
        )
    )
else:
    raise AssertionError("character:Vale was accepted at the seed stage")

# Step 2: the bare/bare control still passes end to end.
seed["candidates"][0]["project_intent"]["target_ref"] = "Vale"
payload = m._valid_expansion(v)
payload["project_plan"] = [
    {
        "seed_id": "seed_001",
        "project_type": "court_patron",
        "actor_ref": "Mara",
        "target_ref": "Vale",
        "rationale": "Mara courts Vale backing.",
    }
]
ok = validate_expansion_plan(
    payload=payload, packet=packet, seed_candidate_response=seed
)
print(
    json.dumps(
        {
            "step": 2,
            "matching_name_control": "accepted",
            "target_ref": ok.project_plan[0].target_ref,
        }
    )
)

# Step 3: a genuinely different character is still rejected.
payload["project_plan"][0]["target_ref"] = "Orla"
try:
    validate_expansion_plan(
        payload=payload, packet=packet, seed_candidate_response=seed
    )
except ValueError as exc:
    message = str(exc)
    assert "changes target_ref" in message, message
    print(json.dumps({"step": 3, "different_target": "Orla", "error": message}))
else:
    raise AssertionError("A different target_ref was accepted")
