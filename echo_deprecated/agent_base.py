#!/usr/bin/env python3
"""
agent_base.py: Base Agent Class for Night City Stories

This module defines the abstract base class for all agent modules in the Night City Stories system.
It establishes the standard communication protocol with the Maestro orchestrator, defines the message
processing lifecycle, and provides common utilities such as configuration validation, logging,
state management, and progress tracking.

Integration with Maestro:
  - Agents must accept messages in the AgentMessage format (see maestro.py).
  - The lifecycle includes:
      1. Initialization (__init__)
      2. Message processing (process_message)
         - Dispatches to specialized handlers based on message type:
           • handle_request for "request" messages
           • handle_response for "response" messages
           • handle_error for "error" messages
  - Existing or new agent modules should inherit from BaseAgent and implement the abstract methods.

Communication Protocol:
  - Agents communicate via a standardized messaging protocol using send_message and receive_message.
  - Messages have a consistent structure with type, action, and parameters.
  - Direct module-to-module communication is supported for efficient operation.
  - Maestro orchestrator can monitor and manage all inter-module communications.

Shared Utilities:
  - Configuration loading and validation via a settings dictionary.
  - Standardized logging using Python's logging module.
  - Internal state management helpers.
  - Progress tracking/telemetry (e.g., track_progress method).
  - Placeholders for memory access wrappers (e.g., via memnon) and other shared utilities.

Usage:
  - Existing agents must be refactored to extend BaseAgent.
  - New agent modules should implement the required interfaces.
  - The test suite below calls functions from the central testing module (`prove.py`).

Requirements:
  - Python 3.8+
  - Proper use of the ABC module for abstract methods.
  - Comprehensive docstrings and type hints.
"""

import logging
import inspect
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union, Callable
from pathlib import Path

class BaseAgent(ABC):
    """
    Base class for all Night City Stories agents.
    
    This class defines the standard interface and shared utilities that all specialized agents must
    implement to ensure consistent behavior and seamless integration with the Maestro orchestrator.
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the agent with optional settings.

        Args:
            settings: Optional dictionary containing configuration settings.
        """
        self.settings: Dict[str, Any] = settings if settings is not None else {}
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)
        self.state: Dict[str, Any] = {}
        self._message_handlers: Dict[str, Callable] = {}
        self._validate_settings()
        self._register_message_handlers()

    def _validate_settings(self) -> None:
        """
        Validate and load configuration settings.

        This method can be overridden by subclasses if additional validation is required.
        Currently, it logs the settings for debugging purposes.
        """
        self.logger.debug("Loaded settings: %s", self.settings)

    def _register_message_handlers(self) -> None:
        """
        Register specialized message handlers for different action types.
        
        This method scans the agent for methods matching the pattern 'on_{action}' and
        registers them as handlers for the corresponding action types.
        """
        for name, method in inspect.getmembers(self, inspect.ismethod):
            if name.startswith('on_'):
                action = name[3:]  # Extract action name (e.g., 'on_build_context' -> 'build_context')
                self._message_handlers[action] = method
                self.logger.debug(f"Registered handler for action: {action}")

    def send_message(self, target_module: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a message to another module.
        
        This method handles the communication protocol between modules. It constructs
        a properly formatted message according to the AgentMessage standard, logs 
        the communication, and returns the response.
        
        Args:
            target_module: Name of the target module to send the message to.
            message: Dictionary containing the message content with fields:
                     - type: Message type (request, response, error)
                     - action: The action to perform
                     - parameters: Dictionary of parameters for the action
        
        Returns:
            Response dictionary from the target module.
            
        Raises:
            ValueError: If the message doesn't contain required fields.
            RuntimeError: If the target module cannot be reached.
        """
        # Validate message format
        if not isinstance(message, dict):
            raise ValueError("Message must be a dictionary")
        
        if 'action' not in message:
            raise ValueError("Message must contain an 'action' field")
        
        # Determine the sender name (this module's name)
        sender_name = self.__class__.__name__.lower()
        if sender_name.endswith('agent'):
            sender_name = sender_name[:-5]  # Remove 'agent' suffix if present
            
        # Format as an AgentMessage
        agent_message = {
            "sender": sender_name,
            "recipient": target_module,
            "message_type": message.get("type", "request"),
            "content": {
                "action": message["action"],
                "parameters": message.get("parameters", {})
            }
        }
            
        # Log the outgoing message
        self.logger.debug(f"Sending message to {target_module}: {message.get('action')}")
        
        try:
            # Get reference to the target module
            target = self._get_target_module(target_module)
            
            if hasattr(target, 'receive_message'):
                # If the target has the receive_message method, send the message directly
                response = target.receive_message(agent_message)
                self.logger.debug(f"Received response from {target_module}")
                return response
            else:
                raise RuntimeError(f"Target module {target_module} does not support receive_message")
                
        except Exception as e:
            self.logger.error(f"Error sending message to {target_module}: {str(e)}")
            return {
                "status": "error",
                "message": f"Communication error: {str(e)}",
                "details": {
                    "target_module": target_module,
                    "action": message.get("action")
                }
            }
    
    def _get_target_module(self, module_name: str) -> Any:
        """
        Get a reference to the target module.
        
        This method attempts to resolve the module name to an actual module instance.
        It first checks if a reference to the maestro instance is available and uses its
        registry, otherwise falls back to a simple import-based approach.
        
        Args:
            module_name: Name of the module to retrieve.
            
        Returns:
            Reference to the requested module.
            
        Raises:
            RuntimeError: If the module cannot be found or accessed.
        """
        # Try to use maestro registry if available
        if hasattr(self, 'maestro') and self.maestro is not None:
            if hasattr(self.maestro, 'agent_registry'):
                agent = self.maestro.agent_registry.get_agent(module_name)
                if agent is not None:
                    return agent["instance"]
        
        # If not available through maestro, try direct import
        # (useful for development and testing)
        try:
            # Try importing as a top-level module first
            module_path = Path(f"{module_name}.py")
            if module_path.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is not None and spec.loader is not None:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module
            
            # Try searching in known module directories
            module_dirs = ["agents", "memory", "adapters"]
            for directory in module_dirs:
                module_path = Path(f"{directory}/{module_name}.py")
                if module_path.exists():
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    if spec is not None and spec.loader is not None:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        return module
                
            # If none of those worked, raise a descriptive exception
            raise RuntimeError(
                f"Module '{module_name}' could not be found. "
                f"Please ensure the module exists in the project directory or "
                f"in one of the subdirectories: {', '.join(module_dirs)}"
            )
            
        except Exception as e:
            self.logger.error(f"Error resolving module '{module_name}': {str(e)}")
            raise RuntimeError(f"Failed to resolve module '{module_name}': {str(e)}")
            
    def set_maestro(self, maestro_instance: Any) -> None:
        """
        Set a reference to the maestro orchestrator.
        
        This method allows the agent to access the maestro's registry and
        other centralized services.
        
        Args:
            maestro_instance: Reference to the maestro orchestrator.
        """
        self.maestro = maestro_instance
        self.logger.debug("Maestro reference set")
    
    def receive_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receive and process a message from another module.
        
        This method implements the standard communication protocol for receiving
        messages from other modules. It parses the message, dispatches to the
        appropriate handler based on the action, and returns a response.
        
        Args:
            message: Dictionary containing the AgentMessage with fields:
                     - sender: Name of the sending module
                     - recipient: Name of the receiving module (this agent)
                     - message_type: Type of message (request, response, error)
                     - content: Dictionary with action and parameters
        
        Returns:
            Response dictionary with fields:
            - status: "success" or "error"
            - message: Description of the result or error
            - data: Optional result data (for success responses)
            - error: Optional error details (for error responses)
        """
        try:
            # Extract message type and content
            sender = message.get("sender", "unknown")
            msg_type = message.get("message_type", "request")
            content = message.get("content", {})
            action = content.get("action", "unknown")
            
            # Log the incoming message
            self.logger.debug(f"Received {msg_type} message from {sender} with action: {action}")
            
            # Check if we have a specialized handler for this action
            handler_name = f"on_{action}"
            if hasattr(self, handler_name) and callable(getattr(self, handler_name)):
                handler = getattr(self, handler_name)
                return handler(content)
            
            # Process based on message type
            if msg_type == "request":
                return self.handle_request(content)
            elif msg_type == "response":
                return self.handle_response(content)
            elif msg_type == "error":
                return self.handle_error(content)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown message type: {msg_type}"
                }
                
        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}")
            return {
                "status": "error",
                "message": f"Error processing message: {str(e)}",
                "details": {
                    "exception_type": type(e).__name__
                }
            }

    @abstractmethod
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a message from the Maestro orchestrator.

        This is a legacy method for backward compatibility with older code.
        New agent implementations should use the receive_message method instead,
        which fully implements the communication protocol.

        Args:
            message: The message dictionary with content and message_type fields.

        Returns:
            A dictionary containing the response data.
        """
        pass

    @abstractmethod
    def handle_request(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a request message type.

        Args:
            content: The content of the message as a dictionary.

        Returns:
            A dictionary with the processed response.
        """
        pass

    @abstractmethod
    def handle_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a response message type.

        Args:
            content: The content of the message as a dictionary.

        Returns:
            A dictionary with the processed response.
        """
        pass

    @abstractmethod
    def handle_error(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an error message type.

        Args:
            content: The content of the message as a dictionary.

        Returns:
            A dictionary containing error details or remedial actions.
        """
        pass

    # Shared Utilities

    def create_response(self, status: str = "success", message: str = "", data: Any = None, error: Any = None) -> Dict[str, Any]:
        """
        Create a standardized response message.
        
        This helper method creates a properly formatted response message following
        the system's communication protocol.
        
        Args:
            status: Response status ("success" or "error")
            message: Human-readable message describing the response
            data: Optional data to include (for success responses)
            error: Optional error details (for error responses)
            
        Returns:
            A properly formatted response dictionary
        """
        response = {
            "status": status,
            "message": message
        }
        
        if data is not None:
            response["data"] = data
            
        if error is not None:
            response["error"] = error
            
        return response
        
    def log(self, message: str, level: int = logging.INFO) -> None:
        """
        Log a message using the agent's logger.

        Args:
            message: The log message.
            level: Logging level (default is logging.INFO).
        """
        self.logger.log(level, message)

    def update_state(self, key: str, value: Any) -> None:
        """
        Update the agent's internal state.

        Args:
            key: The state key.
            value: The new state value.
        """
        self.state[key] = value
        self.logger.debug("State updated: %s = %s", key, value)

    def get_state(self, key: str) -> Any:
        """
        Retrieve a value from the agent's internal state.

        Args:
            key: The state key.

        Returns:
            The state value associated with the key, or None if not found.
        """
        return self.state.get(key)

    def track_progress(self, progress: float) -> None:
        """
        Track and log the progress of an ongoing task.

        Args:
            progress: A float between 0.0 and 1.0 indicating progress.
        """
        self.logger.info("Progress: %.2f%%", progress * 100)


# DummyAgent implementation for testing
class DummyAgent(BaseAgent):
    """
    Dummy implementation of the BaseAgent class for testing purposes.
    
    This class provides simple implementations of all required abstract methods
    and can be used for testing the communication protocol.
    """
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Implement the legacy process_message method for compatibility"""
        return self.receive_message(message)
    
    def handle_request(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a request message"""
        action = content.get("action", "unknown")
        self.logger.debug(f"Handling request with action: {action}")
        
        # Try to dispatch to a specialized handler
        handler_name = f"handle_{action}_request"
        if hasattr(self, handler_name) and callable(getattr(self, handler_name)):
            handler = getattr(self, handler_name)
            return handler(content.get("parameters", {}))
        
        # Default response
        return self.create_response(
            status="success",
            message=f"Handled request for action: {action}",
            data={"action": action, "handled": True}
        )
    
    def handle_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a response message"""
        return self.create_response(
            status="success",
            message="Acknowledged response",
            data={"acknowledged": True}
        )
    
    def handle_error(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an error message"""
        return self.create_response(
            status="success",
            message="Acknowledged error",
            data={"acknowledged": True}
        )
    
    # Example of a specialized action handler
    def on_test_action(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the test_action action"""
        parameters = content.get("parameters", {})
        test_value = parameters.get("test_value", "default")
        
        return self.create_response(
            status="success",
            message=f"Handled test_action with value: {test_value}",
            data={"test_value": test_value, "processed": True}
        )


# ========================
# Test Functions using prove.py
# ========================

if __name__ == "__main__":
    # Import the central testing utilities from prove.py
    try:
        from prove import TestEnvironment
    except ImportError:
        raise ImportError("The central testing module (prove.py) could not be imported.")
    
    # Define test functions for the DummyAgent.
    def test_state_update() -> bool:
        agent = DummyAgent(settings={"test_key": "test_value"})
        agent.update_state("key1", "value1")
        assert agent.get_state("key1") == "value1", "State update failed"
        return True

    def test_handle_request() -> bool:
        agent = DummyAgent(settings={"test_key": "test_value"})
        message = {"message_type": "request", "content": {"data": "test_request"}}
        response = agent.process_message(message)
        assert "response" in response and "test_request" in response["response"], "Handle request failed"
        return True

    def test_handle_response() -> bool:
        agent = DummyAgent(settings={"test_key": "test_value"})
        message = {"message_type": "response", "content": {"data": "test_response"}}
        response = agent.process_message(message)
        assert "response" in response and "test_response" in response["response"], "Handle response failed"
        return True

    def test_handle_error() -> bool:
        agent = DummyAgent(settings={"test_key": "test_value"})
        message = {"message_type": "error", "content": {"error_info": "test_error"}}
        response = agent.process_message(message)
        assert "error" in response and "test_error" in response["error"], "Handle error failed"
        return True
        
    def test_send_receive_message() -> bool:
        agent = DummyAgent(settings={"test_key": "test_value"})
        # Test sending message
        message = {
            "type": "request",
            "action": "test_action",
            "parameters": {"param1": "value1"}
        }
        response = agent.send_message("dummy_target", message)
        assert response["status"] == "success", "Send message failed"
        
        # Test receiving message with specialized handler
        message = {
            "type": "request",
            "action": "test_action",
            "parameters": {"param1": "value1"}
        }
        response = agent.receive_message(message)
        assert response["status"] == "success" and response["message"] == "Test action processed", "Specialized action handler failed"
        return True

    # Run tests using the centralized testing environment from prove.py.
    with TestEnvironment() as env:
        env.run_test("State Update Test", test_state_update)
        env.run_test("Handle Request Test", test_handle_request)
        env.run_test("Handle Response Test", test_handle_response)
        env.run_test("Handle Error Test", test_handle_error)
        env.run_test("Send/Receive Message Test", test_send_receive_message)
