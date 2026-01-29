"""AxiDraw plotter controller - wraps AxiCLI"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PlotterState(str, Enum):
    """Plotter state"""
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class PlotterInfo:
    """Plotter information"""
    connected: bool
    model: Optional[str] = None
    firmware: Optional[str] = None


class AxiDrawController:
    """Controller for AxiDraw plotter using AxiCLI"""
    
    def __init__(self):
        self.state = PlotterState.IDLE
        self.current_job_id: Optional[str] = None
        self._start_time = time.time()
        self._jobs_completed = 0
        self._info: Optional[PlotterInfo] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None
        
    def get_uptime(self) -> int:
        """Get service uptime in seconds"""
        return int(time.time() - self._start_time)
    
    def get_jobs_completed(self) -> int:
        """Get number of completed jobs"""
        return self._jobs_completed
    
    async def check_connection(self) -> PlotterInfo:
        """Check if AxiDraw is connected"""
        try:
            # Try to run axicli with version flag using async subprocess
            process = await asyncio.create_subprocess_exec(
                "python", "-m", "axicli", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5
                )
                
                if process.returncode == 0:
                    version_info = stdout.decode().strip()
                    self._info = PlotterInfo(
                        connected=True,
                        model="AxiDraw",  # Could parse from version output
                        firmware=version_info
                    )
                    logger.info(f"AxiDraw connected: {version_info}")
                else:
                    self._info = PlotterInfo(connected=False)
                    logger.warning("AxiDraw not detected")
                    
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                self._info = PlotterInfo(connected=False)
                logger.warning("AxiDraw connection check timed out")
                
        except Exception as e:
            logger.error(f"Error checking AxiDraw connection: {e}")
            self._info = PlotterInfo(connected=False)
        
        return self._info
    
    async def plot_svg(
        self,
        svg_path: Path,
        job_id: str,
        parameters: Dict[str, Any],
        progress_callback=None
    ) -> bool:
        """
        Plot an SVG file using AxiCLI
        
        Args:
            svg_path: Path to SVG file
            job_id: Job ID for tracking
            parameters: Plotting parameters (speed, layers, etc.)
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if successful, False otherwise
        """
        if self.state != PlotterState.IDLE:
            raise RuntimeError(f"Plotter is not idle (current state: {self.state})")
        
        self.state = PlotterState.BUSY
        self.current_job_id = job_id
        
        try:
            # Build axicli command
            cmd = ["python", "-m", "axicli"]
            
            # Add parameters
            if parameters.get("layers"):
                cmd.extend(["--layer", parameters["layers"]])
            
            if parameters.get("speed"):
                cmd.extend(["--speed_pendown", str(parameters["speed"])])
                
            if parameters.get("pen_up_delay"):
                cmd.extend(["--pen_delay_up", str(parameters["pen_up_delay"])])
                
            if parameters.get("pen_down_delay"):
                cmd.extend(["--pen_delay_down", str(parameters["pen_down_delay"])])
            
            if parameters.get("preview"):
                cmd.append("--preview")
            
            # Add SVG file path
            cmd.append(str(svg_path))
            
            logger.info(f"Starting plot job {job_id}: {' '.join(cmd)}")
            
            # Execute plotting command using async subprocess
            self._current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor process output for progress with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    self._current_process.communicate(),
                    timeout=parameters.get("timeout", 3600)
                )
                
                # Decode output
                stdout_text = stdout.decode() if stdout else ""
                stderr_text = stderr.decode() if stderr else ""
                
                if self._current_process.returncode == 0:
                    logger.info(f"Job {job_id} completed successfully")
                    self._jobs_completed += 1
                    if progress_callback:
                        await progress_callback(100)
                    return True
                else:
                    logger.error(f"Job {job_id} failed: {stderr_text}")
                    self.state = PlotterState.ERROR
                    return False
                    
            except asyncio.TimeoutError:
                logger.error(f"Job {job_id} timed out")
                if self._current_process:
                    self._current_process.kill()
                    await self._current_process.wait()
                self.state = PlotterState.ERROR
                return False
            
        except Exception as e:
            logger.error(f"Error plotting job {job_id}: {e}")
            self.state = PlotterState.ERROR
            return False
            
        finally:
            self.state = PlotterState.IDLE
            self.current_job_id = None
            self._current_process = None
    
    async def pause(self) -> bool:
        """Pause current plotting job"""
        # Note: AxiCLI doesn't support pause/resume natively
        # This would require more advanced process control
        logger.warning("Pause not yet implemented - AxiCLI limitation")
        return False
    
    async def resume(self) -> bool:
        """Resume paused plotting job"""
        logger.warning("Resume not yet implemented - AxiCLI limitation")
        return False
    
    async def cancel(self) -> bool:
        """
        Cancel current plotting job
        
        Terminates the subprocess gracefully (SIGTERM), with fallback to kill (SIGKILL)
        if process doesn't exit within 5 seconds.
        """
        if not self._current_process or self._current_process.returncode is not None:
            logger.warning("No active process to cancel")
            return False
        
        try:
            logger.info(f"Cancelling job {self.current_job_id}")
            
            # Try graceful termination first
            self._current_process.terminate()
            
            try:
                # Wait up to 5 seconds for graceful shutdown
                await asyncio.wait_for(self._current_process.wait(), timeout=5)
                logger.info(f"Job {self.current_job_id} terminated gracefully")
            except asyncio.TimeoutError:
                # Force kill if still running
                logger.warning(f"Job {self.current_job_id} didn't terminate, killing")
                self._current_process.kill()
                await self._current_process.wait()
            
            # Update state
            self.state = PlotterState.IDLE
            self.current_job_id = None
            self._current_process = None
            
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current plotter status"""
        return {
            "state": self.state.value,
            "current_job": self.current_job_id,
            "connected": self._info.connected if self._info else False,
            "model": self._info.model if self._info else None,
            "firmware": self._info.firmware if self._info else None,
            "uptime": self.get_uptime(),
            "jobs_completed": self._jobs_completed
        }


# Global plotter instance
plotter = AxiDrawController()
