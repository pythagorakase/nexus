# NEXUS UI Design Document

## Vision Statement
A retrofuturistic web interface for narrative exploration that captures the aesthetic of 1980s cyberpunk terminals while providing modern performance and usability. Think "what if Gibson's cyberspace cowboys had React" - authentic terminal aesthetics without terminal limitations.

## Aesthetic & Visual Design

### Core Visual Identity
- **Era**: 1980s-1990s cyberpunk terminal
- **Reference Points**: 
  - Blade Runner computer terminals
  - Gibson's Neuromancer descriptions
  - Original Shadowrun decker interfaces
  - War Games / WOPR terminal
  - Alien (1979) Nostromo computer displays
- **Feel**: Phosphor CRT glow, subtle scanlines, monospace typography, functional minimalism

### Color Palette

```css
/* Primary - LORE's signature green phosphor */
--nexus-green-primary: #41FF00;     /* Main text/borders */
--nexus-green-secondary: #33FF33;   /* Hover states */
--nexus-green-glow: #39FF14;        /* Glow effects */
--nexus-green-dim: #2A8F00;         /* Inactive/dim states */

/* User Interface - Purple/Magenta */
--nexus-user: #9933FF;               /* User input/prompts */
--nexus-user-bright: #CC66FF;       /* User highlights */

/* System - Cyan */
--nexus-system: #00FFFF;             /* System messages */
--nexus-system-dim: #00A0A0;        /* System secondary */

/* Alerts & Errors */
--nexus-error: #FF33FF;              /* Errors/warnings */
--nexus-error-alt: #FF6633;         /* Critical errors */
--nexus-warning: #FFB000;           /* Warnings */

/* Background */
--nexus-bg: #000000;                 /* Pure black */
--nexus-bg-panel: #0A0A0A;          /* Slight elevation */
--nexus-scanline: rgba(0, 255, 0, 0.03); /* CRT effect */
```

### Typography

```css
/* Primary font stack */
font-family: 'IBM Plex Mono', 'Fira Code', 'Source Code Pro', 
             'Courier New', monospace;

/* Sizes */
--text-xs: 0.75rem;   /* 12px - metadata */
--text-sm: 0.875rem;  /* 14px - secondary info */
--text-base: 1rem;    /* 16px - main content */
--text-lg: 1.125rem;  /* 18px - headers */

/* All text should have subtle glow */
text-shadow: 0 0 5px currentColor;
```

### Visual Effects

```css
/* CRT Phosphor Glow */
.phosphor-glow {
  text-shadow: 
    0 0 5px currentColor,
    0 0 10px currentColor,
    0 0 15px rgba(65, 255, 0, 0.5);
}

/* Scanline Overlay */
.crt-scanlines::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    transparent 50%,
    var(--nexus-scanline) 50%
  );
  background-size: 100% 4px;
  pointer-events: none;
  z-index: 1;
}

/* Flicker Animation (subtle) */
@keyframes terminal-flicker {
  0%, 100% { opacity: 1; }
  92% { opacity: 0.98; }
}

/* Boot Sequence Animation */
@keyframes boot-sequence {
  0% { 
    opacity: 0;
    filter: blur(2px);
  }
  50% {
    opacity: 1;
    filter: blur(1px);
  }
  100% {
    opacity: 1;
    filter: blur(0);
  }
}
```

## Component Architecture

### Layout Structure

```typescript
interface AppLayout {
  statusBar: StatusBar;          // Top - system status
  mainContent: {
    narrative: NarrativePane;    // Center - primary content
    navigation?: NavigationPane; // Right - collapsible outline
    telemetry?: TelemetryPane;  // Left - collapsible debug info
  };
  commandBar: CommandBar;        // Bottom - input interface
}
```

### Core Components

#### 1. StatusBar
```typescript
interface StatusBar {
  left: {
    title: "NEXUS";
    model: string;        // "llama-70b" or "gpt-oss-120b"
    dbStatus: "OK" | "ERROR" | "CONNECTING";
  };
  center: {
    currentChunk: number;
    season: number;
    episode: number;
    scene: number;
  };
  right: {
    latency: number;      // ms
    timestamp: string;    // "23:45:17"
  };
}
```

#### 2. NarrativePane (Main Content)
```typescript
interface NarrativePane {
  mode: "read" | "query" | "stream";
  content: ChunkDisplay | QueryResult | StreamingResponse;
  scrollBehavior: "smooth" | "instant";
  virtualScroll: boolean; // Use react-window for performance
}

interface ChunkDisplay {
  target: NarrativeChunk;
  context: NarrativeChunk[]; // -10 to +10 chunks
  highlighting?: TextHighlight[]; // For search results
}
```

#### 3. NavigationPane (Outline)
```typescript
interface NavigationPane {
  type: "tree" | "timeline" | "graph";
  data: StoryOutline;
  expandedNodes: Set<string>;
  onNodeClick: (chunkId: number) => void;
}

interface StoryOutline {
  seasons: Array<{
    number: number;
    episodes: Array<{
      number: number;
      title?: string;
      scenes: Array<{
        number: number;
        chunkId: number;
        preview: string; // First 50 chars
      }>;
    }>;
  }>;
}
```

#### 4. TelemetryPane (Debug/Reasoning)
```typescript
interface TelemetryPane {
  sections: {
    reasoning?: ReasoningStream;
    queries?: GeneratedQuery[];
    sqlAttempts?: SQLAttempt[];
    performance?: PerformanceMetrics;
  };
  autoScroll: boolean;
  verbosity: "minimal" | "normal" | "verbose";
}
```

#### 5. CommandBar
```typescript
interface CommandBar {
  mode: "command" | "input";
  history: string[];
  currentInput: string;
  suggestions?: CommandSuggestion[];
  placeholder: "Enter directive or /command...";
}
```

### Command System

```typescript
enum Commands {
  READ = "/read",      // /read s03e05[c004] or /read <chunk_id>
  QUERY = "/query",    // /query "What happened to Emilia?"
  CHUNK = "/chunk",    // /chunk <id>
  NAV = "/nav",        // /nav show|hide|tree|timeline
  TELEMETRY = "/telem", // /telem show|hide|verbose
  THEME = "/theme",    // /theme crt|clean|matrix
  EXPORT = "/export",  // /export json|md|txt
  HELP = "/help",      // /help [command]
  CLEAR = "/clear",    // /clear
}
```

## Backend Integration

### API Endpoints Required

```typescript
// Core narrative operations
GET  /api/chunk/{id}
GET  /api/chunk/{id}/context?window=10
GET  /api/narrative/search?q={query}
GET  /api/outline

// LORE operations
POST /api/query
  body: { directive: string, chunkId: number }
  returns: Stream<ReasoningStep | Result>

GET  /api/status
  returns: { model: string, db: boolean, telemetry: object }

// Real-time updates (WebSocket)
WS   /api/ws
  -> { type: "subscribe", channel: "reasoning" }
  <- { type: "reasoning", data: {...} }
```

### Data Models

```typescript
interface NarrativeChunk {
  id: number;
  season: number;
  episode: number;
  scene: number;
  text: string;
  metadata: {
    location?: string;
    timestamp?: string;
    characters?: string[];
  };
}

interface QueryResult {
  directive: string;
  chunkId: number;
  reasoning: ReasoningStep[];
  queries: string[];
  results: NarrativeChunk[];
  summary: string;
  latency: number;
}

interface ReasoningStep {
  timestamp: number;
  type: "analysis" | "search" | "synthesis";
  content: string;
}
```

## Performance Requirements

### Critical Metrics
- Initial page load: < 1 second
- Chunk navigation: < 50ms
- Virtual scroll FPS: 60fps minimum
- Memory usage: < 100MB for 10k chunks
- Copy/paste latency: Native (0ms)

### Optimization Strategies
1. **Virtual Scrolling**: Only render visible chunks using `react-window`
2. **Code Splitting**: Lazy load telemetry and navigation panes
3. **Caching**: LRU cache for recently viewed chunks
4. **Prefetching**: Load ±50 chunks around current position
5. **WebSocket Streaming**: Stream reasoning steps as they occur

## Interactive States

### Loading States
```css
/* Typewriter effect for loading */
@keyframes typewriter {
  from { width: 0; }
  to { width: 100%; }
}

.loading-text {
  overflow: hidden;
  white-space: nowrap;
  animation: typewriter 2s steps(40, end);
}
```

### Keyboard Shortcuts
- `↑/↓` - Navigate history
- `PgUp/PgDn` - Scroll chunks
- `Ctrl+K` - Clear screen
- `Ctrl+L` - Focus command bar
- `Ctrl+N` - Toggle navigation
- `Ctrl+T` - Toggle telemetry
- `Ctrl+C` - Copy selection (native)
- `/` - Quick command mode
- `Esc` - Cancel/close panels

## Theme Variations

### 1. Classic CRT (Default)
- Full phosphor glow effects
- Scanlines enabled
- Slight flicker animation
- Green monochrome

### 2. Clean Terminal
- No scanlines
- Reduced glow
- Static display
- Multi-color support

### 3. Matrix Rain (Easter Egg)
- Digital rain background
- Green cascade effects
- Character substitution animations

## Responsive Design

### Desktop (>1280px)
- Three-column layout
- All panels visible
- Full telemetry display

### Tablet (768-1280px)
- Two-column layout
- Navigation collapsed by default
- Telemetry as overlay

### Mobile (Not Recommended)
- Single column
- Read-only mode
- Swipe navigation
- No telemetry

## Implementation Notes

### React Component Tree
```
<App>
  <ThemeProvider theme={currentTheme}>
    <StatusBar />
    <MainLayout>
      <TelemetryPane />     {/* Optional */}
      <NarrativePane />     {/* Always visible */}
      <NavigationPane />    {/* Collapsible */}
    </MainLayout>
    <CommandBar />
  </ThemeProvider>
</App>
```

### State Management
```typescript
// Use Zustand or Redux Toolkit
interface AppState {
  // Navigation
  currentChunk: number;
  chunkBuffer: Map<number, NarrativeChunk>;
  
  // UI State
  panels: {
    navigation: boolean;
    telemetry: boolean;
  };
  
  // LORE State
  activeQuery?: {
    directive: string;
    reasoning: ReasoningStep[];
    status: "pending" | "streaming" | "complete";
  };
  
  // Settings
  theme: "crt" | "clean" | "matrix";
  scrollBehavior: "smooth" | "instant";
}
```

### Backend Connection
```typescript
// Simple fetch wrapper
class NexusAPI {
  async getChunk(id: number): Promise<NarrativeChunk> {
    return fetch(`/api/chunk/${id}`).then(r => r.json());
  }
  
  async queryLORE(directive: string, chunkId: number) {
    const response = await fetch('/api/query', {
      method: 'POST',
      body: JSON.stringify({ directive, chunkId })
    });
    
    // Handle streaming response
    const reader = response.body.getReader();
    // ... stream processing
  }
}
```

## Summary

This design provides:
1. **Authentic retro cyberpunk aesthetic** without sacrificing modern UX
2. **Native browser performance** - faster than any terminal UI
3. **Full copy/paste support** - critical for debugging
4. **Modular architecture** - easy to extend and modify
5. **Clean backend integration** - reuses existing LORE/MEMNON code

The key insight: We're not trying to make a web app look like a terminal - we're creating the terminal that cyberpunk authors imagined but couldn't build in the 1980s.