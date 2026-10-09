"""Real read-only init plans over healthy, then stale, disposable databases.

Requires PostgreSQL and schema_migrations plus the IDF corpus tables. Each
template/slot stand-in is a qa640_803s6 clone; the plan applies no migration,
changes no stamp and leaves the test's locked clone locked.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import ExitStack, closing
from dataclasses import dataclass
import json

from psycopg2 import sql
import pytest

from nexus.api.save_slots import is_slot_locked
from nexus.config import load_settings
from nexus.runtime.contract import HOME_ENV, RUNTIME_CONFIG_ENV
from nexus.runtime.init_plan import build_init_plan, render_plan
from nexus.runtime.readiness import REGISTRY, CheckSpec, ReadinessContext
from scripts import migrate
from tests import pg_fixtures

pytestmark = pytest.mark.requires_postgres

# This deliberate subset exercises database planning without owner resources.
# It is independent of the identity/model checks added to the complete registry.
PLAN_DATABASE_CHECKS = {
    "config.valid",
    "postgres.reachable",
    "postgres.extensions",
    "template.present",
    "template.migrations_current",
    "slots.migrations_current",
    "template.idf_analyzer_current",
    "slots.idf_analyzer_current",
}


@dataclass(frozen=True)
class StandIns:
    """Disposable template and routed slots retained by the fixture's stack."""

    template: str
    slots: dict[int, str]
    stack: ExitStack


@pytest.fixture(autouse=True)
def developer_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the checkout config, never an inherited owner-home locator."""
    for name in (HOME_ENV, RUNTIME_CONFIG_ENV, "NEXUS_API_URL", "NEXUS_GATEWAY_PORT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def healthy_stand_ins(monkeypatch: pytest.MonkeyPatch) -> Iterator[StandIns]:
    """Create current, unlocked clones, without the readiness fixture's staleness."""
    settings = load_settings()
    assert settings.runtime is not None
    with ExitStack() as stack:
        template = stack.enter_context(
            pg_fixtures.disposable_slot_database("qa640_803s6_template")
        )
        slots = {
            slot: stack.enter_context(
                pg_fixtures.disposable_slot_database(f"qa640_803s6_slot{slot}")
            )
            for slot in settings.runtime.readiness.slots
        }
        monkeypatch.setattr(migrate, "TEMPLATE_DB", template)
        pg_fixtures.route_slots_to_disposable(monkeypatch.setattr, slots)
        yield StandIns(template, slots, stack)


def _registry() -> list[CheckSpec]:
    """Select only the ordered eight database checks, retaining registry order."""
    registry = [spec for spec in REGISTRY if spec.id in PLAN_DATABASE_CHECKS]
    assert {spec.id for spec in registry} == PLAN_DATABASE_CHECKS
    return registry


def _dependents(root: str, specs: Sequence[CheckSpec]) -> list[str]:
    """Collect a check's transitive dependents in registry order."""
    result: list[str] = []
    for spec in specs:
        if any(parent == root or parent in result for parent in spec.depends_on):
            result.append(spec.id)
    return result


def _remove_stamp(dbname: str, version: str) -> None:
    """Make exactly one migration pending in a disposable stand-in."""
    with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
        assert cur.rowcount == 1


def _set_read_only(dbname: str, on: bool) -> None:
    """Lock only this fixture's clone and reset its policy during teardown."""
    assert dbname.startswith("qa640_803s6_")
    setting = (
        "SET default_transaction_read_only = on"
        if on
        else "RESET default_transaction_read_only"
    )
    admin = pg_fixtures.connect("postgres")
    admin.autocommit = True
    with closing(admin), admin.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER DATABASE {} " + setting).format(sql.Identifier(dbname))
        )


def test_plan_names_pending_migrations_in_registry_order(
    healthy_stand_ins: StandIns,
) -> None:
    """Sorting flips the steps; applying them changes the stamps or lock below."""
    stand_ins = healthy_stand_ins
    assert {1, 2} <= stand_ins.slots.keys()
    registry = _registry()
    latest = migrate.discover_migrations()[-1][0]

    healthy = build_init_plan(ReadinessContext(), registry=registry)
    assert healthy.ok
    assert healthy.steps == [] and healthy.blocked == []

    _remove_stamp(stand_ins.template, latest)
    plan = build_init_plan(ReadinessContext(), registry=registry)
    assert not plan.ok
    assert plan.blocked == []
    assert [step.model_dump() for step in plan.steps] == [
        {
            "number": 1,
            "check_id": "template.migrations_current",
            "observed": f"{stand_ins.template}: 1 pending ({latest})",
            "remediation": "python scripts/migrate.py --template",
        }
    ]

    _remove_stamp(stand_ins.slots[2], latest)
    plan = build_init_plan(ReadinessContext(), registry=registry)
    assert [step.check_id for step in plan.steps] == [
        "template.migrations_current",
        "slots.migrations_current",
    ]
    assert [step.number for step in plan.steps] == [1, 2]
    assert plan.steps[1].remediation == "python scripts/migrate.py --slot 2"

    _remove_stamp(stand_ins.slots[1], latest)
    # Registered after clone contexts: undo the lock before their drop callbacks.
    stand_ins.stack.callback(_set_read_only, stand_ins.slots[1], False)
    _set_read_only(stand_ins.slots[1], True)
    plan = build_init_plan(ReadinessContext(), registry=registry)
    assert [step.check_id for step in plan.steps] == [
        "template.migrations_current",
        "slots.migrations_current",
    ]
    assert [step.number for step in plan.steps] == [1, 2]
    assert plan.steps[1].remediation == (
        "python scripts/migrate.py --slot 1 --write-locked-slot; "
        "python scripts/migrate.py --slot 2"
    )
    assert not plan.ok and plan.blocked == []
    print("\n".join(render_plan(plan)))
    print(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True))

    for dbname in (stand_ins.template, stand_ins.slots[1], stand_ins.slots[2]):
        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM schema_migrations WHERE version = %s", (latest,)
            )
            assert cur.fetchone()[0] == 0
    assert is_slot_locked(1)


def test_plan_without_template_blocks_its_dependents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing template blocks all slot checks before an owner name is used."""
    monkeypatch.setattr(migrate, "TEMPLATE_DB", "qa640_803s6_absent")
    registry = _registry()
    plan = build_init_plan(ReadinessContext(), registry=registry)
    assert not plan.ok
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.check_id == "template.present"
    assert step.observed == "qa640_803s6_absent does not exist"
    assert step.remediation == (
        "Restore qa640_803s6_absent from a known-good slot (CLAUDE.md, Refreshing "
        "the Template); new slots are cloned from it."
    )
    assert plan.blocked == _dependents("template.present", registry)
