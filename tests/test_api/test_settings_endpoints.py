"""Tests for the GET/PATCH /api/settings surface (nexus/api/settings_endpoints).

These exercise the real nexus.toml in the repository root (payload assembly,
metadata derivation) and real tomlkit writes against a temporary copy - no
mocks. The HTTP layer itself is exercised by the live round-trip in the U5
validation workflow (uvicorn + curl); these tests pin the pure logic.
"""

import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException

from nexus.api.settings_endpoints import (
    SettingsPatchRequest,
    FontSlotsPatch,
    _build_payload,
    _provider_from_ref,
    _read_raw_settings,
    _updates_from_patch,
)
from nexus.config.loader import save_settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def raw_settings() -> dict:
    return _read_raw_settings()


class TestBuildPayload:
    def test_strips_secrets(self, raw_settings: dict) -> None:
        payload = _build_payload(raw_settings)
        assert "secrets" not in payload

    def test_legacy_aliases_present(self, raw_settings: dict) -> None:
        payload = _build_payload(raw_settings)
        assert payload["Agent Settings"]["global"] == raw_settings["global"]
        assert payload["Agent Settings"]["LORE"] == raw_settings["lore"]
        assert payload["API Settings"]["apex"] == raw_settings["apex"]

    def test_role_refs_left_unresolved(self, raw_settings: dict) -> None:
        payload = _build_payload(raw_settings)
        assert payload["apex"]["model"].startswith("@")

    def test_meta_roles_cover_registry(self, raw_settings: dict) -> None:
        payload = _build_payload(raw_settings)
        meta = payload["settings_meta"]
        refs = {r["ref"] for r in meta["model_roles"]}
        for provider, cfg in raw_settings["global"]["model"]["api_models"].items():
            for role in cfg.get("roles", {}):
                assert f"@{provider}.{role}" in refs

    def test_apex_allowlist_excludes_test_provider(self, raw_settings: dict) -> None:
        meta = _build_payload(raw_settings)["settings_meta"]
        assert "test" not in meta["apex_allowed_providers"]
        assert "openai" in meta["apex_allowed_providers"]
        assert "anthropic" in meta["apex_allowed_providers"]

    def test_typewriter_bounds_from_model(self, raw_settings: dict) -> None:
        meta = _build_payload(raw_settings)["settings_meta"]
        assert meta["typewriter"] == {"min": 1, "max": 500}


class TestUpdatesFromPatch:
    def test_full_patch_maps_dot_keys(self) -> None:
        patch = SettingsPatchRequest(
            theme="gilded",
            fonts={"vector": FontSlotsPatch(menu="Monaco")},
            typewriter_ms_per_char=42,
            test_mode=True,
            apex_model_ref="@anthropic.deep",
            wizard_model_ref="@openai.default",
            apex_context_window=100_000,
        )
        updates = _updates_from_patch(patch)
        assert updates == {
            "ui.theme": "gilded",
            "ui.fonts.vector.menu": "Monaco",
            "ui.typewriter_ms_per_char": 42,
            "global.narrative.test_mode": True,
            "apex.model": "@anthropic.deep",
            "apex.provider": "anthropic",
            "wizard.default_model": "@openai.default",
            "lore.token_budget.apex_context_window": 100_000,
        }

    def test_empty_patch_yields_no_updates(self) -> None:
        assert _updates_from_patch(SettingsPatchRequest()) == {}

    def test_malformed_ref_raises_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _updates_from_patch(SettingsPatchRequest(apex_model_ref="gpt-5.5"))
        assert exc_info.value.status_code == 422


class TestProviderFromRef:
    def test_extracts_provider(self) -> None:
        assert _provider_from_ref("@anthropic.fast", "test") == "anthropic"

    @pytest.mark.parametrize("ref", ["gpt-5.5", "@anthropic", "anthropic.fast"])
    def test_rejects_malformed(self, ref: str) -> None:
        with pytest.raises(HTTPException):
            _provider_from_ref(ref, "test")


class TestRoundTripOnCopy:
    """Real tomlkit write of endpoint-shaped updates on a temp copy."""

    def test_patch_updates_persist_and_preserve_comments(
        self, tmp_path: Path
    ) -> None:
        toml_copy = tmp_path / "nexus.toml"
        shutil.copy2(REPO_ROOT / "nexus.toml", toml_copy)
        original = toml_copy.read_text()

        patch = SettingsPatchRequest(
            theme="vector",
            apex_model_ref="@anthropic.deep",
            typewriter_ms_per_char=42,
        )
        save_settings(_updates_from_patch(patch), path=toml_copy, backup=False)

        settings = load_settings(toml_copy)
        assert settings.ui.theme == "vector"
        assert settings.ui.typewriter_ms_per_char == 42
        assert settings.apex.provider == "anthropic"
        # Role ref resolves to the registry's concrete ID at load time.
        anthropic = settings.global_.model.api_models["anthropic"]
        assert settings.apex.model == anthropic.roles["deep"]

        # Comments survive the write.
        updated = toml_copy.read_text()
        assert "# Typewriter reveal speed" in updated
        assert "# Resolved via api_models registry" in updated
        assert original != updated
