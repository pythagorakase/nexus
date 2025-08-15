"""
GAIA - World State Tracking Utility Module

GAIA is responsible for tracking the physical world state including
locations, zones, factions, and spatial relationships. Currently 
implements spatial queries with plans for full world state tracking.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from .utils.spatial import SpatialQuery, SpatialResult

logger = logging.getLogger("nexus.gaia")


class GAIA:
    """
    World state tracking utility module.
    
    Current capabilities:
    - Spatial queries (distances, nearest neighbors, travel times)
    - Zone containment and relationships
    - Minimap generation for narrative context
    
    Future capabilities (TODO):
    - Faction territory tracking
    - Object location tracking
    - World state consistency checking
    - Temporal state management
    - Causal relationship tracking
    """
    
    def __init__(self, memnon_instance):
        """
        Initialize GAIA with a MEMNON instance for database access.
        
        Args:
            memnon_instance: MEMNON agent instance for DB operations
        """
        self.memnon = memnon_instance
        self.spatial = SpatialQuery(memnon_instance)
        logger.info("GAIA world state tracker initialized")
        
    # ========== Spatial Query Methods ==========
    
    def get_places_near(
        self, 
        place_id: int, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get places near a given place (in same zone).
        
        Args:
            place_id: ID of origin place
            limit: Maximum results
            
        Returns:
            List of nearby places with distance info
        """
        results = self.spatial.places_in_same_zone(place_id, limit)
        return self._format_spatial_results(results)
    
    def find_nearest_places(
        self, 
        lon: float, 
        lat: float, 
        k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find k-nearest places to coordinates.
        
        Args:
            lon: Longitude
            lat: Latitude
            k: Number of results
            
        Returns:
            List of nearest places with distance info
        """
        results = self.spatial.nearest_places(lon, lat, k)
        return self._format_spatial_results(results)
    
    def calculate_distance(
        self, 
        place1_id: int, 
        place2_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate distance between two places.
        
        Args:
            place1_id: First place ID
            place2_id: Second place ID
            
        Returns:
            Distance and travel info
        """
        return self.spatial.distance_between_places(place1_id, place2_id)
    
    def generate_minimap(
        self,
        place_id: Optional[int] = None,
        mentioned_places: Optional[List[int]] = None,
        context_size: int = 5
    ) -> Dict[str, Any]:
        """
        Generate spatial context minimap for narrative.
        
        Args:
            place_id: Current location ID
            mentioned_places: Other mentioned place IDs
            context_size: Number of nearby places to include
            
        Returns:
            Minimap dict with origin and nearby places
        """
        return self.spatial.minimap_for_chunk(
            place_id=place_id,
            mentioned_place_ids=mentioned_places,
            limit=context_size
        )
    
    # ========== Zone Methods ==========
    
    def get_zone_info(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Get information about a zone.
        
        Args:
            zone_id: Zone ID
            
        Returns:
            Zone information including boundary
        """
        sql = f"""
        SELECT 
            z.id, z.name, z.description,
            ST_AsGeoJSON(z.boundary) as boundary_geojson,
            ST_Y(ST_Centroid(z.boundary)) as centroid_lat,
            ST_X(ST_Centroid(z.boundary)) as centroid_lon,
            COUNT(p.id) as place_count
        FROM zones z
        LEFT JOIN places p ON p.zone = z.id
        WHERE z.id = {zone_id}
        GROUP BY z.id, z.name, z.description, z.boundary
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return None
            
        row = result['rows'][0]
        return {
            'id': row['id'],
            'name': row['name'],
            'description': row.get('description'),
            'centroid': {
                'lat': row.get('centroid_lat'),
                'lon': row.get('centroid_lon')
            },
            'place_count': row.get('place_count', 0),
            'boundary_geojson': row.get('boundary_geojson')
        }
    
    def get_places_in_zone(self, zone_id: int) -> List[Dict[str, Any]]:
        """
        Get all places within a zone.
        
        Args:
            zone_id: Zone ID
            
        Returns:
            List of places in the zone
        """
        sql = f"""
        SELECT 
            p.id, p.name, p.summary,
            ST_Y(p.coordinates::geometry) as lat,
            ST_X(p.coordinates::geometry) as lon
        FROM places p
        WHERE p.zone = {zone_id}
          AND p.coordinates IS NOT NULL
        ORDER BY p.name
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return []
            
        return [
            {
                'id': row['id'],
                'name': row['name'],
                'summary': row.get('summary'),
                'lat': row.get('lat'),
                'lon': row.get('lon')
            }
            for row in result['rows']
        ]
    
    # ========== Faction Methods ==========
    
    def get_faction_territory(self, faction_id: int) -> Dict[str, Any]:
        """
        Get territorial control information for a faction.
        
        Args:
            faction_id: Faction ID
            
        Returns:
            Faction territory information
        """
        # Get faction basic info
        faction_sql = f"""
        SELECT 
            f.id, f.name, f.summary, f.power_level,
            f.territory, f.primary_location,
            p.name as hq_name,
            ST_Y(p.coordinates::geometry) as hq_lat,
            ST_X(p.coordinates::geometry) as hq_lon
        FROM factions f
        LEFT JOIN places p ON f.primary_location = p.id
        WHERE f.id = {faction_id}
        """
        
        result = self.memnon.execute_readonly_sql(faction_sql)
        
        if not result or not result.get('rows'):
            return None
            
        faction = result['rows'][0]
        
        # TODO: Expand to track actual controlled locations
        # For now, return basic faction info with HQ location
        return {
            'id': faction['id'],
            'name': faction['name'],
            'summary': faction.get('summary'),
            'power_level': float(faction.get('power_level', 0.5)),
            'territory_description': faction.get('territory'),
            'headquarters': {
                'place_id': faction.get('primary_location'),
                'name': faction.get('hq_name'),
                'lat': faction.get('hq_lat'),
                'lon': faction.get('hq_lon')
            } if faction.get('primary_location') else None
        }
    
    # ========== Future World State Methods (TODO) ==========
    
    def track_object_location(self, object_id: int, location_id: int):
        """
        TODO: Track an object's location.
        Future implementation for object tracking.
        """
        raise NotImplementedError("Object tracking not yet implemented")
    
    def check_world_consistency(self) -> List[Dict[str, Any]]:
        """
        TODO: Check world state for inconsistencies.
        Future implementation for consistency checking.
        """
        raise NotImplementedError("World consistency checking not yet implemented")
    
    def get_world_timeline(
        self, 
        start_time=None, 
        end_time=None
    ) -> List[Dict[str, Any]]:
        """
        TODO: Get timeline of world state changes.
        Future implementation for temporal tracking.
        """
        raise NotImplementedError("Timeline tracking not yet implemented")
    
    # ========== Helper Methods ==========
    
    def _format_spatial_results(
        self, 
        results: List[SpatialResult]
    ) -> List[Dict[str, Any]]:
        """
        Format SpatialResult objects for output.
        
        Args:
            results: List of SpatialResult objects
            
        Returns:
            List of formatted dicts
        """
        return [
            {
                'id': r.place.id,
                'name': r.place.name,
                'lat': r.place.lat,
                'lon': r.place.lon,
                'zone_name': r.place.zone_name,
                'distance_meters': round(r.distance_meters, 0),
                'distance_km': round(r.distance_meters / 1000, 1),
                'bearing_degrees': round(r.bearing_degrees, 0),
                'travel_time_minutes': round(r.travel_time_minutes, 0)
            }
            for r in results
        ]