# MLX vs GGUF Performance Testing Framework

A comprehensive testing framework for comparing memory usage, performance, and stability between MLX and GGUF model formats using LM Studio's API.

## Features

- **Automated Testing**: Run standardized tests across multiple model formats
- **Memory Monitoring**: Real-time memory usage tracking with 100ms sampling
- **Performance Metrics**: TTFT, tokens/second, and throughput measurements
- **MoE Analysis**: Special tests for Mixture of Experts models
- **Memory Leak Detection**: Sequential prompt testing to identify memory issues
- **Comprehensive Reporting**: Markdown reports with visualizations

## Quick Start

1. **Setup Environment**:
   ```bash
   chmod +x setup_environment.sh
   ./setup_environment.sh
   source venv/bin/activate
   ```

2. **Start LM Studio**:
   - Launch LM Studio
   - Ensure API server is running on port 1234
   - Models will be loaded/unloaded automatically during testing
   - Make sure all test models are downloaded in LM Studio

3. **Run Tests**:
   ```bash
   python run_tests.py
   ```

## Usage

### Run All Tests
```bash
python run_tests.py
```

### Run Single Test
```bash
python run_tests.py --single-test "model_id" "gguf" "simple_gen"
```

### Analyze Existing Results
```bash
python run_tests.py --analyze-only results/20250111_120000
```

### Verbose Mode
```bash
python run_tests.py --verbose
```

## Configuration

Edit `config/test_config.yaml` to:
- Add new model pairs
- Adjust test parameters
- Modify prompts
- Configure output settings

## Test Scenarios

1. **Cold Start**: Memory usage from model loading
2. **Simple Generation**: Basic prompt performance
3. **Context Stress**: Large context handling (4000 tokens)
4. **Memory Leak**: Sequential prompts to detect leaks
5. **MoE Specific**: Expert routing pattern analysis

## Output

Results are saved in timestamped directories under `results/`:
- `test_results.json`: Complete test results
- `report.md`: Comprehensive analysis report
- `metrics/`: Raw metrics data (CSV and JSON)
- `plots/`: Visualization graphs

## Model Configuration

Currently configured model pairs:
- Llama 3.3 70B (Q6_K vs MLX)
- Scout 17Bx16E (Q4_K_M vs MLX)
- Mixtral 8x22B (Q4_K_M vs MLX)

## Troubleshooting

1. **LM Studio not connected**:
   - Ensure LM Studio is running
   - Check API is enabled on port 1234
   - Verify models are loaded

2. **Out of memory**:
   - Reduce context size in config
   - Test one model at a time
   - Close other applications

3. **Test failures**:
   - Check `mlx_gguf_testing.log` for details
   - Verify model IDs match loaded models
   - Ensure sufficient disk space

## Extending the Framework

To add new test scenarios:
1. Create new class in `tests/test_scenarios.py`
2. Add prompts to `tests/test_prompts.py`
3. Update configuration in `config/test_config.yaml`

## License

This testing framework is part of the NEXUS project.