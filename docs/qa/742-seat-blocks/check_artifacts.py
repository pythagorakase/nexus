"""Check the archived frontier renders without rerunning retrieval or inference."""

import json
from pathlib import Path
import re

from nexus.prompts.registry import PromptId, load

OUTPUT = Path(__file__).parent
HEADERS = (
    "SCENE CONDITIONS",
    "ENTITY DOSSIER",
    "HISTORICAL CONTEXT",
    "RECALLED SCENES",
    "RECENT NARRATIVE",
    "WORLD KNOWLEDGE",
    "ORRERY TAG LIBRARY",
    "RECENT ORRERY RULINGS",
    "ORRERY IMMINENT ACTIVITY",
    "ORRERY SCENE PRESSURE",
    "ORRERY JOINT BEATS",
    "USER INPUT",
    "INSTRUCTIONS",
    "FINISHED WRITER NARRATIVE (VERBATIM)",
)


def blocks(text: str) -> dict[str, str]:
    """Split known renderer headings, ignoring only their joining whitespace."""
    text = re.sub(r"(?m)^PRESENT:.*$", "", text)
    pattern = r"(?m)^=== (" + "|".join(map(re.escape, HEADERS)) + r") ===$"
    parts = re.split(pattern, text)
    return {name: content.strip() for name, content in zip(parts[1::2], parts[2::2])}


def main() -> None:
    """Assert seat separation and unchanged common prose against both captures."""
    before = json.loads((OUTPUT / "before.json").read_text())
    after = json.loads((OUTPUT / "after.json").read_text())
    assert before["fingerprint"] == after["fingerprint"]
    instructions = {
        "ORRERY IMMINENT ACTIVITY": PromptId.TURN_BLOCKS_IMMINENT_ACTIVITY,
        "ORRERY SCENE PRESSURE": PromptId.TURN_BLOCKS_SCENE_PRESSURE,
        "ORRERY JOINT BEATS": PromptId.TURN_BLOCKS_JOINT_BEATS,
    }
    for seat in ("skald_writer", "gaia"):
        old_text = (OUTPUT / f"before-{seat}.txt").read_text()
        text = (OUTPUT / f"after-{seat}.txt").read_text()
        old, new = blocks(old_text), blocks(text)
        assert "INSTRUCTIONS" not in new
        assert (
            new["USER INPUT"]
            .removesuffix(
                load(
                    PromptId.WRITER_CLOSER
                    if seat == "skald_writer"
                    else PromptId.GAIA_CLOSER
                )
            )
            .strip()
            == old["USER INPUT"]
        )
        for name, content in old.items():
            if name in {"USER INPUT", "INSTRUCTIONS"}:
                continue
            if seat == "skald_writer":
                if name == "ORRERY TAG LIBRARY":
                    assert name not in new
                    continue
                if name in instructions:
                    paragraph = load(instructions[name])
                    assert paragraph not in text
                    content = content.replace(paragraph + "\n", "")
            assert new[name] == content, (seat, name)
        if seat == "skald_writer":
            assert text.endswith(load(PromptId.WRITER_CLOSER))
            assert re.findall(r"(?m)^PRESENT:.*$", text) == re.findall(
                r"(?m)^PRESENT:.*$", old_text
            )
            assert text.split("=== USER INPUT ===\n")[1] == (
                old["USER INPUT"] + "\n" + load(PromptId.WRITER_CLOSER)
            )
        else:
            assert all(load(prompt_id) in text for prompt_id in instructions.values())
    print(
        "ARTIFACT_PROOF_PASSED: writer suffix exact; common prose and card text unchanged; "
        "Gaia library/instructions retained; fingerprint unchanged"
    )


if __name__ == "__main__":
    main()
