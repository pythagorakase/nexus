#!/usr/bin/env python
"""
Test GAIA spatial functionality.
"""

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.gaia.gaia import GAIA

# Dummy interface for MEMNON
class DummyInterface:
    def __init__(self):
        pass

# Initialize MEMNON
print("Initializing MEMNON...")
memnon = MEMNON(DummyInterface(), headless=True)

# Initialize GAIA with MEMNON
print("Initializing GAIA...")
gaia = GAIA(memnon)

# Test 1: Distance between Night City and The Silo
print("\n=== Test 1: Distance between places ===")
distance_info = gaia.calculate_distance(131, 181)  # Sato's Night City Safehouse to The Silo
if distance_info:
    print(f"From: {distance_info['place1_name']}")
    print(f"To: {distance_info['place2_name']}")
    print(f"Distance: {distance_info['distance_km']:.1f} km ({distance_info['distance_miles']:.1f} miles)")
    print(f"Travel time: {distance_info['travel_time_minutes']:.0f} minutes")
    print(f"Bearing: {distance_info['bearing_degrees']:.0f}°")

# Test 2: Places near The Silo
print("\n=== Test 2: Places near The Silo ===")
nearby = gaia.get_places_near(181, limit=5)
for place in nearby:
    print(f"- {place['name']}: {place['distance_km']:.1f} km, {place['travel_time_minutes']:.0f} min")

# Test 3: Nearest places to arbitrary coordinates
print("\n=== Test 3: Nearest to coordinates ===")
nearest = gaia.find_nearest_places(-77.0, 39.0, k=3)
for place in nearest:
    print(f"- {place['name']}: {place['distance_km']:.1f} km away")

# Test 4: Generate minimap
print("\n=== Test 4: Minimap for The Silo ===")
minimap = gaia.generate_minimap(place_id=181, mentioned_places=[131, 119])
print(f"Origin: {minimap['origin']['name']} ({minimap['origin']['zone']})")
print(f"Nearby in same zone: {len(minimap['same_zone_nearby'])} places")
for place in minimap['same_zone_nearby'][:3]:
    print(f"  - {place['name']}: {place['km']} km")
print(f"Mentioned places: {len(minimap['mentioned_places'])} places")
for place in minimap['mentioned_places']:
    print(f"  - {place['name']}: {place['km']} km")

print("\n✅ GAIA tests complete!")