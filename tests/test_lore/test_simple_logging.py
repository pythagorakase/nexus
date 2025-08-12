#!/usr/bin/env python
"""
Simple test to demonstrate LORE's narrative analysis with visible logging.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nexus.agents.lore.utils.local_llm import LocalLLMManager

def main():
    print("="*70)
    print("LORE NARRATIVE ANALYSIS - VISIBLE LOGGING TEST")
    print("="*70)
    
    # Load settings
    with open('tests/test_lore/lore_test_settings.json') as f:
        settings = json.load(f)
    
    # Create manager
    manager = LocalLLMManager(settings)
    print(f"\n✅ Connected to LM Studio")
    print(f"   Model: {manager.loaded_model_id}")
    
    # Test 1: Simple semantic query
    print("\n" + "="*70)
    print("TEST 1: SEMANTIC DELEGATION")
    print("="*70)
    
    prompt = """You are analyzing a narrative. The user asks: "What happened when Victor betrayed Alex?"

Based on this query, identify:
1. Key entities to search for
2. The narrative context type 
3. Natural language queries to find relevant content

Respond in natural language."""
    
    print("\nPROMPT SENT TO LLM:")
    print("-" * 40)
    print(prompt)
    print("-" * 40)
    
    response = manager.query(prompt, temperature=0.7, max_tokens=300)
    
    print("\nLLM RESPONSE:")
    print("-" * 40)
    if response:
        # Clean up any channel markers if present
        clean_response = response.replace('<|channel|>', '[').replace('<|message|>', '] ').replace('<|end|>', '\n')
        print(clean_response[:500])
    else:
        print("No response received")
    print("-" * 40)
    
    # Test 2: Narrative context analysis
    print("\n" + "="*70)
    print("TEST 2: NARRATIVE CONTEXT ANALYSIS")
    print("="*70)
    
    warm_slice = [{
        'id': 114,
        'raw_text': """Victor's hand trembled as he reached for the neural interface. 
"Alex, I'm sorry," he whispered, his voice barely audible over the hum of the 
Dynacorp machinery. "They have my daughter. I had no choice." The betrayal hung 
between them like a blade.""",
        'world_time': '2073-10-15T22:30:00'
    }]
    
    user_input = "What led to Victor betraying Alex?"
    
    print(f"\nUSER QUERY: {user_input}")
    print(f"NARRATIVE CHUNK: #{warm_slice[0]['id']}")
    print(f"EXCERPT: ...{warm_slice[0]['raw_text'][:100]}...")
    
    print("\n[Calling analyze_narrative_context...]")
    analysis = manager.analyze_narrative_context(warm_slice, user_input)
    
    print("\nANALYSIS RESULT:")
    print("-" * 40)
    print(json.dumps(analysis, indent=2))
    print("-" * 40)
    
    # Test 3: Query generation
    print("\n" + "="*70)
    print("TEST 3: NATURAL LANGUAGE QUERY GENERATION")
    print("="*70)
    
    print(f"\nCONTEXT FOR QUERY GENERATION:")
    print(f"  Characters: {analysis.get('characters', [])}")
    print(f"  Entities: {analysis.get('entities_for_retrieval', [])}")
    
    print("\n[Calling generate_retrieval_queries...]")
    queries = manager.generate_retrieval_queries(analysis, user_input)
    
    print(f"\nGENERATED QUERIES ({len(queries)} total):")
    print("-" * 40)
    for i, query in enumerate(queries[:5], 1):
        print(f"  {i}. {query}")
    print("-" * 40)
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent / f"lore_analysis_output_{timestamp}.txt"
    
    with open(output_file, 'w') as f:
        f.write("LORE NARRATIVE ANALYSIS OUTPUT\n")
        f.write("="*70 + "\n\n")
        
        f.write("PROMPT:\n")
        f.write(prompt + "\n\n")
        
        f.write("LLM RESPONSE:\n")
        f.write(str(response) + "\n\n")
        
        f.write("ANALYSIS RESULT:\n")
        f.write(json.dumps(analysis, indent=2) + "\n\n")
        
        f.write("GENERATED QUERIES:\n")
        for query in queries:
            f.write(f"- {query}\n")
    
    print(f"\n✅ Results saved to: {output_file}")
    print(f"   View with: cat {output_file}")


if __name__ == "__main__":
    main()