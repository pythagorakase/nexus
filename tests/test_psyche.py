#!/usr/bin/env python3
"""
Test PSYCHE character context auto-generation for a specific chunk.

Usage:
    python test_psyche.py --chunk 100           # Print to screen
    python test_psyche.py --chunk 100 --json    # Output as JSON
    python test_psyche.py --chunk 100 --json --output psyche_100.json
"""

import sys
import json
import argparse
import logging
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.psyche import PSYCHE

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def get_character_references(memnon, chunk_id):
    """Simple SQL lookup for character references in a chunk."""
    sql = f"""
    SELECT character_id, reference 
    FROM chunk_character_references 
    WHERE chunk_id = {chunk_id}
    ORDER BY character_id
    """
    
    result = memnon.execute_readonly_sql(sql)
    
    if not result or not result.get('rows'):
        return []
    
    return result['rows']


def print_formatted(context):
    """Print character context in readable format."""
    print(f"\nPSYCHE Character Context")
    print("=" * 60)
    
    # Present characters
    present = context.get('present_characters', {})
    if present:
        print(f"\nPresent Characters ({len(present)}):")
        print("-" * 40)
        for char_id, data in present.items():
            print(f"\n  {data.get('name', 'Unknown')} (ID: {char_id})")
            if data.get('summary'):
                print(f"    Summary: {data['summary']}")
            if data.get('emotional_state'):
                print(f"    Emotional State: {data['emotional_state']}")
            if data.get('current_activity'):
                print(f"    Current Activity: {data['current_activity']}")
    else:
        print("\nNo present characters")
    
    # Mentioned characters
    mentioned = context.get('mentioned_characters', {})
    if mentioned:
        print(f"\nMentioned Characters ({len(mentioned)}):")
        print("-" * 40)
        for char_id, data in mentioned.items():
            print(f"\n  {data.get('name', 'Unknown')} (ID: {char_id})")
            if data.get('summary'):
                print(f"    Summary: {data['summary']}")
            if data.get('current_location'):
                print(f"    Current Location: {data['current_location']}")
            if data.get('current_activity'):
                print(f"    Current Activity: {data['current_activity']}")
    else:
        print("\nNo mentioned characters")
    
    # Relationships
    relationships = context.get('relationships', [])
    if relationships:
        print(f"\nRelationships ({len(relationships)}):")
        print("-" * 40)
        for rel in relationships:
            chars = rel.get('characters', [])
            if len(chars) >= 2:
                print(f"\n  {chars[0]['name']} ↔ {chars[1]['name']}")
                if rel.get('type'):
                    print(f"    Type: {rel['type']}")
                if rel.get('emotional_valence'):
                    print(f"    Emotional: {rel['emotional_valence']}")
                if rel.get('dynamic'):
                    # Truncate long dynamics
                    dynamic = rel['dynamic']
                    if len(dynamic) > 100:
                        dynamic = dynamic[:100] + "..."
                    print(f"    Dynamic: {dynamic}")
    
    print("\n" + "=" * 60)
    print(f"Summary: {context.get('summary', 'No summary')}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Test PSYCHE character context generation')
    parser.add_argument('--chunk', type=int, required=True, help='Chunk ID to analyze')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--output', type=str, help='Save JSON to file')
    parser.add_argument('--expand', action='store_true', help='Include deep psychology profiles')
    
    args = parser.parse_args()
    
    try:
        # Initialize MEMNON
        logger.info(f"Analyzing chunk {args.chunk} for character references...")
        
        # Create minimal interface for MEMNON
        class MinimalInterface:
            def assistant_message(self, msg): pass
            def error_message(self, msg): logger.error(msg)
        
        class MinimalAgentState:
            state = {"name": "test_psyche"}
        
        class MinimalUser:
            id = "test"
            name = "Test"
        
        # Initialize MEMNON with database connection
        memnon = MEMNON(
            interface=MinimalInterface(),
            agent_state=MinimalAgentState(),
            user=MinimalUser(),
            db_url="postgresql://pythagor@localhost/NEXUS",
            debug=False
        )
        
        # Get character references from chunk
        char_refs = get_character_references(memnon, args.chunk)
        
        if not char_refs:
            logger.warning(f"No character references found in chunk {args.chunk}")
            # Still continue to show empty structure
        
        # Separate present and mentioned characters
        present_ids = [ref['character_id'] for ref in char_refs if ref['reference'] == 'present']
        mentioned_ids = [ref['character_id'] for ref in char_refs if ref['reference'] == 'mentioned']
        
        logger.info(f"Found {len(present_ids)} present, {len(mentioned_ids)} mentioned characters")
        
        # Initialize PSYCHE utility
        psyche = PSYCHE(memnon)
        
        # Generate character context
        context = psyche.generate_character_context(
            present_character_ids=present_ids,
            mentioned_character_ids=mentioned_ids,
            expand_psychology=args.expand,
            include_relationships=True
        )
        
        # Output results
        if args.json:
            output_data = {
                "chunk_id": args.chunk,
                "character_references": {
                    "present": present_ids,
                    "mentioned": mentioned_ids
                },
                "context": context
            }
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2, default=str)
                logger.info(f"Saved to {args.output}")
            else:
                print(json.dumps(output_data, indent=2, default=str))
        else:
            print_formatted(context)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()