"""Job management endpoints"""
import aiofiles
import logging
import re
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.models import (
    JobResponse, JobSubmitResponse, JobStatus, JobParameters, ErrorResponse
)
from src.api.dependencies import verify_api_key
from src.config import settings
from src.queue.database import get_session, JobStatus as DBJobStatus
from src.queue.manager import queue_manager

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)

# Rate limiter instance (will use app.state.limiter)
limiter = Limiter(key_func=get_remote_address)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    - Removes path separators and null bytes
    - Keeps only safe characters (alphanumeric, dash, underscore, dot, space)
    - Ensures filename is not empty or hidden
    - Falls back to UUID-based name if invalid
    """
    # Remove path separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    
    # Keep only safe characters
    filename = re.sub(r'[^\w\-_\. ]', '_', filename)
    
    # Get just the filename part (no directory)
    filename = Path(filename).name
    
    # Ensure it's not empty or hidden file
    if not filename or filename.startswith('.') or filename == '':
        filename = f"upload_{uuid.uuid4().hex[:8]}.svg"
    
    # Ensure it has .svg extension
    if not filename.lower().endswith('.svg'):
        filename = f"{filename}.svg"
    
    return filename


@router.post("", response_model=JobSubmitResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_window}")
async def submit_job(
    request: Request,
    file: UploadFile = File(..., description="SVG file to plot"),
    layers: str = Form(None, description="Comma-separated layer IDs"),
    speed: int = Form(25, ge=1, le=100, description="Plotting speed"),
    pen_up_delay: int = Form(150, ge=0, description="Pen up delay (ms)"),
    pen_down_delay: int = Form(150, ge=0, description="Pen down delay (ms)"),
    preview: bool = Form(False, description="Preview mode (no plotting)"),
    session: AsyncSession = Depends(get_session)
):
    """
    Submit a new plotting job
    
    Upload an SVG file with plotting parameters. The job will be queued and
    processed in FIFO order.
    """
    # Validate file type
    if not file.filename.lower().endswith('.svg'):
        raise HTTPException(status_code=400, detail="Only SVG files are supported")
    
    # Check file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    
    if size_mb > settings.max_svg_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.max_svg_size_mb}MB"
        )
    
    # Check queue size
    queue_size = await queue_manager.get_queue_size(session)
    if queue_size >= settings.max_queue_size:
        raise HTTPException(
            status_code=429,
            detail=f"Queue is full (max {settings.max_queue_size} jobs)"
        )
    
    # Sanitize filename BEFORE any file operations (prevent path traversal)
    filename = sanitize_filename(file.filename)
    uploads_resolved = settings.uploads_dir.resolve()
    filepath = settings.uploads_dir / filename
    
    # Verify resolved path is within uploads directory BEFORE writing
    try:
        resolved_path = filepath.resolve()
        if not resolved_path.is_relative_to(uploads_resolved):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename: path traversal detected"
            )
    except (ValueError, OSError) as e:
        logger.error(f"Path validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Handle duplicate filenames (validate each new path)
    counter = 1
    while filepath.exists():
        name_part = Path(filename).stem
        ext_part = Path(filename).suffix
        new_filename = f"{name_part}_{counter}{ext_part}"
        filepath = settings.uploads_dir / new_filename
        
        # Re-validate new path BEFORE any file write
        if not filepath.resolve().is_relative_to(uploads_resolved):
            raise HTTPException(status_code=400, detail="Invalid filename")
        counter += 1
    
    # Now safe to write the file
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(content)
    
    logger.info(f"Saved uploaded file: {filepath}")
    
    # Create job parameters
    parameters = JobParameters(
        layers=layers,
        speed=speed,
        pen_up_delay=pen_up_delay,
        pen_down_delay=pen_down_delay,
        preview=preview
    )
    
    # Create job in database
    job = await queue_manager.create_job(
        session,
        filename=filepath.name,
        filepath=filepath,
        parameters=parameters
    )
    
    # Get queue position
    position = await queue_manager.get_queue_position(session, job.id)
    
    return JobSubmitResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        created_at=job.created_at,
        position=position
    )


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    status: DBJobStatus = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """
    List all jobs
    
    Optionally filter by status. Jobs are returned in reverse chronological order.
    """
    jobs = await queue_manager.get_all_jobs(session, status=status, limit=limit)
    
    responses = []
    for job in jobs:
        position = None
        if job.status == DBJobStatus.QUEUED.value:
            position = await queue_manager.get_queue_position(session, job.id)
        
        responses.append(queue_manager.job_to_response(job, position=position))
    
    return responses


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Get job status by ID"""
    job = await queue_manager.get_job(session, job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    position = None
    if job.status == DBJobStatus.QUEUED.value:
        position = await queue_manager.get_queue_position(session, job.id)
    
    return queue_manager.job_to_response(job, position=position)


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a job
    
    Only queued, completed, failed, or cancelled jobs can be deleted.
    Running jobs must be cancelled first.
    """
    job = await queue_manager.get_job(session, job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if job.status == DBJobStatus.RUNNING.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete running job. Cancel it first."
        )
    
    success = await queue_manager.delete_job(session, job_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete job")
    
    return {"message": f"Job {job_id} deleted"}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Cancel a job (queued or running)"""
    job = await queue_manager.get_job(session, job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if job.status in [DBJobStatus.COMPLETED.value, DBJobStatus.FAILED.value, DBJobStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status} state"
        )
    
    # If running, stop the plotter
    if job.status == DBJobStatus.RUNNING.value:
        from src.plotter.controller import plotter
        cancel_success = await plotter.cancel()
        if not cancel_success:
            raise HTTPException(status_code=500, detail="Failed to cancel running job")
    
    # Mark as cancelled
    await queue_manager.update_job_status(session, job_id, DBJobStatus.CANCELLED)
    
    return {"message": f"Job {job_id} cancelled"}
