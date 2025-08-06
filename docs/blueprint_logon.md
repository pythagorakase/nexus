# LOGON Utility Module Blueprint (API Communication Handler)

## Overview

LOGON is a utility module called by LORE to interface with the apex LLM (Claude 3.5 or GPT-4o) to generate high-quality narrative text. It manages API communication, formats payloads for optimal narrative generation, handles errors and fallbacks, and processes responses back into the narrative system.

## Key Responsibilities

1. **API Communication** - Manage communication with external LLM APIs
2. **Prompt Engineering** - Format context and instructions for optimal narrative generation
3. **Error Handling** - Implement robust error handling and fallback mechanisms
4. **Response Processing** - Validate and process API responses
5. **Offline Mode** - Provide functionality during API outages
6. **Quality Control** - Apply validation and improvement to generated text

## Technical Requirements

### Integration as Utility Module

- Implemented as a callable utility module
- Use Letta's API client utilities
- Implement custom prompt formatting for narrative generation
- Leverage Letta's error handling mechanisms

### API Management

- Implement connection pooling for efficient API usage
- Create rate limiting and retry logic for robust operation
- Develop API key and authentication management
- Design backup strategies for API failures

### Prompt Engineering

- Create narrative-specific system prompts
- Format context for maximum coherence and continuity
- Design specialized narrative instruction templates
- Optimize token usage for different narrative needs

### Response Processing

- Implement validation for narrative responses
- Extract state change directives from responses
- Parse character and world updates from generated text
- Format narrative text for display and storage

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from typing import List, Dict, Any, Optional, Tuple, Union
import json
import time
import backoff

class LOGON(Agent):
    """
    LOGON (Narrative Generator) agent responsible for generating high-quality
    narrative text via apex LLM APIs.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize LOGON agent with API communication capabilities.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize API configuration
        self.api_config = self._load_api_config()
        
        # Set up LLM clients
        self.llm_clients = self._initialize_llm_clients()
        
        # Track API health status
        self.api_health = {
            "primary": {"status": "healthy", "last_checked": time.time()},
            "secondary": {"status": "healthy", "last_checked": time.time()}
        }
        
        # Initialize prompt templates
        self._initialize_prompt_templates()
    
    def _load_api_config(self) -> Dict[str, Any]:
        """Load API configuration from settings."""
        # Implementation will load from Letta config
        # Returns dict with API settings
        pass
    
    def _initialize_llm_clients(self) -> Dict[str, Any]:
        """Initialize LLM API clients."""
        # Implementation will create clients for different LLMs
        # Returns dict of client name -> client instance
        pass
    
    def _initialize_prompt_templates(self) -> None:
        """Initialize narrative-specific prompt templates."""
        # Implementation will load prompt templates from memory blocks
        pass
    
    def generate_narrative(self, 
                          context: str, 
                          instruction: str,
                          max_tokens: int = 1000,
                          temperature: float = 0.7) -> Dict[str, Any]:
        """
        Generate narrative text using the apex LLM.
        
        Args:
            context: Narrative context including history and world state
            instruction: Specific instructions for the generation task
            max_tokens: Maximum tokens to generate
            temperature: Generation temperature (creativity)
            
        Returns:
            Dict containing generated text and metadata
        """
        # Prepare the prompt payload
        prompt_payload = self._prepare_narrative_prompt(context, instruction)
        
        # Set up API parameters
        api_params = {
            "model": self.api_config["primary_model"],
            "messages": prompt_payload,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Attempt to call primary API
        try:
            response = self._call_api(
                client_key="primary", 
                params=api_params)
            
            # Update API health status
            self._update_api_health("primary", "healthy")
            
            # Process the response
            processed_result = self._process_api_response(response)
            
            return processed_result
            
        except Exception as e:
            # Log the error
            self._log_api_error("primary", str(e))
            
            # Update API health status
            self._update_api_health("primary", "degraded")
            
            # Try fallback if primary fails
            return self._attempt_fallback_generation(context, instruction, max_tokens, temperature)
    
    def _prepare_narrative_prompt(self, context: str, instruction: str) -> List[Dict[str, str]]:
        """Prepare formatted prompt for narrative generation."""
        # Implementation will format context and instruction into prompt messages
        # Returns list of formatted messages for LLM API
        pass
    
    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def _call_api(self, client_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call LLM API with retry logic."""
        # Implementation will call API with specified parameters
        # Returns raw API response
        pass
    
    def _update_api_health(self, api_key: str, status: str) -> None:
        """Update API health status tracking."""
        # Implementation will update health status
        pass
    
    def _log_api_error(self, api_key: str, error_message: str) -> None:
        """Log API error for monitoring."""
        # Implementation will log error details
        pass
    
    def _process_api_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Process API response into standardized format."""
        # Implementation will extract and format generated text
        # Returns structured response with text and metadata
        pass
    
    def _attempt_fallback_generation(self, 
                                   context: str, 
                                   instruction: str,
                                   max_tokens: int,
                                   temperature: float) -> Dict[str, Any]:
        """Attempt fallback generation when primary API fails."""
        # Try secondary model if available
        if self.api_health["secondary"]["status"] == "healthy":
            try:
                # Adjust prompt for secondary model if needed
                fallback_prompt = self._prepare_fallback_prompt(context, instruction)
                
                # Set up API parameters for secondary model
                api_params = {
                    "model": self.api_config["secondary_model"],
                    "messages": fallback_prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                
                # Call secondary API
                response = self._call_api(
                    client_key="secondary", 
                    params=api_params)
                
                # Update API health status
                self._update_api_health("secondary", "healthy")
                
                # Process the response
                processed_result = self._process_api_response(response)
                
                # Mark result as from fallback
                processed_result["source"] = "fallback"
                
                return processed_result
                
            except Exception as e:
                # Log the error
                self._log_api_error("secondary", str(e))
                
                # Update API health status
                self._update_api_health("secondary", "degraded")
        
        # If all APIs fail, enter offline mode
        return self._enter_offline_mode(context, instruction)
    
    def _prepare_fallback_prompt(self, context: str, instruction: str) -> List[Dict[str, str]]:
        """Prepare prompt for fallback generation model."""
        # Implementation will adjust prompt for fallback model
        # Returns formatted messages for fallback model
        pass
    
    def _enter_offline_mode(self, context: str, instruction: str) -> Dict[str, Any]:
        """Enter offline mode when all APIs are unavailable."""
        # Implementation will provide offline mode response
        # Typically just a message saying generation is unavailable
        pass
    
    def extract_world_state_updates(self, generated_text: str) -> List[Dict[str, Any]]:
        """
        Extract world state update directives from generated text.
        
        Args:
            generated_text: Raw text from LLM
            
        Returns:
            List of world state update directives
        """
        # Implementation will use regex or LLM to extract directives
        # Returns structured update instructions
        pass
    
    def extract_character_state_updates(self, generated_text: str) -> List[Dict[str, Any]]:
        """
        Extract character state update directives from generated text.
        
        Args:
            generated_text: Raw text from LLM
            
        Returns:
            List of character state update directives
        """
        # Implementation will use regex or LLM to extract directives
        # Returns structured update instructions
        pass
    
    def format_narrative_for_display(self, generated_text: str) -> str:
        """
        Format generated text for display, removing any directives or metadata.
        
        Args:
            generated_text: Raw text from LLM
            
        Returns:
            Formatted narrative text for display
        """
        # Implementation will clean up text for display
        # Removes directives, metadata, etc.
        pass
    
    def validate_narrative_quality(self, generated_text: str, context: str) -> Dict[str, Any]:
        """
        Validate quality of generated narrative and check for inconsistencies.
        
        Args:
            generated_text: Generated narrative text
            context: Original context provided
            
        Returns:
            Dict containing validation results
        """
        # Implementation will check narrative quality
        # Returns quality metrics and potential issues
        pass
    
    def check_api_health(self) -> Dict[str, Any]:
        """
        Check health status of all configured APIs.
        
        Returns:
            Dict with health status of each API
        """
        # Implementation will perform health checks
        # Returns status information
        pass
    
    def regenerate_with_feedback(self, 
                               context: str, 
                               instruction: str,
                               previous_attempt: str,
                               feedback: str) -> Dict[str, Any]:
        """
        Regenerate narrative with feedback about previous attempt.
        
        Args:
            context: Narrative context
            instruction: Generation instructions
            previous_attempt: Previous generation result
            feedback: Feedback about issues to fix
            
        Returns:
            Dict containing new generation and metadata
        """
        # Implementation will incorporate feedback into prompting
        # Returns improved generation
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform LOGON functions.
        This is the main entry point required by Letta Agent framework.
        
        Args:
            messages: Incoming messages to process
            
        Returns:
            Agent response
        """
        # Implementation will handle different message types and commands
        # Will delegate to appropriate methods based on content
        pass
```

## Implementation Notes

1. **Prompt Engineering**: The narrative generation prompt should include:
   - System instructions for narrative style and quality
   - Format guidelines for state update directives
   - Context about story continuity requirements
   - Specific narrative guidance for current turn

2. **API Management**: Implement robust API handling with:
   - Connection pooling to minimize connection overhead
   - Exponential backoff for retries
   - Circuit breaker pattern for failing APIs
   - Health monitoring for all endpoints

3. **Offline Mode**: When APIs are unavailable:
   - Provide clear message to user about generation being unavailable
   - Enable browsing of existing narrative
   - Allow queue of generation requests for when connectivity returns
   - Support local fallback if available

4. **Quality Control**: Implement the following validations:
   - Narrative continuity with previous content
   - Character consistency with established traits
   - World state consistency with established rules
   - Content safety and appropriateness checks

5. **Integration Considerations**:
   - Coordinate with LORE for context construction
   - Send state update directives to GAIA and PSYCHE
   - Provide generated narrative to MEMNON for storage
   - Handle user feedback for regeneration

## Next Steps

1. Implement API client configuration
2. Develop narrative-specific prompt templates
3. Create robust error handling and fallback logic
4. Build directive extraction system
5. Implement quality validation
6. Test with sample narrative contexts 