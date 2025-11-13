"""
FastAPI application for core NEXUS system operations.

Provides REST API endpoints for:
- Model load/unload management
- System health and status
- Model availability queries
"""
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from nexus.agents.lore.utils.model_manager import ModelManager

# Initialize FastAPI app
app = FastAPI(title="NEXUS Core API", version="1.0.0")

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to settings.json
ROOT_DIR = Path(__file__).resolve().parents[2]
SETTINGS_PATH = ROOT_DIR / "settings.json"


# Request/Response models
class ModelLoadRequest(BaseModel):
    model_id: str
    context_window: Optional[int] = None


class ModelStatusResponse(BaseModel):
    loaded_models: List[str]


class ModelAvailableResponse(BaseModel):
    available_models: List[str]


class ModelOperationResponse(BaseModel):
    success: bool
    message: str
    model_id: Optional[str] = None


# Endpoints
@app.post("/api/models/load", response_model=ModelOperationResponse)
async def load_model(request: ModelLoadRequest):
    """Load a specific model by ID."""
    try:
        manager = ModelManager(settings_path=str(SETTINGS_PATH), unload_on_exit=False)

        # Load the model with optional context window override
        success = manager.load_model(
            model_id=request.model_id,
            context_window=request.context_window
        )

        if success:
            return ModelOperationResponse(
                success=True,
                message=f"Model {request.model_id} loaded successfully",
                model_id=request.model_id
            )
        else:
            return ModelOperationResponse(
                success=False,
                message=f"Failed to load model {request.model_id}",
                model_id=request.model_id
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/unload", response_model=ModelOperationResponse)
async def unload_model():
    """Unload the currently loaded model to free resources."""
    try:
        manager = ModelManager(settings_path=str(SETTINGS_PATH))

        # Get current model before unloading
        loaded_models = manager.get_loaded_models()
        current_model = loaded_models[0] if loaded_models else None

        success = manager.unload_model()

        if success:
            return ModelOperationResponse(
                success=True,
                message=f"Model {current_model} unloaded successfully" if current_model else "Model unloaded successfully",
                model_id=current_model
            )
        else:
            return ModelOperationResponse(
                success=False,
                message="Failed to unload model"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/status", response_model=ModelStatusResponse)
async def get_model_status():
    """Get list of currently loaded models."""
    try:
        manager = ModelManager(settings_path=str(SETTINGS_PATH))
        loaded_models = manager.get_loaded_models()

        return ModelStatusResponse(loaded_models=loaded_models)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/available", response_model=ModelAvailableResponse)
async def get_available_models():
    """Get list of available (downloaded) models."""
    try:
        manager = ModelManager(settings_path=str(SETTINGS_PATH))
        available_models = manager.update_available_models()

        return ModelAvailableResponse(available_models=available_models)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": "NEXUS Core API"
    }
