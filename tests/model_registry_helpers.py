"""Choose registered models for provider coverage without pinning roster versions."""

from nexus.config import load_settings


def registry_model(provider: str) -> str:
    """Prefer a configured component's model, otherwise the provider's first ID."""
    settings = load_settings()
    for model in (
        settings.wizard.default_model,
        settings.apex.model,
        settings.apex.gaia_model,
        settings.local_models.model,
    ):
        if model is not None and settings.provider_for_model(model) == provider:
            return model
    return settings.global_.model.api_models[provider].models[0].id
