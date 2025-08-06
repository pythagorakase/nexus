# NEMESIS Utility Module Blueprint (Threat Director)

## Overview

NEMESIS is a utility module called by LORE for managing narrative tension and ensuring compelling stakes throughout the story. It tracks potential threats across multiple domains, analyzes user decisions for risk-taking behavior, and directs the introduction and evolution of appropriate consequences and challenges. NEMESIS maintains awareness of narrative pacing needs, helping to prevent the common AI tendency toward conflict avoidance.

## Key Responsibilities

1. **Threat Modeling** - Track potential threats across physical, social, resource, and psychological domains
2. **Risk Assessment** - Analyze user decisions and actions for risk-taking behavior
3. **Consequence Management** - Ensure meaningful consequences for risky player choices
4. **Tension Calibration** - Maintain appropriate narrative tension levels throughout story arcs
5. **Recovery Pathway Design** - Define meaningful effort required to overcome setbacks
6. **Threat Directive Generation** - Provide specific guidance to the Apex AI for threat integration

## Technical Requirements

### Integration with Letta Framework

- Implemented as a callable utility module
- Utilize Letta's memory system for threat tracking
- Implement database schema extensions for threat profiles and evolution
- Leverage Letta's query system for retrieving character and world state information

### Memory Management

- Create specialized memory blocks for different threat types
- Define schema for tracking threat progression and lifecycle stages
- Implement versioning of threats for tracking evolution
- Develop efficient threat relationship mapping to characters and world elements

### Threat Analysis

- Implement decision analysis for risk assessment
- Define metrics for threat likelihood and impact
- Create multi-domain threat classification system
- Develop threat evolution tracking mechanisms with explicit triggers

### Directive Generation

- Format threat directives for inclusion in Apex AI prompts
- Balance directive specificity vs. creative freedom
- Scale directive intensity based on user preference settings
- Provide multiple consequence options with explicit escalation/de-escalation paths

## Pseudocode Implementation

```python
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from typing import List, Dict, Any, Optional, Tuple, Union
import datetime
import json

class NEMESIS(Agent):
    """
    NEMESIS (Threat Director) agent responsible for managing narrative tension
    through threat modeling, risk assessment, and consequence management.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: AgentState,
                 user,
                 **kwargs):
        """
        Initialize NEMESIS agent with specialized threat memory blocks and settings.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework
            user: User information
            **kwargs: Additional arguments
        """
        # Initialize parent Agent class
        super().__init__(interface, agent_state, user, **kwargs)
        
        # Initialize specialized threat memory blocks if not present
        self._initialize_threat_memory_blocks()
        
        # Threat tracking systems
        self.active_threats = {}
        self.threat_templates = {}
        
        # Threat domains
        self.threat_domains = {
            "physical": ["injury", "health", "mobility", "safety"],
            "social": ["relationship", "reputation", "alliance", "conflict"],
            "resource": ["equipment", "finance", "territory", "data"],
            "psychological": ["stress", "trauma", "addiction", "manipulation"]
        }
        
        # Threat lifecycle stages with transition triggers
        self.lifecycle_stages = [
            "inception",     # Initial introduction of potential threat
            "gestation",     # Hidden development, not yet apparent to characters
            "manifestation", # First visible signs of the threat
            "escalation",    # Increasing impact and urgency
            "culmination",   # Peak threat moment
            "resolution",    # Threat concludes or is overcome
            "aftermath"      # Lasting effects even after resolution
        ]
        
        # Load settings from configuration
        self._load_settings()
    
    def _initialize_threat_memory_blocks(self):
        """Initialize specialized memory blocks for threat tracking if not present."""
        # Check if threat blocks exist and create if needed
        required_blocks = [
            "threat_profiles", "consequence_history", 
            "risk_assessments", "tension_settings"
        ]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=50000,  # Generous limit for threat data
                    description=f"Threat {block_name} tracking"
                )
                # Add block to memory
                # Implementation will use Letta API to create block
    
    def _load_settings(self) -> None:
        """Load tension settings from settings.json."""
        # Implementation will retrieve settings from config
        self.debug = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("debug")
        self.difficulty_level = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("difficulty_level")
        self.threat_diversity_min = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("threat_diversity_min")
        self.consequence_probability_base = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("consequence_probability_base")
        self.escalation_factor = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("escalation_factor")
        self.recovery_complexity = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("recovery_complexity")
    
    def analyze_user_decision(self, 
                             decision_text: str,
                             character_context: Dict[str, Any],
                             world_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a user decision for risk-taking and potential consequences.
        
        Args:
            decision_text: Text of user's decision
            character_context: Current character state information
            world_context: Current world state information
            
        Returns:
            Dict containing risk assessment and potential consequences
        """
        # Extract risk patterns from decision
        risk_assessment = self._assess_risk_level(
            decision_text, character_context, world_context)
        
        # Identify relevant active threats
        relevant_threats = self._identify_relevant_threats(
            risk_assessment, character_context)
        
        # Determine potential consequences based on direct causality
        potential_consequences = self._determine_potential_consequences(
            risk_assessment, relevant_threats)
        
        # Generate risk report
        risk_report = {
            "decision_text": decision_text,
            "risk_level": risk_assessment["overall_risk"],
            "risk_domains": risk_assessment["domain_risks"],
            "relevant_threats": relevant_threats,
            "potential_consequences": potential_consequences,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Store risk assessment for later reference
        self._store_risk_assessment(risk_report)
        
        return risk_report
    
    def _assess_risk_level(self, 
                         decision_text: str,
                         character_context: Dict[str, Any],
                         world_context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risk level of user decision across multiple domains."""
        # Implementation will use LLM to analyze risk levels
        # Returns dict with overall risk and domain-specific risks
        pass
    
    def _identify_relevant_threats(self, 
                                 risk_assessment: Dict[str, Any],
                                 character_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify active threats relevant to the risk assessment."""
        # Implementation will query active threats and filter by relevance
        # Returns list of relevant threats
        pass
    
    def _determine_potential_consequences(self, 
                                        risk_assessment: Dict[str, Any],
                                        relevant_threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Determine potential consequences based on direct causality."""
        # Implementation will generate potential consequences
        # Each consequence has domain, severity, probability, causal explanation
        # Returns list of potential consequences
        pass
    
    def _store_risk_assessment(self, risk_report: Dict[str, Any]) -> None:
        """Store risk assessment for future reference."""
        # Implementation will save assessment to memory block
        pass
    
    def create_threat(self, 
                    threat_type: str,
                    threat_data: Dict[str, Any]) -> str:
        """
        Create a new threat profile.
        
        Args:
            threat_type: Type of threat (template identifier)
            threat_data: Initial threat data
            
        Returns:
            ID of newly created threat
        """
        # Generate unique ID for threat
        threat_id = self._generate_threat_id(threat_type, threat_data)
        
        # Get threat template if available
        template = self.threat_templates.get(threat_type, {})
        
        # Merge template with provided data
        threat_profile = self._initialize_threat_profile(template, threat_data)
        
        # Add explicit transition triggers for each lifecycle stage
        threat_profile["transition_triggers"] = self._generate_transition_triggers(
            threat_profile)
        
        # Validate threat profile
        self._validate_threat_profile(threat_profile)
        
        # Add to active threats
        self.active_threats[threat_id] = threat_profile
        
        # Store threat in memory
        self._store_threat_profile(threat_id, threat_profile)
        
        return threat_id
    
    def _generate_threat_id(self, threat_type: str, threat_data: Dict[str, Any]) -> str:
        """Generate a unique ID for a threat."""
        # Implementation will create a unique identifier
        pass
    
    def _initialize_threat_profile(self, 
                                template: Dict[str, Any],
                                threat_data: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize a threat profile based on template and provided data."""
        # Implementation will merge template and data
        # Will add default values for missing fields
        # Returns complete threat profile
        pass
    
    def _generate_transition_triggers(self, threat_profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Generate explicit triggers that cause threat to transition between lifecycle stages.
        
        For each stage, define:
        - Escalation triggers: User choices that advance the threat
        - De-escalation triggers: User choices that mitigate the threat
        - Narrative cues: How the threat should be represented at this stage
        """
        # Implementation will generate triggers appropriate to the threat type
        # Returns dict mapping stages to their transition triggers
        pass
    
    def _validate_threat_profile(self, threat_profile: Dict[str, Any]) -> None:
        """Validate threat profile for required fields and data types."""
        # Implementation will check required fields and data types
        pass
    
    def _store_threat_profile(self, threat_id: str, threat_profile: Dict[str, Any]) -> None:
        """Store threat profile in memory block."""
        # Implementation will save threat to memory
        pass
    
    def update_threat_status(self, 
                           threat_id: str,
                           update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update status of an existing threat.
        
        Args:
            threat_id: ID of threat to update
            update_data: Data to update
            
        Returns:
            Updated threat profile
        """
        # Retrieve current threat profile
        threat_profile = self._get_threat_profile(threat_id)
        
        # Apply updates
        updated_profile = self._apply_threat_updates(threat_profile, update_data)
        
        # Check for lifecycle stage transitions
        if "lifecycle_stage" in update_data:
            # If moving to resolution, prepare aftermath effects
            if update_data["lifecycle_stage"] == "resolution":
                updated_profile["aftermath_effects"] = self._generate_aftermath_effects(
                    updated_profile, self.difficulty_level)
            
            # Log the transition with reason
            updated_profile["stage_history"].append({
                "from_stage": threat_profile["lifecycle_stage"],
                "to_stage": update_data["lifecycle_stage"],
                "reason": update_data.get("transition_reason", "Unspecified"),
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # Store updated profile
        self._store_threat_profile(threat_id, updated_profile)
        
        # If threat reached aftermath stage, archive it
        if updated_profile.get("lifecycle_stage") == "aftermath":
            self._archive_threat(threat_id, updated_profile)
        
        return updated_profile
    
    def _get_threat_profile(self, threat_id: str) -> Dict[str, Any]:
        """Get a threat profile by ID."""
        # Implementation will retrieve profile from memory
        pass
    
    def _apply_threat_updates(self, 
                            threat_profile: Dict[str, Any],
                            update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply updates to a threat profile."""
        # Implementation will update fields and track history
        pass
    
    def _generate_aftermath_effects(self, 
                                  threat_profile: Dict[str, Any],
                                  difficulty_level: float) -> List[Dict[str, Any]]:
        """
        Generate lasting aftermath effects for a resolved threat.
        
        Effects scale with difficulty level - higher difficulty means
        more significant and longer-lasting effects.
        """
        # Implementation will generate appropriate aftermath effects
        # Returns list of aftermath effect objects
        pass
    
    def _archive_threat(self, threat_id: str, threat_profile: Dict[str, Any]) -> None:
        """Archive a resolved threat with its aftermath effects."""
        # Implementation will move threat to archived state
        pass
    
    def generate_threat_directives(self, 
                                 narrative_state: Dict[str, Any],
                                 token_budget: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate threat directives for inclusion in the Apex AI prompt.
        
        Args:
            narrative_state: Current narrative state information
            token_budget: Maximum tokens for directives (uses settings.json value if None)
            
        Returns:
            Dict containing formatted directives and metadata
        """
        # Use token_budget from settings if not provided
        if token_budget is None:
            token_budget = self.agent_state.config.get("Agent Settings").get("NEMESIS").get("token_budget")
        # Calculate current tension metrics
        tension_metrics = self._calculate_tension_metrics(narrative_state)
        
        # Determine which threats to focus on
        focus_threats = self._select_focus_threats(tension_metrics)
        
        # Generate specific threat directives with clear paths
        threat_directives = self._format_threat_directives(
            focus_threats, token_budget)
        
        # Generate narrative tension guidance
        tension_guidance = self._format_tension_guidance(tension_metrics)
        
        return {
            "threat_directives": threat_directives,
            "tension_guidance": tension_guidance,
            "focus_threats": [t["threat_id"] for t in focus_threats],
            "tension_metrics": tension_metrics
        }
    
    def _calculate_tension_metrics(self, narrative_state: Dict[str, Any]) -> Dict[str, float]:
        """Calculate current tension metrics based on narrative state."""
        # Implementation will analyze current tension levels
        # Returns dict with tension metrics
        pass
    
    def _select_focus_threats(self, tension_metrics: Dict[str, float]) -> List[Dict[str, Any]]:
        """Select which threats to focus on based on tension metrics."""
        # Implementation will select appropriate threats
        # Returns list of threats to focus on
        pass
    
    def _format_threat_directives(self,
                                focus_threats: List[Dict[str, Any]],
                                token_budget: int) -> List[Dict[str, Any]]:
        """
        Format threat directives for inclusion in prompt.
        
        For each threat, include:
        - Current stage description
        - Narrative representation guidance
        - Explicit escalation triggers (user choices that would advance the threat)
        - Explicit de-escalation triggers (user choices that would mitigate the threat)
        """
        # Implementation will create formatted directives
        # Returns list of directive objects
        pass
    
    def _format_tension_guidance(self, tension_metrics: Dict[str, float]) -> Dict[str, Any]:
        """Format general tension guidance based on metrics."""
        # Implementation will create tension guidance
        # Returns guidance object
        pass
    
    def analyze_generated_narrative(self, 
                                  narrative_text: str,
                                  threat_directives: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze generated narrative for threat manifestation and consequence delivery.
        
        Args:
            narrative_text: Generated narrative text
            threat_directives: Directives that were provided
            
        Returns:
            Dict containing analysis results
        """
        # Check if threats manifested as directed
        threat_manifestation = self._check_threat_manifestation(
            narrative_text, threat_directives)
        
        # Check if consequences were delivered
        consequence_delivery = self._check_consequence_delivery(
            narrative_text, threat_directives)
        
        # Detect new threats that emerged in narrative
        new_threats = self._detect_new_threats(narrative_text)
        
        # Assess overall tension level in generated text
        tension_assessment = self._assess_narrative_tension(narrative_text)
        
        # Process any needed updates to threat states
        threat_updates = self._process_threat_updates(
            threat_manifestation, consequence_delivery, new_threats)
        
        return {
            "threat_manifestation": threat_manifestation,
            "consequence_delivery": consequence_delivery,
            "new_threats": new_threats,
            "tension_assessment": tension_assessment,
            "threat_updates": threat_updates
        }
    
    def _check_threat_manifestation(self, 
                                 narrative_text: str, 
                                 threat_directives: Dict[str, Any]) -> Dict[str, Any]:
        """Check if threats manifested in the narrative as directed."""
        # Implementation will check for threat manifestation
        # Returns assessment of manifestation success
        pass
    
    def _check_consequence_delivery(self, 
                                 narrative_text: str, 
                                 threat_directives: Dict[str, Any]) -> Dict[str, Any]:
        """Check if consequences were delivered in the narrative."""
        # Implementation will check for consequence delivery
        # Returns assessment of delivery success
        pass
    
    def _detect_new_threats(self, narrative_text: str) -> List[Dict[str, Any]]:
        """Detect new threats that emerged in the narrative."""
        # Implementation will look for new threat patterns
        # Returns list of potential new threats
        pass
    
    def _assess_narrative_tension(self, narrative_text: str) -> Dict[str, float]:
        """Assess overall tension level in the narrative."""
        # Implementation will analyze tension indicators
        # Returns tension assessment
        pass
    
    def _process_threat_updates(self,
                              threat_manifestation: Dict[str, Any],
                              consequence_delivery: Dict[str, Any],
                              new_threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process updates to threat states based on narrative analysis."""
        # Implementation will determine needed threat updates
        # Returns list of threat updates to apply
        pass
    
    def design_recovery_pathway(self, 
                              setback_type: str,
                              setback_severity: float,
                              character_context: Dict[str, Any],
                              world_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Design a recovery pathway for a character setback.
        
        Args:
            setback_type: Type of setback experienced
            setback_severity: Severity of the setback (0.0-1.0)
            character_context: Character state information
            world_context: World state information
            
        Returns:
            Dict containing recovery pathway design
        """
        # Determine appropriate recovery complexity based on settings
        recovery_complexity = self._calculate_recovery_complexity(
            setback_type, setback_severity)
        
        # Generate possible recovery steps with explicit conditions
        recovery_steps = self._generate_recovery_steps(
            setback_type, recovery_complexity, character_context, world_context)
        
        # Determine recovery constraints
        recovery_constraints = self._determine_recovery_constraints(
            setback_type, setback_severity)
        
        # Format recovery pathway
        recovery_pathway = {
            "setback_type": setback_type,
            "setback_severity": setback_severity,
            "recovery_complexity": recovery_complexity,
            "recovery_steps": recovery_steps,
            "recovery_constraints": recovery_constraints,
            "recovery_conditions": self._generate_recovery_conditions(
                setback_type, setback_severity, recovery_complexity)
        }
        
        return recovery_pathway
    
    def _calculate_recovery_complexity(self, 
                                    setback_type: str, 
                                    setback_severity: float) -> float:
        """Calculate appropriate recovery complexity based on setback."""
        # Implementation will determine complexity based on:
        # - Setback type and severity
        # - Difficulty setting from configuration
        # Returns complexity score (0.0-1.0)
        pass
    
    def _generate_recovery_steps(self,
                              setback_type: str,
                              recovery_complexity: float,
                              character_context: Dict[str, Any],
                              world_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate possible recovery steps based on setback and context."""
        # Implementation will generate appropriate recovery steps
        # Returns list of possible recovery steps
        pass
    
    def _determine_recovery_constraints(self, 
                                     setback_type: str, 
                                     setback_severity: float) -> List[str]:
        """Determine constraints that should apply to recovery."""
        # Implementation will generate appropriate constraints
        # Returns list of constraint descriptions
        pass
    
    def _generate_recovery_conditions(self,
                                   setback_type: str,
                                   setback_severity: float,
                                   recovery_complexity: float) -> List[Dict[str, Any]]:
        """
        Generate specific conditions that must be met for recovery.
        
        These are explicit events/choices/actions that should occur
        before the setback is considered resolved.
        """
        # Implementation will generate appropriate recovery conditions
        # Returns list of condition objects with descriptions and criteria
        pass
    
    def adjust_tension_settings(self, settings_updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adjust tension settings based on provided updates.
        
        Args:
            settings_updates: Settings values to update
            
        Returns:
            Dict containing updated settings
        """
        # Validate settings updates
        self._validate_tension_settings(settings_updates)
        
        # Apply updates to settings
        if "difficulty_level" in settings_updates:
            self.difficulty_level = settings_updates["difficulty_level"]
        if "threat_diversity_min" in settings_updates:
            self.threat_diversity_min = settings_updates["threat_diversity_min"]
        if "consequence_probability_base" in settings_updates:
            self.consequence_probability_base = settings_updates["consequence_probability_base"]
        if "escalation_factor" in settings_updates:
            self.escalation_factor = settings_updates["escalation_factor"]
        if "recovery_complexity" in settings_updates:
            self.recovery_complexity = settings_updates["recovery_complexity"]
        
        # Store updated settings
        self._store_tension_settings()
        
        # Return current settings
        return {
            "difficulty_level": self.difficulty_level,
            "threat_diversity_min": self.threat_diversity_min,
            "consequence_probability_base": self.consequence_probability_base,
            "escalation_factor": self.escalation_factor,
            "recovery_complexity": self.recovery_complexity
        }
    
    def _validate_tension_settings(self, settings_updates: Dict[str, Any]) -> None:
        """Validate tension settings updates."""
        # Implementation will check setting values are in valid ranges
        pass
    
    def _store_tension_settings(self) -> None:
        """Store tension settings in memory block."""
        # Implementation will save settings to memory
        pass
    
    def get_threat_status_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive threat status report for use by other agents.
        
        This is a core communication function that provides LORE with the threat
        information needed to assemble context for the Apex AI. It is not just
        a debugging tool but an essential part of the inter-agent communication
        system that enables threat-aware narrative generation.
        
        Returns:
            Dict containing threat status information formatted for context assembly
        """
        # Get all active threats
        active_threats = self._get_all_active_threats()
        
        # Group threats by domain
        threats_by_domain = self._group_threats_by_domain(active_threats)
        
        # Calculate threat statistics
        threat_stats = self._calculate_threat_statistics(active_threats)
        
        # Generate threat report with explicit transition paths
        threat_report = {
            "active_threat_count": len(active_threats),
            "threats_by_domain": threats_by_domain,
            "threat_statistics": threat_stats,
            "tension_settings": {
                "difficulty_level": self.difficulty_level,
                "threat_diversity_min": self.threat_diversity_min,
                "consequence_probability_base": self.consequence_probability_base,
                "escalation_factor": self.escalation_factor,
                "recovery_complexity": self.recovery_complexity
            },
            "transition_paths": self._generate_threat_transition_paths(active_threats),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return threat_report
    
    def _get_all_active_threats(self) -> List[Dict[str, Any]]:
        """Get all currently active threats."""
        # Implementation will retrieve all active threats
        pass
    
    def _group_threats_by_domain(self, threats: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group threats by their primary domain."""
        # Implementation will group threats by domain
        pass
    
    def _calculate_threat_statistics(self, threats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics about current threats."""
        # Implementation will calculate various statistics
        # Returns dict with threat statistics
        pass
    
    def _generate_threat_transition_paths(self, threats: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate potential transition paths for active threats.
        
        For each threat, provide:
        - Escalation path: What user choices could make this threat worse
        - De-escalation path: What user choices could reduce this threat
        - Current narrative implications: How this threat should manifest now
        """
        # Implementation will generate transition paths for each threat
        # Returns mapping of threat IDs to their potential paths
        pass
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform NEMESIS functions.
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

1. **Threat Modeling with Explicit Triggers**: The system uses a sophisticated threat modeling approach:
   - Multi-domain classification (physical, social, resource, psychological)
   - Lifecycle tracking with explicit triggers for stage transitions
   - Each threat includes both escalation and de-escalation paths
   - Direct cause-effect relationships drive threat evolution

2. **Choice-Based Evolution System**: Threats evolve through explicit cause-effect relationships:
   - Each threat stage has specific user choices that can trigger progression
   - De-escalation options provide clear paths for threat mitigation
   - Aftermath effects ensure threats have lasting impact proportional to difficulty level
   - No arbitrary time-based progression that would confuse the LLM

3. **Directive Generation**: The system creates appropriately formatted directives for Apex AI:
   - Strategic directives that suggest specific threat manifestations
   - Both escalation and de-escalation options for each active threat
   - Recovery conditions based on meaningful actions rather than time
   - Foreshadowing instructions for emerging threats

4. **Calibration Mechanisms**: Several mechanisms allow tuning the experience:
   - Global difficulty setting (0.0=Easy to 1.0=Hardcore) from settings.json
   - Threat diversity minimum to ensure variety of challenge types
   - Recovery complexity setting to scale effort required for recovery
   - All settings externalized to settings.json for easy adjustment

5. **Integration with Other Agents**:
   - Reads character state from PSYCHE for vulnerability analysis
   - Analyzes world state from GAIA for environmental threats
   - Provides detailed threat report to LORE for context assembly
   - Uses MEMNON for retrieving historical threat patterns

## Next Steps

1. Implement the threat profile data structures with explicit transition triggers
2. Develop risk assessment methodology for user decisions
3. Create directive generation for Apex AI prompts
4. Build aftermath effects system for resolved threats
5. Integrate with PSYCHE and GAIA for comprehensive threat assessment
6. Test with sample narratives for appropriate tension calibration