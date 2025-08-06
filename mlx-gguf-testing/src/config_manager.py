"""Configuration management for MLX vs GGUF testing framework."""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, config_path: str = "config/test_config.yaml"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._validate_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")
    
    def _validate_config(self) -> None:
        """Validate configuration structure and required fields."""
        required_sections = ['lmstudio', 'model_pairs', 'test_scenarios', 
                           'metrics', 'prompts', 'output']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate model pairs
        if not self.config.get('model_pairs'):
            raise ValueError("No model pairs defined in configuration")
        
        for idx, pair in enumerate(self.config['model_pairs']):
            required_fields = ['name', 'gguf_id', 'mlx_id', 'context_size']
            for field in required_fields:
                if field not in pair:
                    raise ValueError(f"Model pair {idx} missing required field: {field}")
    
    def get_lmstudio_config(self) -> Dict[str, Any]:
        """Get LM Studio API configuration."""
        return self.config['lmstudio']
    
    def get_model_pairs(self) -> List[Dict[str, Any]]:
        """Get list of model pairs to test."""
        return self.config['model_pairs']
    
    def get_test_scenarios(self) -> Dict[str, Any]:
        """Get test scenario configurations."""
        return self.config['test_scenarios']
    
    def get_metrics_config(self) -> Dict[str, Any]:
        """Get metrics collection configuration."""
        return self.config['metrics']
    
    def get_prompts(self) -> Dict[str, str]:
        """Get test prompts."""
        prompts = self.config['prompts'].copy()
        
        # Load long context from file if specified
        if 'long_context' in prompts and prompts['long_context'].endswith('.txt'):
            try:
                with open(prompts['long_context'], 'r') as f:
                    prompts['long_context'] = f.read()
            except FileNotFoundError:
                logger.warning(f"Long context file not found: {prompts['long_context']}")
                prompts['long_context'] = "This is a placeholder for the long context test. " * 500
        
        return prompts
    
    def get_output_config(self) -> Dict[str, Any]:
        """Get output configuration."""
        return self.config['output']
    
    def get_scenario_config(self, scenario_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific test scenario."""
        return self.config['test_scenarios'].get(scenario_name)