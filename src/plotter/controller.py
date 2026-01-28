"""AxiDraw plotter controller - wraps AxiCLI"""
import logging
import subprocess
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
        
    def get_uptime(self) -> int:
        """Get service uptime in seconds"""
        return int(time.time() - self._start_time)
    
    def get_jobs_completed(self) -> int:
        """Get number of completed jobs"""
        return self._jobs_completed
    
    async def check_connection(self) -> PlotterInfo:
        """Check if AxiDraw is connected"""
        try:
            # Try to run axicli with version flag
            result = subprocess.run(
                ["python", "-m", "axicli", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version_info = result.stdout.strip()
                self._info = PlotterInfo(
                    connected=True,
                    model="AxiDraw",  # Could parse from version output
                    firmware=version_info
                )
                logger.info(f"AxiDraw connected: {version_info}")
            else:
                self._info = PlotterInfo(connected=False)
                logger.warning("AxiDraw not detected")
                
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
            
            # Execute plotting command
            # Note: This is a blocking operation. For production, consider using
            # asyncio subprocess or threading for better async handling
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor process output for progress
            # AxiCLI doesn't provide detailed progress, so we'll simulate
            # In production, you might parse output or use time-based estimation
            stdout, stderr = process.communicate(timeout=parameters.get("timeout", 3600))
            
            if process.returncode == 0:
                logger.info(f"Job {job_id} completed successfully")
                self._jobs_completed += 1
                if progress_callback:
                    await progress_callback(100)
                return True
            else:
                logger.error(f"Job {job_id} failed: {stderr}")
                self.state = PlotterState.ERROR
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Job {job_id} timed out")
            process.kill()
            self.state = PlotterState.ERROR
            return False
            
        except Exception as e:
            logger.error(f"Error plotting job {job_id}: {e}")
            self.state = PlotterState.ERROR
            return False
            
        finally:
            self.state = PlotterState.IDLE
            self.current_job_id = None
    
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
        """Cancel current plotting job"""
        # Would need to track subprocess and kill it
        logger.warning("Cancel not yet implemented")
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
