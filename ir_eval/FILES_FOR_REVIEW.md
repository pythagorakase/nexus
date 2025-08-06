# Files for A/B Testing Review

## Core System Files

1. **IR Evaluation Main Files**:
   - `/Users/pythagor/nexus/ir_eval/ir_eval.py` - Main IR evaluation interface
   - `/Users/pythagor/nexus/ir_eval/pg_db.py` - PostgreSQL database manager
   - `/Users/pythagor/nexus/ir_eval/scripts/golden_queries_module.py` - Module that runs queries through MEMNON
   - `/Users/pythagor/nexus/ir_eval/golden_queries.json` - Contains experimental settings and test queries

2. **MEMNON Search System**:
   - `/Users/pythagor/nexus/nexus/agents/memnon/memnon.py` - Main MEMNON class
   - `/Users/pythagor/nexus/nexus/agents/memnon/utils/temporal_search.py` - Temporal search functionality
   - `/Users/pythagor/nexus/nexus/agents/memnon/utils/db_access.py` - Database and search utilities
   - `/Users/pythagor/nexus/nexus/agents/memnon/utils/idf_dictionary.py` - Term weighting utilities

3. **Settings Files**:
   - `/Users/pythagor/nexus/settings.json` - Base settings file (control)
   - `/Users/pythagor/nexus/ir_eval/golden_queries.json` - Contains experimental settings

## Debug and Testing Files

4. **Diagnosis and Testing Tools**:
   - `/Users/pythagor/nexus/ir_eval/ir_eval_debug.py` - Special debug version for isolating the issue
   - `/Users/pythagor/nexus/ir_eval/REVIEW_NOTES.md` - Summary of issues and findings

## Relevant Directories

- `/Users/pythagor/nexus/ir_eval/` - IR evaluation system root
- `/Users/pythagor/nexus/ir_eval/scripts/` - IR evaluation helper scripts
- `/Users/pythagor/nexus/nexus/agents/memnon/` - MEMNON search system

## Debug Logs

Logs are stored in the following locations:
- `/Users/pythagor/nexus/ir_eval/logs/ir_eval.log` - Main IR evaluation logs
- `/Users/pythagor/nexus/ir_eval/logs/ir_eval_debug.log` - Debug-specific logs