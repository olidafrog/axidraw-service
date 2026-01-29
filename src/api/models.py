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
    """Job plotting parameters with validation"""
    layers: Optional[str] = Field(
        None, 
        description="Comma-separated layer IDs (e.g., '1,2,3')",
        pattern=r'^[\d,\s]*$',  # Only digits, commas, spaces
        max_length=100
    )
    speed: int = Field(
        25, 
        ge=1, 
        le=100, 
        description="Plotting speed (1-100)"
    )
    pen_up_delay: int = Field(
        150, 
        ge=0, 
        le=5000,  # Max 5 seconds
        description="Pen up delay in milliseconds (0-5000)"
    )
    pen_down_delay: int = Field(
        150, 
        ge=0, 
        le=5000,  # Max 5 seconds
        description="Pen down delay in milliseconds (0-5000)"
    )
    preview: bool = Field(
        False, 
        description="Preview mode (no actual plotting)"
    )
    timeout: int = Field(
        3600,
        ge=60,
        le=86400,  # Max 24 hours
        description="Job timeout in seconds (60-86400)"
    )


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
