"""Job management endpoints"""
import aiofiles
import logging
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models import (
    JobResponse, JobSubmitResponse, JobStatus, JobParameters, ErrorResponse
)
from src.config import settings
from src.queue.database import get_session, JobStatus as DBJobStatus
from src.queue.manager import queue_manager

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.post("", response_model=JobSubmitResponse)
async def submit_job(
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
    
    # Save file
    filename = file.filename
    filepath = settings.uploads_dir / filename
    
    # Handle duplicate filenames
    counter = 1
    while filepath.exists():
        name_part = Path(filename).stem
        ext_part = Path(filename).suffix
        filepath = settings.uploads_dir / f"{name_part}_{counter}{ext_part}"
        counter += 1
    
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
    
    # If running, we'd need to stop the plotter (not implemented yet)
    if job.status == DBJobStatus.RUNNING.value:
        raise HTTPException(status_code=501, detail="Cancelling running jobs not yet implemented")
    
    # Mark as cancelled
    await queue_manager.update_job_status(session, job_id, DBJobStatus.CANCELLED)
    
    return {"message": f"Job {job_id} cancelled"}
