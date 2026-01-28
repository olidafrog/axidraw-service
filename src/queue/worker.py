"""Background worker for processing job queue"""
import asyncio
import logging
from pathlib import Path

from src.queue.manager import queue_manager
from src.queue.database import AsyncSessionLocal, JobStatus
from src.plotter.controller import plotter, PlotterState

logger = logging.getLogger(__name__)


class JobWorker:
    """Background worker that processes jobs from the queue"""
    
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the worker"""
        if self.running:
            logger.warning("Worker already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._work_loop())
        logger.info("Job worker started")
    
    async def stop(self):
        """Stop the worker"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Job worker stopped")
    
    async def _work_loop(self):
        """Main worker loop"""
        logger.info("Worker loop started")
        
        while self.running:
            try:
                # Check if plotter is idle
                if plotter.state != PlotterState.IDLE:
                    await asyncio.sleep(5)
                    continue
                
                # Get next job from queue
                async with AsyncSessionLocal() as session:
                    next_job = await queue_manager.get_next_job(session)
                    
                    if not next_job:
                        # No jobs in queue, sleep and check again
                        await asyncio.sleep(5)
                        continue
                    
                    # Mark job as running
                    await queue_manager.update_job_status(
                        session,
                        next_job.id,
                        JobStatus.RUNNING,
                        progress=0
                    )
                
                logger.info(f"Processing job {next_job.id}: {next_job.filename}")
                
                # Parse parameters
                import json
                parameters = json.loads(next_job.parameters) if next_job.parameters else {}
                
                # Plot the SVG
                svg_path = Path(next_job.filepath)
                
                async def progress_callback(progress: int):
                    """Update job progress"""
                    async with AsyncSessionLocal() as session:
                        await queue_manager.update_job_status(
                            session,
                            next_job.id,
                            JobStatus.RUNNING,
                            progress=progress
                        )
                
                success = await plotter.plot_svg(
                    svg_path,
                    next_job.id,
                    parameters,
                    progress_callback=progress_callback
                )
                
                # Update final status
                async with AsyncSessionLocal() as session:
                    if success:
                        await queue_manager.update_job_status(
                            session,
                            next_job.id,
                            JobStatus.COMPLETED,
                            progress=100
                        )
                        logger.info(f"Job {next_job.id} completed successfully")
                    else:
                        await queue_manager.update_job_status(
                            session,
                            next_job.id,
                            JobStatus.FAILED,
                            error="Plotting failed"
                        )
                        logger.error(f"Job {next_job.id} failed")
                
            except asyncio.CancelledError:
                logger.info("Worker loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("Worker loop ended")


# Global worker instance
worker = JobWorker()
