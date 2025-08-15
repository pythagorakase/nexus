"""
GAIA - World State Tracking Utility Module

GAIA tracks the physical world state including locations, zones, 
factions, and spatial relationships. It provides spatial query 
capabilities and world consistency checking.
"""

from .gaia import GAIA

__all__ = ['GAIA']