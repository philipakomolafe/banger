"""
FastAPI application factory - creates and configures the app.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.api.routes import router as api_router
from app.api.auth import router as auth_router
from app.api.payments import router as payments_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Banger API",
        version="1.0.0",
        description="X/Twitter Post Generator API"
    )
    
    # CORS middleware
    allowed_origins = [
        "https://getbanger.tech",
        "https://www.getbanger.tech",
        "https://banger-npf3.onrender.com",  # Updated Render URL
        "http://localhost:8000",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Root redirect to web frontend.
    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url="/web/")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "Banger"}

    # Mount static files for web frontend
    web_path = Path(__file__).parent.parent / "web"
    if web_path.exists():
        app.mount("/web", StaticFiles(directory=web_path, html=True), name="web")

    # Register API routes
    app.include_router(api_router)
    app.include_router(auth_router)
    app.include_router(payments_router)
    
    return app


# Useful for uvicorn entrypoint. ["app.main:app"]
app = create_app()