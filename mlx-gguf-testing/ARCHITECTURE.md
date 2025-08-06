# MLX vs GGUF Testing Framework Architecture

## Overview
This framework provides automated testing to compare memory usage, performance, and stability between MLX and GGUF model formats using LM Studio's API.

## Directory Structure
```
mlx-gguf-testing/
├── config/
│   └── test_config.yaml         # Main configuration file
├── src/
│   ├── __init__.py
│   ├── config_manager.py        # Configuration loading and validation
│   ├── metrics_collector.py     # System metrics collection
│   ├── lmstudio_client.py       # LM Studio API client
│   ├── test_runner.py           # Test orchestration
│   └── results_analyzer.py      # Analysis and reporting
├── tests/
│   ├── __init__.py
│   ├── test_prompts.py          # Test prompt definitions
│   └── test_scenarios.py        # Test scenario implementations
├── results/
│   └── [timestamped folders]    # Test results
├── requirements.txt
├── setup_environment.sh         # Environment setup script
├── run_tests.py                 # Main entry point
└── README.md

```

## Component Design

### 1. Configuration Manager (`config_manager.py`)
- Loads and validates YAML configuration
- Provides configuration access to all components
- Handles model pair definitions
- Manages test parameters

### 2. Metrics Collector (`metrics_collector.py`)
- Real-time system monitoring (100ms sampling)
- Memory tracking (RSS, VMS, percent)
- CPU utilization monitoring
- GPU memory tracking (macOS specific)
- Thread-safe metric storage
- Export to CSV/JSON

### 3. LM Studio Client (`lmstudio_client.py`)
- Robust API client with retry logic
- Model loading/unloading
- Streaming response handling
- Connection pooling
- Timeout management
- Error recovery

### 4. Test Runner (`test_runner.py`)
- Orchestrates test execution
- Progress tracking with tqdm
- Interrupt handling (graceful shutdown)
- Result collection
- State management between tests

### 5. Results Analyzer (`results_analyzer.py`)
- Statistical analysis
- Visualization generation (matplotlib)
- Markdown report creation
- Comparison algorithms
- Memory leak detection

## Test Scenarios

### Cold Start Test
1. Record baseline memory
2. Load model via API
3. Measure load time
4. Track memory after load
5. Idle for 60 seconds
6. Record idle memory

### Simple Generation Test
1. Use 200-word standardized prompt
2. Track memory before/during/after
3. Measure Time To First Token (TTFT)
4. Calculate tokens/second
5. Record peak memory usage

### Context Stress Test
1. Load 4000-token document
2. Request comprehensive summary
3. Monitor memory scaling with context
4. Track generation performance
5. Measure memory recovery

### Memory Leak Detection
1. Run 10 varied prompts sequentially
2. 5-second delay between prompts
3. Track memory after each completion
4. Plot memory growth curve
5. Calculate leak rate

### MoE-Specific Test (Scout & Mixtral only)
1. Math problem → technical experts
2. Creative writing → language experts
3. Code generation → programming experts
4. Factual queries → knowledge experts
5. Track expert activation patterns

## Implementation Phases

### Phase 1: Core Infrastructure
- Environment setup automation
- Configuration system
- Basic metrics collection
- API client foundation

### Phase 2: Test Implementation
- Scenario implementations
- Prompt management
- Progress tracking
- Error handling

### Phase 3: Analysis & Reporting
- Statistical analysis
- Visualization generation
- Report templates
- Comparison logic

### Phase 4: Testing & Refinement
- Unit tests
- Integration tests
- Full test suite execution
- Documentation

## Key Design Decisions

1. **Modular Architecture**: Each component is independent and testable
2. **Configuration-Driven**: All parameters externalized to YAML
3. **Extensible**: Easy to add new models and test scenarios
4. **Robust Error Handling**: Graceful failures with detailed logging
5. **Reproducible**: Fixed seeds and deterministic execution
6. **Real-time Monitoring**: 100ms sampling for accurate metrics

## Success Metrics

- Automated execution without manual intervention
- Clear memory usage differences between formats
- Accurate performance metrics
- Actionable insights in reports
- Framework extensibility for future models