#!/usr/bin/env python3
"""
logon.py: Narrative Generator Agent for Night City Stories

This module serves as a conduit to an apex LLM (like Claude 3.5 or GPT-4o),
delivering an API payload and receiving the response. It does not have a role
in the creation of the API payload, nor in the processing of the response.
It is merely a responsible, patient, and reliable courier.

The NarrativeGenerator class inherits from BaseAgent and implements the 
required interface for seamless integration with the Maestro orchestrator.

Usage:
    from logon import NarrativeGenerator
    
    generator = NarrativeGenerator()
    response = generator.generate_narrative(context_package)
"""

import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path

# Import from project modules
from agent_base import BaseAgent
import config_manager as config
import prove

# Configure logging
logger = logging.getLogger(__name__)

class NarrativeGenerator(BaseAgent):
    """
    Agent responsible for generating narrative text via API calls to apex LLMs.
    
    This class handles communication with external API services (Claude 3.5 or GPT-4o),
    manages prompt formatting, error recovery, and response handling.
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the NarrativeGenerator agent.
        
        Args:
            settings: Optional dictionary containing configuration settings.
                     If None, settings will be loaded from config_manager.
        """
        # Initialize base class
        super().__init__(settings)
        
        # Load settings from config manager if not provided
        if not settings:
            self.settings = {
                "model": config.get("narrative.api_model", "gpt-4o"),
                "temperature": config.get("narrative.temperature", 0.7),
                "max_retries": config.get("agents.logon.max_retries", 3),
                "retry_delay": config.get("agents.logon.retry_delay", 5),
                "offline_mode": config.get("agents.logon.offline_mode", False),
                "api_keys": {
                    "openai": os.getenv("OPENAI_API_KEY", ""),
                    "anthropic": os.getenv("ANTHROPIC_API_KEY", "")
                }
            }
        
        # Initialize state
        self.state = {
            "last_api_call_time": 0,
            "api_call_count": 0,
            "last_error": None,
            "offline_mode": self.settings.get("offline_mode", False)
        }
        
        # Log initialization
        self.log(f"NarrativeGenerator initialized with model: {self.settings['model']}")
    
    def _validate_settings(self) -> None:
        """
        Validate and prepare required settings.
        
        Ensures API keys are available for the selected model.
        """
        model = self.settings.get("model", "gpt-4o")
        
        # Check for required API keys based on selected model
        if "gpt" in model and not self.settings.get("api_keys", {}).get("openai"):
            self.log("Warning: OpenAI API key not found but GPT model selected", logging.WARNING)
        
        if "claude" in model and not self.settings.get("api_keys", {}).get("anthropic"):
            self.log("Warning: Anthropic API key not found but Claude model selected", logging.WARNING)
        
        # Log selected model and temperature
        self.log(f"Model: {model}, Temperature: {self.settings.get('temperature', 0.7)}")
    
    def process_message(self, message: Any) -> Dict[str, Any]:
        """
        Process a message from the Maestro orchestrator.
        
        Routes the message to the appropriate handler based on message type.
        
        Args:
            message: The message object from Maestro.
            
        Returns:
            Dictionary containing the response.
        """
        msg_type = message.get("message_type", "request")
        content = message.get("content", {})
        
        if msg_type == "request":
            return self.handle_request(content)
        elif msg_type == "response":
            return self.handle_response(content)
        elif msg_type == "error":
            return self.handle_error(content)
        else:
            self.log(f"Unknown message type: {msg_type}", logging.WARNING)
            return {"error": f"Unknown message type: {msg_type}"}
    
    def handle_request(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle request messages, which typically contain context packages for
        generating narrative text.
        
        Args:
            content: Dictionary containing the request content.
            
        Returns:
            Dictionary containing the response with generated narrative.
        """
        self.log("Processing narrative generation request")
        
        # Extract context package from request content
        context_package = content.get("context_package", {})
        temperature = content.get("temperature", self.settings.get("temperature", 0.7))
        
        # Generate narrative based on context package
        try:
            narrative_response = self.generate_narrative(context_package, temperature)
            return {
                "status": "success",
                "narrative": narrative_response.get("narrative", ""),
                "db_updates": narrative_response.get("db_updates", {}),
                "metadata": {
                    "model_used": self.settings.get("model"),
                    "timestamp": time.time()
                }
            }
        except Exception as e:
            self.log(f"Error generating narrative: {str(e)}", logging.ERROR)
            self.update_state("last_error", str(e))
            return {
                "status": "error",
                "error": str(e),
                "metadata": {
                    "model_used": self.settings.get("model"),
                    "timestamp": time.time()
                }
            }
    
    def handle_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle response messages, which typically contain feedback or
        confirmations about previously generated narratives.
        
        Args:
            content: Dictionary containing the response content.
            
        Returns:
            Dictionary containing the acknowledgment.
        """
        self.log("Processing response message")
        
        # Extract relevant information from response
        status = content.get("status", "unknown")
        narrative_id = content.get("narrative_id")
        
        if status == "success":
            self.log(f"Narrative {narrative_id} was successfully processed")
        else:
            self.log(f"Narrative {narrative_id} processing status: {status}", logging.WARNING)
        
        return {
            "status": "acknowledged",
            "message": f"Response for narrative {narrative_id} received"
        }
    
    def handle_error(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle error messages related to narrative generation.
        
        Args:
            content: Dictionary containing error details.
            
        Returns:
            Dictionary containing error handling response.
        """
        self.log(f"Processing error: {content.get('error', 'Unknown error')}", logging.ERROR)
        
        # Record error in state
        self.update_state("last_error", content.get("error"))
        
        # Check if we need to switch to offline mode
        if "api" in content.get("error_type", ""):
            self.log("API error detected, considering switching to offline mode", logging.WARNING)
            if self.settings.get("auto_offline_mode", True):
                self.update_state("offline_mode", True)
                self.log("Switched to offline mode due to API error", logging.WARNING)
        
        return {
            "status": "error_acknowledged",
            "action_taken": "recorded_error",
            "offline_mode": self.get_state("offline_mode")
        }
    
    # Core functionality methods
    
    def generate_narrative(self, context_package: Dict[str, Any], temperature: float = 0.7) -> Dict[str, Any]:
        """
        Generate narrative text by making an API call to the selected LLM.
        
        Args:
            context_package: Dictionary containing all the context needed for narrative generation.
            temperature: Controls randomness in generation, higher is more random.
            
        Returns:
            Dictionary containing the generated narrative and database updates.
        """
        # Check if offline mode is active
        if self.get_state("offline_mode") or not self.is_api_available():
            self.log("Operating in offline mode, using fallback generation", logging.WARNING)
            return self._generate_offline_narrative(context_package)
        
        # Format prompts based on context package
        system_prompt = context_package.get("system_prompt", self._get_default_system_prompt())
        user_prompt = self.format_prompt(context_package)
        
        # Select model and make API call
        model = self.settings.get("model", "gpt-4o")
        
        # Track API call in state
        self.update_state("last_api_call_time", time.time())
        self.update_state("api_call_count", self.get_state("api_call_count", 0) + 1)
        
        # Make API call with retries
        response = None
        max_retries = self.settings.get("max_retries", 3)
        retry_delay = self.settings.get("retry_delay", 5)
        
        for attempt in range(max_retries):
            try:
                if "gpt" in model:
                    response = self._call_openai_api(system_prompt, user_prompt, model, temperature)
                elif "claude" in model:
                    response = self._call_anthropic_api(system_prompt, user_prompt, model, temperature)
                else:
                    raise ValueError(f"Unsupported model: {model}")
                
                # Process the response
                return self._process_api_response(response, context_package)
                
            except Exception as e:
                self.log(f"API call attempt {attempt+1} failed: {str(e)}", logging.ERROR)
                self.update_state("last_error", str(e))
                
                if attempt < max_retries - 1:
                    self.log(f"Retrying in {retry_delay} seconds...", logging.WARNING)
                    time.sleep(retry_delay)
                else:
                    self.log("All retry attempts failed, switching to offline mode", logging.ERROR)
                    self.update_state("offline_mode", True)
                    return self._generate_offline_narrative(context_package)
    
    def format_prompt(self, context_package: Dict[str, Any]) -> str:
        """
        Format the user prompt from the context package.
        
        Args:
            context_package: Dictionary containing all context components.
            
        Returns:
            Formatted user prompt string.
        """
        # Extract components from context package
        storytelling_rules = context_package.get("storytelling_rules", {})
        character_summaries = context_package.get("character_summaries", {})
        character_relationships = context_package.get("character_relationships", {})
        structured_summaries = context_package.get("structured_summaries", {})
        location_status = context_package.get("location_status", {})
        hidden_information = context_package.get("hidden_information", {})
        faction_data = context_package.get("faction_data", {})
        recent_narrative = context_package.get("recent_narrative", "")
        user_input = context_package.get("user_input", "")
        ai_queries = context_package.get("ai_queries", {})
        retrieved_context = context_package.get("retrieved_context", {})
        
        # Build the user prompt in the specified order
        user_prompt = (
            "### Parameters\n"
            f"**Storytelling Rules:**\n{json.dumps(storytelling_rules, indent=2)}\n\n"
            
            "### Summarized Information\n"
            f"**Character Summaries:**\n{json.dumps(character_summaries, indent=2)}\n\n"
            f"**Character Relationships:**\n{json.dumps(character_relationships, indent=2)}\n\n"
            f"**Structured Summaries:**\n{json.dumps(structured_summaries, indent=2)}\n\n"
            f"**Location Status:**\n{json.dumps(location_status, indent=2)}\n\n"
            f"**Hidden Information:**\n{json.dumps(hidden_information, indent=2)}\n\n"
            f"**Faction Data:**\n{json.dumps(faction_data, indent=2)}\n\n"
            
            "### Narrative Body\n"
            f"**Recent Narrative:** (approx. {len(recent_narrative)} characters)\n{recent_narrative}\n\n"
            f"**User Input:**\n{user_input}\n\n"
            
            "### Contextual Augmentation\n"
            f"**AI Queries:**\n{json.dumps(ai_queries, indent=2)}\n\n"
            f"**Retrieved Context:**\n{json.dumps(retrieved_context, indent=2)}\n\n"
            
            "Based on the above payload, generate a JSON object with two keys:\n"
            "  - 'narrative': A narrative passage that continues the story.\n"
            "  - 'db_updates': A JSON object with update instructions for the database.\n"
            "Return your response as pure JSON with no additional text."
        )
        
        return user_prompt
    
    def _get_default_system_prompt(self) -> str:
        """
        Get the default system prompt for narrative generation.
        
        Returns:
            System prompt string.
        """
        return (
            "You are an AI narrative generator working on an interactive storytelling project.\n"
            "Your task is to generate a JSON object with two keys:\n"
            "  - 'narrative': A narrative passage continuing the story in a cinematic, emotionally engaging style.\n"
            "  - 'db_updates': A structured set of update instructions for the database (e.g., hidden information updates).\n"
            "Follow the storytelling rules provided and do not include any extra commentary.\n"
        )
    
    def _call_openai_api(self, system_prompt: str, user_prompt: str, model: str, temperature: float) -> Dict[str, Any]:
        """
        Make an API call to OpenAI.
        
        Args:
            system_prompt: The system prompt to use.
            user_prompt: The user prompt containing context.
            model: The OpenAI model to use (e.g., "gpt-4o").
            temperature: Controls randomness in generation.
            
        Returns:
            API response object.
        """
        try:
            import openai
            
            # Ensure API key is set
            openai.api_key = self.settings.get("api_keys", {}).get("openai")
            if not openai.api_key:
                raise ValueError("OpenAI API key not found")
            
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            
            return response.choices[0].message.content
            
        except ImportError:
            self.log("OpenAI package not installed. Install with: pip install openai", logging.ERROR)
            raise
        except Exception as e:
            self.log(f"OpenAI API call failed: {str(e)}", logging.ERROR)
            raise
    
    def _call_anthropic_api(self, system_prompt: str, user_prompt: str, model: str, temperature: float) -> Dict[str, Any]:
        """
        Make an API call to Anthropic (Claude).
        
        Args:
            system_prompt: The system prompt to use.
            user_prompt: The user prompt containing context.
            model: The Anthropic model to use (e.g., "claude-3-opus-20240229").
            temperature: Controls randomness in generation.
            
        Returns:
            API response object.
        """
        try:
            import anthropic
            
            # Ensure API key is set
            api_key = self.settings.get("api_keys", {}).get("anthropic")
            if not api_key:
                raise ValueError("Anthropic API key not found")
            
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=4096,
            )
            
            return response.content[0].text
            
        except ImportError:
            self.log("Anthropic package not installed. Install with: pip install anthropic", logging.ERROR)
            raise
        except Exception as e:
            self.log(f"Anthropic API call failed: {str(e)}", logging.ERROR)
            raise
    
    def _process_api_response(self, response_content: str, context_package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process and clean the API response.
        
        Args:
            response_content: The raw response content from the API.
            context_package: Original context package for reference.
            
        Returns:
            Cleaned and structured response dictionary.
        """
        # Clean and parse JSON from response
        try:
            # Try to extract JSON if surrounded by backticks or other markers
            if "```json" in response_content and "```" in response_content:
                # Extract the JSON part
                start = response_content.find("```json") + 7
                end = response_content.find("```", start)
                json_content = response_content[start:end].strip()
                response_dict = json.loads(json_content)
            else:
                # Assume the entire response is JSON
                response_dict = json.loads(response_content)
            
            # Ensure expected keys are present
            if "narrative" not in response_dict:
                self.log("Response missing 'narrative' key", logging.WARNING)
                response_dict["narrative"] = "The narrative continues..."
            
            if "db_updates" not in response_dict:
                self.log("Response missing 'db_updates' key", logging.WARNING)
                response_dict["db_updates"] = {}
            
            # Save narrative to history if needed
            self.save_narrative_to_history(response_dict["narrative"], context_package)
            
            return response_dict
            
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse JSON response: {str(e)}", logging.ERROR)
            # Return a fallback response
            return {
                "narrative": "The story continues, but technical difficulties obscure the details...",
                "db_updates": {},
                "error": f"JSON parsing error: {str(e)}",
                "raw_response": response_content[:1000]  # First 1000 chars for debugging
            }
    
    def _generate_offline_narrative(self, context_package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a fallback narrative when offline mode is active.
        
        Args:
            context_package: Context package containing story information.
            
        Returns:
            Dictionary containing a simple fallback narrative.
        """
        self.log("Generating offline fallback narrative", logging.WARNING)
        
        # Get user input if available
        user_input = context_package.get("user_input", "")
        
        # Create a simple acknowledgment narrative
        fallback_narrative = (
            f"The Night City mainframe is experiencing connectivity issues. "
            f"Your input has been recorded: \"{user_input}\"\n\n"
            f"Normal narrative generation will resume when connectivity is restored."
        )
        
        return {
            "narrative": fallback_narrative,
            "db_updates": {},
            "offline_mode": True
        }
    
    def save_narrative_to_history(self, narrative_text: str, context_package: Dict[str, Any]) -> None:
        """
        Save the generated narrative to history if required.
        
        Args:
            narrative_text: The generated narrative text.
            context_package: Original context package with metadata.
        """
        save_history = self.settings.get("save_history", True)
        if not save_history:
            return
        
        try:
            # Construct filename based on episode/timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            episode = context_package.get("episode", "unknown_episode")
            filename = f"narrative_{episode}_{timestamp}.txt"
            
            # Get output directory from config
            output_dir = config.get("paths.output_dir", "output/")
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Save narrative to file
            with open(Path(output_dir) / filename, "w", encoding="utf-8") as f:
                f.write(narrative_text)
                
            self.log(f"Narrative saved to {filename}")
            
        except Exception as e:
            self.log(f"Failed to save narrative to history: {str(e)}", logging.ERROR)
    
    def is_api_available(self) -> bool:
        """
        Check if the API service is available.
        
        Returns:
            Boolean indicating whether the API is available.
        """
        # If explicitly in offline mode, return False
        if self.get_state("offline_mode"):
            return False
        
        # If recent API calls worked, assume it's still available
        last_error = self.get_state("last_error")
        if not last_error:
            return True
        
        # Perform simple connectivity check to API endpoint
        try:
            model = self.settings.get("model", "gpt-4o")
            
            if "gpt" in model:
                response = requests.get("https://api.openai.com/v1/models", 
                                       timeout=5,
                                       headers={"Authorization": f"Bearer {self.settings.get('api_keys', {}).get('openai')}"})
                return response.status_code == 200
            elif "claude" in model:
                response = requests.get("https://api.anthropic.com/v1/models",
                                       timeout=5,
                                       headers={"x-api-key": self.settings.get("api_keys", {}).get("anthropic")})
                return response.status_code == 200
            else:
                return False
                
        except Exception as e:
            self.log(f"API availability check failed: {str(e)}", logging.WARNING)
            return False


# ========================
# Test Functions using prove.py
# ========================

if __name__ == "__main__":
    # Import the central testing utilities
    try:
        from prove import TestEnvironment
    except ImportError:
        raise ImportError("The central testing module (prove.py) could not be imported.")
    
    # Define test functions
    def test_initialization():
        """Test agent initialization with default settings."""
        generator = NarrativeGenerator()
        assert generator.settings["model"] in ["gpt-4o", "claude-3.5-sonnet"], "Default model not set correctly"
        return True
    
    def test_prompt_formatting():
        """Test prompt formatting with sample context package."""
        generator = NarrativeGenerator()
        context_package = {
            "storytelling_rules": {"rule1": "Show, don't tell"},
            "character_summaries": {"Alex": "Cyberpunk hacker"},
            "recent_narrative": "Night City glowed in the rain.",
            "user_input": "Alex heads to the market."
        }
        formatted_prompt = generator.format_prompt(context_package)
        assert "Night City glowed in the rain." in formatted_prompt, "Recent narrative not included in prompt"
        assert "Alex heads to the market." in formatted_prompt, "User input not included in prompt" 
        return True
    
    def test_offline_mode():
        """Test offline mode narrative generation."""
        generator = NarrativeGenerator()
        generator.update_state("offline_mode", True)
        context_package = {
            "user_input": "Alex heads to the market."
        }
        result = generator.generate_narrative(context_package)
        assert "offline_mode" in result and result["offline_mode"] is True, "Offline mode flag not set in result"
        assert "narrative" in result and len(result["narrative"]) > 0, "No narrative generated in offline mode"
        return True
    
    # Run tests
    with TestEnvironment() as env:
        env.run_test("Initialization Test", test_initialization)
        env.run_test("Prompt Formatting Test", test_prompt_formatting)
        env.run_test("Offline Mode Test", test_offline_mode) 