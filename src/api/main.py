"""Main FastAPI application"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.routes import health, jobs, plotter
from src.queue.database import init_db
from src.queue.worker import worker
from src.plotter.controller import plotter as plotter_controller

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.version}")
    
    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    
    # Check plotter connection
    logger.info("Checking AxiDraw connection...")
    await plotter_controller.check_connection()
    
    # Start background worker
    logger.info("Starting job worker...")
    await worker.start()
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    await worker.stop()
    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="REST API for controlling AxiDraw pen plotter",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(jobs.router, prefix=settings.api_prefix, tags=["jobs"])
app.include_router(plotter.router, prefix=settings.api_prefix, tags=["plotter"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health"
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """404 handler"""
    return {
        "error": "Not found",
        "detail": str(exc.detail) if hasattr(exc, 'detail') else "The requested resource was not found"
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """500 handler"""
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return {
        "error": "Internal server error",
        "detail": "An unexpected error occurred"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
