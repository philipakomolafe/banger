"""
FastAPI application factory - creates and configures the app.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Banger API",
        version="1.0.0",
        description="X/Twitter Post Generator API"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files for web frontend
    web_path = Path(__file__).parent.parent / "web"
    if web_path.exists():
        app.mount("/web", StaticFiles(directory=web_path, html=True), name="web")

    # Register API routes
    app.include_router(api_router)
    
    return app


# Create the app instance for uvicorn
app = create_app()
