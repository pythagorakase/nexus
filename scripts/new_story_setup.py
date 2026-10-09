#!/usr/bin/env python3
"""
Utilities for new-story save slots.

Actions:
  - Check that the assets tables exist (`assets.new_story_creator`)
  - Clone the public schema into a save slot schema (save_02 ... save_05) using pg_dump-based rewrite

The implementation is nexus.maintenance.new_story_setup; this module
re-exports its names.
Assigning a name here does not change the implementation: patch
nexus.maintenance.new_story_setup instead.
"""

from nexus.maintenance.new_story_setup import (
    LOG,
    TEMPLATE_SEED_TABLES,
    USE_POOL,
    _STAGING_FAILURE_GUIDANCE,
    _align_slot_number,
    _build_from_template,
    _clone_source_identity,
    _connect,
    _copy_template_data,
    _get_default_slot_model,
    _initialize_empty_idf_corpora,
    _locked_target_message,
    _post_clone_cleanup,
    _postgres_tools,
    _refuse_locked_target,
    _require_migration_stamps,
    _restore_clone,
    _restore_plain_dump,
    _target_name,
    clone_slot_with_data,
    create_slot_schema_only,
    ensure_global_variables,
    initialize_slot_database,
    main,
    require_assets_tables,
    stage_slot_clone,
    stage_slot_from_template,
)

__all__ = [
    "LOG",
    "TEMPLATE_SEED_TABLES",
    "USE_POOL",
    "_STAGING_FAILURE_GUIDANCE",
    "_align_slot_number",
    "_build_from_template",
    "_clone_source_identity",
    "_connect",
    "_copy_template_data",
    "_get_default_slot_model",
    "_initialize_empty_idf_corpora",
    "_locked_target_message",
    "_post_clone_cleanup",
    "_postgres_tools",
    "_refuse_locked_target",
    "_require_migration_stamps",
    "_restore_clone",
    "_restore_plain_dump",
    "_target_name",
    "clone_slot_with_data",
    "create_slot_schema_only",
    "ensure_global_variables",
    "initialize_slot_database",
    "main",
    "require_assets_tables",
    "stage_slot_clone",
    "stage_slot_from_template",
]


if __name__ == "__main__":
    main()
