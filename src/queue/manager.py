"""Job queue manager"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.queue.database import Job, JobStatus, get_session
from src.api.models import JobParameters, JobResponse

logger = logging.getLogger(__name__)


class JobQueueManager:
    """Manages job queue using SQLite database"""
    
    async def create_job(
        self,
        session: AsyncSession,
        filename: str,
        filepath: Path,
        parameters: JobParameters
    ) -> Job:
        """Create a new job"""
        job = Job(
            id=str(uuid.uuid4()),
            filename=filename,
            filepath=str(filepath),
            status=JobStatus.QUEUED.value,
            created_at=datetime.utcnow(),
            parameters=json.dumps(parameters.model_dump())
        )
        
        session.add(job)
        await session.commit()
        await session.refresh(job)
        
        logger.info(f"Created job {job.id}: {filename}")
        return job
    
    async def get_job(self, session: AsyncSession, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        result = await session.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all_jobs(
        self,
        session: AsyncSession,
        status: Optional[JobStatus] = None,
        limit: int = 100
    ) -> List[Job]:
        """Get all jobs, optionally filtered by status"""
        query = select(Job).order_by(Job.created_at.desc()).limit(limit)
        
        if status:
            query = query.where(Job.status == status.value)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    async def get_next_job(self, session: AsyncSession) -> Optional[Job]:
        """Get next queued job (FIFO)"""
        result = await session.execute(
            select(Job)
            .where(Job.status == JobStatus.QUEUED.value)
            .order_by(Job.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_queue_position(self, session: AsyncSession, job_id: str) -> int:
        """Get position of job in queue (1-indexed)"""
        job = await self.get_job(session, job_id)
        if not job or job.status != JobStatus.QUEUED.value:
            return 0
        
        # Count jobs created before this one that are still queued
        result = await session.execute(
            select(func.count(Job.id))
            .where(Job.status == JobStatus.QUEUED.value)
            .where(Job.created_at <= job.created_at)
        )
        return result.scalar() or 0
    
    async def update_job_status(
        self,
        session: AsyncSession,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        error: Optional[str] = None
    ) -> Optional[Job]:
        """Update job status"""
        job = await self.get_job(session, job_id)
        if not job:
            return None
        
        job.status = status.value
        
        if progress is not None:
            job.progress = progress
        
        if error is not None:
            job.error = error
        
        # Update timestamps
        if status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(job)
        
        logger.info(f"Updated job {job_id}: status={status.value}, progress={progress}")
        return job
    
    async def delete_job(self, session: AsyncSession, job_id: str) -> bool:
        """Delete a job (and its file)"""
        job = await self.get_job(session, job_id)
        if not job:
            return False
        
        # Delete file if exists
        try:
            filepath = Path(job.filepath)
            if filepath.exists():
                filepath.unlink()
                logger.info(f"Deleted file: {filepath}")
        except Exception as e:
            logger.error(f"Error deleting file {job.filepath}: {e}")
        
        # Delete from database
        await session.delete(job)
        await session.commit()
        
        logger.info(f"Deleted job {job_id}")
        return True
    
    async def get_queue_size(self, session: AsyncSession) -> int:
        """Get number of queued jobs"""
        result = await session.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.QUEUED.value)
        )
        return result.scalar() or 0
    
    def job_to_response(self, job: Job, position: Optional[int] = None) -> JobResponse:
        """Convert database job to API response"""
        parameters = JobParameters.model_validate_json(job.parameters) if job.parameters else JobParameters()
        
        return JobResponse(
            job_id=job.id,
            filename=job.filename,
            status=JobStatus(job.status),
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error=job.error,
            parameters=parameters,
            position=position
        )


# Global queue manager instance
queue_manager = JobQueueManager()
