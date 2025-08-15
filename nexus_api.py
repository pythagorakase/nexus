"""
NEXUS API Server
FastAPI backend for the React UI, serving narrative data and LORE queries.

Run with:
    uvicorn nexus_api:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Import our existing NEXUS components
from nexus.agents.lore.lore import LORE
from nexus.agents.memnon.memnon import MEMNON

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="NEXUS API",
    description="Neural Exploration eXtended User System - Backend API",
    version="2.1.0"
)

# Configure CORS for React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances (initialized on startup)
lore_instance: Optional[LORE] = None
memnon_instance: Optional[MEMNON] = None


# Pydantic models for API
class NarrativeChunk(BaseModel):
    id: int
    season: Optional[int] = None
    episode: Optional[int] = None
    scene: Optional[int] = None
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChunkContext(BaseModel):
    target: NarrativeChunk
    context: List[NarrativeChunk]
    window: int


class QueryRequest(BaseModel):
    directive: str
    chunk_id: int


class QueryResponse(BaseModel):
    directive: str
    chunk_id: int
    reasoning: List[Dict[str, Any]]
    results: List[NarrativeChunk]
    summary: str
    latency: float


class SystemStatus(BaseModel):
    model: str
    db_connected: bool
    chunks_available: int
    telemetry: Dict[str, Any]


class StoryOutline(BaseModel):
    seasons: List[Dict[str, Any]]


@app.on_event("startup")
async def startup_event():
    """Initialize LORE and MEMNON on server startup."""
    global lore_instance, memnon_instance
    
    logger.info("Initializing NEXUS components...")
    
    try:
        # Initialize LORE (includes MEMNON)
        lore_instance = LORE()
        memnon_instance = lore_instance.memnon
        
        # Keep model loaded for server lifetime
        if hasattr(lore_instance, "llm_manager"):
            lore_instance.llm_manager.unload_on_exit = False
        
        logger.info("NEXUS API ready!")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        # Continue anyway - some endpoints might still work


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on server shutdown."""
    global lore_instance
    
    if lore_instance and hasattr(lore_instance, "llm_manager"):
        try:
            lore_instance.llm_manager.unload_model()
        except:
            pass


@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API info."""
    return {
        "name": "NEXUS API",
        "version": "2.1.0",
        "status": "online",
        "endpoints": {
            "chunks": "/api/chunk/{id}",
            "context": "/api/chunk/{id}/context",
            "outline": "/api/outline",
            "query": "/api/query",
            "status": "/api/status"
        }
    }


@app.get("/api/chunk/{chunk_id}", response_model=NarrativeChunk, tags=["chunks"])
async def get_chunk(chunk_id: int):
    """Get a single narrative chunk by ID."""
    if not memnon_instance:
        raise HTTPException(status_code=503, detail="MEMNON not initialized")
    
    try:
        # Use MEMNON to fetch chunk
        data = await asyncio.to_thread(memnon_instance.get_chunk_by_id, chunk_id)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")
        
        # Extract metadata from the chunk
        metadata = {}
        if "location" in data:
            metadata["location"] = data["location"]
        if "time" in data:
            metadata["timestamp"] = f"{data.get('date', '')}-{data['time']}"
        if "characters" in data:
            metadata["characters"] = data["characters"]
        
        return NarrativeChunk(
            id=chunk_id,
            season=data.get("season"),
            episode=data.get("episode"),
            scene=data.get("scene"),
            text=data.get("text", ""),
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Error fetching chunk {chunk_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chunk/{chunk_id}/context", response_model=ChunkContext, tags=["chunks"])
async def get_chunk_with_context(
    chunk_id: int,
    window: int = Query(default=10, ge=1, le=50, description="Number of chunks before/after")
):
    """Get a chunk with surrounding context."""
    if not memnon_instance:
        raise HTTPException(status_code=503, detail="MEMNON not initialized")
    
    try:
        # Fetch target chunk
        target = await get_chunk(chunk_id)
        
        # Fetch surrounding chunks efficiently
        chunk_ids = list(range(max(1, chunk_id - window), chunk_id + window + 1))
        context_chunks = []
        
        # Batch fetch using MEMNON
        for cid in chunk_ids:
            if cid == chunk_id:
                continue  # Skip target, we already have it
            try:
                chunk_data = await get_chunk(cid)
                context_chunks.append(chunk_data)
            except HTTPException:
                # Skip missing chunks
                continue
        
        return ChunkContext(
            target=target,
            context=context_chunks,
            window=window
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching context for chunk {chunk_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/outline", response_model=StoryOutline, tags=["navigation"])
async def get_story_outline():
    """Get the hierarchical story outline (seasons/episodes/scenes)."""
    if not memnon_instance:
        raise HTTPException(status_code=503, detail="MEMNON not initialized")
    
    try:
        from sqlalchemy import text
        
        def fetch_outline():
            with memnon_instance.Session() as session:
                # Get all seasons
                seasons_query = text("""
                    SELECT DISTINCT season 
                    FROM chunk_metadata 
                    WHERE season IS NOT NULL 
                    ORDER BY season
                """)
                seasons = session.execute(seasons_query).fetchall()
                
                outline = []
                for (season_num,) in seasons:
                    # Get episodes for this season
                    episodes_query = text("""
                        SELECT DISTINCT episode 
                        FROM chunk_metadata 
                        WHERE season = :season AND episode IS NOT NULL
                        ORDER BY episode
                    """)
                    episodes = session.execute(episodes_query, {"season": season_num}).fetchall()
                    
                    episode_list = []
                    for (episode_num,) in episodes:
                        # Get scenes for this episode
                        scenes_query = text("""
                            SELECT DISTINCT scene, MIN(chunk_id) as first_chunk
                            FROM chunk_metadata 
                            WHERE season = :season AND episode = :episode AND scene IS NOT NULL
                            GROUP BY scene
                            ORDER BY scene
                        """)
                        scenes = session.execute(
                            scenes_query, 
                            {"season": season_num, "episode": episode_num}
                        ).fetchall()
                        
                        scene_list = [
                            {"number": scene_num, "chunk_id": chunk_id}
                            for scene_num, chunk_id in scenes
                        ]
                        
                        episode_list.append({
                            "number": episode_num,
                            "scenes": scene_list
                        })
                    
                    outline.append({
                        "number": season_num,
                        "episodes": episode_list
                    })
                
                return outline
        
        seasons = await asyncio.to_thread(fetch_outline)
        return StoryOutline(seasons=seasons)
        
    except Exception as e:
        logger.error(f"Error fetching story outline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query", tags=["lore"])
async def query_lore(request: QueryRequest):
    """
    Execute a LORE query and stream the results.
    Returns a streaming response with reasoning steps and results.
    """
    if not lore_instance:
        raise HTTPException(status_code=503, detail="LORE not initialized")
    
    try:
        async def generate():
            # Stream initial status
            yield f"data: {json.dumps({'type': 'status', 'message': 'Processing query...'})}\n\n"
            
            # Execute LORE retrieval
            start_time = datetime.now()
            result = await asyncio.to_thread(
                lore_instance.retrieve_context,
                [request.directive],
                chunk_id=request.chunk_id
            )
            
            # Stream reasoning steps if available
            if "reasoning" in result:
                for step in result["reasoning"]:
                    yield f"data: {json.dumps({'type': 'reasoning', 'content': step})}\n\n"
                    await asyncio.sleep(0.1)  # Small delay for streaming effect
            
            # Stream final results
            elapsed = (datetime.now() - start_time).total_seconds()
            final_response = {
                "type": "complete",
                "directive": request.directive,
                "chunk_id": request.chunk_id,
                "results": result.get("results", []),
                "summary": result.get("summary", ""),
                "latency": elapsed
            }
            yield f"data: {json.dumps(final_response)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status", response_model=SystemStatus, tags=["system"])
async def get_system_status():
    """Get current system status."""
    status = {
        "model": "unknown",
        "db_connected": False,
        "chunks_available": 0,
        "telemetry": {}
    }
    
    try:
        if lore_instance:
            lore_status = lore_instance.get_status()
            components = lore_status.get("components", {})
            
            # Model status
            if components.get("local_llm"):
                status["model"] = "local_llm_active"
            
            # Database status
            if components.get("memnon"):
                status["db_connected"] = True
                # Get chunk count
                if memnon_instance:
                    from sqlalchemy import text
                    with memnon_instance.Session() as session:
                        count = session.execute(
                            text("SELECT COUNT(*) FROM narrative_chunks")
                        ).scalar()
                        status["chunks_available"] = count or 0
            
            # Add telemetry
            status["telemetry"] = {
                "components": components,
                "settings": lore_status.get("settings", {})
            }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        status["telemetry"]["error"] = str(e)
    
    return SystemStatus(**status)


@app.get("/api/search", tags=["search"])
async def search_narrative(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=10, ge=1, le=50)
):
    """Search narrative chunks."""
    if not memnon_instance:
        raise HTTPException(status_code=503, detail="MEMNON not initialized")
    
    try:
        # Use MEMNON's search capabilities
        results = await asyncio.to_thread(
            memnon_instance.search,
            q,
            limit=limit
        )
        
        # Convert to API format
        chunks = []
        for result in results:
            chunks.append(NarrativeChunk(
                id=result["chunk_id"],
                season=result.get("season"),
                episode=result.get("episode"),
                scene=result.get("scene"),
                text=result.get("text", ""),
                metadata={
                    "score": result.get("score", 0),
                    "location": result.get("location"),
                    "timestamp": f"{result.get('date', '')}-{result.get('time', '')}"
                }
            ))
        
        return {"query": q, "results": chunks}
        
    except Exception as e:
        logger.error(f"Error searching: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Run with: python nexus_api.py
    uvicorn.run(
        "nexus_api:app",
        host="0.0.0.0",  # Allow connections from any IP on your network
        port=8000,
        reload=True,
        log_level="info"
    )