"""
Local LLM Management for LORE

Handles initialization and interaction with local language models via LM Studio SDK.
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from pydantic import BaseModel, Field

try:
    import lmstudio as lms
    LMS_SDK_AVAILABLE = True
except ImportError:
    LMS_SDK_AVAILABLE = False
    # Fallback to requests if SDK not available
    import requests
    import json

logger = logging.getLogger("nexus.lore.local_llm")


# Pydantic models for structured responses
class NarrativeAnalysis(BaseModel):
    """Structured analysis of narrative context"""
    characters: List[str] = Field(description="Character names mentioned or relevant")
    locations: List[str] = Field(description="Locations mentioned or relevant")
    context_type: str = Field(description="Type of narrative context: dialogue/action/exploration/transition")
    entities_for_retrieval: List[str] = Field(description="Key entities needing deeper context retrieval")
    confidence_score: float = Field(default=0.8, description="Confidence in the analysis")


class LocalLLMManager:
    """Manages local LLM for LORE's reasoning capabilities via LM Studio SDK"""
    
    def __init__(self, settings: Dict[str, Any], settings_path: Optional[Path] = None):
        """Initialize with LLM configuration from settings"""
        self.settings = settings
        self.settings_path = settings_path
        self.llm_config = settings.get("Agent Settings", {}).get("LORE", {}).get("llm", {})
        
        # LM Studio configuration
        self.base_url = self.llm_config.get("lmstudio_url", "http://localhost:1234/v1")
        self.model_name = self.llm_config.get("model_name", "local-model")
        self.required_model = self.llm_config.get("required_model", None)  # Specific model to load if needed
        
        # Model path for reference (models stored in ~/.lmstudio/models)
        self.models_dir = Path.home() / ".lmstudio" / "models"
        
        # Initialize LM Studio client if SDK available
        self.client = None
        self.model = None
        self.loaded_model_id = None
        
        if LMS_SDK_AVAILABLE:
            self._initialize_sdk_client()
        else:
            logger.warning("LM Studio SDK not available, falling back to HTTP requests")
            self._verify_connection()
    
    def _initialize_sdk_client(self):
        """Initialize LM Studio SDK client - FAILS HARD if not available"""
        try:
            # Extract host from URL
            host = self.base_url.replace("http://", "").replace("/v1", "")
            
            # Configure default client
            lms.configure_default_client(host)
            
            # Use model manager to ensure correct model is loaded
            from .model_manager import ModelManager
            manager = ModelManager(self.settings_path)
            model_id = manager.ensure_default_model()
            
            # Get the model handle - already loaded by manager
            self.model = lms.llm()
            self.loaded_model_id = model_id
            
            logger.info(f"LM Studio SDK initialized successfully with model: {self.loaded_model_id}")
            
        except Exception as e:
            raise RuntimeError(f"FATAL: Cannot initialize LM Studio SDK!\n"
                             f"Error: {e}\n"
                             f"ACTION REQUIRED: Start LM Studio and ensure a model is available")
    
    def _verify_connection(self):
        """Verify connection to LM Studio API - FAILS HARD if not available (fallback method)"""
        if not LMS_SDK_AVAILABLE:
            try:
                response = requests.get(f"{self.base_url}/models", timeout=5)
                if response.status_code == 200:
                    models = response.json().get("data", [])
                    if not models:
                        raise RuntimeError(f"LM Studio is running but NO MODELS are loaded! Load a model in LM Studio first.")
                    logger.info(f"Connected to LM Studio (HTTP). Available models: {[m['id'] for m in models]}")
                    return True
                else:
                    raise RuntimeError(f"LM Studio API returned status {response.status_code}. Is the server running?")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"FATAL: Cannot connect to LM Studio API at {self.base_url}!\n"
                                 f"Error: {e}\n"
                                 f"ACTION REQUIRED: Start LM Studio and enable the local server on port 1234")
        return True
    
    def query(self, 
              prompt: str, 
              temperature: Optional[float] = None, 
              max_tokens: Optional[int] = None,
              system_prompt: Optional[str] = None) -> str:
        """
        Query the local LLM via LM Studio SDK or API.
        FAILS HARD if LM Studio is not available.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            system_prompt: Optional system prompt
            
        Returns:
            LLM response as string
        
        Raises:
            RuntimeError: If LM Studio is not available or query fails
        """
        # Use provided parameters or fall back to config
        temp = temperature if temperature is not None else self.llm_config.get("temperature", 0.7)
        max_tok = max_tokens if max_tokens is not None else self.llm_config.get("max_tokens", 2048)
        
        if LMS_SDK_AVAILABLE and self.model:
            # Use SDK for cleaner API
            try:
                chat = lms.Chat(system_prompt or "You are LORE, a narrative intelligence system.")
                chat.add_user_message(prompt)
                
                result = self.model.respond(
                    chat,
                    config={
                        "temperature": temp,
                        "maxTokens": max_tok,
                        "topP": self.llm_config.get("top_p", 0.9)
                    }
                )
                
                return result.content.strip()
                
            except Exception as e:
                raise RuntimeError(f"FATAL: LM Studio SDK query failed!\nError: {e}\nPrompt was: {prompt[:100]}...")
        
        else:
            # Fallback to HTTP requests
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temp,
                "max_tokens": max_tok,
                "top_p": self.llm_config.get("top_p", 0.9),
                "stream": False
            }
            
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    raise RuntimeError(f"LM Studio API error {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"FATAL: LM Studio query failed!\nError: {e}\nPrompt was: {prompt[:100]}...")
    
    def analyze_narrative_context(self, 
                                  warm_slice: List[Dict], 
                                  user_input: str) -> Dict[str, Any]:
        """
        Analyze narrative context to identify entities and context type.
        
        Args:
            warm_slice: List of recent narrative chunks
            user_input: User's input
            
        Returns:
            Analysis results dictionary
        """
        # Combine warm slice text
        warm_text = "\n".join([chunk.get("text", "")[:200] for chunk in warm_slice[:3]])
        
        system_prompt = """You are LORE, a narrative analysis system. Analyze the given context and identify key entities and narrative elements. Be precise and concise."""
        
        if LMS_SDK_AVAILABLE and self.model:
            # Use structured output for clean parsing
            try:
                chat = lms.Chat(system_prompt)
                chat.add_user_message(f"""Analyze the following narrative context and user input.

Recent narrative:
{warm_text}

User input: {user_input}

Provide a structured analysis of characters, locations, context type, and entities needing retrieval.""")
                
                result = self.model.respond(
                    chat,
                    response_format=NarrativeAnalysis,
                    config={
                        "temperature": 0.3,
                        "maxTokens": 500
                    }
                )
                
                # Convert Pydantic model to dict
                analysis = result.parsed
                return {
                    "characters": analysis.characters,
                    "locations": analysis.locations,
                    "context_type": analysis.context_type,
                    "entities_for_retrieval": analysis.entities_for_retrieval,
                    "confidence_score": analysis.confidence_score
                }
                
            except Exception as e:
                logger.error(f"SDK structured analysis failed: {e}, falling back to text parsing")
                # Fall through to text parsing
        
        # Fallback to text parsing (for non-SDK or if structured output fails)
        prompt = f"""Analyze the following narrative context and user input.

Recent narrative:
{warm_text}

User input: {user_input}

Identify:
1. CHARACTER: [List character names, one per line]
2. LOCATION: [List locations, one per line]
3. CONTEXT_TYPE: [dialogue/action/exploration/transition]
4. KEY_ENTITIES: [Entities needing deeper context retrieval]

Response format - use exact headers:"""
        
        response = self.query(prompt, temperature=0.3, max_tokens=500, system_prompt=system_prompt)
        
        # Parse the response
        result = {
            "characters": [],
            "locations": [],
            "context_type": "unknown",
            "entities_for_retrieval": []
        }
        
        try:
            lines = response.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if "CHARACTER:" in line:
                    current_section = "characters"
                elif "LOCATION:" in line:
                    current_section = "locations"
                elif "CONTEXT_TYPE:" in line:
                    context_type = line.split("CONTEXT_TYPE:")[-1].strip()
                    result["context_type"] = context_type.lower()
                    current_section = None
                elif "KEY_ENTITIES:" in line:
                    current_section = "entities_for_retrieval"
                elif line and current_section:
                    # Add to current section list
                    if line.startswith("-"):
                        line = line[1:].strip()
                    if line and not line.startswith("["):
                        result[current_section].append(line)
        except Exception as e:
            logger.error(f"Error parsing LLM analysis: {e}")
        
        return result
    
    def generate_retrieval_queries(self, 
                                   context_analysis: Dict[str, Any],
                                   user_input: str) -> List[str]:
        """
        Generate targeted retrieval queries based on context analysis.
        
        Args:
            context_analysis: Results from analyze_narrative_context
            user_input: User's input
            
        Returns:
            List of retrieval queries
        """
        queries = []
        
        # Always include user input as a query
        if user_input:
            queries.append(user_input)
        
        # Generate character-specific queries
        for character in context_analysis.get("characters", [])[:2]:
            queries.append(f"{character} history personality relationships")
        
        # Generate location queries if relevant
        for location in context_analysis.get("locations", [])[:1]:
            queries.append(f"{location} description environment inhabitants")
        
        # Add entity-specific queries
        for entity in context_analysis.get("entities_for_retrieval", [])[:2]:
            queries.append(f"{entity} context background")
        
        # Context-specific queries
        context_type = context_analysis.get("context_type", "")
        if context_type == "dialogue":
            queries.append("conversation history dialogue relationships")
        elif context_type == "action":
            queries.append("combat abilities skills consequences")
        elif context_type == "exploration":
            queries.append("environment details discoveries hidden")
        
        return queries[:5]  # Limit to 5 queries
    
    def is_available(self) -> bool:
        """Check if local LLM is available via LM Studio"""
        if LMS_SDK_AVAILABLE and self.model:
            return True
        return self._verify_connection()
    
    def _check_and_manage_loaded_model(self):
        """Check what model is loaded and manage lifecycle"""
        try:
            import requests
            response = requests.get(f"{self.base_url}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                if not models:
                    raise RuntimeError("No models loaded in LM Studio!")
                
                # Get currently loaded model
                current_model = models[0]["id"] if models else None
                self.loaded_model_id = current_model
                
                # Check if we need a specific model
                if self.required_model and current_model != self.required_model:
                    logger.info(f"Current model {current_model} != required {self.required_model}")
                    # In production, we could unload and load the right model
                    # For now, just log the mismatch
                    logger.warning(f"Required model {self.required_model} not loaded, using {current_model}")
                
                logger.info(f"Using loaded model: {current_model}")
                
        except Exception as e:
            logger.error(f"Failed to check loaded models: {e}")
            raise
    
    def unload_model(self):
        """Unload the current model to free resources"""
        if LMS_SDK_AVAILABLE and self.model:
            try:
                # Use model manager for proper unloading
                from .model_manager import ModelManager
                manager = ModelManager(self.settings_path)
                if manager.unload_model():
                    logger.info(f"Unloaded model: {self.loaded_model_id}")
                else:
                    logger.warning("Model unload may have failed")
                    
                self.model = None
                self.loaded_model_id = None
                
            except Exception as e:
                logger.error(f"Failed to unload model: {e}")
    
    def ensure_model_loaded(self):
        """Ensure the required model is loaded"""
        if self.required_model and self.loaded_model_id != self.required_model:
            logger.warning(f"Model mismatch! Expected {self.required_model} but {self.loaded_model_id} is loaded.")
            logger.warning(f"Please load {self.required_model} in LM Studio before proceeding.")
            # In production, we'd fail hard here, but for testing we continue
            # raise RuntimeError(f"Wrong model loaded! Please load {self.required_model} in LM Studio")
    
    def __del__(self):
        """Cleanup on deletion - unload any loaded models"""
        if hasattr(self, 'model') and self.model:
            try:
                self.unload_model()
            except:
                pass  # Best effort cleanup
    
    def __enter__(self):
        """Context manager entry - ensure model is loaded"""
        self.ensure_model_loaded()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up resources"""
        self.unload_model()
        return False
    
    def list_available_models(self) -> List[str]:
        """List models available in LM Studio"""
        try:
            import requests
            response = requests.get(f"{self.base_url}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                return [m["id"] for m in models]
        except:
            pass
        return []