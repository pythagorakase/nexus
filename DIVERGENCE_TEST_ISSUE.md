# Divergence Detection Test Infrastructure Issue

## Summary
Async divergence detection tests in `test_lore.py` fail due to LLM model lifecycle management issues.

## Status
- ✅ **FIXED**: `requests` import error (commit 2e599cd)
- ❌ **BLOCKED**: Async test execution

## Problem Description

### Issue 1: Async Test Not Awaited in Unittest Phase
The `TestDivergenceDetection.test_divergence_with_chunks()` method is async, but unittest's synchronous test runner doesn't await it:

```
RuntimeWarning: coroutine 'TestDivergenceDetection.test_divergence_with_chunks' was never awaited
```

**Location**: `nexus/agents/lore/test_lore.py:520`

### Issue 2: Model Unloaded Before Async Tests Run
Test execution flow:
1. Synchronous tests run (lines ~650-700) ✅
2. Model gets unloaded in cleanup (`tearDownModule()`) ✅
3. Async test runner starts (line 719: `asyncio.run(run_async_tests())`)
4. Async tests try to run but fail with "No models loaded" error ❌

**Error**:
```
LM Studio API error 404: {
    "error": {
        "message": "No models loaded. Please load a model in the developer page or use the `lms load` command.",
        "type": "invalid_request_error",
        "param": "model",
        "code": "model_not_found"
    }
}
```

## Attempted Fixes

### Attempt 1: Wrap async with `asyncio.run()`
Changed test method from `async def` to regular `def` calling `asyncio.run()`:

```python
def test_divergence_with_chunks(self):
    asyncio.run(self._run_divergence_tests())
```

**Result**: Failed with "asyncio.run() cannot be called from a running event loop"
**Reason**: The async test runner (line 713) is already inside an event loop created by line 719's `asyncio.run(run_async_tests())`

### Attempt 2: Keep Method Async
Reverted to original async signature:

```python
async def test_divergence_with_chunks(self):
    for chunk_id in _test_chunks:
        await self._test_single_chunk(chunk_id)
```

**Result**: Method isn't awaited during unittest phase, then fails when async runner tries to execute it because model is unloaded.

## Root Cause
The test infrastructure has two execution contexts:
1. **Synchronous unittest runner** (runs first, includes model cleanup)
2. **Async test runner** (runs after cleanup, expects model to be loaded)

The divergence test needs:
- To run in async context (uses `await` for turn cycle methods)
- To have LLM model loaded (for divergence detection)

But the test lifecycle causes model to be unloaded between these contexts.

## Possible Solutions

### Option A: Don't Unload Model Until After Async Tests
Modify `run_tests()` to defer model unloading:

```python
# Run async tests
asyncio.run(run_async_tests())

# THEN cleanup (not before)
tearDownModule()
```

**Location**: `nexus/agents/lore/test_lore.py:718-726`

### Option B: Reload Model for Async Tests
Have async test runner ensure model is loaded:

```python
async def run_async_tests():
    lore_instance = _get_shared_lore()

    # Ensure model is loaded
    if lore_instance.llm_manager:
        lore_instance.llm_manager.ensure_model_loaded()

    # ... rest of async tests
```

**Location**: `nexus/agents/lore/test_lore.py:688-717`

### Option C: Remove Async Test from Unittest Suite
Mark the test to skip during unittest phase, only run in async section:

```python
def test_divergence_with_chunks(self):
    # Skip in unittest phase - will run in async section
    self.skipTest("Async-only test, run via --test-chunks")
```

## Test Execution Evidence

### First Run (with `asyncio.run()` fix):
- `requests` import error: ❌ (now fixed)
- Async test execution: Progressed far, executed turn cycle phases, but ultimately failed with "asyncio.run() cannot be called from a running event loop"

### Second Run (reverted to async):
- `requests` import error: ✅ Fixed
- Async test execution: ❌ Failed with "No models loaded" (model unloaded before async tests)

## Reproduction Steps

```bash
poetry run python nexus/agents/lore/test_lore.py --test-chunks 1369 3 --save-context
```

**Expected**: Divergence detection tests run and complete successfully
**Actual**: Tests fail during async execution phase with "No models loaded" error

## Files Involved
- `nexus/agents/lore/test_lore.py:505-647` - TestDivergenceDetection class
- `nexus/agents/lore/test_lore.py:650-743` - run_tests() and async test runner
- `nexus/agents/lore/utils/local_llm.py:7-9` - Fixed requests import (✅ resolved)

## Next Steps for Codex
1. Review test lifecycle in `run_tests()` function
2. Choose and implement one of the solutions above (recommend Option A)
3. Verify divergence tests execute successfully with `--test-chunks 1369 3`
4. Confirm LLM divergence detection actually analyzes the user input and detects divergence for chunk 1369 (expected: divergent due to "karaoke" reference)
