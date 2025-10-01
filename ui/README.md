# NEXUS IRIS - Narrative Intelligence System

A cyberpunk terminal-style interface for exploring complex narrative datasets. Built with React, TypeScript, Express, and PostgreSQL.

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
- **Backend**: Express.js, Node.js
- **Database**: PostgreSQL with PostGIS extensions
- **ORM**: Drizzle ORM
- **State Management**: TanStack Query
- **Routing**: Wouter

## Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set up PostgreSQL database**:
   - Create a Neon or local PostgreSQL database
   - Set `DATABASE_URL` environment variable
   
3. **Import narrative data** (if not already present):
   ```bash
   psql $DATABASE_URL < attached_assets/massiveDUMP_1759202904039.sql
   ```

4. **Run development server**:
   ```bash
   npm run dev
   ```

5. **Access the application**:
   - Open http://localhost:5000

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
├── server/             # Express backend
│   ├── routes.ts       # API endpoints
│   ├── storage.ts      # Data access layer
│   └── index.ts        # Server entry point
├── shared/             # Shared types and schemas
│   └── schema.ts       # Drizzle ORM schemas
└── attached_assets/    # SQL dump and reference data
```

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
- Frontend: React + TypeScript
- Backend: Express with `tsx` for TypeScript execution
- Database: Drizzle ORM with type-safe queries

For database schema changes, use:
```bash
npm run db:push
```

## License

MIT
