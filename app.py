"""
Main FastAPI server for AI Video Generator application.
Handles chat interactions, video generation pipeline, and static file serving.
"""

import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn
import sqlite3
import aiofiles
from dotenv import load_dotenv

# Import custom modules
from services.chat_service import ChatService
from services.video_service import VideoService
from services.media_service import MediaService
from services.voice_service import VoiceService
from services.prompt_service import PromptService
from database.db_manager import DatabaseManager
from models.schemas import (
    ChatRequest, ChatResponse, 
    VideoGenerationRequest, VideoGenerationResponse,
    HistoryResponse, ErrorResponse
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_DIR = Path(__file__).parent / "output"
DATABASE_PATH = Path(__file__).parent / "data" / "chat_history.db"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SUPPORTED_VIDEO_FORMATS = {".mp4", ".webm", ".mov"}
SUPPORTED_AUDIO_FORMATS = {".mp3", ".wav", ".ogg"}

# Initialize FastAPI app
app = FastAPI(
    title="AI Video Generator",
    description="Generate AI-powered videos with voiceovers and text overlays",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Initialize services
db_manager = DatabaseManager(str(DATABASE_PATH))
chat_service = ChatService(db_manager)
video_service = VideoService(OUTPUT_DIR)
media_service = MediaService()
voice_service = VoiceService()
prompt_service = PromptService()

# Ensure directories exist
STATIC_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = "healthy"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0"


# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and store WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket connected: {client_id}")
    
    async def disconnect(self, client_id: str):
        """Remove WebSocket connection."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket disconnected: {client_id}")
    
    async def send_message(self, client_id: str, message: dict):
        """Send message to specific client."""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {client_id}: {e}")
                await self.disconnect(client_id)
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for client_id in list(self.active_connections.keys()):
            await self.send_message(client_id, message)


manager = ConnectionManager()


# API Routes
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Process chat message and generate response.
    
    Args:
        request: Chat request containing message and session ID
        
    Returns:
        Chat response with AI-generated reply
    """
    try:
        # Validate input
        if not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Process chat message
        response = await chat_service.process_message(
            message=request.message,
            session_id=request.session_id,
            context=request.context
        )
        
        # Save to history
        await db_manager.save_chat_entry(
            session_id=request.session_id,
            user_message=request.message,
            ai_response=response.text,
            metadata=response.metadata
        )
        
        return ChatResponse(
            text=response.text,
            session_id=request.session_id,
            suggestions=response.suggestions,
            metadata=response.metadata
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@app.post("/api/generate-video", response_model=VideoGenerationResponse)
async def generate_video_endpoint(request: VideoGenerationRequest):
    """
    Generate video based on user request.
    
    Args:
        request: Video generation request with parameters
        
    Returns:
        Video generation response with status and file info
    """
    try:
        # Validate request
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
        # Generate unique video ID
        video_id = str(uuid.uuid4())
        
        # Parse prompt using AI
        parsed_prompt = await prompt_service.parse_prompt(request.prompt)
        
        # Fetch media assets
        media_assets = await media_service.fetch_media(
            query=parsed_prompt.search_terms,
            media_type=request.media_type or "video",
            count=request.media_count or 5
        )
        
        if not media_assets:
            raise HTTPException(status_code=404, detail="No suitable media found")
        
        # Generate voiceover if needed
        voiceover_path = None
        if request.voiceover_enabled and parsed_prompt.script:
            voiceover_path = await voice_service.generate_voiceover(
                text=parsed_prompt.script,
                voice_id=request.voice_id or "default",
                language=request.language or "en"
            )
        
        # Generate video
        video_path = await video_service.generate_video(
            video_id=video_id,
            media_assets=media_assets,
            voiceover_path=voiceover_path,
            text_overlays=parsed_prompt.text_overlays,
            background_music=request.background_music,
            transition_style=request.transition_style or "fade",
            resolution=request.resolution or "1080p",
            duration=request.duration or 30
        )
        
        # Save generation record
        await db_manager.save_video_record(
            video_id=video_id,
            prompt=request.prompt,
            video_path=str(video_path),
            metadata={
                "media_count": len(media_assets),
                "has_voiceover": voiceover_path is not None,
                "duration": request.duration or 30,
                "resolution": request.resolution or "1080p"
            }
        )
        
        return VideoGenerationResponse(
            video_id=video_id,
            status="completed",
            video_url=f"/output/{video_path.name}",
            thumbnail_url=f"/output/{video_path.stem}_thumb.jpg",
            duration=request.duration or 30,
            metadata={
                "media_count": len(media_assets),
                "has_voiceover": voiceover_path is not None
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")


@app.get("/api/history/{session_id}", response_model=List[HistoryResponse])
async def get_chat_history(session_id: str, limit: int = 50, offset: int = 0):
    """
    Retrieve chat history for a session.
    
    Args:
        session_id: Session identifier
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        
    Returns:
        List of chat history entries
    """
    try:
        history = await db_manager.get_chat_history(
            session_id=session_id,
            limit=min(limit, 100),  # Cap at 100
            offset=offset
        )
        return [HistoryResponse(**entry) for entry in history]
    
    except Exception as e:
        logger.error(f"History retrieval error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history")


@app.delete("/api/history/{session_id}")
async def clear_chat_history(session_id: str):
    """
    Clear chat history for a session.
    
    Args:
        session_id: Session identifier
    """
    try:
        await db_manager.clear_history(session_id)
        return {"status": "success", "message": "Chat history cleared"}
    
    except Exception as e:
        logger.error(f"History clear error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear chat history")


@app.get("/api/video-status/{video_id}")
async def get_video_status(video_id: str):
    """
    Check status of video generation.
    
    Args:
        video_id: Video identifier
        
    Returns:
        Video status information
    """
    try:
        status = await video_service.get_video_status(video_id)
        if not status:
            raise HTTPException(status_code=404, detail="Video not found")
        return status
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video status error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get video status")


@app.get("/api/download/{video_id}")
async def download_video(video_id: str):
    """
    Download generated video file.
    
    Args:
        video_id: Video identifier
        
    Returns:
        Video file for download
    """
    try:
        video_path = await video_service.get_video_path(video_id)
        if not video_path or not video_path.exists():
            raise HTTPException(status_code=404, detail="Video not found")
        
        return FileResponse(
            path=video_path,
            media_type="video/mp4",
            filename=f"video_{video_id}.mp4",
            headers={
                "Content-Disposition": f'attachment; filename="video_{video_id}.mp4"'
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download video")


# WebSocket endpoint for real-time updates
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time communication.
    
    Args:
        websocket: WebSocket connection
        client_id: Client identifier
    """
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await manager.send_message(client_id, {"type": "pong"})
            elif message.get("type") == "progress":
                # Echo progress updates
                await manager.send_message(client_id, {
                    "type": "progress_update",
                    "data": message.get("data", {})
                })
            else:
                # Process other message types
                response = await chat_service.process_websocket_message(message)
                await manager.send_message(client_id, response)
    
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {str(e)}")
        await manager.disconnect(client_id)


# Serve main application
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main application page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Application not found")
    
    async with aiofiles.open(index_path, "r") as f:
        content = await f.read()
    return HTMLResponse(content=content)


@app.get("/{full_path:path}")
async def serve_static_or_fallback(full_path: str):
    """
    Serve static files or fallback to index for SPA routing.
    
    Args:
        full_path: Requested path
    """
    # Check if file exists in static directory
    file_path = STATIC_DIR / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(path=file_path)
    
    # For SPA routing, serve index.html
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        async with aiofiles.open(index_path, "r") as f:
            content = await f.read()
        return HTMLResponse(content=content)
    
    raise HTTPException(status_code=404, detail="Resource not found")


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            status_code=exc.status_code,
            timestamp=datetime.now().isoformat()
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            status_code=500,
            timestamp=datetime.now().isoformat()
        ).dict()
    )


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting AI Video Generator application...")
    
    # Initialize database
    await db_manager.initialize()
    
    # Initialize services
    await chat_service.initialize()
    await video_service.initialize()
    await media_service.initialize()
    await voice_service.initialize()
    await prompt_service.initialize()
    
    logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on shutdown."""
    logger.info("Shutting down AI Video Generator application...")
    
    # Cleanup services
    await chat_service.cleanup()
    await video_service.cleanup()
    await media_service.cleanup()
    await voice_service.cleanup()
    await prompt_service.cleanup()
    await db_manager.close()
    
    logger.info("Application shutdown complete")


if __name__ == "__main__":
    """Run the application server."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENVIRONMENT", "development") == "development"
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        workers=4 if not reload else 1
    )