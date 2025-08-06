"""Test orchestration for MLX vs GGUF testing."""

import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from tqdm import tqdm

from src.config_manager import ConfigManager
from src.metrics_collector import MetricsCollector
from src.lmstudio_sdk_client_v2 import LMStudioSDKClient
from tests.test_scenarios import get_test_scenario, TestResult

logger = logging.getLogger(__name__)


class TestRunner:
    """Orchestrates test execution."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        
        # Always use SDK client
        lm_config = config_manager.get_lmstudio_config()
        logger.info("Initializing LM Studio SDK client")
        self.client = LMStudioSDKClient(**lm_config)
        
        self.collector = MetricsCollector(
            sampling_interval=config_manager.get_metrics_config()['sampling_interval']
        )
        self.results: List[TestResult] = []
        self._interrupted = False
        
        # Setup interrupt handler
        signal.signal(signal.SIGINT, self._handle_interrupt)
    
    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signal gracefully."""
        logger.info("\nInterrupt received. Finishing current test...")
        self._interrupted = True
    
    def _verify_memory_state(self, checkpoint: str) -> None:
        """Verify memory state and log it."""
        import psutil
        mem = psutil.virtual_memory()
        
        # Check if any models are still loaded
        loaded_models = self.client.get_models()
        
        logger.info(f"\nMemory checkpoint: {checkpoint}")
        logger.info(f"  System memory: {mem.percent:.1f}% used ({mem.used / (1024**3):.2f} GB / {mem.total / (1024**3):.2f} GB)")
        logger.info(f"  Available memory: {mem.available / (1024**3):.2f} GB")
        logger.info(f"  Models loaded: {len(loaded_models)} - {[m['id'] for m in loaded_models]}")
        
        # Warning if memory usage is high
        if mem.percent > 85:
            logger.warning(f"High memory usage detected: {mem.percent:.1f}%")
    
    def _cleanup_models(self) -> None:
        """Clean up any loaded models with verification."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                loaded_models = self.client.get_models()
                if not loaded_models:
                    logger.info("No models to clean up")
                    return
                    
                logger.info(f"Cleaning up {len(loaded_models)} loaded models (attempt {attempt + 1}/{max_attempts})...")
                logger.info(f"Models to unload: {[m['id'] for m in loaded_models]}")
                
                # Unload each model
                for model in loaded_models:
                    model_id = model['id']
                    logger.info(f"Unloading: {model_id}")
                    success = self.client.unload_model(model_id)
                    if not success:
                        logger.warning(f"Failed to unload {model_id}, will retry")
                
                # Wait for cleanup
                logger.info("Waiting for memory cleanup...")
                time.sleep(10)
                
                # Verify all models are unloaded
                remaining = self.client.get_models()
                if not remaining:
                    logger.info("All models successfully unloaded")
                    return
                else:
                    logger.warning(f"Still loaded after cleanup: {[m['id'] for m in remaining]}")
                    if attempt < max_attempts - 1:
                        time.sleep(5)  # Extra wait before retry
                        
            except Exception as e:
                logger.error(f"Error during model cleanup attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(5)
                    
        # Final check
        try:
            final_models = self.client.get_models()
            if final_models:
                logger.error(f"Failed to unload all models after {max_attempts} attempts. Still loaded: {[m['id'] for m in final_models]}")
                raise RuntimeError("Model cleanup failed")
        except Exception as e:
            logger.error(f"Final cleanup check failed: {e}")
    
    def run_all_tests(self) -> None:
        """Run all configured tests."""
        # Check API availability
        if not self.client.wait_for_ready():
            logger.error("LM Studio API is not available. Please start LM Studio.")
            sys.exit(1)
        
        # Get available models
        available_models = [m['id'] for m in self.client.get_models()]
        logger.info(f"Currently loaded models in LM Studio: {available_models}")
        
        # Ensure clean state - unload any existing models
        if available_models:
            logger.info("Found models already loaded at startup. Cleaning up...")
            self._cleanup_models()
            
            # Verify cleanup was successful
            remaining = self.client.get_models()
            if remaining:
                logger.error(f"Cleanup failed. Models still loaded: {[m['id'] for m in remaining]}")
                logger.error("Please manually unload models in LM Studio before running tests")
                sys.exit(1)
        
        # Run tests for each model pair
        model_pairs = self.config.get_model_pairs()
        
        try:
            for pair in model_pairs:
                if self._interrupted:
                    break
                    
                logger.info(f"\n{'='*60}")
                logger.info(f"Testing model pair: {pair['name']}")
                logger.info(f"{'='*60}")
                
                # Memory verification before loading
                self._verify_memory_state("before_test")
                
                # Test GGUF version
                gguf_id = pair['gguf_id']
                logger.info(f"\nPreparing to test GGUF model: {gguf_id}")
                
                # Load GGUF model
                if self.client.load_model(gguf_id):
                    self._run_model_tests(pair, 'gguf', gguf_id)
                    # Unload model after tests
                    self.client.unload_model()
                    logger.info(f"Unloaded GGUF model: {gguf_id}")
                    
                    # Verify memory was freed
                    self._verify_memory_state("after_gguf_unload")
                else:
                    logger.error(f"Failed to load GGUF model: {gguf_id}")
                    logger.info("Tip: Make sure the model is downloaded in LM Studio")
                    logger.info("Skipping tests for this model")
                
                if self._interrupted:
                    break
                
                # Test MLX version
                mlx_id = pair['mlx_id']
                logger.info(f"\nPreparing to test MLX model: {mlx_id}")
                
                # Load MLX model
                if self.client.load_model(mlx_id):
                    self._run_model_tests(pair, 'mlx', mlx_id)
                    # Unload model after tests
                    self.client.unload_model()
                    logger.info(f"Unloaded MLX model: {mlx_id}")
                    
                    # Verify memory was freed
                    self._verify_memory_state("after_mlx_unload")
                else:
                    logger.error(f"Failed to load MLX model: {mlx_id}")
                    logger.info("Tip: Make sure the model is downloaded in LM Studio")
                    logger.info("Skipping tests for this model")
        finally:
            # Ensure cleanup even if interrupted
            self._cleanup_models()
        
        # Save results
        self._save_results()
    
    def _run_model_tests(self, pair: Dict[str, Any], model_type: str, 
                        model_id: str) -> None:
        """Run all tests for a specific model."""
        logger.info(f"\nTesting {model_type.upper()} model: {model_id}")
        
        scenarios = pair.get('test_scenarios', [])
        scenario_configs = self.config.get_test_scenarios()
        
        for scenario_name in tqdm(scenarios, desc=f"{model_type.upper()} tests"):
            if self._interrupted:
                break
            
            try:
                # Get scenario configuration
                scenario_config = scenario_configs.get(scenario_name, {})
                
                # Create and run scenario
                scenario = get_test_scenario(
                    scenario_name,
                    self.client,
                    self.collector
                )
                
                logger.info(f"Running {scenario_name}...")
                result = scenario.run(model_id, model_type, scenario_config)
                
                # Add context size to result
                result.metrics['context_size'] = pair['context_size']
                
                self.results.append(result)
                
                # Log any errors
                if result.errors:
                    for error in result.errors:
                        logger.error(f"  Error: {error}")
                
                # Brief pause between tests
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Failed to run {scenario_name}: {e}")
                self.results.append(TestResult(
                    scenario=scenario_name,
                    model_type=model_type,
                    model_id=model_id,
                    metrics={},
                    errors=[str(e)]
                ))
    
    def _save_results(self) -> None:
        """Save test results and metrics."""
        output_config = self.config.get_output_config()
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime(output_config['timestamp_format'])
        output_dir = Path(output_config['results_dir']) / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"\nSaving results to {output_dir}")
        
        # Save raw metrics
        if output_config.get('save_raw_data', True):
            self.collector.save_to_csv(output_dir / 'metrics')
            self.collector.save_to_json(output_dir / 'metrics')
        
        # Save test results summary
        self._save_results_summary(output_dir)
    
    def _save_results_summary(self, output_dir: Path) -> None:
        """Save summary of all test results."""
        summary = {
            'test_run': {
                'timestamp': datetime.now().isoformat(),
                'interrupted': self._interrupted,
                'total_tests': len(self.results),
                'failed_tests': sum(1 for r in self.results if r.errors)
            },
            'results': []
        }
        
        for result in self.results:
            summary['results'].append({
                'scenario': result.scenario,
                'model_type': result.model_type,
                'model_id': result.model_id,
                'success': len(result.errors) == 0,
                'errors': result.errors,
                'metrics': result.metrics
            })
        
        # Save as JSON
        import json
        with open(output_dir / 'test_results.json', 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved test results summary")
    
    def run_single_test(self, model_id: str, model_type: str, 
                       scenario_name: str) -> TestResult:
        """Run a single test scenario."""
        scenario_config = self.config.get_scenario_config(scenario_name)
        if not scenario_config:
            raise ValueError(f"Unknown scenario: {scenario_name}")
        
        scenario = get_test_scenario(
            scenario_name,
            self.client,
            self.collector
        )
        
        return scenario.run(model_id, model_type, scenario_config)