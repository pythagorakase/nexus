"""
Database ENUM definitions for NEXUS Storyteller AI
===================================================

This module contains all PostgreSQL ENUM type definitions used in the NEXUS database,
represented as Python Enums for type safety and validation in Pydantic schemas.

These definitions MUST stay synchronized with the database constraints.
Any changes to database ENUMs should be reflected here immediately.
"""

from enum import Enum


class AgentType(str, Enum):
    """Types of AI agents in the NEXUS system"""
    LOGON = "LOGON"
    LORE = "LORE"
    GAIA = "GAIA"
    PSYCHE = "PSYCHE"
    MEMNON = "MEMNON"
    MAESTRO = "MAESTRO"
    NEMESIS = "NEMESIS"


class EmotionalValence(str, Enum):
    """Emotional valence scale for character relationships"""
    DEVOTED = "+5|devoted"
    ADMIRING = "+4|admiring"
    TRUSTING = "+3|trusting"
    FRIENDLY = "+2|friendly"
    FAVORABLE = "+1|favorable"
    NEUTRAL = "0|neutral"
    WARY = "-1|wary"
    DISAPPROVING = "-2|disapproving"
    RESENTFUL = "-3|resentful"
    HOSTILE = "-4|hostile"
    HATEFUL = "-5|hateful"


class EntityType(str, Enum):
    """Types of entities that can be referenced in chunks"""
    CHARACTER = "character"
    FACTION = "faction"
    PLACE = "place"
    ITEM = "item"  # Note: items table is currently empty


class FactionMemberRole(str, Enum):
    """Roles that characters can have within factions"""
    LEADER = "leader"
    EMPLOYEE = "employee"
    MEMBER = "member"
    TARGET = "target"
    INFORMANT = "informant"
    SYMPATHIZER = "sympathizer"
    DEFECTOR = "defector"
    EXILE = "exile"
    INSIDER_THREAT = "insider_threat"


class FactionRelationshipType(str, Enum):
    """Types of relationships between factions"""
    ALLIANCE = "alliance"
    TRADE_PARTNERS = "trade_partners"
    TRUCE = "truce"
    VASSALAGE = "vassalage"
    COALITION = "coalition"
    WAR = "war"
    RIVALRY = "rivalry"
    IDEOLOGICAL_ENEMY = "ideological_enemy"
    COMPETITOR = "competitor"
    SPLINTER = "splinter"
    UNKNOWN = "unknown"
    SHADOW_PARTNER = "shadow_partner"


class ItemType(str, Enum):
    """Categories of items in the world"""
    CURRENCY = "currency"
    WEAPON = "weapon"
    CYBERNETIC = "cybernetic"
    TECH = "tech"
    WEARABLE = "wearable"
    CONSUMABLE = "consumable"
    TOOL = "tool"
    DATA = "data"
    ARTIFACT = "artifact"


class LogLevel(str, Enum):
    """Logging levels for system operations"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ModelName(str, Enum):
    """Available LLM models"""
    GPT_5 = "gpt-5"
    GPT_4O = "gpt-4o"
    O3 = "o3"
    CLAUDE_SONNET_4_5 = "claude-sonnet-4-5"
    CLAUDE_OPUS_4_1 = "claude-opus-4-1"
    DEEPSEEK_V3_2_EXP = "deepseek-v3.2-exp"
    KIMI_K2_0905_PREVIEW = "kimi-k2-0905-preview"
    HERMES_4_405B = "hermes-4-405b"
    CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929"
    CLAUDE_OPUS_4_1_20250514 = "claude-opus-4-1-20250514"


class PlaceReferenceType(str, Enum):
    """How a place is referenced in a narrative chunk"""
    SETTING = "setting"     # The primary location where action occurs
    MENTIONED = "mentioned"  # Referenced but not visited
    TRANSIT = "transit"      # Passed through briefly


class PlaceType(str, Enum):
    """Categories of places in the world"""
    FIXED_LOCATION = "fixed_location"
    VEHICLE = "vehicle"
    VIRTUAL = "virtual"
    OTHER = "other"


class Provider(str, Enum):
    """LLM API providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    MOONSHOT = "moonshot"
    NOUSRESEARCH = "nousresearch"


class QueryCategory(str, Enum):
    """Categories for user queries"""
    CHARACTER = "character"
    EVENT = "event"
    GENERAL = "general"
    LOCATION = "location"
    RELATIONSHIP = "relationship"
    THEME = "theme"


class ReasoningEffort(str, Enum):
    """Level of reasoning effort for LLM operations"""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReferenceType(str, Enum):
    """How entities are referenced in chunks"""
    PRESENT = "present"     # Entity is actively present/participating
    MENTIONED = "mentioned"  # Entity is referenced but not present


class RelationshipType(str, Enum):
    """Types of relationships between characters"""
    FAMILY = "family"
    ROMANTIC = "romantic"
    FRIEND = "friend"
    COMPANION = "companion"
    ALLY = "ally"
    CONTACT = "contact"
    PEDAGOGICAL = "pedagogical"
    ACQUAINTANCE = "acquaintance"
    STRANGER = "stranger"
    COMPLEX = "complex"


class ThreatDomain(str, Enum):
    """Domains in which threats operate"""
    PHYSICAL = "physical"
    PSYCHOLOGICAL = "psychological"
    SOCIAL = "social"
    ENVIRONMENTAL = "environmental"


class ThreatLifecycle(str, Enum):
    """Stages in a threat's lifecycle"""
    INCEPTION = "inception"
    GESTATION = "gestation"
    MANIFESTATION = "manifestation"
    ESCALATION = "escalation"
    CULMINATION = "culmination"
    RESOLUTION = "resolution"
    AFTERMATH = "aftermath"


class WorldLayerType(str, Enum):
    """Narrative layers for chunk categorization"""
    PRIMARY = "primary"           # Main narrative timeline
    FLASHBACK = "flashback"       # Past events
    DREAM = "dream"               # Dream sequences
    EXTRADIEGETIC = "extradiegetic"  # Meta-narrative elements


# Validation helpers
def get_active_entity_types() -> list[str]:
    """
    Returns only entity types that have populated tables.
    Used to filter out empty entity types from API responses.
    """
    # TODO: Query database to dynamically determine which tables have data
    # For now, hardcoded based on known state:
    # - characters: populated (35 records)
    # - factions: populated (9 records)
    # - places: populated (100+ records)
    # - items: empty
    # - threats: empty (table doesn't exist)
    # - events: no table exists
    return ["character", "faction", "place"]