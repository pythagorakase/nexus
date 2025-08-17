"""
Spatial query utilities for GAIA.

Handles all PostGIS spatial operations including KNN searches,
distance calculations, and travel time estimates.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import math

logger = logging.getLogger("nexus.gaia.spatial")


@dataclass
class Place:
    """Simple place representation for spatial queries."""
    id: int
    name: str
    lat: float
    lon: float
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None


@dataclass
class SpatialResult:
    """Result from spatial query with distance information."""
    place: Place
    distance_meters: float
    bearing_degrees: float
    travel_time_minutes: float


class SpatialQuery:
    """
    Handles spatial queries using PostGIS functions.
    Uses MEMNON for database access.
    """
    
    def __init__(self, memnon):
        """
        Initialize with MEMNON instance for database access.
        
        Args:
            memnon: MEMNON instance for database operations
        """
        self.memnon = memnon
        self.DEFAULT_SPEED_KMH = 70  # Default motorcycle speed
        
    def places_in_same_zone(
        self, 
        place_id: int, 
        limit: Optional[int] = 10
    ) -> List[SpatialResult]:
        """
        Get places in the same zone as the given place, ordered by distance.
        
        Args:
            place_id: ID of the origin place
            limit: Maximum number of results
            
        Returns:
            List of SpatialResult objects ordered by distance
        """
        # First get the origin place and its zone
        origin_sql = """
        SELECT p.id, p.name, p.zone,
               ST_Y(p.coordinates::geometry) as lat,
               ST_X(p.coordinates::geometry) as lon,
               z.name as zone_name
        FROM places p
        LEFT JOIN zones z ON p.zone = z.id
        WHERE p.id = %s
        """
        
        origin_result = self.memnon.execute_readonly_sql(
            origin_sql.replace('%s', str(place_id))
        )
        
        if not origin_result or not origin_result.get('rows'):
            logger.warning(f"Place {place_id} not found")
            return []
            
        origin = origin_result['rows'][0]
        
        if not origin.get('zone'):
            logger.info(f"Place {place_id} has no zone")
            return []
        
        # Query for places in same zone with distances
        # If same zone doesn't yield enough results, expand search
        neighbors_sql = f"""
        WITH zone_places AS (
            -- First try to get places in same zone
            SELECT 
                p.id,
                p.name,
                p.zone,
                z.name as zone_name,
                ST_Y(p.coordinates::geometry) as lat,
                ST_X(p.coordinates::geometry) as lon,
                ST_Distance(
                    (SELECT coordinates FROM places WHERE id = {place_id}),
                    p.coordinates
                ) as distance_meters,
                degrees(
                    ST_Azimuth(
                        (SELECT geom FROM places WHERE id = {place_id}),
                        p.geom
                    )
                ) as bearing_degrees,
                1 as priority  -- Same zone gets priority
            FROM places p
            LEFT JOIN zones z ON p.zone = z.id
            WHERE p.zone = {origin['zone']} 
              AND p.id != {place_id}
              AND p.coordinates IS NOT NULL
            ORDER BY (SELECT geom FROM places WHERE id = {place_id}) <-> p.geom
            LIMIT {limit if limit else 10}
        ),
        other_places AS (
            -- If we don't have enough from same zone, get from other zones
            SELECT 
                p.id,
                p.name,
                p.zone,
                z.name as zone_name,
                ST_Y(p.coordinates::geometry) as lat,
                ST_X(p.coordinates::geometry) as lon,
                ST_Distance(
                    (SELECT coordinates FROM places WHERE id = {place_id}),
                    p.coordinates
                ) as distance_meters,
                degrees(
                    ST_Azimuth(
                        (SELECT geom FROM places WHERE id = {place_id}),
                        p.geom
                    )
                ) as bearing_degrees,
                2 as priority  -- Other zones get lower priority
            FROM places p
            LEFT JOIN zones z ON p.zone = z.id
            WHERE p.zone != {origin['zone']} 
              AND p.id != {place_id}
              AND p.coordinates IS NOT NULL
              AND (SELECT COUNT(*) FROM zone_places) < 3  -- Only if we need more
            ORDER BY (SELECT geom FROM places WHERE id = {place_id}) <-> p.geom
            LIMIT {limit if limit else 10}
        )
        SELECT * FROM (
            SELECT * FROM zone_places
            UNION ALL
            SELECT * FROM other_places
        ) combined
        ORDER BY priority, distance_meters
        LIMIT {limit if limit else 10}
        """
        
        result = self.memnon.execute_readonly_sql(neighbors_sql)
        
        if not result or not result.get('rows'):
            return []
            
        # Convert to SpatialResult objects
        results = []
        for row in result['rows']:
            place = Place(
                id=row['id'],
                name=row['name'],
                lat=row['lat'],
                lon=row['lon'],
                zone_id=row.get('zone', origin['zone']),
                zone_name=row.get('zone_name', origin.get('zone_name'))
            )
            
            distance_m = row['distance_meters']
            travel_time = self._estimate_travel_time(distance_m)
            
            results.append(SpatialResult(
                place=place,
                distance_meters=distance_m,
                bearing_degrees=row.get('bearing_degrees', 0),
                travel_time_minutes=travel_time
            ))
            
        return results
    
    def nearest_places(
        self, 
        lon: float, 
        lat: float, 
        k: int = 10
    ) -> List[SpatialResult]:
        """
        Find k-nearest places to a given coordinate.
        
        Args:
            lon: Longitude
            lat: Latitude  
            k: Number of nearest places to return
            
        Returns:
            List of SpatialResult objects ordered by distance
        """
        sql = f"""
        SELECT 
            p.id,
            p.name,
            ST_Y(p.coordinates::geometry) as lat,
            ST_X(p.coordinates::geometry) as lon,
            z.id as zone_id,
            z.name as zone_name,
            ST_DistanceSphere(
                ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geometry,
                p.geom
            ) as distance_meters,
            degrees(
                ST_Azimuth(
                    ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geometry,
                    p.geom
                )
            ) as bearing_degrees
        FROM places p
        LEFT JOIN zones z ON p.zone = z.id
        WHERE p.coordinates IS NOT NULL
        ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)::geometry
        LIMIT {k}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return []
            
        # Convert to SpatialResult objects
        results = []
        for row in result['rows']:
            place = Place(
                id=row['id'],
                name=row['name'],
                lat=row['lat'],
                lon=row['lon'],
                zone_id=row.get('zone_id'),
                zone_name=row.get('zone_name')
            )
            
            distance_m = row['distance_meters']
            travel_time = self._estimate_travel_time(distance_m)
            
            results.append(SpatialResult(
                place=place,
                distance_meters=distance_m,
                bearing_degrees=row.get('bearing_degrees', 0),
                travel_time_minutes=travel_time
            ))
            
        return results
    
    def distance_between_places(
        self, 
        place1_id: int, 
        place2_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate distance and travel time between two places.
        
        Args:
            place1_id: ID of first place
            place2_id: ID of second place
            
        Returns:
            Dict with distance, bearing, and travel time info
        """
        sql = f"""
        SELECT 
            p1.name as place1_name,
            p2.name as place2_name,
            ST_Distance(p1.coordinates, p2.coordinates) as distance_meters,
            degrees(ST_Azimuth(p1.geom, p2.geom)) as bearing_degrees,
            ST_AsText(p1.coordinates) as place1_coords,
            ST_AsText(p2.coordinates) as place2_coords
        FROM places p1, places p2
        WHERE p1.id = {place1_id} AND p2.id = {place2_id}
          AND p1.coordinates IS NOT NULL 
          AND p2.coordinates IS NOT NULL
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows') or not result['rows']:
            return None
            
        row = result['rows'][0]
        distance_m = row['distance_meters']
        
        return {
            'place1_name': row['place1_name'],
            'place2_name': row['place2_name'],
            'distance_meters': distance_m,
            'distance_km': distance_m / 1000,
            'distance_miles': distance_m / 1609.34,
            'bearing_degrees': row.get('bearing_degrees', 0),
            'travel_time_minutes': self._estimate_travel_time(distance_m),
            'place1_coords': row['place1_coords'],
            'place2_coords': row['place2_coords']
        }
    
    def minimap_for_chunk(
        self, 
        place_id: Optional[int] = None,
        mentioned_place_ids: Optional[List[int]] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Generate a minimap context for a narrative chunk.
        
        Args:
            place_id: Current location ID
            mentioned_place_ids: Other places mentioned in the chunk
            limit: Max places to include in same zone
            
        Returns:
            Dict with origin, nearby places, and mentioned places
        """
        minimap = {
            'origin': None,
            'same_zone_nearby': [],
            'mentioned_places': []
        }
        
        # Get origin place info if provided
        if place_id:
            origin_sql = f"""
            SELECT 
                p.id, p.name,
                ST_Y(p.coordinates::geometry) as lat,
                ST_X(p.coordinates::geometry) as lon,
                z.name as zone_name
            FROM places p
            LEFT JOIN zones z ON p.zone = z.id
            WHERE p.id = {place_id}
            """
            
            result = self.memnon.execute_readonly_sql(origin_sql)
            if result and result.get('rows'):
                row = result['rows'][0]
                minimap['origin'] = {
                    'id': row['id'],
                    'name': row['name'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'zone': row.get('zone_name')
                }
                
                # Get nearby places in same zone
                nearby = self.places_in_same_zone(place_id, limit)
                minimap['same_zone_nearby'] = [
                    {
                        'id': r.place.id,
                        'name': r.place.name,
                        'km': round(r.distance_meters / 1000, 1),
                        'bearing_deg': round(r.bearing_degrees, 0),
                        'eta_min': round(r.travel_time_minutes, 0)
                    }
                    for r in nearby
                ]
        
        # Get info for mentioned places
        if mentioned_place_ids and place_id:
            for mentioned_id in mentioned_place_ids:
                if mentioned_id != place_id:
                    distance_info = self.distance_between_places(place_id, mentioned_id)
                    if distance_info:
                        minimap['mentioned_places'].append({
                            'id': mentioned_id,
                            'name': distance_info['place2_name'],
                            'km': round(distance_info['distance_km'], 1),
                            'bearing_deg': round(distance_info['bearing_degrees'], 0),
                            'eta_min': round(distance_info['travel_time_minutes'], 0)
                        })
        
        return minimap
    
    def _estimate_travel_time(
        self, 
        distance_meters: float, 
        speed_kmh: Optional[float] = None
    ) -> float:
        """
        Estimate travel time based on distance.
        
        Args:
            distance_meters: Distance in meters
            speed_kmh: Speed in km/h (default: motorcycle speed)
            
        Returns:
            Travel time in minutes
        """
        if speed_kmh is None:
            speed_kmh = self.DEFAULT_SPEED_KMH
            
        distance_km = distance_meters / 1000
        hours = distance_km / speed_kmh
        return hours * 60  # Convert to minutes