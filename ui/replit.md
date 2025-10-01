# NEXUS IRIS - Narrative Intelligence System

## Overview

NEXUS IRIS is an interactive cyberpunk narrative browser and visualization system. The application provides an immersive terminal-style interface for exploring a complex sci-fi story set in Night City, featuring AI consciousness, corporate intrigue, and digital immortality themes. Users can navigate through narrative chunks organized by seasons and episodes, explore character profiles and relationships, and view geographic locations on an interactive map.

The system manages a rich database of 1,425+ narrative chunks across 5 seasons, detailed character psychology profiles, relationship dynamics, faction interactions, and geographic data with zone boundaries.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture

**React + TypeScript SPA** with a cyberpunk terminal aesthetic:
- **Component Library**: Radix UI primitives styled with Tailwind CSS for accessibility and consistency
- **Design System**: Custom cyberpunk terminal theme with phosphor green (`#00ff41`), monospace fonts (Courier Prime, Source Code Pro), and CRT-inspired visual effects (scanlines, glow)
- **State Management**: TanStack Query for server state caching and synchronization
- **Routing**: Wouter for lightweight client-side routing
- **Layout**: Fixed-position status bar (top) and command bar (bottom), with tabbed content area supporting Narrative, Map, and Characters views
- **Responsive Design**: Mobile-first approach with hamburger menu and adaptive layouts

**Key UI Patterns**:
- Collapsible hierarchical navigation (Season → Episode → Chunk)
- Modal dialogs for detailed character profiles and chunk content
- SVG-based map visualization with zone polygons and place markers
- Typewriter effects for narrative streaming (planned feature)

### Backend Architecture

**Express.js REST API** with PostgreSQL database:
- **Server Framework**: Express.js with TypeScript, running on Node.js
- **Database ORM**: Drizzle ORM for type-safe database queries
- **API Design**: RESTful endpoints organized by resource type (narrative, characters, places, zones)
- **Development Tooling**: Vite for HMR during development, esbuild for production builds

**API Endpoints**:
- `/api/narrative/seasons` - List all seasons
- `/api/narrative/episodes/:seasonId` - Episodes for a season
- `/api/narrative/chunks/:episodeId` - Paginated chunks for an episode
- `/api/characters` - Character listings with ID range filtering
- `/api/characters/:id/relationships` - Character relationship network
- `/api/characters/:id/psychology` - Detailed psychological profile
- `/api/places` - Geographic locations with coordinates
- `/api/zones` - Zone boundaries (GeoJSON polygons)
- `/api/factions` - Faction information

### Data Storage Solutions

**PostgreSQL Database** with PostGIS extensions:
- **Primary Database**: Neon serverless PostgreSQL instance
- **Schema Design**: Normalized relational structure with JSONB for flexible metadata
- **Geospatial Data**: PostGIS geometry types for zone boundaries (MULTIPOLYGON) and place coordinates (POINTZM)
- **Key Tables**:
  - `narrative_chunks` - Story content with markdown text
  - `chunk_metadata` - Scene, episode, season, location, atmosphere, thematic elements
  - `characters` - Name, appearance, background, personality, emotional state
  - `character_psychology` - Self-concept, cognitive framework, defense mechanisms (JSONB)
  - `character_relationships` - Bidirectional relationships with emotional valence
  - `places` - Locations with geographic coordinates and zone membership
  - `zones` - Geographic regions with polygon boundaries
  - `episodes` - Episode summaries and chunk ranges
  - `seasons` - Season-level summaries
  - `factions` - Organizations with ideology, history, and power dynamics

**Schema Considerations**:
- Uses PostgreSQL-specific features (PostGIS, int8range, custom ENUMs, pgvector)
- Large JSON fields for flexible metadata storage (character psychology, episode summaries)
- Chunk references stored as many-to-many relationships (chunk_character_references, chunk_faction_references)
- 112,411 line SQL dump contains complete narrative dataset

### External Dependencies

**Core Infrastructure**:
- **Neon Database** (`@neondatabase/serverless`) - Serverless PostgreSQL hosting with WebSocket support for edge deployment
- **Drizzle ORM** (`drizzle-orm`, `drizzle-kit`, `drizzle-zod`) - Type-safe database queries with schema migrations and Zod validation
- **PostGIS** - Geospatial extensions for polygon and coordinate storage (zone boundaries, place locations)

**Frontend Libraries**:
- **TanStack Query** (`@tanstack/react-query`) - Server state management and caching
- **Radix UI** - Accessible component primitives (dialogs, collapsibles, tabs, scroll areas)
- **Tailwind CSS** - Utility-first styling with custom cyberpunk theme
- **Lucide React** - Icon library for UI elements

**Development Tools**:
- **Vite** - Development server with HMR and build tooling
- **TypeScript** - Type safety across client and server
- **esbuild** - Fast production bundling for server code
- **Wouter** - Lightweight client-side routing

**Planned Integrations** (based on TODO.md):
- AI model integration for narrative generation (Llama 3.3 mentioned in status bar)
- Asset management for character portraits (Alex Ward portrait already included)
- WebSocket support for real-time narrative streaming

**Data Import Process**:
- Manual SQL dump import: `psql $DATABASE_URL < attached_assets/massiveDUMP_1759202904039.sql`
- JSON data files for reference (characters, episodes, seasons, places, zones stored in `attached_assets/`)
- PostGIS geometry parsing required for zone boundaries and place coordinates