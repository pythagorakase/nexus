#!/usr/bin/env python3
"""
Script to debug import issues with golden_queries_module.
"""

import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("debug_import")

def test_import_methods():
    """Test different ways of importing the golden_queries_module."""
    
    logger.info("Current working directory: %s", os.getcwd())
    logger.info("Current script path: %s", os.path.abspath(__file__))
    
    # Get paths to important directories
    nexus_root = os.path.dirname(os.path.abspath(__file__))
    ir_eval_dir = os.path.join(nexus_root, "ir_eval")
    scripts_dir = os.path.join(nexus_root, "scripts")
    ir_eval_scripts_dir = os.path.join(ir_eval_dir, "scripts")
    
    logger.info("Nexus root directory: %s", nexus_root)
    logger.info("ir_eval directory: %s", ir_eval_dir)
    logger.info("Main scripts directory: %s", scripts_dir)
    logger.info("ir_eval scripts directory: %s", ir_eval_scripts_dir)
    
    # Check if files exist
    scripts_module_path = os.path.join(scripts_dir, "golden_queries_module.py")
    ir_eval_module_path = os.path.join(ir_eval_scripts_dir, "golden_queries_module.py")
    
    logger.info("Does scripts/golden_queries_module.py exist? %s", os.path.exists(scripts_module_path))
    logger.info("Does ir_eval/scripts/golden_queries_module.py exist? %s", os.path.exists(ir_eval_module_path))
    
    # Try importing with various methods
    logger.info("Attempting imports with different methods...")
    
    # Method 1: Direct import
    try:
        logger.info("Method 1: Direct import")
        import golden_queries_module
        logger.info("SUCCESS - Module imported directly")
        logger.info("Module path: %s", golden_queries_module.__file__)
    except ImportError as e:
        logger.info("FAILED - Direct import: %s", e)
    
    # Method 2: Add scripts dir to path and import
    try:
        logger.info("Method 2: Add scripts dir to path and import")
        sys.path.insert(0, scripts_dir)
        import golden_queries_module
        logger.info("SUCCESS - Module imported after adding scripts dir to path")
        logger.info("Module path: %s", golden_queries_module.__file__)
    except ImportError as e:
        logger.info("FAILED - Import after adding scripts dir: %s", e)
    
    # Method 3: Import from scripts package
    try:
        logger.info("Method 3: Import from scripts package")
        from scripts import golden_queries_module
        logger.info("SUCCESS - Module imported from scripts package")
        logger.info("Module path: %s", golden_queries_module.__file__)
    except ImportError as e:
        logger.info("FAILED - Import from scripts package: %s", e)
    
    # Method 4: Import from ir_eval.scripts
    try:
        logger.info("Method 4: Import from ir_eval.scripts")
        from ir_eval.scripts import golden_queries_module
        logger.info("SUCCESS - Module imported from ir_eval.scripts package")
        logger.info("Module path: %s", golden_queries_module.__file__)
    except ImportError as e:
        logger.info("FAILED - Import from ir_eval.scripts: %s", e)

if __name__ == "__main__":
    test_import_methods()