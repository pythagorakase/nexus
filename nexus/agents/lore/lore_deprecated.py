import logging
import json
import re
import requests
from typing import Dict, List, Optional, Any

# Placeholder imports - LORE will likely need access to settings, DB models, etc.
# from letta.agent import Agent # Example if LORE becomes a Letta agent
# from ..memnon.memnon import Character, Place # Example DB models needed
# from sqlalchemy.orm import Session # Example DB session

# Configure Lore-specific logger (using nexus.lore for now)
logger = logging.getLogger("nexus.lore")
# Basic config if run standalone, assumes root logger is configured elsewhere
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


# Placeholder for settings - LORE will need its own config or access to global settings
LORE_SETTINGS = {} 
LLM_GLOBAL_SETTINGS = {} # Assume loaded elsewhere

class LORE:
    """
    LORE Agent - Responsible for Narrative Synthesis and Analysis using LLMs.
    (This is a basic structure, assuming functions moved from MEMNON)
    """
    def __init__(self, model_id="default_model", settings=None):
        # Basic initialization, likely needs expansion
        self.model_id = model_id # Example: Needs proper configuration
        # TODO: Load settings properly (LORE_SETTINGS, LLM_GLOBAL_SETTINGS)
        # TODO: Initialize database session if needed (self.Session = ...)
        logger.info("LORE agent initialized (basic structure).")

    def _query_llm(self, prompt: str, temperature: float = None, max_tokens: int = None, timeout: int = None) -> str:
        """
        Query the local LLM with a prompt, using global settings.
        (Moved from MEMNON)

        Args:
            prompt: The prompt to send to the LLM
            temperature: Optional temperature parameter (overrides global setting)
            max_tokens: Optional max tokens parameter (overrides global setting)
            timeout: Optional timeout in seconds (overrides global setting)

        Returns:
            LLM response as string
        """
        # Get LLM settings from global configuration
        # Use LLM_GLOBAL_SETTINGS loaded during __init__ (Placeholder)
        api_base = LLM_GLOBAL_SETTINGS.get("api_base", "http://localhost:1234")
        
        # Use provided parameters or fall back to global settings
        llm_temp = temperature if temperature is not None else LLM_GLOBAL_SETTINGS.get("temperature", 0.8)
        llm_max_tokens = max_tokens if max_tokens is not None else LLM_GLOBAL_SETTINGS.get("max_tokens", 2048)
        llm_timeout = timeout if timeout is not None else LLM_GLOBAL_SETTINGS.get("timeout", 120) # Default 120s timeout
        llm_top_p = LLM_GLOBAL_SETTINGS.get("top_p", 0.95)
        llm_top_k = LLM_GLOBAL_SETTINGS.get("top_k", 40)
        llm_min_p = LLM_GLOBAL_SETTINGS.get("min_p", 0.05)
        # OMITTING PENALTIES: repeat_penalty, presence_penalty, frequency_penalty
        
        completions_endpoint = f"{api_base}/v1/completions"
        chat_endpoint = f"{api_base}/v1/chat/completions"
        
        logger.debug(f"Querying LLM ({self.model_id}) with timeout {llm_timeout}s. Temp: {llm_temp}, MaxTokens: {llm_max_tokens}")
        
        headers = {"Content-Type": "application/json"}
        
        # Try completions endpoint first
        try:
            payload = {
                "model": self.model_id,
                "prompt": prompt, # Removed reset_token logic
                "temperature": llm_temp,
                "max_tokens": llm_max_tokens,
                "top_p": llm_top_p,
                "top_k": llm_top_k,
                "min_p": llm_min_p,
                "stream": False
                # Penalties omitted
            }
            
            logger.debug(f"Attempting completions endpoint: {completions_endpoint}")
            response = requests.post(completions_endpoint, json=payload, headers=headers, timeout=llm_timeout)
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0 and "text" in response_json["choices"][0]:
                    logger.debug("Received successful response from completions endpoint.")
                    return response_json["choices"][0]["text"].strip()
                else:
                    logger.warning(f"Unexpected response format from LLM completions API: {response_json}")
            else:
                 logger.warning(f"Completions API failed. Status: {response.status_code}, Response: {response.text[:200]}...")
                 # Don't raise error yet, try chat endpoint

        except requests.Timeout:
            logger.warning(f"Completions endpoint request timed out after {llm_timeout}s. Trying chat endpoint.")
        except Exception as e:
            logger.warning(f"Error during completions request: {e}. Trying chat endpoint.")

        # Fallback to chat completions API
        try:
            # Get system prompt from LORE settings (Placeholder)
            system_prompt = LORE_SETTINGS.get("prompts", {}).get(
                 "system",
                 "You are LORE, a narrative analysis and synthesis system." # Fallback system prompt
            )

            chat_payload = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt} # Removed reset_token logic
                ],
                "temperature": llm_temp,
                "max_tokens": llm_max_tokens,
                "top_p": llm_top_p,
                "top_k": llm_top_k,
                "min_p": llm_min_p,
                "stream": False
                # Penalties omitted
            }
            
            logger.debug(f"Attempting chat completions endpoint: {chat_endpoint}")
            response = requests.post(chat_endpoint, json=chat_payload, headers=headers, timeout=llm_timeout)
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0 and "message" in response_json["choices"][0] and "content" in response_json["choices"][0]["message"]:
                     logger.debug("Received successful response from chat completions endpoint.")
                     return response_json["choices"][0]["message"]["content"].strip()
                else:
                    logger.error(f"Unexpected response format from LLM chat completions API: {response_json}")
                    raise ValueError("Invalid response format from LLM chat API")
            else:
                error_msg = f"Chat completions API also failed. Status: {response.status_code}, Response: {response.text[:200]}..."
                logger.error(error_msg)
                raise ValueError(error_msg)
                
        except requests.Timeout:
            error_msg = f"LLM chat request also timed out after {llm_timeout}s"
            logger.error(error_msg)
            raise TimeoutError(error_msg) # Raise timeout if both endpoints fail
            
        except Exception as e:
            logger.error(f"Fatal error querying LLM via both endpoints: {e}")
            # import traceback # Consider adding traceback for debugging if needed
            # logger.error(f"Traceback: {traceback.format_exc()}")
            raise # Re-raise the exception if both attempts fail catastrophically

        # Should not be reachable if exceptions are raised correctly, but as a final fallback:
        logger.error("All LLM query attempts failed without raising expected exceptions.")
        return "" # Return empty string only if all attempts fail silently (shouldn't happen)

    def _analyze_query(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a query to understand the information need and query type using LLM.
        (Moved from MEMNON - needs dependencies like logger, _query_llm)
        
        Args:
            query: The query string
            query_type: Optional explicit query type
            
        Returns:
            Dict with query analysis
        """
        # Start with basic analysis
        query_info = {
            "raw_query": query,
            "type": query_type if query_type else "general",
            "entities": [],
            "keywords": [],
            "focus": "narrative"
        }
        
        # Extract entities using basic pattern matching (or potentially another LLM call/NER)
        # This is a simple implementation that could be enhanced
        entity_patterns = [
            (r'\\b([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)\\b', 'person'),  # Capitalized words as names
            # Add more specific patterns as needed
            (r'\\b(Night City|The Wastes|Neon Bay)\\b', 'location'), 
            (r'\\b(Arasaka|NetWatch|Militech)\\b', 'organization') 
        ]
        
        for pattern, entity_type in entity_patterns:
            matches = re.finditer(pattern, query)
            for match in matches:
                entity = match.group(1)
                # Avoid adding duplicates (simple check)
                if not any(e['text'] == entity for e in query_info["entities"]):
                     query_info["entities"].append({
                        "text": entity,
                        "type": entity_type
                    })
        
        # Extract keywords using simple techniques
        keywords = []
        common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "about", "from"}
        words = re.findall(r'\\b\\w+\\b', query.lower())
        for word in words:
            if len(word) > 3 and word not in common_words:
                keywords.append(word)
        query_info["keywords"] = list(set(keywords)) # Use set for uniqueness
        
        # If query type wasn't provided, try to determine it
        if not query_type:
            # Use pattern matching first (optional, could rely solely on LLM)
            type_patterns = {
                "character": r'\\b(who|person|character|about|background)\\b',
                "location": r'\\b(where|location|place|setting)\\b',
                "event": r'\\b(what happened|when|event|incident|occurrence)\\b',
                "relationship": r'\\b(relationship|connection|feel about|interaction)\\b',
                "theme": r'\\b(theme|symbolism|represent|meaning|significance)\\b'
            }
            
            determined_type = "general"
            for qtype, pattern in type_patterns.items():
                if re.search(pattern, query.lower()):
                    determined_type = qtype
                    break
            
            # If pattern matching didn't work or yielded 'general', use LLM
            if determined_type == "general":
                try:
                    # Use a structured prompt that limits the LLM's response options
                    structured_prompt = """Analyze the narrative query to determine the primary information type.

Query: "{query}"

Categories:
A) character: About a specific character.
B) location: About a place or setting.
C) event: About something that happened.
D) theme: About narrative themes, symbolism, or motifs.
E) relationship: About connections between characters.
F) general: Doesn't fit neatly into the above.

Respond with ONLY the single best category name (e.g., "character").""".format(query=query)
                    
                    # Query LLM for classification
                    response = self._query_llm(structured_prompt, temperature=0.1, max_tokens=15) # Reduced max_tokens
                    
                    # Extract type from response (more robust cleaning)
                    cleaned_response = response.lower().strip()
                    # Remove potential markdown or formatting artifacts
                    cleaned_response = re.sub(r'[`*]', '', cleaned_response) 
                    # Remove punctuation
                    cleaned_response = re.sub(r'[^\w\s]', '', cleaned_response) 
                    
                    first_word = cleaned_response.split()[0] if cleaned_response else ""
                    
                    valid_types = {"character", "location", "event", "theme", "relationship", "general"}
                    
                    if first_word in valid_types:
                        determined_type = first_word
                        logger.info(f"LLM classified query as {determined_type}")
                    else:
                         logger.warning(f"LLM returned unexpected format for query type: '{response}'. Using 'general'.")
                         # Keep determined_type as "general"
                    
                except Exception as e:
                    logger.warning(f"Failed to classify query with LLM: {e}")
                    # Keep determined_type as "general"

            query_info["type"] = determined_type

        # Optional: Fallback logic if type remains general
        if query_info["type"] == "general" and any(entity.get("type") == "person" for entity in query_info["entities"]):
            query_info["type"] = "character" # Simple heuristic
            
        return query_info

    def _generate_search_plan(self, query: str, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a dynamic search plan for a given query using LLM reasoning.
        (Moved from MEMNON - needs dependencies like logger, _query_llm, potentially settings/DB info)
        
        Args:
            query: The original query string
            query_info: Analyzed query information from _analyze_query (LLM version)
            
        Returns:
            Search plan with strategies in priority order
        """
        # Prepare information about available data sources (example, needs real data)
        # This might come from MEMNON or be configured in LORE
        structured_tables = {
            "characters": "detailed character info",
            "places": "location descriptions",
            "events": "narrative events",
            # Add other relevant tables MEMNON might query
        }
        vector_collections = {
            "narrative_chunks": "semantic text passages"
        }
        
        # Construct the prompt
        prompt = f"""You are LORE, planning a search for the MEMNON retrieval system.
Given the query analysis, create an optimal search strategy using MEMNON's capabilities.

QUERY: "{query}"
ANALYZED TYPE: {query_info["type"]}
ENTITIES: {json.dumps(query_info.get("entities", []))}
KEYWORDS: {json.dumps(query_info.get("keywords", []))}

MEMNON's AVAILABLE SEARCH METHODS:
1. structured_data: Exact lookup in tables like {list(structured_tables.keys())}. Best for known entities.
2. vector_search: Semantic search in collections like {list(vector_collections.keys())}. Best for concepts, events, relationships.
3. text_search: Keyword matching in narrative text. Good fallback or for specific terms.

Create a JSON search plan specifying strategies, priorities, and parameters (tables, collections, keywords).

RESPONSE JSON STRUCTURE:
{{
  "strategies": [
    {{ "type": "structured_data", "priority": 1, "tables": ["table1", "table2"] }},
    {{ "type": "vector_search", "priority": 2, "collections": ["collection1"] }},
    {{ "type": "text_search", "priority": 3, "keywords": ["key", "words"] }}
  ],
  "explanation": "Brief reasoning for the plan."
}}

Return ONLY the JSON object.
"""
        
        # Query LLM for search plan
        llm_response = self._query_llm(prompt, temperature=0.3) # Lower temp for structured output
        logger.info(f"LLM response for search plan: {llm_response[:300]}...")
        
        # Extract JSON from response (simplified extraction)
        try:
            # Find the first '{' and last '}'
            start = llm_response.find('{')
            end = llm_response.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = llm_response[start:end+1]
                search_plan = json.loads(json_str)
                
                # Basic validation
                if "strategies" not in search_plan or "explanation" not in search_plan:
                     raise ValueError("Search plan missing required fields.")
                for strategy in search_plan["strategies"]:
                     if "type" not in strategy or "priority" not in strategy:
                         raise ValueError("Search strategy missing required fields.")
                
                logger.info("Successfully parsed search plan from LLM.")
                return search_plan
            else:
                raise ValueError("Could not find JSON object delimiters.")

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse search plan JSON from LLM response: {e}. Response: {llm_response}")
            # Fallback to a default plan (example)
            return {
                "strategies": [
                    {"type": "vector_search", "priority": 1, "collections": ["narrative_chunks"]},
                    {"type": "text_search", "priority": 2, "keywords": query_info.get("keywords", [])}
                ],
                "explanation": "Default fallback search plan (vector + text)."
            }
            
    def _synthesize_response(self, query: str, results: List[Dict[str, Any]], query_type: str) -> str:
        """
        Generate a synthesized narrative response using LLM based on retrieved results.
        (Moved from MEMNON - needs dependencies like logger, _query_llm)

        Args:
            query: The original query
            results: List of retrieved results (from MEMNON)
            query_type: Type of query (determined by _analyze_query)

        Returns:
            Synthesized response as a string
        """
        # Format results for LLM context
        context_str = ""
        for i, result in enumerate(results[:10]): # Limit context size
            source = result.get("source", "unknown")
            score = result.get("score", 0.0)
            text = result.get("text", "")[:300] # Truncate individual results
            
            context_str += f"Result {i+1} (Source: {source}, Score: {score:.3f}):\n"
            # Add metadata if useful (e.g., character name, location name)
            if source == "structured_data":
                 name = result.get("name", "")
                 if name:
                     context_str += f"  Name: {name}\n"
            context_str += f"  Content: {text}...\n\n"

        if not results:
            context_str = "No relevant information was found by the retrieval system.\n"

        # Create prompt for LLM synthesis
        prompt = f"""You are LORE, a narrative intelligence system. 
Answer the user's query concisely based *only* on the provided context retrieved by MEMNON. 
If the context doesn't answer the query, say so. Do not invent information.

QUERY: "{query}"
(This query was classified as type: {query_type})

RETRIEVED CONTEXT:
--- START CONTEXT ---
{context_str}
--- END CONTEXT ---

Synthesize a direct answer to the query based *only* on the context above (2-4 sentences):
"""

        try:
            # Query LLM for synthesized response
            response = self._query_llm(prompt, temperature=0.7, max_tokens=300) # Synthesis settings
            response = response.strip()

            # Basic check if response is meaningful
            if not response or len(response) < 10 or "cannot answer" in response.lower():
                 # Fallback if LLM fails or context is insufficient
                 return self._generate_basic_summary(query, results, query_type) 

            return response

        except Exception as e:
            logger.error(f"Error synthesizing response: {e}")
            # Fallback on error
            return self._generate_basic_summary(query, results, query_type)

    def _generate_basic_summary(self, query: str, results: List[Dict[str, Any]], query_type: str) -> str:
        """
        Generate a basic summary if LLM synthesis fails or context is poor.
        (Moved from MEMNON)

        Args:
            query: The original query
            results: Results from search
            query_type: Type of query

        Returns:
            Basic summary as a string
        """
        if not results:
             return f"I couldn't find any information related to your query about '{query[:50]}...'."

        summary = f"Based on the retrieved information regarding '{query[:50]}...':\n\n"
        
        for i, result in enumerate(results[:3]): # Include top 3 results
            source = result.get("source", "unknown")
            score = result.get("score", 0.0)
            text = result.get("text", "")[:150] # Shorter summary snippet
            
            summary += f"- (From {source}, Score: {score:.2f}): {text}...\n"
            
        if len(results) > 3:
            summary += f"\n... and {len(results) - 3} more related items."
            
        return summary

# Example usage (if run directly for testing)
if __name__ == '__main__':
    # Configure logger for direct run
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)
    logger.setLevel(logging.DEBUG)

    # Basic test
    lore_agent = LORE() 
    # Note: LLM calls will likely fail without proper settings configuration
    try:
        test_query = "Tell me about Alex's background"
        analysis = lore_agent._analyze_query(test_query)
        print(f"Analyzed Query: {analysis}")
        
        # Mock results for synthesis test
        mock_results = [
             {'id': '1', 'text': 'Alex grew up in the lower districts, skilled in tech.', 'score': 0.9, 'source': 'vector_search'},
             {'id': 'char_alex', 'text': 'Alex summary: A netrunner with a mysterious past.', 'score': 0.95, 'source': 'structured_data', 'name': 'Alex'}
        ]
        
        summary = lore_agent._synthesize_response(test_query, mock_results, analysis.get('type', 'general'))
        print(f"Synthesized Response:\n{summary}")

    except Exception as e:
        print(f"Error during test run: {e}")
        print("Note: LLM calls require proper configuration and a running server.") 