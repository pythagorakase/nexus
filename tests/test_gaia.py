#!/usr/bin/env python3
"""
Test GAIA place context auto-generation for a specific chunk.

Usage:
    python test_gaia.py --chunk 100           # Print to screen (with nearby places)
    python test_gaia.py --chunk 100 --json    # Output as JSON
    python test_gaia.py --chunk 100 --extended  # Include cross-zone spatial data
    python test_gaia.py --chunk 100 --json --output gaia_100.json
"""

import sys
import json
import argparse
import logging
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.gaia import GAIA

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def meters_to_miles(meters):
    """Convert meters to miles for our American friends 🦅"""
    return meters * 0.000621371


def get_place_references(memnon, chunk_id):
    """Simple SQL lookup for place references in a chunk."""
    # First check chunk_metadata for primary place
    primary_sql = f"""
    SELECT cm.place, p.name 
    FROM chunk_metadata cm
    LEFT JOIN places p ON cm.place = p.id
    WHERE cm.chunk_id = {chunk_id}
    """
    
    primary_result = memnon.execute_readonly_sql(primary_sql)
    primary_place = None
    if primary_result and primary_result.get('rows') and primary_result['rows'][0].get('place'):
        primary_place = {
            'place_id': primary_result['rows'][0]['place'],
            'name': primary_result['rows'][0].get('name'),
            'is_primary': True
        }
    
    # Then check place_chunk_references
    refs_sql = f"""
    SELECT pcr.place_id, pcr.reference_type, p.name
    FROM place_chunk_references pcr
    LEFT JOIN places p ON pcr.place_id = p.id
    WHERE pcr.chunk_id = {chunk_id}
    ORDER BY pcr.place_id
    """
    
    refs_result = memnon.execute_readonly_sql(refs_sql)
    
    references = []
    if primary_place:
        references.append(primary_place)
    
    if refs_result and refs_result.get('rows'):
        for row in refs_result['rows']:
            # Don't duplicate primary place
            if primary_place and row['place_id'] == primary_place['place_id']:
                continue
            references.append({
                'place_id': row['place_id'],
                'name': row.get('name'),
                'reference_type': row['reference_type']
            })
    
    return references


def format_distance(meters):
    """Format distance in miles with appropriate precision."""
    miles = meters_to_miles(meters)
    if miles < 0.1:
        return f"{int(meters * 3.28084)} feet"  # Convert to feet for very short distances
    elif miles < 1:
        return f"{miles:.2f} miles"
    else:
        return f"{miles:.1f} miles"


def format_bearing(degrees):
    """Convert bearing degrees to cardinal direction."""
    if degrees is None:
        return "unknown"
    
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]


def format_travel_time(minutes):
    """Format travel time in appropriate units."""
    if minutes < 60:
        return f"{int(minutes)} min"
    else:
        hours = minutes / 60
        if hours < 24:
            return f"{hours:.1f} hours"
        else:
            days = hours / 24
            return f"{days:.1f} days"


def print_formatted(context, gaia_instance, extended=False):
    """Print place context in readable format."""
    print(f"\nGAIA Place Context")
    print("=" * 60)
    
    # Setting places
    setting = context.get('setting_places', {})
    if setting:
        print(f"\nSetting Locations ({len(setting)}):")
        print("-" * 40)
        for place_id, data in setting.items():
            print(f"\n  {data.get('name', 'Unknown')} (ID: {place_id})")
            if data.get('summary'):
                print(f"    Summary: {data['summary']}")
            if data.get('current_status'):
                print(f"    Current Status: {data['current_status']}")
            if data.get('coordinates'):
                coord = data['coordinates']
                print(f"    Coordinates: {coord['lat']:.4f}°N, {abs(coord['lon']):.4f}°W")
            if data.get('inhabitants'):
                inhabitants = data['inhabitants']
                if isinstance(inhabitants, list) and inhabitants:
                    print(f"    Inhabitants: {', '.join(inhabitants[:3])}" + 
                          (" and others" if len(inhabitants) > 3 else ""))
            
            # Get nearby places (always included for American experience)
            try:
                nearby = gaia_instance.get_places_near(int(place_id), limit=5)
                if nearby:
                    print(f"\n    Nearby Places (ordered by zone, then distance):")
                    
                    # Group by zone for clarity
                    by_zone = {}
                    for place in nearby[:5]:
                        zone_name = place.get('zone_name', 'Unknown Zone')
                        if zone_name not in by_zone:
                            by_zone[zone_name] = []
                        by_zone[zone_name].append(place)
                    
                    # Print grouped by zone
                    for zone_name, zone_places in by_zone.items():
                        if zone_name == data.get('zone_name'):
                            print(f"      Same Zone ({zone_name}):")
                        else:
                            print(f"      {zone_name}:")
                        
                        for place in zone_places:
                            print(f"        • {place['name']} (ID: {place['id']})")
            except Exception as e:
                logger.debug(f"Could not get nearby places: {e}")
    else:
        print("\nNo setting locations")
    
    # Mentioned places
    mentioned = context.get('mentioned_places', {})
    if mentioned:
        print(f"\nMentioned Locations ({len(mentioned)}):")
        print("-" * 40)
        for place_id, data in mentioned.items():
            print(f"\n  {data.get('name', 'Unknown')} (ID: {place_id})")
            if data.get('summary'):
                print(f"    Summary: {data['summary']}")
    else:
        print("\nNo mentioned locations")
    
    # Zones
    zones = context.get('zones', {})
    if zones:
        print(f"\nZones ({len(zones)}):")
        print("-" * 40)
        for zone_id, data in zones.items():
            print(f"\n  {data.get('name', 'Unknown')} (ID: {zone_id})")
            if data.get('summary'):
                print(f"    Summary: {data['summary']}")
    
    print("\n" + "=" * 60)
    print(f"Summary: {context.get('summary', 'No summary')}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Test GAIA place context generation')
    parser.add_argument('--chunk', type=int, required=True, help='Chunk ID to analyze')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--output', type=str, help='Save JSON to file')
    parser.add_argument('--extended', action='store_true', help='Include extended spatial data')
    
    args = parser.parse_args()
    
    try:
        # Initialize MEMNON
        logger.info(f"Analyzing chunk {args.chunk} for place references...")
        
        # Create minimal interface for MEMNON
        class MinimalInterface:
            def assistant_message(self, msg): pass
            def error_message(self, msg): logger.error(msg)
        
        class MinimalAgentState:
            state = {"name": "test_gaia"}
        
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
        
        # Get place references from chunk
        place_refs = get_place_references(memnon, args.chunk)
        
        if not place_refs:
            logger.warning(f"No place references found in chunk {args.chunk}")
            # Still continue to show empty structure
        
        # Separate setting and mentioned places
        setting_ids = []
        mentioned_ids = []
        
        for ref in place_refs:
            if ref.get('is_primary') or ref.get('reference_type') == 'setting':
                setting_ids.append(ref['place_id'])
            elif ref.get('reference_type') == 'mentioned':
                mentioned_ids.append(ref['place_id'])
            elif ref.get('reference_type') == 'transit':
                mentioned_ids.append(ref['place_id'])
        
        # Remove duplicates while preserving order
        setting_ids = list(dict.fromkeys(setting_ids))
        mentioned_ids = list(dict.fromkeys(mentioned_ids))
        
        logger.info(f"Found {len(setting_ids)} setting, {len(mentioned_ids)} mentioned places")
        
        # Initialize GAIA utility
        gaia = GAIA(memnon)
        
        # Generate place context
        context = gaia.generate_place_context(
            setting_place_ids=setting_ids,
            mentioned_place_ids=mentioned_ids,
            expand_details=args.extended,
            include_inhabitants=True
        )
        
        # Add spatial minimap for setting locations (always included for 'Murica)
        for place_id in setting_ids:
            try:
                nearby = gaia.get_places_near(place_id, limit=5)
                if place_id in context['setting_places']:
                    # Convert to miles for display
                    nearby_formatted = []
                    for place in nearby:
                        nearby_formatted.append({
                            'id': place['id'],
                            'name': place['name'],
                            'distance_miles': round(meters_to_miles(place['distance_meters']), 2),
                            'bearing': format_bearing(place['bearing_degrees']),
                            'travel_time_min': round(place['travel_time_minutes'])
                        })
                    context['setting_places'][place_id]['nearby_places'] = nearby_formatted
            except Exception as e:
                logger.debug(f"Could not get nearby places for {place_id}: {e}")
        
        # Output results
        if args.json:
            output_data = {
                "chunk_id": args.chunk,
                "place_references": place_refs,
                "context": context
            }
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2, default=str)
                logger.info(f"Saved to {args.output}")
            else:
                print(json.dumps(output_data, indent=2, default=str))
        else:
            print_formatted(context, gaia, extended=args.extended)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()