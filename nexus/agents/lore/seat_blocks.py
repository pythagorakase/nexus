"""Ordered storyteller context blocks; seat composition is a design contract."""

from types import MappingProxyType
from typing import Literal, Mapping, get_args

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
# The memory lanes the trimming pass drops from, in this order of unpacking:
# warm scenes, retrieved passages, and recalled scenes from either source.
TRIMMABLE_BLOCKS: tuple[BlockId, BlockId, BlockId] = (
    "recent narrative",
    "historical context",
    "recalled scenes",
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


# Shadow-only compile-time selection policy (#744): what each block is allowed
# to teach the seat. Roles are recorded beside attempt manifests and never alter
# rendering; they declare intent and do not claim semantic isolation.
InfluenceRole = Literal[
    # May teach diction: the prompt family and recent accepted prose.
    "voice_source",
    # The player's exact words.
    "player_language",
    # Facts the seat must honor, meant to arrive as terse evidence.
    "canonical_evidence",
    # Direction for what the seat should do or produce next.
    "authorial_plan",
]
# Attempt-manifest entries that surround the rendered seat blocks.
ManifestKind = Literal[
    "system",
    "finished writer output",
    "structured output retry",
    "request framing",
]
BLOCK_INFLUENCE_ROLES: Mapping[str, InfluenceRole] = MappingProxyType(
    {
        "system": "voice_source",
        "recent narrative": "voice_source",
        "user input": "player_language",
        "intertitle": "canonical_evidence",
        "scene conditions": "canonical_evidence",
        "private storyteller correspondence": "canonical_evidence",
        "entity dossier": "canonical_evidence",
        "historical context": "canonical_evidence",
        "recalled scenes": "canonical_evidence",
        "bootstrap context": "canonical_evidence",
        "scene roster": "canonical_evidence",
        "world knowledge": "canonical_evidence",
        "orrery tag library": "canonical_evidence",
        "recent orrery rulings": "canonical_evidence",
        # Gaia reconciles the writer's immutable pass as evidence of the turn.
        "finished writer output": "canonical_evidence",
        "orrery imminent activity": "authorial_plan",
        "orrery scene pressure": "authorial_plan",
        "orrery ambient scene seeds": "authorial_plan",
        "orrery joint beats": "authorial_plan",
        "orrery ambient peripherals": "authorial_plan",
        "author's note": "authorial_plan",
        "instructions": "authorial_plan",
        "writer closer": "authorial_plan",
        "gaia closer": "authorial_plan",
        "structured output retry": "authorial_plan",
        "request framing": "authorial_plan",
    }
)


def influence_role(kind: str) -> InfluenceRole:
    """Return a block's declared influence role; an undeclared kind is an error."""
    try:
        return BLOCK_INFLUENCE_ROLES[kind]
    except KeyError:
        raise ValueError(f"Block kind {kind!r} declares no influence role") from None


def influence_token_totals(block_tokens: Mapping[str, int]) -> dict[str, int]:
    """Sum measured block tokens per influence role, in role declaration order."""
    totals = dict.fromkeys(get_args(InfluenceRole), 0)
    for kind, tokens in block_tokens.items():
        totals[influence_role(kind)] += tokens
    return totals


def order_seat_blocks(
    sections: RenderedSections, seat: ContextSeat
) -> RenderedSections:
    """Apply the seat manifest while preserving exact chunk ownership for #903.

    A rendered block whose kind the seat's manifest does not list is a
    composition error, never something to drop quietly.
    """
    manifest = SEAT_BLOCKS[seat]
    foreign = sorted(set(sections.kinds) - set(manifest))
    if foreign:
        raise ValueError(f"Blocks rendered outside the {seat} manifest: {foreign}")
    ordered = RenderedSections()
    for block_id in manifest:
        ordered.kind = block_id
        for index, (kind, content) in enumerate(zip(sections.kinds, sections)):
            if kind == block_id:
                if index in sections.sources:
                    ordered.sources[len(ordered)] = sections.sources[index]
                ordered.append(content)
    return ordered
