"""
FastAPI endpoints for live narrative turns with incubator support
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

# Import our new schema
from nexus.agents.logon.apex_schema import (
    StorytellerResponseStandard,
    ChronologyUpdate,
    ChunkMetadataUpdate,
)
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import LORE

logger = logging.getLogger("nexus.api.narrative")

app = FastAPI(title="NEXUS Narrative API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session_progress: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def send_progress(self, session_id: str, status: str, data: Dict = None):
        """Send progress update for a specific session"""
        progress = {
            "session_id": session_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "data": data or {}
        }
        self.session_progress[session_id] = progress
        await self.broadcast(json.dumps(progress))

manager = ConnectionManager()

# Database connection
def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host="localhost",
        database="NEXUS",
        user="pythagor"
    )

def load_settings():
    """Load settings from settings.json"""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    with open(settings_path, "r") as f:
        return json.load(f)

# Request/Response models
class ContinueNarrativeRequest(BaseModel):
    """Request to continue narrative from a chunk"""
    chunk_id: int = Field(description="Parent chunk ID to continue from")
    user_text: str = Field(description="User's completion text")
    test_mode: Optional[bool] = Field(default=None, description="Override test mode setting")

class ContinueNarrativeResponse(BaseModel):
    """Response from narrative continuation"""
    session_id: str = Field(description="Session ID for tracking this generation")
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Status message")

class ApproveNarrativeRequest(BaseModel):
    """Request to approve and commit narrative"""
    session_id: str = Field(description="Session ID of the narrative to approve")
    commit: bool = Field(default=True, description="Whether to commit to database")

class NarrativeStatus(BaseModel):
    """Status of a narrative generation session"""
    session_id: str
    status: str  # provisional, approved, committed, error
    chunk_id: Optional[int]
    parent_chunk_id: Optional[int]
    created_at: Optional[datetime]
    error: Optional[str]

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "narrative_api"}

@app.post("/api/narrative/continue", response_model=ContinueNarrativeResponse)
async def continue_narrative(
    request: ContinueNarrativeRequest,
    background_tasks: BackgroundTasks
):
    """
    Continue narrative from a given chunk
    Initiates async generation and returns session_id for tracking
    """
    session_id = str(uuid.uuid4())

    logger.info(f"Starting narrative continuation for chunk {request.chunk_id}")
    logger.info(f"Session ID: {session_id}")
    logger.info(f"User text: {request.user_text[:100]}...")

    # Send initial progress
    await manager.send_progress(session_id, "initiated", {
        "chunk_id": request.chunk_id,
        "parent_chunk_id": request.chunk_id
    })

    # Start async generation in background
    background_tasks.add_task(
        generate_narrative_async,
        session_id,
        request.chunk_id,
        request.user_text,
        request.test_mode
    )

    return ContinueNarrativeResponse(
        session_id=session_id,
        status="processing",
        message=f"Narrative generation started for chunk {request.chunk_id}"
    )

async def generate_narrative_async(
    session_id: str,
    parent_chunk_id: int,
    user_text: str,
    test_mode: Optional[bool] = None
):
    """
    Async function to generate narrative
    Sends progress updates via WebSocket
    """
    conn = None
    try:
        # Connect to database
        conn = get_db_connection()

        # Send progress: loading chunk
        await manager.send_progress(session_id, "loading_chunk")

        # Get parent chunk info
        chunk_info = await get_chunk_info(conn, parent_chunk_id)

        # Send progress: building context
        await manager.send_progress(session_id, "building_context", {
            "parent_info": {
                "season": chunk_info["season"],
                "episode": chunk_info["episode"],
                "place": chunk_info["place_name"]
            }
        })

        # Initialize LORE and build context
        # NOTE: This is simplified - real implementation needs proper async handling
        await asyncio.sleep(2)  # Simulate context building

        # Send progress: calling LLM
        await manager.send_progress(session_id, "calling_llm")

        # Generate narrative (mock for now)
        await asyncio.sleep(3)  # Simulate LLM call

        storyteller_text = generate_mock_narrative(chunk_info, user_text)

        # Send progress: processing response
        await manager.send_progress(session_id, "processing_response")

        # Prepare incubator data
        incubator_data = {
            "chunk_id": parent_chunk_id + 1,
            "parent_chunk_id": parent_chunk_id,
            "user_text": user_text,
            "storyteller_text": storyteller_text,
            "metadata_updates": {
                "episode_transition": "continue",
                "time_delta_seconds": 180,
                "time_delta_description": "A few minutes later",
                "world_layer": "primary",
                "pacing": "moderate"
            },
            "entity_updates": [],
            "reference_updates": {
                "character_present": [1],  # Alex
                "character_referenced": [],
                "place_referenced": []
            },
            "session_id": session_id,
            "llm_response_id": f"resp_{uuid.uuid4().hex[:8]}",
            "status": "provisional"
        }

        # Write to incubator
        await write_to_incubator(conn, incubator_data)

        # Send progress: complete
        await manager.send_progress(session_id, "complete", {
            "chunk_id": parent_chunk_id + 1,
            "preview": storyteller_text[:200] + "..."
        })

        logger.info(f"Narrative generation complete for session {session_id}")

    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        await manager.send_progress(session_id, "error", {"error": str(e)})
    finally:
        if conn:
            conn.close()

async def get_chunk_info(conn, chunk_id: int) -> Dict[str, Any]:
    """Get information about a chunk"""
    query = """
    SELECT
        nv.id,
        nv.raw_text,
        nv.season,
        nv.episode,
        nv.world_time,
        cm.place,
        p.name as place_name
    FROM narrative_view nv
    JOIN chunk_metadata cm ON cm.chunk_id = nv.id
    LEFT JOIN places p ON p.id = cm.place
    WHERE nv.id = %s
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (chunk_id,))
        result = cur.fetchone()

    if not result:
        raise ValueError(f"Chunk {chunk_id} not found")

    return dict(result)

async def write_to_incubator(conn, data: Dict[str, Any]):
    """Write data to the incubator table"""
    with conn.cursor() as cur:
        # Clear any existing incubator entry (singleton table)
        cur.execute("DELETE FROM incubator WHERE id = TRUE")

        # Insert new incubator entry
        query = """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            metadata_updates, entity_updates, reference_updates,
            session_id, llm_response_id, status
        ) VALUES (
            TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        cur.execute(query, (
            data["chunk_id"],
            data["parent_chunk_id"],
            data["user_text"],
            data["storyteller_text"],
            json.dumps(data["metadata_updates"]),
            json.dumps(data["entity_updates"]),
            json.dumps(data["reference_updates"]),
            data["session_id"],
            data["llm_response_id"],
            data["status"]
        ))

    conn.commit()

def generate_mock_narrative(chunk_info: Dict, user_text: str) -> str:
    """Generate mock narrative for testing"""
    return f"""The scene continues from {chunk_info['place_name']}.

{user_text}

The morning stretches on, and with it comes a growing sense of purpose. The team's focus sharpens
as they review the data streams flowing across their screens. Each piece of information adds another
layer to the complex puzzle they're trying to solve.

Sullivan, now officially part of the crew, watches from his perch with an air of feline wisdom,
as if he too understands the gravity of what's about to unfold."""

@app.get("/api/narrative/status/{session_id}", response_model=NarrativeStatus)
async def get_narrative_status(session_id: str):
    """Get status of a narrative generation session"""

    # Check WebSocket manager for active sessions
    if session_id in manager.session_progress:
        progress = manager.session_progress[session_id]
        return NarrativeStatus(
            session_id=session_id,
            status=progress["status"],
            chunk_id=progress.get("data", {}).get("chunk_id"),
            parent_chunk_id=progress.get("data", {}).get("parent_chunk_id"),
            created_at=datetime.fromisoformat(progress["timestamp"]),
            error=progress.get("data", {}).get("error")
        )

    # Check incubator for completed sessions
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM incubator WHERE session_id = %s",
                (session_id,)
            )
            result = cur.fetchone()

        if result:
            return NarrativeStatus(
                session_id=session_id,
                status=result["status"],
                chunk_id=result["chunk_id"],
                parent_chunk_id=result["parent_chunk_id"],
                created_at=result["created_at"],
                error=None
            )

        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    finally:
        conn.close()

@app.post("/api/narrative/approve/{session_id}")
async def approve_narrative(
    session_id: str,
    request: ApproveNarrativeRequest
):
    """
    Approve narrative and optionally commit to database
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get incubator data
            cur.execute(
                "SELECT * FROM incubator WHERE session_id = %s",
                (session_id,)
            )
            incubator_data = cur.fetchone()

        if not incubator_data:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        if request.commit:
            # TODO: Implement actual commit to narrative_chunks and related tables
            # For now, just update status
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE incubator SET status = 'approved' WHERE session_id = %s",
                    (session_id,)
                )
            conn.commit()

            return {
                "status": "approved",
                "message": f"Narrative for chunk {incubator_data['chunk_id']} approved",
                "chunk_id": incubator_data["chunk_id"]
            }
        else:
            # Just mark as reviewed
            return {
                "status": "reviewed",
                "message": "Narrative reviewed but not committed",
                "chunk_id": incubator_data["chunk_id"]
            }

    finally:
        conn.close()

@app.websocket("/ws/narrative")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for messages
            data = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Utility endpoints
@app.get("/api/narrative/incubator")
async def get_incubator_contents():
    """Get current incubator contents"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM incubator_view")
            result = cur.fetchone()

        if result:
            return dict(result)
        else:
            return {"message": "Incubator is empty"}
    finally:
        conn.close()

@app.delete("/api/narrative/incubator")
async def clear_incubator():
    """Clear the incubator table"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM incubator WHERE id = TRUE")
        conn.commit()
        return {"message": "Incubator cleared"}
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)