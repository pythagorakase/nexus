"""
Curveball Analyzer for Two-Pass Context Assembly

Simple inference-based gap detection using LORE's memory and entity rosters.
No regex patterns, no fancy algorithms - just let the LLM think.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("nexus.lore.curveball_analyzer")


class AnalysisStrategy(Enum):
    """Strategy for handling user input in Pass 2"""
    GAP_FILLING = "gap_filling"  # Novel entities detected, need targeted retrieval
    WARM_EXPANSION = "warm_expansion"  # No gaps, just extend the warm slice


@dataclass
class CurveballAnalysis:
    """Results of analyzing user input against existing context"""
    strategy: AnalysisStrategy
    has_novel_content: bool
    reasoning: str  # LLM's explanation
    
    # Simple findings
    novel_entities: List[str] = field(default_factory=list)
    auto_vector_chunk_ids: List[int] = field(default_factory=list)
    deep_cut_chunks: List[int] = field(default_factory=list)  # Remote references
    
    # Token budget
    tokens_available: int = 0


class CurveballAnalyzer:
    """
    Dead simple analyzer that trusts the local LLM to figure out gaps.
    
    1. Auto-vector user input to find relevant chunks
    2. LORE remembers what it assembled in Pass 1
    3. LLM compares to detect novel content
    4. We either fill gaps or extend the warm slice
    """
    
    def __init__(self, local_llm_manager, memnon_instance=None):
        """
        Initialize CurveballAnalyzer.
        
        Args:
            local_llm_manager: LocalLLMManager for inference (required)
            memnon_instance: MEMNON for database queries and vector search
        """
        if not local_llm_manager:
            raise ValueError("CurveballAnalyzer requires LocalLLMManager")
        
        self.llm = local_llm_manager
        self.memnon = memnon_instance
        
        # Load prompts from markdown file
        self.prompts = self._load_prompts()
        
        logger.info("CurveballAnalyzer initialized - simple inference-based approach")
    
    def analyze_user_input(
        self,
        user_text: str,
        session_context: 'SessionContext',  # From session_store
        tokens_available: int = 32768  # 25% of 131072
    ) -> CurveballAnalysis:
        """
        Analyze user input using auto-vector and inference.
        
        Args:
            user_text: The user's input text
            session_context: Complete context from Pass 1
            tokens_available: Token budget for Pass 2
            
        Returns:
            CurveballAnalysis with strategy decision
        """
        # Step 1: Auto-vector the user input
        from .auto_vector import auto_vector_user_input, detect_deep_cuts
        
        auto_vector_results = {}
        deep_cuts = []
        
        if self.memnon:
            auto_vector_results = auto_vector_user_input(
                user_text,
                self.memnon,
                k=10
            )
            
            # Detect deep cuts (remote references like karaoke)
            pass1_chunk_ids = session_context.chunk_ids if session_context else []
            deep_cuts = detect_deep_cuts(
                auto_vector_results,
                pass1_chunk_ids,
                distance_threshold=100
            )
            
            if deep_cuts:
                logger.info(f"Found {len(deep_cuts)} deep cut references")
        
        # Step 2: Get entity rosters for comparison
        entity_rosters = self._get_entity_rosters() if self.memnon else {}
        
        # Step 3: Build Pass 1 summary
        pass1_summary = {
            "entities_in_context": {
                "characters": list(session_context.present_characters.keys()) + 
                              list(session_context.mentioned_characters.keys()),
                "places": list(session_context.setting_places.keys()) + 
                         list(session_context.mentioned_places.keys())
            },
            "understanding": session_context.lore_state.understanding if session_context.lore_state else "",
            "gaps": session_context.lore_state.context_gaps if session_context.lore_state else [],
            "executed_queries": list(session_context.executed_queries) if session_context.executed_queries else []
        }
        
        # Step 4: Use LLM to analyze for gaps
        # Use the prompt template, being careful with the JSON formatting
        if "pass2_gap_detection" in self.prompts:
            prompt_template = self.prompts["pass2_gap_detection"]
        else:
            prompt_template = self.prompts.get("fallback_prompt", "")
        
        # Replace placeholders safely
        prompt = prompt_template.replace("{pass1_summary}", json.dumps(pass1_summary, indent=2))
        prompt = prompt.replace("{user_text}", user_text)
        prompt = prompt.replace("{chunk_ids}", str(auto_vector_results.get("chunk_ids", [])))
        prompt = prompt.replace("{entity_rosters}", json.dumps(entity_rosters, indent=2)[:2000])
        
        try:
            # Let the LLM analyze
            response = self.llm.query(prompt, max_tokens=500, temperature=0.3)
            
            # Parse the response
            analysis_data = json.loads(response)
            
            # Check for novel content (either from LLM analysis or deep cuts)
            has_novel = analysis_data.get("has_novel_content", False) or bool(deep_cuts)
            
            analysis = CurveballAnalysis(
                strategy=AnalysisStrategy.GAP_FILLING if has_novel else AnalysisStrategy.WARM_EXPANSION,
                has_novel_content=has_novel,
                reasoning=analysis_data.get("reasoning", ""),
                novel_entities=analysis_data.get("novel_entities", []),
                auto_vector_chunk_ids=auto_vector_results.get("chunk_ids", []),
                deep_cut_chunks=deep_cuts,
                tokens_available=tokens_available
            )
            
            logger.info(f"Analysis: {analysis.strategy.value} - {analysis.reasoning}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}, defaulting to warm expansion")
            
            # Safe fallback - just extend the warm slice
            return CurveballAnalysis(
                strategy=AnalysisStrategy.WARM_EXPANSION,
                has_novel_content=False,
                reasoning=f"Analysis failed ({str(e)}), defaulting to warm expansion",
                tokens_available=tokens_available
            )
    
    def _get_entity_rosters(self) -> Dict[str, List[Dict]]:
        """
        Get simple entity rosters from database.
        Just id and name for each entity type.
        """
        if not self.memnon:
            return {}
        
        rosters = {}
        
        # Define entity queries
        queries = {
            "characters": "SELECT id, name FROM characters ORDER BY id",
            "zones": "SELECT id, name FROM zones ORDER BY id",
            "places": "SELECT id, name FROM places ORDER BY id",
            "factions": "SELECT id, name FROM factions ORDER BY id"
            # "events": table doesn't exist yet
        }
        
        for entity_type, query in queries.items():
            try:
                result = self.memnon.execute_readonly_sql(query)
                if result and result.get('rows'):
                    rosters[entity_type] = result['rows']
                else:
                    rosters[entity_type] = []
            except Exception as e:
                logger.warning(f"Failed to get {entity_type} roster: {e}")
                rosters[entity_type] = []
        
        return rosters
    
    def _load_prompts(self) -> Dict[str, str]:
        """
        Load prompts from lore_system_prompt.md.
        """
        prompts = {}
        
        # Path to the prompt file
        prompt_file = Path(__file__).parent.parent / "lore_system_prompt.md"
        
        if prompt_file.exists():
            try:
                content = prompt_file.read_text()
                
                # Extract Pass 2 Gap Detection Prompt
                if "### Pass 2 Gap Detection Prompt" in content:
                    start = content.find("### Pass 2 Gap Detection Prompt")
                    start = content.find("```", start) + 4  # Skip past ```\n
                    end = content.find("```", start)
                    prompts["pass2_gap_detection"] = content[start:end].strip()
                
                # Extract Gap Filling Prompt
                if "### Gap Filling Prompt" in content:
                    start = content.find("### Gap Filling Prompt")
                    start = content.find("```", start) + 3
                    end = content.find("```", start)
                    prompts["gap_filling"] = content[start:end].strip()
                
                # Extract Warm Expansion Prompt
                if "### Warm Expansion Prompt" in content:
                    start = content.find("### Warm Expansion Prompt")
                    start = content.find("```", start) + 3
                    end = content.find("```", start)
                    prompts["warm_expansion"] = content[start:end].strip()
                
                logger.info(f"Loaded {len(prompts)} prompts from {prompt_file}")
                
            except Exception as e:
                logger.warning(f"Failed to load prompts from file: {e}")
        
        # Fallback prompts if file loading fails
        if "pass2_gap_detection" not in prompts:
            prompts["pass2_gap_detection"] = """You are LORE analyzing user input in Pass 2.

YOUR PASS 1 SUMMARY:
{pass1_summary}

USER INPUT:
{user_text}

AUTO-VECTOR RESULTS:
Found chunks: {chunk_ids}

ENTITY ROSTERS:
{entity_rosters}

Does the user input reference anything NOT in your Pass 1 context?
Be precise. Check entity IDs and chunks.

Respond with JSON:
{{
  "has_novel_content": true/false,
  "reasoning": "Brief explanation",
  "novel_entities": ["list of new entities mentioned"],
  "strategy": "gap_filling" or "warm_expansion"
}}"""
        
        return prompts
    
    def get_expansion_directive(self, analysis: CurveballAnalysis) -> str:
        """
        Simple directive for what to do in Pass 2.
        """
        if analysis.strategy == AnalysisStrategy.GAP_FILLING:
            # If we have deep cuts, prioritize those
            if analysis.deep_cut_chunks:
                return f"Retrieve chunks {analysis.deep_cut_chunks} (deep cut references)"
            
            # Otherwise list novel entities
            if analysis.novel_entities:
                return f"Retrieve context for: {', '.join(analysis.novel_entities)}"
            
            return "Fill detected gaps with targeted retrieval"
        
        else:  # WARM_EXPANSION
            return "Extend the warm slice to fill remaining token budget"