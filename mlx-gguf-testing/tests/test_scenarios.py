"""Test scenario implementations for MLX vs GGUF testing."""

import time
import logging
from typing import Dict, Any, List
from dataclasses import dataclass
from tqdm import tqdm

from src.lmstudio_sdk_client_v2 import LMStudioSDKClient
from src.metrics_collector import MetricsCollector
from tests.test_prompts import TEST_PROMPTS, get_long_context

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Container for test results."""
    scenario: str
    model_type: str  # 'gguf' or 'mlx'
    model_id: str
    metrics: Dict[str, Any]
    errors: List[str]
    
    
class TestScenario:
    """Base class for test scenarios."""
    
    def __init__(self, client: LMStudioSDKClient, collector: MetricsCollector):
        self.client = client
        self.collector = collector
        
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        """Run the test scenario."""
        raise NotImplementedError


class ColdStartTest(TestScenario):
    """Measure memory and load time from cold start."""
    
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        logger.info(f"Running cold start test for {model_id}")
        errors = []
        
        # Note: Model is already loaded by test runner, so we just measure idle memory
        # Start metrics collection
        label = f"cold_start_{model_type}_{model_id.replace('/', '_')}"
        
        # Get initial memory state
        self.collector.start_collection(label)
        
        try:
            # Verify model is loaded
            models = self.client.get_models()
            model_loaded = any(m.get('id') == model_id for m in models)
            
            if not model_loaded:
                errors.append(f"Model {model_id} not loaded")
            
            # Idle for specified time to measure steady-state memory
            idle_time = config.get('idle_time', 60)
            logger.info(f"Measuring idle memory for {idle_time} seconds...")
            time.sleep(idle_time)
            
        except Exception as e:
            errors.append(f"Cold start test error: {str(e)}")
        finally:
            self.collector.stop_collection()
        
        # Get metrics summary
        summary = self.collector.get_summary(label)
        
        metrics = {
            'idle_time': config.get('idle_time', 60),
            'memory_summary': summary.get('memory', {}),
            'cpu_summary': summary.get('cpu', {})
        }
        
        return TestResult(
            scenario='cold_start',
            model_type=model_type,
            model_id=model_id,
            metrics=metrics,
            errors=errors
        )


class SimpleGenerationTest(TestScenario):
    """Simple generation with standardized prompt."""
    
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        logger.info(f"Running simple generation test for {model_id}")
        errors = []
        
        # Start metrics collection
        label = f"simple_gen_{model_type}_{model_id.replace('/', '_')}"
        self.collector.start_collection(label)
        
        try:
            # Generate with simple prompt
            result = self.client.generate(
                model=model_id,
                prompt=TEST_PROMPTS['simple'],
                max_tokens=config.get('max_tokens', 500),
                temperature=config.get('temperature', 0.7),
                stream=True  # To measure TTFT
            )
            
            if 'error' in result:
                errors.append(result['error'])
            
        except Exception as e:
            errors.append(f"Simple generation error: {str(e)}")
            result = {}
        finally:
            self.collector.stop_collection()
        
        # Get metrics summary
        summary = self.collector.get_summary(label)
        
        metrics = {
            'generation_metrics': {
                'duration': result.get('duration', 0),
                'ttft': result.get('ttft'),
                'tokens_generated': result.get('tokens_generated', 0),
                'tokens_per_second': result.get('tokens_per_second', 0)
            },
            'memory_summary': summary.get('memory', {}),
            'cpu_summary': summary.get('cpu', {})
        }
        
        return TestResult(
            scenario='simple_generation',
            model_type=model_type,
            model_id=model_id,
            metrics=metrics,
            errors=errors
        )


class ContextStressTest(TestScenario):
    """Load large context and request summary."""
    
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        logger.info(f"Running context stress test for {model_id}")
        errors = []
        
        # Start metrics collection
        label = f"context_stress_{model_type}_{model_id.replace('/', '_')}"
        self.collector.start_collection(label)
        
        try:
            # Generate with long context
            long_prompt = get_long_context()
            
            result = self.client.generate(
                model=model_id,
                prompt=long_prompt,
                max_tokens=config.get('max_tokens', 1000),
                temperature=config.get('temperature', 0.7),
                stream=True
            )
            
            if 'error' in result:
                errors.append(result['error'])
            
        except Exception as e:
            errors.append(f"Context stress error: {str(e)}")
            result = {}
        finally:
            self.collector.stop_collection()
        
        # Get metrics summary
        summary = self.collector.get_summary(label)
        
        metrics = {
            'context_size': len(get_long_context().split()),
            'generation_metrics': {
                'duration': result.get('duration', 0),
                'ttft': result.get('ttft'),
                'tokens_generated': result.get('tokens_generated', 0),
                'tokens_per_second': result.get('tokens_per_second', 0)
            },
            'memory_summary': summary.get('memory', {}),
            'cpu_summary': summary.get('cpu', {})
        }
        
        return TestResult(
            scenario='context_stress',
            model_type=model_type,
            model_id=model_id,
            metrics=metrics,
            errors=errors
        )


class MemoryLeakTest(TestScenario):
    """Sequential prompts to detect memory leaks."""
    
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        logger.info(f"Running memory leak test for {model_id}")
        errors = []
        memory_checkpoints = []
        
        # Start metrics collection
        label = f"memory_leak_{model_type}_{model_id.replace('/', '_')}"
        self.collector.start_collection(label)
        
        try:
            num_prompts = config.get('num_prompts', 10)
            delay = config.get('delay_between', 5)
            
            # Test prompts cycle
            prompts = ['simple', 'math', 'creative', 'code', 'reasoning', 'memory_test']
            
            for i in tqdm(range(num_prompts), desc="Memory leak test"):
                # Select prompt
                prompt_key = prompts[i % len(prompts)]
                prompt = TEST_PROMPTS[prompt_key]
                
                # Generate
                result = self.client.generate(
                    model=model_id,
                    prompt=prompt,
                    max_tokens=200,
                    temperature=0.7
                )
                
                if 'error' in result:
                    errors.append(f"Prompt {i}: {result['error']}")
                
                # Wait between prompts
                time.sleep(delay)
                
                # Record memory checkpoint
                current_metrics = self.collector.get_summary(label)
                if current_metrics:
                    memory_checkpoints.append({
                        'iteration': i,
                        'memory_mb': current_metrics.get('memory', {}).get('final_mb', 0)
                    })
            
        except Exception as e:
            errors.append(f"Memory leak test error: {str(e)}")
        finally:
            self.collector.stop_collection()
        
        # Calculate memory growth
        if len(memory_checkpoints) >= 2:
            initial_memory = memory_checkpoints[0]['memory_mb']
            final_memory = memory_checkpoints[-1]['memory_mb']
            memory_growth = final_memory - initial_memory
            growth_per_iteration = memory_growth / (len(memory_checkpoints) - 1)
        else:
            memory_growth = 0
            growth_per_iteration = 0
        
        # Get metrics summary
        summary = self.collector.get_summary(label)
        
        metrics = {
            'num_prompts': config.get('num_prompts', 10),
            'memory_checkpoints': memory_checkpoints,
            'memory_growth_mb': memory_growth,
            'growth_per_iteration_mb': growth_per_iteration,
            'memory_summary': summary.get('memory', {}),
            'cpu_summary': summary.get('cpu', {})
        }
        
        return TestResult(
            scenario='memory_leak',
            model_type=model_type,
            model_id=model_id,
            metrics=metrics,
            errors=errors
        )


class MoESpecificTest(TestScenario):
    """Test different expert routing patterns for MoE models."""
    
    def run(self, model_id: str, model_type: str, config: Dict[str, Any]) -> TestResult:
        logger.info(f"Running MoE-specific test for {model_id}")
        errors = []
        expert_results = {}
        
        # Start metrics collection
        label = f"moe_specific_{model_type}_{model_id.replace('/', '_')}"
        self.collector.start_collection(label)
        
        try:
            prompt_types = config.get('prompt_types', ['math', 'creative', 'code', 'factual'])
            
            for prompt_type in tqdm(prompt_types, desc="MoE expert routing"):
                # Get appropriate prompt
                prompt_key = f"moe_{prompt_type}"
                prompt = TEST_PROMPTS.get(prompt_key, TEST_PROMPTS[prompt_type])
                
                # Generate
                start_time = time.time()
                result = self.client.generate(
                    model=model_id,
                    prompt=prompt,
                    max_tokens=300,
                    temperature=0.7,
                    stream=True
                )
                
                if 'error' in result:
                    errors.append(f"{prompt_type}: {result['error']}")
                
                expert_results[prompt_type] = {
                    'duration': result.get('duration', 0),
                    'ttft': result.get('ttft'),
                    'tokens_per_second': result.get('tokens_per_second', 0),
                    'response_length': len(result.get('content', ''))
                }
                
                # Brief pause between different expert tests
                time.sleep(2)
            
        except Exception as e:
            errors.append(f"MoE test error: {str(e)}")
        finally:
            self.collector.stop_collection()
        
        # Get metrics summary
        summary = self.collector.get_summary(label)
        
        metrics = {
            'expert_results': expert_results,
            'memory_summary': summary.get('memory', {}),
            'cpu_summary': summary.get('cpu', {})
        }
        
        return TestResult(
            scenario='moe_specific',
            model_type=model_type,
            model_id=model_id,
            metrics=metrics,
            errors=errors
        )


# Factory function to get test scenario
def get_test_scenario(scenario_name: str, client: LMStudioSDKClient, 
                     collector: MetricsCollector) -> TestScenario:
    """Get test scenario instance by name."""
    scenarios = {
        'cold_start': ColdStartTest,
        'simple_gen': SimpleGenerationTest,
        'context_stress': ContextStressTest,
        'memory_leak': MemoryLeakTest,
        'moe_specific': MoESpecificTest
    }
    
    scenario_class = scenarios.get(scenario_name)
    if not scenario_class:
        raise ValueError(f"Unknown test scenario: {scenario_name}")
    
    return scenario_class(client, collector)