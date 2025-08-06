#!/usr/bin/env python3
"""
test_config_integration.py: Test the consolidated configuration system

This script tests that the consolidated config_manager.py works correctly
and maintains backward compatibility with code expecting either tinker.py
or config_manager.py.

Usage:
    python test_config_integration.py
"""

import os
import sys
import unittest
import tempfile
import json
import importlib
import shutil
from pathlib import Path


class TestConfigIntegration(unittest.TestCase):
    """Test suite for the consolidated configuration system"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.old_dir = os.getcwd()
        
        # Create a temporary settings file
        self.settings_path = os.path.join(self.test_dir, "settings.json")
        self.test_settings = {
            "database": {
                "path": "test_db.sqlite",
                "verbose_logging": True
            },
            "testing": {
                "use_mock_data": True
            }
        }
        
        with open(self.settings_path, "w") as f:
            json.dump(self.test_settings, f)
        
        # Copy the config_manager.py to the test directory
        shutil.copy("config_manager.py", os.path.join(self.test_dir, "config_manager.py"))
        
        # Create a symbolic link or copy for tinker.py
        tinker_path = os.path.join(self.test_dir, "tinker.py")
        with open(tinker_path, "w") as f:
            f.write("""#!/usr/bin/env python3
\"\"\"
tinker.py: Compatibility import for config_manager.py
\"\"\"

from config_manager import *
""")
        
        # Change to the test directory
        os.chdir(self.test_dir)
        
        # Add the test directory to Python path
        if self.test_dir not in sys.path:
            sys.path.insert(0, self.test_dir)
        
        # Clean up modules if they were already imported
        for module_name in list(sys.modules.keys()):
            if module_name in ['config_manager', 'tinker']:
                del sys.modules[module_name]
    
    def tearDown(self):
        """Clean up after tests"""
        # Close log handlers to prevent resource warnings
        try:
            import config_manager
            if hasattr(config_manager, 'close_log_handlers'):
                config_manager.close_log_handlers()
        except:
            pass
        
        # Change back to the original directory
        os.chdir(self.old_dir)
        
        # Remove the test directory from Python path
        if self.test_dir in sys.path:
            sys.path.remove(self.test_dir)
        
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_direct_import(self):
        """Test importing config_manager directly"""
        # Import the module
        import config_manager
        
        # Reset module state
        config_manager.reset_module_state()
        
        # Test basic functionality
        config_manager.load_config()
        db_path = config_manager.get("database.path")
        self.assertEqual(db_path, "test_db.sqlite")
        
        # Test setting a value
        config_manager.set("database.path", "new_path.db")
        db_path = config_manager.get("database.path")
        self.assertEqual(db_path, "new_path.db")
    
    def test_tinker_import(self):
        """Test importing tinker as an alias for config_manager"""
        # Import the modules
        import config_manager
        import tinker
        
        # Reset module state
        config_manager.reset_module_state()
        
        # Test basic functionality
        tinker.load_config()
        db_path = tinker.get("database.path")
        self.assertEqual(db_path, "test_db.sqlite")
        
        # Test setting a value
        tinker.set("database.path", "new_path.db")
        db_path = tinker.get("database.path")
        self.assertEqual(db_path, "new_path.db")
    
    def test_cross_module_compatibility(self):
        """Test that tinker and config_manager share the same state"""
        # Import config_manager first
        import config_manager
        
        # Reset module state
        config_manager.reset_module_state()
        
        # Load config and set a value
        config_manager.load_config()
        config_manager.set("database.path", "new_path.db")
        
        # Now import tinker - it should share the same state as config_manager
        import tinker
        
        # Get value through tinker without calling load_config again
        db_path = tinker.get("database.path")
        self.assertEqual(db_path, "new_path.db")
    
    def test_backward_compatibility(self):
        """Test backward compatibility features"""
        # Import both modules
        import config_manager
        import tinker
        
        # Reset module state
        config_manager.reset_module_state()
        
        # Test that both modules have the same functions
        self.assertTrue(hasattr(config_manager, "get"))
        self.assertTrue(hasattr(tinker, "get"))
        
        self.assertTrue(hasattr(config_manager, "set"))
        self.assertTrue(hasattr(tinker, "set"))
        
        self.assertTrue(hasattr(config_manager, "get_section"))
        self.assertTrue(hasattr(tinker, "get_section"))
        
        self.assertTrue(hasattr(config_manager, "load_config"))
        self.assertTrue(hasattr(tinker, "load_config"))
        
        self.assertTrue(hasattr(config_manager, "save_config"))
        self.assertTrue(hasattr(tinker, "save_config"))
        
        # Test aliases for backward compatibility
        self.assertTrue(hasattr(config_manager, "save"))
        self.assertTrue(hasattr(tinker, "save"))
        
        self.assertTrue(hasattr(config_manager, "load"))
        self.assertTrue(hasattr(tinker, "load"))
    
    def test_save_and_load(self):
        """Test saving and loading configuration"""
        # Import the module
        import config_manager
        
        # Reset module state
        config_manager.reset_module_state()
        
        # Load initial config
        config_manager.load_config()
        
        # Modify configuration
        config_manager.set("database.path", "modified_db.sqlite")
        config_manager.set("testing.new_value", "test value")
        
        # Save configuration
        config_manager.save_config()
        
        # Reset and reload to verify persistence
        config_manager.reset_module_state()
        config_manager.load_config()
        
        # Check values
        self.assertEqual(config_manager.get("database.path"), "modified_db.sqlite")
        self.assertEqual(config_manager.get("testing.new_value"), "test value")


if __name__ == "__main__":
    unittest.main()