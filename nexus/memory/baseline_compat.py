"""Field-by-field compatibility contract for durable Pass-2 baselines.

A Pass-2 baseline records what an accepted turn's context held (memory
identities and token accounting) plus fingerprints of the settings that
produced it. Every leaf of the fingerprinted settings, the ``[memory]`` and
``[lore.token_budget]`` tables, carries one explicit compatibility class:

``budget``
    Sizing inputs the next turn recomputes from live settings. A change to
    only these rebases a schema-2 baseline: its memory identities and prior
    accounting are kept, and the live turn re-derives the remaining budget
    capped by the new Phase-2 budget.
``semantic``
    Values that change what a baseline means: retrieval selection and
    behavior, and the Pass-1 reserve recorded in the accounting. A change
    fails loudly until an operator explicitly accepts it.

A settings field without a class fails at import, so a new field can never
silently become rebasable. ``docs/settings_scopes.md`` documents the matrix.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, List, Literal, Mapping, Tuple, Type, get_args

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from nexus.config.settings_models import MemorySettings, TokenBudgetConfig

CompatibilityClass = Literal["budget", "semantic"]
COMPATIBILITY_CLASSES: Tuple[CompatibilityClass, ...] = ("budget", "semantic")

# Dotted settings prefix -> (key in the legacy fingerprint payload, model).
FINGERPRINTED_SECTIONS: Mapping[str, Tuple[str, Type[BaseModel]]] = MappingProxyType(
    {
        "memory": ("memory", MemorySettings),
        "lore.token_budget": ("lore_token_budget", TokenBudgetConfig),
    }
)

FIELD_COMPATIBILITY: Mapping[str, CompatibilityClass] = MappingProxyType(
    {
        # Window sizing: every turn resolves it from the story pin or the
        # repository default, then recomputes total_available and the Phase-2
        # budget before Pass 2 runs.
        "lore.token_budget.apex_context_window": "budget",
        "lore.token_budget.provider_overrides": "budget",
        # Allocation hints read by the live budget calculation; nothing in a
        # stored baseline is derived from them.
        "lore.token_budget.system_prompt_tokens": "budget",
        "lore.token_budget.prompt_overhead_tokens": "budget",
        # Multiplies the live window into the Phase-2 cap each turn, exactly
        # like a window change; the baseline records nothing derived from it.
        "memory.phase2_fraction": "budget",
        # Pass-2 retrieval breadth: the candidate pool, not a token amount.
        "memory.raw_search_k": "semantic",
        # Whether Pass 2 runs at all for a bare choice.
        "memory.skip_simple_choices": "semantic",
        # Baked into the stored accounting (reserved_for_pass2 and
        # reserve_shortfall) when Pass 1 stores the baseline.
        "memory.pass2_budget_reserve": "semantic",
        # Retrieval behavior that shapes which memories a baseline holds.
        "memory.warm_slice_default": "semantic",
        "memory.max_sql_iterations": "semantic",
    }
)


def _is_settings_model(annotation: Any) -> bool:
    """Return whether an annotation is, or wraps, a nested settings model."""

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return any(_is_settings_model(argument) for argument in get_args(annotation))


def fingerprinted_leaf_paths(
    sections: Mapping[str, Tuple[str, Type[BaseModel]]] = FINGERPRINTED_SECTIONS,
) -> Tuple[str, ...]:
    """Enumerate every leaf path of the fingerprinted settings models."""

    paths: List[str] = []
    for prefix, (_, model) in sections.items():
        for name, field in model.model_fields.items():
            if _is_settings_model(field.annotation):
                raise TypeError(
                    f"{prefix}.{name} is a nested settings model; classify its "
                    "leaves and teach nexus.memory.baseline_compat to flatten it"
                )
            paths.append(f"{prefix}.{name}")
    return tuple(paths)


def require_complete_classification(
    sections: Mapping[str, Tuple[str, Type[BaseModel]]] = FINGERPRINTED_SECTIONS,
    classification: Mapping[str, str] = FIELD_COMPATIBILITY,
) -> None:
    """Fail unless every fingerprinted leaf has exactly one known class."""

    leaves = set(fingerprinted_leaf_paths(sections))
    unclassified = sorted(leaves - set(classification))
    stale = sorted(set(classification) - leaves)
    unknown = sorted(
        f"{path}={value!r}"
        for path, value in classification.items()
        if value not in COMPATIBILITY_CLASSES
    )
    if unclassified or stale or unknown:
        raise RuntimeError(
            "Pass-2 baseline compatibility matrix is out of date: "
            f"unclassified={unclassified}, stale={stale}, unknown classes={unknown}. "
            "Classify every [memory] and [lore.token_budget] field as 'budget' or "
            "'semantic' in nexus/memory/baseline_compat.py FIELD_COMPATIBILITY and "
            "the matrix in docs/settings_scopes.md."
        )


require_complete_classification()


def fingerprinted_config(settings: Mapping[str, Any]) -> Dict[str, Any]:
    """Select the settings subtrees the Pass-2 config fingerprint hashes.

    The selection, including the legacy ``Agent Settings`` branch, is frozen:
    changing it would invalidate every stored baseline.
    """

    legacy_agent_settings = settings.get("Agent Settings")
    legacy_lore_settings = (
        legacy_agent_settings.get("LORE")
        if isinstance(legacy_agent_settings, Mapping)
        else None
    )
    lore_settings = (
        legacy_lore_settings
        if isinstance(legacy_lore_settings, Mapping)
        else settings.get("lore", {})
    )
    return {
        "memory": settings.get("memory", {}),
        "lore_token_budget": (
            lore_settings.get("token_budget", {})
            if isinstance(lore_settings, Mapping)
            else {}
        ),
    }


def config_hash(payload: Any) -> str:
    """Return the canonical SHA-256 of one JSON-compatible payload."""

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def pass2_baseline_config_fingerprint(settings: Mapping[str, Any]) -> str:
    """Fingerprint configuration that determines two-pass memory behavior."""

    return config_hash(fingerprinted_config(settings))


class _Absent:
    """Marker for a classified setting missing from a settings mapping."""

    def __repr__(self) -> str:
        return "<unset>"


ABSENT = _Absent()


def _canonical(value: Any) -> str:
    """Render one setting value the way the fingerprints serialize it."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Pass2ConfigSnapshot(BaseModel):
    """Fingerprinted setting values grouped by compatibility class."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    budget: Dict[str, JsonValue]
    semantic: Dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_classes(self) -> "Pass2ConfigSnapshot":
        """Require every recorded path to sit under its declared class."""

        for expected in COMPATIBILITY_CLASSES:
            for path in getattr(self, expected):
                actual = FIELD_COMPATIBILITY.get(path)
                if actual != expected:
                    raise ValueError(
                        f"{path!r} is recorded as {expected} but is classified "
                        f"{actual!r}"
                    )
        return self

    def value(self, path: str) -> Any:
        """Return one recorded value, or ``ABSENT`` when it was not set."""

        values = self.budget if FIELD_COMPATIBILITY[path] == "budget" else self.semantic
        return values.get(path, ABSENT)

    def semantic_fingerprint(self) -> str:
        """Hash only the semantic-class values."""

        return config_hash(self.semantic)

    def legacy_payload(self) -> Dict[str, Dict[str, Any]]:
        """Rebuild the exact payload the full config fingerprint hashes."""

        payload: Dict[str, Dict[str, Any]] = {
            key: {} for key, _ in FINGERPRINTED_SECTIONS.values()
        }
        for path, value in {**self.budget, **self.semantic}.items():
            for prefix, (key, _) in FINGERPRINTED_SECTIONS.items():
                if path.startswith(f"{prefix}."):
                    payload[key][path[len(prefix) + 1 :]] = value
                    break
        return payload


def snapshot_config(settings: Mapping[str, Any]) -> Pass2ConfigSnapshot:
    """Classify every fingerprinted setting value; unclassified keys fail."""

    payload = fingerprinted_config(settings)
    grouped: Dict[str, Dict[str, Any]] = {name: {} for name in COMPATIBILITY_CLASSES}
    for prefix, (key, _) in FINGERPRINTED_SECTIONS.items():
        section = payload[key]
        if not isinstance(section, Mapping):
            raise TypeError(
                f"[{prefix}] settings must be a table to snapshot a Pass-2 "
                f"baseline, got {type(section).__name__}"
            )
        for name, value in section.items():
            path = f"{prefix}.{name}"
            compatibility = FIELD_COMPATIBILITY.get(path)
            if compatibility is None:
                raise ValueError(
                    f"Setting {path!r} has no Pass-2 compatibility class; add it "
                    "to FIELD_COMPATIBILITY in nexus/memory/baseline_compat.py"
                )
            grouped[compatibility][path] = json.loads(_canonical(value))
    return Pass2ConfigSnapshot(budget=grouped["budget"], semantic=grouped["semantic"])


@dataclass(frozen=True)
class SettingChange:
    """One fingerprinted setting that differs between two snapshots."""

    path: str
    compatibility: CompatibilityClass
    stored: Any
    current: Any

    def describe(self) -> str:
        """Render ``path: stored -> current`` for logs and errors."""

        def render(value: Any) -> str:
            return repr(value) if value is ABSENT else _canonical(value)

        return f"{self.path}: {render(self.stored)} -> {render(self.current)}"


def diff_config_snapshots(
    stored: Pass2ConfigSnapshot, current: Pass2ConfigSnapshot
) -> List[SettingChange]:
    """List every classified setting whose serialized value changed."""

    changes: List[SettingChange] = []
    for path in sorted(FIELD_COMPATIBILITY):
        before, after = stored.value(path), current.value(path)
        if before is ABSENT and after is ABSENT:
            continue
        if (
            before is ABSENT
            or after is ABSENT
            or _canonical(before) != _canonical(after)
        ):
            changes.append(
                SettingChange(path, FIELD_COMPATIBILITY[path], before, after)
            )
    return changes


def describe_changes(changes: List[SettingChange]) -> str:
    """Join setting changes for one log line or error message."""

    return "; ".join(change.describe() for change in changes) or "none"
