"""Authoritative, story-bound acceptance and revision of wizard artifacts."""

from typing import Any, Dict

from nexus.api.db_pool import get_connection
from nexus.api.new_story_cache import WizardCache, read_cache_cursor


class WizardStateConflict(ValueError):
    """The player action no longer addresses the persisted wizard state."""


def _validate_action(
    cache: WizardCache | None, thread_id: str, phase: str, artifact_token: str
) -> WizardCache:
    if cache is None or cache.thread_id != thread_id:
        raise WizardStateConflict(
            "This story session changed. Resume it before retrying."
        )
    if cache.artifact_token(phase) != artifact_token:
        raise WizardStateConflict(
            "This artifact changed. Review it again before continuing."
        )
    return cache


def confirm_artifact(
    dbname: str, *, thread_id: str, phase: str, artifact_token: str
) -> Dict[str, Any]:
    """Accept the exact current draft, without invoking a model or advancing twice."""
    if phase not in {"setting", "character"}:
        raise WizardStateConflict("Only setting and character use setup confirmation.")
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cache = _validate_action(
                read_cache_cursor(cur, lock=True), thread_id, phase, artifact_token
            )
            complete = (
                cache.setting_complete()
                if phase == "setting"
                else cache.character_complete()
            )
            if not complete or cache.character_revision_pending:
                raise WizardStateConflict(
                    "Finish the current draft revision before confirming."
                )
            already_confirmed = getattr(cache, f"{phase}_confirmed")
            if already_confirmed or cache.current_phase() != phase:
                raise WizardStateConflict(
                    "This artifact was already confirmed or the wizard phase "
                    "changed. Resume before continuing."
                )
            cur.execute(
                f"UPDATE assets.new_story_creator SET {phase}_confirmed = TRUE, "
                "choice_object = NULL, updated_at = NOW() WHERE id = TRUE"
            )
    return {
        "status": "confirmed",
        "phase": phase,
        "next_phase": "character" if phase == "setting" else "seed",
        "thread_id": thread_id,
    }


def begin_character_revision(
    dbname: str, *, thread_id: str, artifact_token: str
) -> Dict[str, Any]:
    """Enter concept editing without discarding selected mechanics or drafts."""
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cache = _validate_action(
                read_cache_cursor(cur, lock=True),
                thread_id,
                "character",
                artifact_token,
            )
            if (
                cache.current_phase() != "character"
                or not cache.character.has_concept()
            ):
                raise WizardStateConflict(
                    "Character revision is only available before character "
                    "confirmation."
                )
            cur.execute(
                "UPDATE assets.new_story_creator SET character_revision_pending = "
                "TRUE, "
                "character_confirmed = FALSE, choice_object = NULL, updated_at = "
                "NOW() WHERE id = TRUE"
            )
    return {"status": "revision_started", "phase": "character", "thread_id": thread_id}


def replace_character_concept(
    dbname: str, *, thread_id: str, artifact_token: str, concept: Dict[str, Any]
) -> WizardCache:
    """Replace prose only; retain traits/wildcard and invalidate compiled dependents."""
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cache = _validate_action(
                read_cache_cursor(cur, lock=True),
                thread_id,
                "character",
                artifact_token,
            )
            if (
                cache.current_phase() != "character"
                or not cache.character_revision_pending
            ):
                raise WizardStateConflict(
                    "Character revision is no longer active. Resume before retrying."
                )
            cur.execute(
                "UPDATE assets.new_story_creator SET character_name = %s, "
                "character_archetype = %s, character_background = %s, "
                "character_appearance = %s, "
                "character_revision_pending = FALSE, character_confirmed = FALSE, "
                "trait_compile_result = NULL, choice_object = NULL, updated_at = "
                "NOW() WHERE id = TRUE",
                tuple(
                    concept[key]
                    for key in ("name", "archetype", "background", "appearance")
                ),
            )
            return read_cache_cursor(cur)
