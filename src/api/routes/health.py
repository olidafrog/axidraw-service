"""Health check endpoint"""
from fastapi import APIRouter, Depends
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import HealthResponse
from src.config import settings
from src.queue.database import get_session
from src.queue.manager import queue_manager
from src.plotter.controller import plotter

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_session)):
    """Health check endpoint"""
    queue_size = await queue_manager.get_queue_size(session)
    
    return HealthResponse(
        status="healthy",
        uptime=plotter.get_uptime(),
        queue_size=queue_size,
        plotter_connected=plotter._info.connected if plotter._info else False,
        version=settings.version,
        timestamp=datetime.utcnow()
    )
