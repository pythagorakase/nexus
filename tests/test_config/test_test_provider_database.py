"""The TEST provider's database key, its environment route, and its refusals."""

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import psycopg2
import pytest
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.config.loader import TEST_PROVIDER_DATABASE_ENV
from nexus.config.settings_models import APITestProviderSettings

SEEDER = (
    Path(__file__).resolve().parents[2] / "migrations" / "008_populate_mock_database.py"
)


def _load_seeder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migrations_008_populate_mock_database", SEEDER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("dbname", ["save_01", "NEXUS_template", ""])
def test_story_and_empty_names_are_refused(dbname: str) -> None:
    """A story database or an empty name is never the TEST provider database."""

    with pytest.raises(ValidationError):
        APITestProviderSettings(database=dbname)


@pytest.mark.parametrize("dbname", ["mock", "qa640_x"])
def test_test_databases_are_accepted(dbname: str) -> None:
    """The owner's default and a disposable clone both validate."""

    assert APITestProviderSettings(database=dbname).database == dbname


def test_environment_route_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment overlay is validated with the file's values."""

    monkeypatch.setenv(TEST_PROVIDER_DATABASE_ENV, "save_02")
    with pytest.raises(ValidationError):
        load_settings()


def test_environment_route_names_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A routed name reaches the loaded settings."""

    monkeypatch.setenv(TEST_PROVIDER_DATABASE_ENV, "qa640_x")
    settings = load_settings()
    assert settings.api is not None
    assert settings.api.test_provider.database == "qa640_x"


def test_seeder_refuses_a_story_database_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Migration 008 validates its target before it opens a connection."""

    def refuse_connection(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("the seeder connected before validating its target")

    seeder = _load_seeder()
    monkeypatch.setattr(psycopg2, "connect", refuse_connection)
    with pytest.raises(ValidationError):
        seeder.seed_test_provider_database("save_03")


def test_session_default_is_the_unrouted_database() -> None:
    """The conftest routes every unrouted process to a never-created database."""

    assert os.environ[TEST_PROVIDER_DATABASE_ENV] == "qa640_816_test_provider_unrouted"
