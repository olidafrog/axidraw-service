"""Pydantic models for API"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class JobStatus(str, Enum):
    """Job status"""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlotterState(str, Enum):
    """Plotter state"""
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class JobParameters(BaseModel):
    """Job plotting parameters"""
    layers: Optional[str] = Field(None, description="Comma-separated layer IDs")
    speed: int = Field(25, ge=1, le=100, description="Plotting speed (1-100)")
    pen_up_delay: int = Field(150, ge=0, description="Pen up delay in milliseconds")
    pen_down_delay: int = Field(150, ge=0, description="Pen down delay in milliseconds")
    preview: bool = Field(False, description="Preview mode (no actual plotting)")


class JobCreate(BaseModel):
    """Job creation request"""
    filename: str
    parameters: JobParameters = Field(default_factory=JobParameters)


class JobResponse(BaseModel):
    """Job response"""
    job_id: str
    filename: str
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    parameters: JobParameters
    position: Optional[int] = Field(None, description="Position in queue (if queued)")
    
    class Config:
        from_attributes = True


class JobSubmitResponse(BaseModel):
    """Job submission response"""
    job_id: str
    status: JobStatus
    created_at: datetime
    position: int


class PlotterStatus(BaseModel):
    """Plotter status"""
    state: PlotterState
    current_job: Optional[str] = None
    connected: bool
    model: Optional[str] = None
    firmware: Optional[str] = None
    uptime: int = Field(0, description="Service uptime in seconds")
    jobs_completed: int = 0


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    uptime: int
    queue_size: int
    plotter_connected: bool
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
