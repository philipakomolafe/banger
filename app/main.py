"""
FastAPI application factory - creates and configures the app.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse

from app.api.routes import router as api_router
from app.api.auth import router as auth_router
from app.api.x_auth import router as x_auth_router
from app.api.analytics import router as analytics_router
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

    
    # Mount static files for web frontend
    web_path = Path(__file__).parent.parent / "web"

    # Serve robots.txt for SEO and crawler intructions.
    @app.get("/robots.txt", response_class=FileResponse)
    async def serve_robots():
        robot_file = web_path / "robots.txt"
        if robot_file.exists():
            return FileResponse(robot_file, media_type="text/plain")
        return FileResponse(status_code=404)


    # Server sitemap.xml at root for SEO and crawler instructions.
    @app.get("/sitemap.xml", response_class=FileResponse)
    async def serve_sitemap():
        sitemap_file = web_path / "sitemap.xml"
        if sitemap_file.exists():
            return FileResponse(sitemap_file, media_type="application/xml")
        return FileResponse(status_code=404)

    
    @app.get("/bingsiteauth.xml", response_class=FileResponse)
    async def serve_bing_site_auth():
        bing_file = web_path / "BingSiteAuth.xml"
        if bing_file.exists():
            return FileResponse(bing_file, media_type="application/xml")
        return FileResponse(status_code=404)


    # Root redirect to web frontend
    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url="/web/landing.html")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "Banger"}

    if web_path.exists():
        app.mount("/web", StaticFiles(directory=web_path, html=True), name="web")

    # Register API routes
    app.include_router(api_router)
    app.include_router(auth_router)
    app.include_router(payments_router)
    app.include_router(x_auth_router)
    app.include_router(analytics_router)

    return app


# Useful for uvicorn entrypoint. ["app.main:app"]
app = create_app()