# NEXUS IRIS Design Guidelines

## Design Approach: Cyberpunk Terminal Interface

**Selected Approach**: Custom cyberpunk terminal aesthetic inspired by retro computing and sci-fi interfaces
**Rationale**: The project explicitly requires a terminal-style interface with phosphor glow effects for an immersive storytelling experience

---

## Core Design Elements

### A. Color Palette

**Dark Mode (Primary)**
- Background: `0 0% 4%` - Deep black foundation
- Panel Background: `0 0% 8%` - Slightly elevated surfaces
- Primary (Phosphor Green): `142 100% 50%` - Bright terminal green
- Dim Green: `142 70% 35%` - Muted green for secondary elements
- Accent Blue: `180 100% 50%` - Cyan for highlights
- Warning Red: `0 100% 60%` - Critical states
- Text Primary: `142 100% 85%` - Green-tinted white
- Text Secondary: `142 50% 60%` - Dimmed green

### B. Typography

**Font Stack**:
- Primary: 'Courier New', Courier, monospace
- Alternative: 'Source Code Pro', 'Consolas', monospace
- Font sizes maintain strict 1.25 ratio scaling

**Hierarchy**:
- Display: 2rem, weight 700, letter-spacing 0.1em
- Heading: 1.5rem, weight 600, letter-spacing 0.05em
- Body: 1rem, weight 400, letter-spacing 0.02em
- Caption: 0.875rem, weight 400, letter-spacing 0.03em

### C. Layout System

**Spacing Units**: Use Tailwind units of 1, 2, 4, 8, 12, 16, 24, 32 for consistent rhythm

**Grid Structure**:
- Status bar: Fixed height 48px top
- Command bar: Fixed height 56px bottom
- Main content: Flexible middle area with flex layout
- Left pane (narrative/map): Flexible width, minimum 60% viewport
- Right pane (navigation/zones): Fixed 320px collapsible sidebar

### D. Component Library

**Terminal Window Components**:
- **StatusBar**: Fixed top bar with system status, model info, chapter/scene indicators, hamburger menu
- **CommandBar**: Fixed bottom input with prefix label ("ALEX:" or "NEXUS:USER"), monospace input, blinking cursor
- **NarrativePane**: Scrollable story display with typewriter effect, section-based rendering
- **NavigationPane**: Collapsible right sidebar with chunk/episode tree navigation
- **MapPane**: D3.js geographic visualization with location markers
- **ZonesPane**: Location-based zone selection interface

**Visual Effects**:
- Phosphor glow: `0 0 10px currentColor, 0 0 20px currentColor`
- Scanlines: Repeating linear gradient overlay at 2px intervals
- CRT flicker: Subtle opacity animation (0.98-1.0) every 100ms
- Text shadow: `0 0 5px currentColor` for glow effect
- Border glow: `0 0 10px` on focus states

**Interactive States**:
- Hover: Increase glow intensity, slight scale (1.02)
- Focus: Enhanced border glow, no outline
- Active: Slightly dimmed glow
- Disabled: 50% opacity, no glow

### E. Animations

**Core Animations** (use sparingly):
- Typewriter effect: 50ms per character for narrative text
- Loading spinner: Rotating ASCII characters [/,—,\,|]
- Progress bars: ASCII fill animation using █ characters
- Fade in: 300ms ease for panel transitions
- Pulse: Subtle 2s glow pulse for active elements

**Prohibited**: No slide animations, no complex transforms, no parallax

---

## Page-Specific Layouts

### Main Storytelling Interface

**Structure**:
```
┌─────────────────────────────────────────┐
│  StatusBar (Model | S1E1S2 | Status)    │
├─────────────────────────────────┬───────┤
│                                 │       │
│  Narrative/Map Pane             │  Nav/ │
│  (Flexible, scrollable)         │ Zones │
│                                 │ Pane  │
│                                 │(320px)│
├─────────────────────────────────┴───────┤
│  CommandBar (Input with prefix)         │
└─────────────────────────────────────────┘
```

**Narrative Pane Features**:
- Chunk header with metadata (location, timestamp, characters)
- Section-based rendering with "you" vs "storyteller" distinction
- Typewriter reveal for new content
- Provisional input preview during confirmation
- Scrollable with automatic scroll-to-bottom on new content

**Command System**:
- Slash commands: `/nav`, `/map`, `/read`, `/story`, `/model`, `/chunk`
- Story mode: Free text input with confirmation flow
- Visual feedback: Command preview, status changes during processing

---

## Responsive Behavior

**Desktop (≥768px)**:
- Full three-column layout
- Right pane toggles with `/nav` command
- Sidebar visible by default

**Mobile (<768px)**:
- Stack layout with hamburger menu
- Right pane becomes slide-out sheet
- Touch-optimized command input
- Minimum tap targets: 44px

---

## Critical Design Constraints

1. **Strict monospace everywhere** - No proportional fonts
2. **Green phosphor aesthetic** - All primary text in terminal green
3. **CRT effects mandatory** - Scanlines and subtle flicker on all surfaces
4. **ASCII-based indicators** - Use █ ▓ ▒ ░ for progress, [OK] [FAIL] for status
5. **No images/photos** - Pure terminal interface (except map SVG elements)
6. **Typewriter reveals** - All new narrative text types character-by-character
7. **Command-driven UX** - Slash commands as primary navigation pattern

---

## Images

**No traditional images used** - This is a pure terminal interface

**Exception**: Map pane uses D3.js-generated SVG visualizations for geographic data, rendered in the same phosphor green aesthetic

---

## Accessibility Notes

- High contrast green-on-black meets WCAG AAA
- All interactive elements keyboard accessible
- Screen reader labels for all icons/symbols
- Reduced motion option disables scanlines and flicker
- Command bar maintains visible focus indicator