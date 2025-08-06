#!/usr/bin/env python3
"""
Test script to verify LORE's LLM loads correctly with llama-cpp-python
"""

import sys
import json
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from nexus.agents.lore.lore import LORE
from types import SimpleNamespace


def load_settings():
    """Load settings from settings.json"""
    settings_path = Path("settings.json")
    if not settings_path.exists():
        print(f"Error: settings.json not found at {settings_path.absolute()}")
        return None
    
    with open(settings_path, "r") as f:
        return json.load(f)


def test_llm_loading():
    """Test that the LLM loads correctly"""
    print("=" * 60)
    print("Testing LORE LLM Loading")
    print("=" * 60)
    
    # Load settings
    settings = load_settings()
    if not settings:
        return False
    
    # Get LORE settings
    lore_settings = settings.get("Agent Settings", {}).get("LORE", {})
    llm_config = lore_settings.get("llm", {})
    
    print(f"\nLLM Configuration:")
    print(f"  Model Path: {llm_config.get('model_path')}")
    print(f"  Context Size: {llm_config.get('n_ctx')}")
    print(f"  GPU Layers: {llm_config.get('n_gpu_layers')}")
    print(f"  Threads: {llm_config.get('n_threads')}")
    
    # Try to initialize just the LLM part
    try:
        print("\n[1/3] Importing llama-cpp-python...", end="")
        from llama_cpp import Llama
        print(" ✓")
    except ImportError as e:
        print(" ✗")
        print(f"Error: {e}")
        print("\nTo install: CMAKE_ARGS='-DLLAMA_METAL=on' pip install llama-cpp-python")
        return False
    
    # Check model file exists
    model_path = Path(llm_config.get("model_path", ""))
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path
    
    print(f"\n[2/3] Checking model file(s)...", end="")
    
    # Check if this is a multi-file GGUF
    model_dir = model_path.parent
    model_pattern = model_path.stem.replace("-00001-of-00002", "")
    
    # Look for all parts
    model_files = list(model_dir.glob(f"{model_pattern}*.gguf"))
    if not model_files:
        print(" ✗")
        print(f"Error: No model files found matching pattern in {model_dir}")
        return False
    
    # For multi-file GGUFs, we need to use the base name without the part number
    if len(model_files) > 1:
        print(f" ✓ (Multi-file GGUF: {len(model_files)} parts)")
        # Use the base pattern for multi-file models
        base_name = model_pattern + ".gguf"
        model_path = model_dir / base_name
        print(f"  Using base name: {base_name}")
    else:
        if not model_path.exists():
            print(" ✗")
            print(f"Error: Model file not found at {model_path}")
            return False
        model_size = model_path.stat().st_size / (1024**3)
        print(f" ✓ ({model_size:.1f} GB)")
    
    # Try to load the model
    print(f"\n[3/3] Loading model (this may take a moment)...", end="", flush=True)
    try:
        llm = Llama(
            model_path=str(model_path),
            n_ctx=llm_config.get("n_ctx", 32768),
            n_threads=llm_config.get("n_threads", 12),
            n_gpu_layers=llm_config.get("n_gpu_layers", -1),
            seed=llm_config.get("seed", -1),
            f16_kv=llm_config.get("f16_kv", True),
            verbose=False  # Set to True for detailed loading info
        )
        print(" ✓")
        
        # Test a simple prompt
        print("\n" + "=" * 60)
        print("Testing LLM Inference")
        print("=" * 60)
        
        test_prompt = "Hello! Please respond with a brief greeting."
        print(f"\nPrompt: {test_prompt}")
        print("\nGenerating response...")
        
        response = llm(
            test_prompt,
            max_tokens=50,
            temperature=0.7,
            echo=False
        )
        
        generated_text = response['choices'][0]['text'].strip()
        print(f"\nResponse: {generated_text}")
        
        # Print some stats
        print(f"\nTokens generated: {response['usage']['completion_tokens']}")
        print(f"Total tokens: {response['usage']['total_tokens']}")
        
        return True
        
    except Exception as e:
        print(" ✗")
        print(f"\nError loading model: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_lore_initialization():
    """Test full LORE initialization"""
    print("\n" + "=" * 60)
    print("Testing Full LORE Initialization")
    print("=" * 60)
    
    settings = load_settings()
    if not settings:
        return False
    
    try:
        # Create minimal mock objects for LORE initialization
        mock_agent_state = SimpleNamespace(
            id="test-agent-001",
            name="LORE Test",
            memory=SimpleNamespace(compile=lambda: "test memory")
        )
        
        mock_user = SimpleNamespace(
            id="test-user",
            name="Test User"
        )
        
        # Mock managers (not used in basic test)
        mock_message_manager = None
        mock_agent_manager = None
        
        print("\nInitializing LORE agent...", end="", flush=True)
        lore = LORE(
            agent_id="test-lore-001",
            agent_state=mock_agent_state,
            user=mock_user,
            message_manager=mock_message_manager,
            agent_manager=mock_agent_manager,
            settings=settings,
            debug=True
        )
        print(" ✓")
        
        # Test the LLM query method
        print("\nTesting LORE's _query_llm method...")
        test_prompt = "What is your purpose?"
        response = lore._query_llm(test_prompt, temperature=0.7, max_tokens=100)
        
        print(f"\nPrompt: {test_prompt}")
        print(f"Response: {response}")
        
        return True
        
    except Exception as e:
        print(" ✗")
        print(f"\nError initializing LORE: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("NEXUS LORE LLM Test Suite\n")
    
    # Test 1: Basic LLM loading
    if test_llm_loading():
        print("\n✅ LLM loading test passed!")
        
        # Test 2: Full LORE initialization
        if test_lore_initialization():
            print("\n✅ LORE initialization test passed!")
            print("\n🎉 All tests passed! LORE is ready to use.")
        else:
            print("\n❌ LORE initialization test failed!")
    else:
        print("\n❌ LLM loading test failed!")
        print("\nPlease check:")
        print("1. llama-cpp-python is installed with Metal support")
        print("2. Model file exists at the configured path")
        print("3. Model file is not corrupted")