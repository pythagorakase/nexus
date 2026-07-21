"""Unit regressions for Orrery coverage winner and pressure accounting."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from nexus.agents.orrery import coverage
from nexus.agents.orrery.substrate import Template


TEMPLATE_ID = "coverage_probe"


def _template() -> SimpleNamespace:
    return SimpleNamespace(
        id=TEMPLATE_ID,
        drive_band=SimpleNamespace(value="affiliation"),
        branches=(SimpleNamespace(label="Probe branch", promotable=True),),
    )


def _item() -> SimpleNamespace:
    return SimpleNamespace(
        template_id=TEMPLATE_ID,
        drive_band="affiliation",
        gate_passed=True,
        fired=True,
        chosen_branch="Probe branch",
        promotable=True,
    )


def _stack(*, actor: int, target: int | None, winner: bool) -> SimpleNamespace:
    bindings = {"actor": actor}
    if target is not None:
        bindings["target"] = target
    return SimpleNamespace(
        bindings=bindings,
        winner_id=TEMPLATE_ID if winner else None,
        templates=(_item(),) if winner else (),
    )


def _group(
    actor: int,
    *,
    pair_stacks: tuple[SimpleNamespace, ...] = (),
    pressure_stacks: tuple[SimpleNamespace, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        actor_entity_id=actor,
        actor_stack=_stack(actor=actor, target=None, winner=False),
        two_party_stacks=pair_stacks,
        scene_pressure_stacks=pressure_stacks,
    )


def _analyze(
    monkeypatch: Any,
    *,
    groups: tuple[SimpleNamespace, ...],
    fanout_trimmed: tuple[dict[str, Any], ...] = (),
    project_start_arbitration_trimmed: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    report = SimpleNamespace(
        anchor_chunk_id=42,
        world_time=None,
        time_of_day="day",
        actor_count=len(groups),
        actors=groups,
        need_pressures=(),
        entity_names={
            group.actor_entity_id: f"Actor {group.actor_entity_id}" for group in groups
        },
        fanout_trimmed=fanout_trimmed,
        project_start_arbitration_trimmed=project_start_arbitration_trimmed,
    )
    monkeypatch.setattr(
        coverage,
        "build_catalog",
        lambda templates: {
            "drive_bands": [
                {
                    "templates": [
                        {"template_id": template.id, "arity": "actor_target"}
                        for template in templates
                    ]
                }
            ],
            "event_map": {},
        },
    )
    monkeypatch.setattr(coverage, "explain_dry_run", lambda *args, **kwargs: report)
    monkeypatch.setattr(
        coverage,
        "_data_quality_findings",
        lambda *args, **kwargs: {},
    )
    return coverage.analyze_coverage(
        object(),
        (cast(Template, _template()),),
        anchor_chunk_ids=(42,),
        window_chunks=10,
        epoch_min_world_times=10,
    )


def test_pressure_only_firing_is_not_reported_as_never_fired(
    monkeypatch: Any,
) -> None:
    payload = _analyze(
        monkeypatch,
        groups=(
            _group(
                1,
                pressure_stacks=(_stack(actor=1, target=2, winner=True),),
            ),
        ),
    )

    assert payload["templates"][TEMPLATE_ID]["fired"] == 0
    assert payload["templates"][TEMPLATE_ID]["pressure_fired"] == 1
    assert TEMPLATE_ID not in payload["never_fired"]


def test_fanout_trimmed_pair_stays_fired_but_is_not_counted_as_winner(
    monkeypatch: Any,
) -> None:
    payload = _analyze(
        monkeypatch,
        groups=(
            _group(1, pair_stacks=(_stack(actor=1, target=2, winner=True),)),
            _group(3, pair_stacks=(_stack(actor=3, target=4, winner=True),)),
        ),
        fanout_trimmed=(
            {
                "actor_entity_id": 1,
                "target_entity_id": 2,
                "template_id": TEMPLATE_ID,
            },
        ),
    )

    stats = payload["templates"][TEMPLATE_ID]
    assert stats["evaluated"] == 2
    assert stats["fired"] == 2
    assert stats["won"] == 1
    assert stats["branch_chosen"]["Probe branch"] == 2
    assert payload["anchors"][0]["winners_by_band"] == {"affiliation": 1}
    assert payload["anchors"][0]["resolution_winners"] == [
        {
            "actor_entity_id": 3,
            "target_entity_id": 4,
            "template_id": TEMPLATE_ID,
            "drive_band": "affiliation",
            "promotable": True,
        }
    ]


def test_arbitration_trimmed_start_is_not_counted_as_winner(
    monkeypatch: Any,
) -> None:
    """Project starts dropped by _arbitrate_project_starts never commit, so
    coverage must exclude them from winner tallies like fanout trims."""

    payload = _analyze(
        monkeypatch,
        groups=(
            _group(1, pair_stacks=(_stack(actor=1, target=2, winner=True),)),
            _group(3, pair_stacks=(_stack(actor=3, target=4, winner=True),)),
        ),
        project_start_arbitration_trimmed=(
            {
                "actor_entity_id": 1,
                "target_entity_id": 2,
                "faction_entity_id": None,
                "template_id": TEMPLATE_ID,
            },
        ),
    )

    stats = payload["templates"][TEMPLATE_ID]
    assert stats["fired"] == 2
    assert stats["won"] == 1
    assert payload["anchors"][0]["winners_by_band"] == {"affiliation": 1}
    assert [
        winner["actor_entity_id"]
        for winner in payload["anchors"][0]["resolution_winners"]
    ] == [3]
