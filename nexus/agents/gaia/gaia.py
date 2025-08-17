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
    
    # ========== Auto-generation Methods for LORE ==========
    
    def generate_place_context(
        self,
        setting_place_ids: List[int],
        mentioned_place_ids: List[int],
        expand_details: bool = False,
        include_inhabitants: bool = True
    ) -> Dict[str, Any]:
        """
        Generate automatic place context for narrative generation.
        
        Args:
            setting_place_ids: IDs of places where scenes occur
            mentioned_place_ids: IDs of places mentioned but not visited
            expand_details: Whether to include full place details
            include_inhabitants: Whether to include inhabitant lists
            
        Returns:
            Dict containing place context organized by category
        """
        context = {
            "setting_places": {},
            "mentioned_places": {},
            "zones": {},
            "summary": ""
        }
        
        # Process setting places (where action occurs)
        for place_id in setting_place_ids:
            place_data = self._get_place_essentials(
                place_id,
                include_current_status=True,
                include_inhabitants=include_inhabitants
            )
            if place_data:
                context["setting_places"][place_id] = place_data
                # Track zone
                if place_data.get("zone"):
                    zone_id = place_data["zone"]
                    if zone_id not in context["zones"]:
                        context["zones"][zone_id] = self._get_zone_summary(zone_id)
        
        # Process mentioned places
        for place_id in mentioned_place_ids:
            # Skip if already in setting
            if place_id not in setting_place_ids:
                place_data = self._get_place_essentials(
                    place_id,
                    include_current_status=False,
                    include_inhabitants=False
                )
                if place_data:
                    context["mentioned_places"][place_id] = place_data
        
        # Add expanded details if requested
        if expand_details:
            for place_id in setting_place_ids:
                if place_id in context["setting_places"]:
                    expanded = self._get_place_expanded(place_id)
                    if expanded:
                        context["setting_places"][place_id].update(expanded)
        
        # Generate summary
        context["summary"] = self._generate_place_summary(context)
        
        return context
    
    def _get_place_essentials(
        self,
        place_id: int,
        include_current_status: bool = False,
        include_inhabitants: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get essential place information.
        
        Args:
            place_id: Place ID
            include_current_status: Include current_status field
            include_inhabitants: Include inhabitants array
            
        Returns:
            Place data dict or None if not found
        """
        # Build dynamic field list
        fields = ["id", "name", "type", "zone", "summary"]
        if include_current_status:
            fields.append("current_status")
        if include_inhabitants:
            fields.append("inhabitants")
        
        # Also get coordinates for spatial context
        sql = f"""
        SELECT 
            {', '.join(fields)},
            ST_Y(coordinates::geometry) as lat,
            ST_X(coordinates::geometry) as lon
        FROM places
        WHERE id = {place_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            logger.warning(f"Place {place_id} not found")
            return None
        
        row = result['rows'][0]
        place_data = {field: row.get(field) for field in fields if row.get(field) is not None}
        
        # Add coordinates if available
        if row.get('lat') and row.get('lon'):
            place_data['coordinates'] = {
                'lat': row['lat'],
                'lon': row['lon']
            }
        
        return place_data
    
    def _get_place_expanded(self, place_id: int) -> Optional[Dict[str, Any]]:
        """
        Get expanded place details.
        
        Args:
            place_id: Place ID
            
        Returns:
            Expanded place data or None
        """
        sql = f"""
        SELECT 
            history, secrets, extra_data
        FROM places
        WHERE id = {place_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return None
        
        row = result['rows'][0]
        expanded = {}
        
        if row.get('history'):
            expanded['history'] = row['history']
        if row.get('secrets'):
            expanded['secrets'] = row['secrets']
        if row.get('extra_data'):
            expanded['extra_data'] = row['extra_data']
        
        return expanded if expanded else None
    
    def _get_zone_summary(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Get zone summary information.
        
        Args:
            zone_id: Zone ID
            
        Returns:
            Zone summary or None
        """
        sql = f"""
        SELECT 
            id, name, summary,
            ST_Y(ST_Centroid(boundary)) as centroid_lat,
            ST_X(ST_Centroid(boundary)) as centroid_lon
        FROM zones
        WHERE id = {zone_id}
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return None
        
        row = result['rows'][0]
        return {
            'id': row['id'],
            'name': row.get('name'),
            'summary': row.get('summary'),
            'centroid': {
                'lat': row.get('centroid_lat'),
                'lon': row.get('centroid_lon')
            } if row.get('centroid_lat') else None
        }
    
    def _generate_place_summary(self, context: Dict[str, Any]) -> str:
        """
        Generate a brief summary of the place context.
        
        Args:
            context: The full place context dict
            
        Returns:
            Summary string
        """
        setting_count = len(context.get("setting_places", {}))
        mentioned_count = len(context.get("mentioned_places", {}))
        zone_count = len(context.get("zones", {}))
        
        summary_parts = []
        
        if setting_count > 0:
            setting_names = [p.get("name", "Unknown") for p in context["setting_places"].values()]
            summary_parts.append(f"Settings: {', '.join(setting_names[:2])}" +
                                (" and others" if setting_count > 2 else ""))
        
        if mentioned_count > 0:
            mentioned_names = [p.get("name", "Unknown") for p in context["mentioned_places"].values()]
            summary_parts.append(f"Mentioned: {', '.join(mentioned_names[:2])}" +
                                (" and others" if mentioned_count > 2 else ""))
        
        if zone_count > 0:
            zone_names = [z.get("name", "Unknown") for z in context["zones"].values()]
            summary_parts.append(f"Zones: {', '.join(zone_names)}")
        
        return " | ".join(summary_parts) if summary_parts else "No place context"
    
    def analyze_chunk_places(self, chunk_id: int) -> Dict[str, Any]:
        """
        Analyze place references in a specific chunk.
        
        Args:
            chunk_id: Narrative chunk ID
            
        Returns:
            Dict with setting and mentioned place IDs
        """
        # First check chunk_metadata for primary place
        primary_sql = f"""
        SELECT place
        FROM chunk_metadata
        WHERE chunk_id = {chunk_id}
        """
        
        primary_result = self.memnon.execute_readonly_sql(primary_sql)
        primary_place = None
        if primary_result and primary_result.get('rows') and primary_result['rows'][0].get('place'):
            primary_place = primary_result['rows'][0]['place']
        
        # Then check place_chunk_references
        refs_sql = f"""
        SELECT 
            place_id,
            reference_type
        FROM place_chunk_references
        WHERE chunk_id = {chunk_id}
        """
        
        refs_result = self.memnon.execute_readonly_sql(refs_sql)
        
        setting = []
        mentioned = []
        
        # Add primary place as setting if it exists
        if primary_place:
            setting.append(primary_place)
        
        if refs_result and refs_result.get('rows'):
            for row in refs_result['rows']:
                place_id = row['place_id']
                ref_type = row.get('reference_type')
                
                if ref_type == 'setting' and place_id not in setting:
                    setting.append(place_id)
                elif ref_type == 'mentioned':
                    mentioned.append(place_id)
                elif ref_type == 'transit':
                    # Transit places could be considered mentioned
                    mentioned.append(place_id)
        
        return {
            "chunk_id": chunk_id,
            "setting_place_ids": setting,
            "mentioned_place_ids": mentioned
        }
    
    def get_place_list(self) -> List[Dict[str, Any]]:
        """
        Get minimal list of all places (for Apex AI reference).
        
        Returns:
            List of dicts with place id and name
        """
        sql = """
        SELECT id, name
        FROM places
        ORDER BY id
        """
        
        result = self.memnon.execute_readonly_sql(sql)
        
        if not result or not result.get('rows'):
            return []
        
        return [{"id": row['id'], "name": row['name']} for row in result['rows']]
    
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