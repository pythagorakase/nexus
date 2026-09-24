"""Ordered storyteller context blocks; seat composition is a design contract."""

from types import MappingProxyType
from typing import Literal, Mapping

from nexus.telemetry.prompt_window import RenderedSections

ContextSeat = Literal["writer", "gaia", "single_pass", "bootstrap"]
BlockId = Literal[
    "intertitle",
    "scene conditions",
    "private storyteller correspondence",
    "entity dossier",
    "historical context",
    "recalled scenes",
    "recent narrative",
    "bootstrap context",
    "scene roster",
    "user input",
    "world knowledge",
    "orrery tag library",
    "recent orrery rulings",
    "orrery imminent activity",
    "orrery scene pressure",
    "orrery ambient scene seeds",
    "orrery joint beats",
    "orrery ambient peripherals",
    "author's note",
    "instructions",
    "writer closer",
    "gaia closer",
]

_SHARED_START: tuple[BlockId, ...] = (
    "intertitle",
    "scene conditions",
    "private storyteller correspondence",
    "entity dossier",
    "historical context",
    "recalled scenes",
    "recent narrative",
)
_CARDS: tuple[BlockId, ...] = (
    "recent orrery rulings",
    "orrery imminent activity",
    "orrery scene pressure",
    "orrery ambient scene seeds",
    "orrery joint beats",
    "orrery ambient peripherals",
    "author's note",
)
_LEGACY: tuple[BlockId, ...] = (
    *_SHARED_START,
    "bootstrap context",
    "scene roster",
    "user input",
    "world knowledge",
    "orrery tag library",
    *_CARDS,
    "instructions",
)
SEAT_BLOCKS: Mapping[ContextSeat, tuple[BlockId, ...]] = MappingProxyType(
    {
        "writer": (
            *_SHARED_START,
            "world knowledge",
            *_CARDS,
            "scene roster",
            "user input",
            "writer closer",
        ),
        "gaia": (
            *_SHARED_START,
            "world knowledge",
            "orrery tag library",
            *_CARDS,
            "user input",
            "gaia closer",
        ),
        "single_pass": _LEGACY,
        "bootstrap": _LEGACY,
    }
)


def order_seat_blocks(
    sections: RenderedSections, seat: ContextSeat
) -> RenderedSections:
    """Apply the seat manifest while preserving exact chunk ownership for #903."""
    known = {block for manifest in SEAT_BLOCKS.values() for block in manifest}
    unknown = set(sections.kinds) - known
    if unknown:
        raise ValueError(f"Unregistered storyteller context blocks: {sorted(unknown)}")
    ordered = RenderedSections()
    for block_id in SEAT_BLOCKS[seat]:
        ordered.kind = block_id
        for index, (kind, content) in enumerate(zip(sections.kinds, sections)):
            if kind == block_id:
                if index in sections.sources:
                    ordered.sources[len(ordered)] = sections.sources[index]
                ordered.append(content)
    return ordered
