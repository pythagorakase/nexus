"""Pure whole-run fingerprint coverage using the actual typed transition/settings."""

from typing import Any

from nexus.api.new_story_flow import (
    build_transition_data_from_cache,
    genesis_input_fingerprint,
)
from nexus.config import load_settings
from tests.test_api.test_wizard_weird_level import ready_cache


def test_fingerprint_is_stable_and_covers_every_input() -> None:
    """Every ruled input changes the hash independently, including nested settings."""
    transition = build_transition_data_from_cache(ready_cache(weird_level="high"))
    settings = load_settings()
    model = settings.apex.model
    kwargs: dict[str, Any] = dict(
        transition_data=transition, weird_level="high", model=model, settings=settings
    )
    baseline = genesis_input_fingerprint(**kwargs)
    assert baseline == genesis_input_fingerprint(**kwargs)
    assert len(baseline) == 64 and int(baseline, 16) >= 0
    changed_transition = transition.model_copy(
        update={
            "setting": transition.setting.model_copy(
                update={"world_name": transition.setting.world_name + " changed"}
            )
        }
    )
    changed_traits = settings.model_copy(
        update={
            "wizard": settings.wizard.model_copy(
                update={
                    "trait_inputs": settings.wizard.trait_inputs.model_copy(
                        update={
                            "max_tokens": settings.wizard.trait_inputs.max_tokens + 1
                        }
                    )
                }
            )
        }
    )
    changed_retries = settings.model_copy(
        update={
            "wizard": settings.wizard.model_copy(
                update={"max_retries": settings.wizard.max_retries + 1}
            )
        }
    )
    assert settings.orrery is not None
    changed_orrery = settings.model_copy(
        update={
            "orrery": settings.orrery.model_copy(
                update={"enabled": not settings.orrery.enabled}
            )
        }
    )
    changes = (
        {"transition_data": changed_transition},
        {"weird_level": "low"},
        {"model": model + "-changed"},
        {"settings": changed_traits},
        {"settings": changed_retries},
        {"settings": changed_orrery},
    )
    for change in changes:
        assert genesis_input_fingerprint(**{**kwargs, **change}) != baseline, change
