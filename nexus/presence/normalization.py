"""One normalization policy for character minting and reference reads."""

import unicodedata

from nexus.config.settings_models import CharacterIdentitySettings


def normalize_identity_text(name: str, cfg: CharacterIdentitySettings) -> str:
    """Normalize identity text using the configured case and diacritic policy."""
    value = " ".join(name.split())
    if cfg.case_folding:
        value = value.casefold()
    if cfg.strip_diacritics:
        value = "".join(
            char
            for char in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(char)
        )
    return value


def normalize_identity_name(name: str, cfg: CharacterIdentitySettings) -> str:
    """Apply the same configured title normalization to either side of a match."""
    parts = normalize_identity_text(name, cfg).split()
    titles = {normalize_identity_text(title, cfg).rstrip(".") for title in cfg.titles}
    if cfg.strip_titles and parts and parts[0].rstrip(".") in titles:
        parts = parts[1:]
    return " ".join(parts)
