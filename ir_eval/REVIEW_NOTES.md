# NEXUS IR Evaluation A/B Testing System - Review Notes

## Problem Description

The IR Evaluation system's A/B testing functionality is not working properly. When running control vs. experiment configurations, it appears that only the control settings are being applied, with no evidence that the experimental run is actually using different settings. It seems that the system isn't properly executing the second run with experimental settings.

## Current Status

1. We've identified that the issue is related to how settings are loaded and applied in the golden_queries_module.py.
2. We've implemented a fix that correctly sets the environment variable before importing MEMNON, and forces a module reload to ensure fresh settings are loaded.
3. We've updated the create_temp_settings_file function to better handle model paths.
4. Despite these changes, we're still not seeing evidence of the experimental settings being applied - it looks like only the control settings are ever used.

## Key Observations

1. **No Experimental Settings Application**: Logs show the control settings being loaded, but there's no corresponding log for experimental settings:
```
Running with CONTROL settings (from settings.json)...
INFO:nexus.ir_eval:Attempting to import golden_queries_module from: /Users/pythagor/nexus/scripts
INFO:nexus.ir_eval:Successfully imported golden_queries_module from /Users/pythagor/nexus/scripts/golden_queries_module.py
INFO:golden-query-module:Loaded golden queries from /Users/pythagor/nexus/ir_eval/golden_queries.json
INFO:golden-query-module:Using custom settings path: /Users/pythagor/nexus/settings.json
~~~
2025-04-24 11:32:53,870 - nexus.memnon.settings - INFO - Using settings path from environment: /Users/pythagor/nexus/settings.json
nexus.memnon.settings - INFO - Loaded settings from /Users/pythagor/nexus/settings.json
```

2. **Model Loading Issues**: MEMNON fails to load embedding models with the current settings:
```
nexus.memnon - WARNING - No path specified for model bge-large, skipping
nexus.memnon - WARNING - No path specified for model inf-retriever-v1-1.5b, skipping
nexus.memnon - WARNING - No embedding models loaded. Vector search will not work.
```

3. **Temporal Boosting Issue**: Temporal boost is set to 0 despite experimental settings specifying different values:
```
nexus.memnon - INFO - Using time-aware search for temporal query (classification: early, boost factor: 0)
```

## Relevant Files

1. **Main IR Evaluation System**:
   - `/Users/pythagor/nexus/ir_eval/ir_eval.py` - Main evaluation interface
   - `/Users/pythagor/nexus/ir_eval/scripts/golden_queries_module.py` - Module that runs queries through MEMNON
   - `/Users/pythagor/nexus/ir_eval/golden_queries.json` - Contains experimental settings and test queries

2. **MEMNON Search System**:
   - `/Users/pythagor/nexus/nexus/agents/memnon/memnon.py` - Main MEMNON class
   - `/Users/pythagor/nexus/nexus/agents/memnon/utils/temporal_search.py` - Temporal search functionality
   - `/Users/pythagor/nexus/nexus/agents/memnon/utils/db_access.py` - Database and search utilities

3. **Settings Files**:
   - `/Users/pythagor/nexus/settings.json` - Base settings file (control)
   - Temporary settings files are created during runtime with experimental settings

## Areas to Investigate

1. **Execution Flow for Experimental Run**:
   - Is the experimental run being executed at all?
   - If so, is it using the correct settings path?

2. **MEMNON Model Loading**: 
   - How are model paths being determined and loaded? 
   - Why aren't the local_path settings being properly applied?

3. **Temporal Boosting**:
   - Why is the temporal boost factor always 0 regardless of settings?
   - How is temporal_boost_factor propagated from settings to the perform_hybrid_search method?

4. **Settings Pipeline**:
   - Is something in the MEMNON initialization overriding or ignoring our experimental settings?
   - How are settings actually applied when performing a search operation?

5. **Debugging Approach**:
   - Add more detailed logging for the experimental run to confirm it's executing
   - Add logging to trace the settings values throughout the entire pipeline

## Working Hypothesis

The most likely issue is that the experimental run is either not being executed at all, or it's using the same settings as the control run. The environment variable for the settings path may not be properly set before the MEMNON module is loaded, or there may be an issue with how the settings are being passed to the search functions.

A/B testing is critical for evaluating improvements to the retrieval system, so resolving this issue is a high priority.