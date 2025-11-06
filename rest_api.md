# NEXUS Storyteller REST API - Product Requirements Document

## Overview
Build a single-user REST API wrapper around the existing LORE narrative generation system to enable HTTP-based story interactions.

## Objectives
- Expose LORE agent functionality via FastAPI endpoints
- Maintain story session state between requests
- Provide real-time streaming for long-running generations
- Enable programmatic access to narrative generation

## Core Requirements

### 1. Session Management
- File-based session persistence (JSON files in `sessions/` directory)
- Session ID generation using UUID4
- Auto-save session state after each turn
- Session metadata: created_at, last_accessed, turn_count, current_phase

### 2. API Endpoints

#### `POST /api/story/session/create`
Create new story session
- Request: `{"session_name": str (optional), "initial_context": str (optional)}`
- Response: `{"session_id": str, "created_at": datetime, "status": "ready"}`
- Creates session directory at `sessions/{session_id}/`

#### `POST /api/story/turn`
Submit user input and generate narrative
- Request: `{"session_id": str, "user_input": str, "options": dict (optional)}`
- Response: `StoryTurnResponse` schema from `nexus/agents/lore/logon_schemas.py`
- Calls LORE agent's turn cycle with user input
- Persists turn history to `sessions/{session_id}/turns.json`

#### `GET /api/story/session/{session_id}`
Get current session state
- Response: Full session state including metadata, current context, last turn

#### `GET /api/story/context/{session_id}`
Get current context package (for debugging)
- Response: Current warm slice, entities, memory retrievals

#### `GET /api/story/history/{session_id}`
Get turn history
- Query params: `limit` (default 10), `offset` (default 0)
- Response: Array of past turns with user input and AI response

#### `POST /api/story/regenerate`
Regenerate last narrative with different parameters
- Request: `{"session_id": str, "options": dict}`
- Response: New `StoryTurnResponse`
- Replaces last turn in history

#### `DELETE /api/story/session/{session_id}`
Delete session and all associated data
- Response: `{"status": "deleted"}`

#### `GET /api/story/sessions`
List all sessions
- Response: Array of session metadata

#### `WS /api/story/stream/{session_id}`
WebSocket endpoint for real-time generation updates
- Sends progress updates during turn processing
- Streams narrative chunks as they're generated
- Emits phase transitions (user_input → warm_slice → memory → generation → complete)

### 3. Integration Architecture

#### File Structure
```
nexus/
├── api/
│   └── storyteller.py       # New FastAPI application
├── api/
│   └── session_manager.py   # Session persistence logic
└── sessions/                # Session storage (gitignored)
    └── {session_id}/
        ├── metadata.json
        ├── turns.json
        └── context/
            └── {turn_id}.json
```

#### Key Integration Points
1. Import LORE from `nexus/agents/lore/lore.py`
2. Reuse database connection from `nexus/db.py`
3. Import schemas from `nexus/agents/lore/logon_schemas.py`
4. Use settings from `settings.json` (already configured)
5. Reference Apex Audition API (`nexus/api/apex_audition.py`) for patterns

### 4. Technical Specifications

#### Error Handling
- Consistent error response format: `{"error": str, "detail": str, "session_id": str}`
- Graceful handling of LLM API failures with retry logic
- Session recovery from incomplete turns

#### Background Processing
- Use FastAPI BackgroundTasks for post-turn cleanup
- Async generation support for long-running turns
- Queue management for sequential turn processing per session

#### CORS Configuration
```python
origins = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
    "http://localhost:8080",  # Alternative frontend
]
```

#### Startup Tasks
1. Initialize database connection pool
2. Verify 1Password CLI access for API keys
3. Load or create sessions directory
4. Test LLM provider connections

## Implementation Roadmap

### Phase 1: Core API (Priority: High)
1. Create `api/storyteller.py` with FastAPI app structure
2. Implement session creation and management
3. Add `/api/story/turn` endpoint connecting to LORE
4. Basic error handling and response formatting

### Phase 2: Session Persistence (Priority: High)
1. Create `api/session_manager.py` for file-based persistence
2. Implement turn history tracking
3. Add session listing and retrieval endpoints
4. Auto-save functionality

### Phase 3: WebSocket Streaming (Priority: Medium)
1. Add WebSocket endpoint for real-time updates
2. Instrument LORE phases for progress reporting
3. Stream narrative chunks during generation
4. Client reconnection handling

### Phase 4: Enhanced Features (Priority: Low)
1. Context inspection endpoint for debugging
2. Regeneration with parameter adjustment
3. Session export/import functionality
4. Performance metrics endpoint

## Testing Strategy
- Reuse test patterns from `tests/test_apex_audition.py`
- Mock LORE responses for unit tests
- Integration tests with actual LLM calls (use test mode in settings)
- Session persistence verification

## Deployment Notes
- Single-user deployment: `uvicorn nexus.api.storyteller:app --reload`
- Default port: 8001 (to avoid conflict with Apex Audition on 8000)
- No authentication required (single-user)
- File-based sessions (no Redis/external state store needed)

## Success Criteria
- [ ] Can create session and generate narrative via HTTP
- [ ] Sessions persist across server restarts
- [ ] WebSocket provides real-time generation updates
- [ ] Error recovery without data loss
- [ ] Compatible with existing LORE agent without modifications

## Non-Goals
- Multi-user authentication
- Database session storage (use files)
- Modifying existing LORE agent code
- Building frontend UI (API only)
- Production deployment configuration

## Reference Implementation
See `nexus/api/apex_audition.py` for:
- FastAPI application structure
- Database connection patterns
- Background task handling
- Error response formatting
- CORS configuration