# Automated MLX vs GGUF Performance Testing Suite

## Objective

Create an automated testing framework to compare memory usage, performance, and stability between MLX and GGUF model formats using LM Studio's API. The tests should run identical prompts through both model formats and collect detailed metrics for analysis.

## Phase 1: EXPLORE

Please explore the current environment and gather information about:

1. **Python Environment**
   - Current Python version
   - Existing virtual environments
   - Package management setup (pip/conda)

2. **LM Studio Configuration**
   - Available models in both MLX and GGUF formats
   - API endpoints and documentation
   - Current server configuration

3. **System Resources**
   - macOS version and hardware specs
   - Available memory monitoring tools
   - Current memory usage baseline

4. **Project Structure**
   - Existing codebase organization
   - Any relevant testing utilities
   - Current dependencies

## Phase 2: PLAN

Based on your exploration, create a detailed implementation plan:

### Environment Setup Plan

- Create isolated virtual environment: `mlx-gguf-testing`
- Required dependencies:
  - `requests` - API communication
  - `psutil` - System monitoring
  - `pandas` - Data analysis
  - `matplotlib` - Visualization
  - `pyyaml` - Configuration management
  - `tabulate` - Report formatting

### Test Architecture Design

```
mlx-gguf-testing/
├── config/
│   └── test_config.yaml
├── src/
│   ├── metrics_collector.py
│   ├── lmstudio_client.py
│   ├── test_runner.py
│   └── results_analyzer.py
├── tests/
│   ├── test_prompts.py
│   └── test_scenarios.py
├── results/
│   └── [timestamped folders]
├── requirements.txt
└── run_tests.py
```

### Test Scenarios

1. **Cold Start Test**
   - Measure memory before LM Studio starts
   - Load model and measure memory
   - Record load time
   - Let model idle for 60 seconds

2. **Simple Generation Test**
   - Use standardized 200-word prompt
   - Measure memory before/during/after
   - Record TTFT and tokens/second

3. **Context Stress Test**
   - Load 4000-token document
   - Request comprehensive summary
   - Monitor memory scaling

4. **Memory Leak Detection**
   - Run 10 varied prompts sequentially
   - Track memory after each completion
   - Plot memory growth curve

5. **MoE-Specific Test** (Scout & Mixtral only)
   - Math problem (expert routing)
   - Creative writing (different experts)
   - Code generation (technical experts)
   - Factual queries (knowledge experts)

### Model Test Pairs

| Model | GGUF Format | MLX Format |
|-------|-------------|------------|
| Llama 3.3 70B | Q8_K | 8-bit |
| Scout 17Bx16E | Q4_K_M | 4-bit |
| Mixtral 8Ex22B | IQ4_XS | 4-bit |

## Phase 3: CODE

Implement the framework using sub-agents for parallel development:

### Sub-Agent 1: Environment & Configuration Module

**Tasks:**
- Set up virtual environment automation
- Create configuration management system
- Implement model pair definitions
- Design test parameter structure

**Key Files:**
- `setup_environment.sh`
- `config/test_config.yaml`
- `src/config_manager.py`

### Sub-Agent 2: Metrics Collection System

**Tasks:**
- Implement real-time memory monitoring
- Create CPU/GPU utilization tracking
- Design metric storage format
- Build export functionality

**Key Components:**
- SystemMonitor class with 100ms sampling
- Metric aggregation methods
- CSV/JSON export options
- Real-time plotting capability

### Sub-Agent 3: LM Studio API Client

**Tasks:**
- Create robust API client
- Implement model management endpoints
- Add streaming response handling
- Build error recovery mechanisms

**Key Features:**
- Automatic retry logic
- Connection pooling
- Response validation
- Timeout management

### Sub-Agent 4: Test Orchestration Engine

**Tasks:**
- Build test execution framework
- Implement progress tracking
- Create result collection system
- Design interrupt handling

**Standard Test Prompts:**
```python
TEST_PROMPTS = {
    "simple": "Explain quantum entanglement in 200 words.",
    "math": "Solve step by step: If a train travels 120km in 1.5 hours, what is its average speed?",
    "creative": "Write a haiku about artificial intelligence.",
    "code": "Write a Python function to calculate fibonacci numbers.",
    "reasoning": "What are the pros and cons of remote work?",
    "memory_test": "List 20 different types of fruits, then categorize them by color.",
    "long_context": "[4000 token document about climate change]"
}
```

### Sub-Agent 5: Analysis & Reporting Module

**Tasks:**
- Create statistical analysis functions
- Build visualization generators
- Design markdown report templates
- Implement comparison algorithms

**Report Sections:**
- Executive summary
- Detailed metrics tables
- Memory usage graphs
- Performance comparisons
- Model-specific insights
- Recommendations

## Phase 4: COMMIT

### Testing Protocol

1. **Unit Tests**
   - Test each module independently
   - Validate metric collection accuracy
   - Verify API client functionality

2. **Integration Tests**
   - Run single model pair test
   - Validate end-to-end workflow
   - Check report generation

3. **Full Test Suite**
   - Execute all model pairs
   - Monitor system stability
   - Validate result consistency

### Documentation Requirements

1. **README.md**
   - Installation instructions
   - Usage examples
   - Troubleshooting guide

2. **API Documentation**
   - Module interfaces
   - Configuration options
   - Extension points

3. **Results Template**
   - Standardized output format
   - Interpretation guide
   - Comparison methodology

### Automation Scripts

Create main execution script with:
- Environment validation
- LM Studio status check
- Test execution orchestration
- Result archiving
- Cleanup procedures

## Expected Deliverables

### 1. Comprehensive Test Report

**Memory Analysis:**
- Initial vs. peak vs. final memory usage
- Memory efficiency ratio (model size / RAM usage)
- Memory leak detection results
- Growth patterns over time

**Performance Metrics:**
- Load times comparison
- TTFT (Time To First Token)
- Tokens per second
- Response consistency

**Model-Specific Insights:**
- Dense vs. MoE behavior differences
- Expert activation patterns (MoE models)
- Context handling comparison

### 2. Visual Outputs

- Memory usage timeline graphs
- Performance comparison charts
- Memory efficiency scatter plots
- Model-specific behavior visualizations

### 3. Actionable Recommendations

- Best format for each model type
- Memory optimization strategies
- Deployment recommendations for NEXUS LORE
- Specific guidance for Scout 17Bx16E

## Implementation Notes

- Ensure all operations are idempotent
- Add comprehensive logging throughout
- Include system information in all reports
- Make tests reproducible with fixed seeds
- Implement graceful shutdown handling
- Consider adding warmup phases
- Archive raw data for future analysis

## Success Criteria

- Automated tests run without manual intervention
- Results clearly show memory usage differences
- Performance metrics are accurately captured
- Reports provide actionable insights
- Framework is extensible for future models

Proceed with EXPLORE phase and present findings before moving to PLAN phase implementation.