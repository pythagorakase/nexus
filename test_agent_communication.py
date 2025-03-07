#!/usr/bin/env python3
"""
test_agent_communication.py: Test real agent communication without mocks

This module creates actual agent instances using the DummyAgent class from agent_base.py
and tests real message passing between them using the AgentMessage protocol.
"""

import sys
import logging
import json
import types
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_agent_comms")

# Import the necessary classes
try:
    from agent_base import BaseAgent, DummyAgent
    from maestro import Maestro, AgentRegistry, AgentMessage
    HAS_MODULES = True
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure agent_base.py and maestro.py are in the current directory or PYTHONPATH")
    HAS_MODULES = False

def test_direct_communication():
    """Test direct communication between two DummyAgent instances"""
    print("\n=== Testing Direct Agent Communication ===\n")
    
    # Create two agent instances
    agent1 = DummyAgent(settings={"name": "agent1", "test_mode": True})
    agent2 = DummyAgent(settings={"name": "agent2", "test_mode": True})
    agent3 = DummyAgent(settings={"name": "agent3", "test_mode": True})
    
    # Add a specialized action handler to agent2
    def on_custom_action(self, content):
        parameters = content.get("parameters", {})
        test_value = parameters.get("test_value", "default")
        
        return self.create_response(
            status="success",
            message=f"Handled custom_action with value: {test_value}",
            data={"test_value": test_value, "processed": True}
        )
    
    # Add a specialized handler to agent3
    def on_process_data(self, content):
        parameters = content.get("parameters", {})
        data = parameters.get("data", {})
        
        # Process the data
        result = {"processed": True, "original": data}
        
        return self.create_response(
            status="success",
            message="Data processed successfully",
            data=result
        )
    
    # Use this pattern to add methods to an instance
    agent2.on_custom_action = types.MethodType(on_custom_action, agent2)
    agent3.on_process_data = types.MethodType(on_process_data, agent3)
    
    # For direct communication to work, we need to set up references
    # Option 1: Monkey patch the _get_target_module method to return the other agent
    def _get_target_module_override(self, module_name):
        if module_name == "agent2":
            return agent2
        elif module_name == "agent1":
            return agent1
        elif module_name == "agent3":
            return agent3
        raise RuntimeError(f"Unknown module: {module_name}")
    
    agent1._get_target_module = types.MethodType(_get_target_module_override, agent1)
    agent2._get_target_module = types.MethodType(_get_target_module_override, agent2)
    agent3._get_target_module = types.MethodType(_get_target_module_override, agent3)
    
    # Test 1: Sending message from agent1 to agent2
    print("Test 1: Sending message from agent1 to agent2...")
    message1 = {
        "type": "request",
        "action": "custom_action",
        "parameters": {"test_value": "hello world"}
    }
    
    response1 = agent1.send_message("agent2", message1)
    print(f"\nResponse from agent2: {json.dumps(response1, indent=2)}")
    
    # Verify we got the expected response
    success1 = (
        response1 
        and response1.get("status") == "success"
        and "Handled custom_action" in response1.get("message", "")
        and response1.get("data", {}).get("test_value") == "hello world"
    )
    
    # Test 2: Multi-hop communication (agent1 -> agent2 -> agent3)
    print("\nTest 2: Multi-hop communication (agent1 -> agent2 -> agent3)...")
    
    # Add a method to agent2 that forwards to agent3
    def on_forward_to_agent3(self, content):
        parameters = content.get("parameters", {})
        data_to_process = parameters.get("data", {})
        
        # Forward to agent3
        forward_message = {
            "type": "request",
            "action": "process_data", 
            "parameters": {"data": data_to_process}
        }
        
        # Use agent2's send_message to communicate with agent3
        response = self.send_message("agent3", forward_message)
        
        # Return combined result
        return self.create_response(
            status="success",
            message="Forwarded to agent3 and got response",
            data={
                "forwarded": True,
                "agent3_response": response
            }
        )
    
    agent2.on_forward_to_agent3 = types.MethodType(on_forward_to_agent3, agent2)
    
    # Send initial message from agent1 to agent2
    message2 = {
        "type": "request",
        "action": "forward_to_agent3",
        "parameters": {"data": {"key": "value", "test": 123}}
    }
    
    response2 = agent1.send_message("agent2", message2)
    print(f"\nMulti-hop response: {json.dumps(response2, indent=2)}")
    
    # Verify we got the expected multi-hop response
    success2 = (
        response2 
        and response2.get("status") == "success"
        and response2.get("data", {}).get("forwarded") == True
        and "agent3_response" in response2.get("data", {})
        and response2.get("data", {}).get("agent3_response", {}).get("status") == "success"
    )
    
    if success1 and success2:
        print("\n✅ Direct communication test PASSED")
        return True
    else:
        print("\n❌ Direct communication test FAILED")
        if not success1:
            print("  - Test 1 (basic communication) failed")
        if not success2:
            print("  - Test 2 (multi-hop communication) failed")
        return False

def test_maestro_registry_communication():
    """Test communication between agents using Maestro's registry"""
    print("\n=== Testing Communication via Maestro Registry ===\n")
    
    # Create a Maestro instance with a registry
    maestro = Maestro(settings={"test_mode": True})
    
    # Create agent instances
    agent1 = DummyAgent(settings={"name": "agent1", "test_mode": True})
    agent2 = DummyAgent(settings={"name": "agent2", "test_mode": True})
    agent3 = DummyAgent(settings={"name": "agent3", "test_mode": True})
    
    # Add specialized handlers to agent2
    def on_query_data(self, content):
        parameters = content.get("parameters", {})
        query = parameters.get("query", "")
        
        return self.create_response(
            status="success",
            message=f"Processed query: {query}",
            data={"results": [f"Result for {query} 1", f"Result for {query} 2"]}
        )
    
    agent2.on_query_data = types.MethodType(on_query_data, agent2)
    
    # Add specialized handlers to agent3
    def on_process_results(self, content):
        parameters = content.get("parameters", {})
        results = parameters.get("results", [])
        
        processed = [f"Processed: {r}" for r in results]
        
        return self.create_response(
            status="success",
            message=f"Processed {len(results)} results",
            data={"processed_results": processed}
        )
    
    agent3.on_process_results = types.MethodType(on_process_results, agent3)
    
    # Register agents with Maestro's registry
    maestro.agent_registry.register_agent("agent1", agent1, {"enabled": True})
    maestro.agent_registry.register_agent("agent2", agent2, {"enabled": True})
    maestro.agent_registry.register_agent("agent3", agent3, {"enabled": True})
    
    # Connect agents to maestro
    maestro.agent_registry.connect_agents(maestro)
    
    # Now test the communication flow: agent1 -> agent2 -> agent3
    print("Testing multi-agent communication via maestro registry...")
    
    # Step 1: agent1 sends a query to agent2
    query_message = {
        "type": "request",
        "action": "query_data",
        "parameters": {"query": "test query"}
    }
    
    print("Step 1: agent1 sending query to agent2...")
    response1 = agent1.send_message("agent2", query_message)
    print(f"Response from agent2: {json.dumps(response1, indent=2)}")
    
    # Step 2: agent1 sends the results to agent3 for processing
    if response1 and response1.get("status") == "success":
        results = response1.get("data", {}).get("results", [])
        
        process_message = {
            "type": "request",
            "action": "process_results",
            "parameters": {"results": results}
        }
        
        print("\nStep 2: agent1 sending results to agent3 for processing...")
        response2 = agent1.send_message("agent3", process_message)
        print(f"Response from agent3: {json.dumps(response2, indent=2)}")
        
        # Verify final response
        success = (
            response2
            and response2.get("status") == "success"
            and "processed_results" in response2.get("data", {})
            and len(response2.get("data", {}).get("processed_results", [])) == 2
        )
        
        if success:
            print("\n✅ Registry communication test PASSED")
        else:
            print("\n❌ Registry communication test FAILED")
        
        return success
    else:
        print("\n❌ Registry communication test FAILED - Step 1 failed")
        return False

def test_broadcast_communication():
    """Test broadcasting messages to multiple agents"""
    print("\n=== Testing Broadcast Communication ===\n")
    
    # Create a Maestro instance with a registry (we'll create a simpler test)
    # Instead of using Maestro's broadcast, we'll directly send messages to each agent
    
    # Create several agent instances
    agents = {}
    for i in range(1, 4):
        agent_name = f"agent{i}"
        agent = DummyAgent(settings={"name": agent_name, "test_mode": True})
        
        # Add a specialized handler for system_notification
        def on_system_notification(self, content):
            parameters = content.get("parameters", {})
            message = parameters.get("message", "")
            priority = parameters.get("priority", "normal")
            
            return self.create_response(
                status="success",
                message=f"Acknowledged system notification",
                data={
                    "notification_received": True,
                    "message": message,
                    "priority": priority
                }
            )
        
        # Add the handler to this specific agent instance
        agent.on_system_notification = types.MethodType(on_system_notification, agent)
        
        agents[agent_name] = agent
    
    # For direct communication, set up the _get_target_module method for all agents
    def _get_target_module_override(self, module_name):
        if module_name in agents:
            return agents[module_name]
        raise RuntimeError(f"Unknown module: {module_name}")
    
    # Apply the override to all agents
    for agent in agents.values():
        agent._get_target_module = types.MethodType(_get_target_module_override, agent)
    
    # Create a "broadcaster" agent that will send to all others
    broadcaster = DummyAgent(settings={"name": "broadcaster", "test_mode": True})
    broadcaster._get_target_module = types.MethodType(_get_target_module_override, broadcaster)
    
    # Create a notification message
    system_notification = {
        "type": "request",
        "action": "system_notification",
        "parameters": {
            "message": "System maintenance starting in 5 minutes",
            "priority": "high"
        }
    }
    
    print("Broadcasting system notification to all agents...")
    
    # Send the message individually to each agent
    results = {}
    for agent_name, agent in agents.items():
        print(f"  Sending notification to {agent_name}...")
        response = broadcaster.send_message(agent_name, system_notification)
        results[agent_name] = response
    
    print(f"\nBroadcast results: {json.dumps(results, indent=2)}")
    
    # Check if all agents received the message successfully
    success = all(
        result.get("status") == "success" and 
        "notification_received" in result.get("data", {})
        for result in results.values()
    )
    
    if success:
        print("\n✅ Broadcast communication test PASSED")
        return True
    else:
        print("\n❌ Broadcast communication test FAILED")
        return False

def run_all_tests():
    """Run all communication tests"""
    print("=" * 50)
    print("RUNNING AGENT COMMUNICATION TESTS")
    print("=" * 50)
    
    results = []
    
    # Test 1: Direct communication
    results.append(test_direct_communication())
    
    # Test 2: Maestro registry communication
    results.append(test_maestro_registry_communication())
    
    # Test 3: Broadcast communication
    results.append(test_broadcast_communication())
    
    print(f"\nRunning all communication tests")
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"TEST RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 50)
    
    return all(results)

if __name__ == "__main__":
    if not HAS_MODULES:
        print("Required modules not available. Tests cannot run.")
        sys.exit(1)
        
    success = run_all_tests()
    sys.exit(0 if success else 1) 