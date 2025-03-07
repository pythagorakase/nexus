# Night City Stories Testing Framework

This document describes how to use the testing framework for the Night City Stories narrative intelligence system. The framework provides utilities for both unit testing individual modules and integration testing to verify communication between modules.

## Overview

The testing framework is implemented in `prove.py` and provides:

1. **Test Environment Management**: Set up and tear down test environments with temporary directories, test databases, and settings.
2. **Test Data Generation**: Generate mock narrative chunks, entity states, relationships, and memories.
3. **Integration Testing**: Verify communication between modules and end-to-end system functionality.
4. **Interactive CLI**: Run tests interactively through a command-line interface.
5. **Entity Visualization**: Visualize the relationships between entities in the narrative.

## Running Tests

### Interactive Mode

Run the testing utility without arguments to launch the interactive CLI:

```bash
python prove.py
```

This will display the NEXUS DIAGNOSTIC PROTOCOLS menu with available tests:

```
========================================
|NEXUS DIAGNOSTIC PROTOCOLS INITIALIZED|
========================================

Available Tests:
1. Inter-Module Communications Check
2. End-to-End Integration Test
3. Entity Relationship Visualization
4. Run All Tests

0. Exit

Enter test number to run, or 0 to exit:
```

### Command-Line Arguments

Run specific tests directly using command-line arguments:

- `--unit-test`: Run standalone unit tests for individual components
- `--integration-test`: Run integration tests between modules
- `--visualize`: Run entity relationship visualization

Example:
```bash
python prove.py --integration-test
```

## Test Types

### 1. Inter-Module Communications Check

This test verifies that modules can communicate with each other by sending messages and receiving responses. It tests specific communication paths, such as:

- Maestro → Lore: Context Request
- Lore → Memnon: Memory Retrieval
- Memnon → DB_Chroma: Vector Search
- Memnon → DB_SQLite: Entity Lookup
- Logon → API: Narrative Generation
- Gaia → DB_SQLite: State Update

### 2. End-to-End Integration Test

This test simulates the full narrative workflow from receiving new narrative text to generating the next part of the story:

1. Generate a test narrative chunk
2. Process it through the Maestro orchestrator
3. Extract entity states via Gaia
4. Store entity states in the database
5. Store the narrative chunk in the vector database
6. Build context for the next narrative generation
7. Generate new narrative via the Logon API interface

### 3. Entity Relationship Visualization

This test visualizes the relationships between entities in the narrative, helping to understand the structure of the story world:

1. Retrieves entity relationships from the database
2. Displays a text-based graph of the relationships
3. Optionally generates a graphical visualization if required libraries are installed

## Using the Test Environment in Custom Tests

You can use the TestEnvironment class in your own test scripts:

```python
from prove import TestEnvironment

# Create a test environment with a temporary directory, test database, and settings
with TestEnvironment() as env:
    # Run a test function with standardized reporting
    env.run_test("My Custom Test", my_test_function, arg1, arg2)
```

## Extending the Tests

### Adding a New Integration Test

To add a new integration test:

1. Create a new method in the `IntegrationTestHandler` class
2. Update the `display_menu()` function to include your new test
3. Add your test to the `run_interactive_cli()` function
4. Update the appropriate command-line argument handling

### Creating Module-Specific Tests

You can test specific modules by creating `ModuleMessageTest` instances:

```python
# Create a test for communication between two modules
test = ModuleMessageTest(
    name="Module A to Module B Communication",
    source_module="module_a", 
    target_module="module_b",
    message={"type": "request", "action": "do_something"},
    expected_response={"status": "success"}
)

# Run the test
result = test.run(test_handler)
```

## Mock Data Generation

The testing framework provides utilities for generating mock data:

- `generate_test_chunk()`: Generate a test narrative chunk
- `generate_test_states()`: Generate test entity states
- `generate_test_relationships()`: Generate test relationship states
- `generate_test_memory()`: Generate a test memory item
- `mock_api_response()`: Generate a mock API response

## Requirements for Graphics Visualization

To enable graphical visualization of entity relationships, install:

```bash
pip install networkx matplotlib
```

Then run:

```bash
python prove.py --visualize
```

## Troubleshooting

### Module Not Found

If a test reports "Module not found," ensure the module file exists in the expected location:

- `maestro.py`: Root directory
- Agent modules: `agents/` directory
- Memory modules: `memory/` directory
- Database adapters: `adapters/` directory

### Test Failures

Check the following for test failures:

1. Ensure module interfaces match the expected message formats
2. Check that required methods exist in each module
3. Verify database schemas match the expected structure
4. Check log files for error details 

## Test Design

