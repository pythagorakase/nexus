"""Private PostgreSQL proof that Gaia repairs references before staging.

Uses the disposable acceptance fixture's places, incubator, narrative metadata,
and registry tables. Never runs providers or changes an existing save database.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from nexus.agents.logon.orrery_tag_validation import build_storyteller_tag_validator
from nexus.agents.logon.skald_wire import SkaldGaiaWire, SkaldWriterWire
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.narrative_generation import write_to_incubator
from tests.pg_fixtures import connect
from tests.test_api import test_acceptance_staging_pg as acceptance_fixtures
from tests.test_api.test_reentry_wire_pg import staged
from tests.test_lore.test_place_reference_validation import gaia_payload, writer_payload

pytestmark = pytest.mark.requires_postgres
acceptance_slot = acceptance_fixtures.acceptance_slot


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["mentions", "transit", "scene_reset"])
async def test_writer_reference_is_repaired_before_real_staging(
    acceptance_slot: tuple[str, int, int], site: str
) -> None:
    """An undeclared reference is rejected; explicit Gaia repair stages unchanged."""
    dbname, parent, _ = acceptance_slot
    writer = SkaldWriterWire.model_validate(writer_payload(site))
    utility = LogonUtility.__new__(LogonUtility)
    utility._validation_dbname = dbname
    utility.settings = {"orrery": {"retrograde": {"maturation": {"enabled": True}}}}
    utility.provider = SimpleNamespace(
        output_validator=build_storyteller_tag_validator(
            dbname, allow_same_turn_faction_declarations=True
        )
    )
    validator = utility._build_gaia_place_validator(writer)
    with pytest.raises(ModelRetry, match="Machine-Shop"):
        await validator(None, SkaldGaiaWire.model_validate(gaia_payload()))
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM incubator")
        assert cur.fetchone() == (0,)
        cur.execute("SELECT count(*) FROM places WHERE name='Machine-Shop'")
        assert cur.fetchone() == (0,)

    repaired = SkaldGaiaWire.model_validate(gaia_payload(declared=True))
    assert await validator(None, repaired) is repaired
    with connect(dbname) as conn:
        session = acceptance_fixtures.own_draft(conn, parent)
        data = staged(writer, repaired, parent, session)
        await write_to_incubator(conn, data)
        with conn.cursor() as cur:
            cur.execute("SELECT reference_updates, new_entities FROM incubator")
            references, declarations = cur.fetchone()
            assert any(
                reference["place_name"] == "Machine-Shop"
                and reference.get("place_id") is None
                for reference in references["places"]
            )
            assert declarations[0]["name"] == "Machine-Shop"
            cur.execute("SELECT count(*) FROM places WHERE name='Machine-Shop'")
            assert cur.fetchone() == (0,)
