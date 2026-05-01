"""FastAPI application entry point"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.db import init_db

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    logger.info("🚀 Starting Video Editing API")
    settings.ensure_storage_paths()
    init_db()
    logger.info("✅ Database initialized")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Video Editing API")


# Create FastAPI application
app = FastAPI(
    title="Video Editing API",
    description="FastAPI backend for creative video editing with multi-agent collaboration",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "video-editing-api"}


@app.get("/api/health")
async def api_health_check():
    """API health check endpoint"""
    return {"status": "ok", "service": "video-editing-api"}


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include API routes
from src.api import projects, assets, sessions, video_jobs, gateway

app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(assets.router, prefix="/api", tags=["assets"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(video_jobs.router, prefix="/api", tags=["video-jobs"])
app.include_router(gateway.router, prefix="/api", tags=["gateway"])  # Gateway routes


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
