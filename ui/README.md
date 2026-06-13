# NEXUS IRIS - Narrative Intelligence System

A cyberpunk terminal-style interface for exploring complex narrative datasets. Built with React and TypeScript, served by the NEXUS FastAPI gateway.

## Features

### 📖 Narrative Browser
- Hierarchical navigation through seasons, episodes, and narrative chunks
- 1,425+ story chunks organized across 5 seasons
- Expandable/collapsible tree structure with smooth interactions

### 🗺️ Interactive Map
- 45 global locations with conditional label visibility
- Zone-based location index sidebar
- Smart color coding (green: default, cyan: selected, yellow: current narrative)
- Pan and zoom controls with drag navigation

### 👥 Character Profiles
- 35 characters with detailed profiles
- Relationship network visualization
- Psychology profiles with cognitive frameworks
- Character grouping by ID ranges

## Tech Stack

- **Frontend**: React 18, TypeScript, Tailwind CSS, Radix UI
- **Backend**: NEXUS FastAPI gateway (`nexus.api.narrative:app`, one origin
  for APIs, websocket, and static PWA serving; see `../README.md`)
- **Database**: PostgreSQL with PostGIS extensions (per-slot databases)
- **State Management**: TanStack Query
- **Routing**: Wouter

## Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start the gateway** (from the repo root):
   ```bash
   ./iris
   ```

3. **Run the dev server with HMR** (proxies `/api`, `/ws`, and uploads to
   the gateway):
   ```bash
   npm run dev
   ```

4. **Access the application**:
   - Dev (HMR): http://localhost:5001
   - Production build via the gateway: http://localhost:8002
     (after `npm run build`)

## Database Schema

The application uses a comprehensive PostgreSQL schema with:
- `narrative_chunks` - Story content with metadata
- `characters` - Character profiles and psychology
- `character_relationships` - Relationship networks
- `places` - Geographic locations (45 with coordinates)
- `zones` - Geographic regions (20 total)
- `episodes` & `seasons` - Narrative structure
- `factions` - Organizations and power dynamics

## Project Structure

```
├── client/src/          # React frontend
│   ├── components/      # UI components (NarrativeTab, MapTab, CharactersTab)
│   ├── pages/          # Page components
│   └── lib/            # Utilities and query client
└── shared/             # Shared types (wire-format declarations only)
    └── schema.ts       # Type declarations for gateway responses
```

API endpoints are implemented in the FastAPI gateway
(`nexus/api/reader_endpoints.py`, `nexus/api/asset_endpoints.py`, and
peers); the built PWA is served from `dist/public` by
`nexus/api/static_ui.py`.

## API Endpoints

- `GET /api/narrative/seasons` - List all seasons
- `GET /api/narrative/episodes/:seasonId` - Episodes for a season
- `GET /api/narrative/chunks/:episodeId` - Paginated chunks
- `GET /api/characters` - Character listings
- `GET /api/characters/:id/relationships` - Relationship network
- `GET /api/characters/:id/psychology` - Psychology profile
- `GET /api/places` - Geographic locations
- `GET /api/zones` - Zone boundaries
- `GET /api/factions` - Faction information

## Design Philosophy

NEXUS IRIS uses a cyberpunk terminal aesthetic with:
- Phosphor green (#00ff41) primary color
- Monospace fonts (Courier Prime, Source Code Pro)
- CRT-inspired visual effects (scanlines, glow)
- Minimal, information-on-demand interface
- Dark theme optimized for extended reading

## Development

The project uses Vite for fast development with HMR:
- Frontend: React + TypeScript (Vite dev server on port 5001)
- Backend: NEXUS FastAPI gateway (port 8002)

Database schema changes go through the repo-root migration workflow
(`scripts/migrate.py`); see the root `CLAUDE.md`.

## License

MIT
