"""Plotter control endpoints"""
from fastapi import APIRouter, HTTPException

from src.api.models import PlotterStatus, PlotterState
from src.plotter.controller import plotter

router = APIRouter(prefix="/plotter", tags=["plotter"])


@router.get("/status", response_model=PlotterStatus)
async def get_plotter_status():
    """Get current plotter status"""
    status_dict = plotter.get_status()
    return PlotterStatus(**status_dict)


@router.post("/pause")
async def pause_plotter():
    """Pause current plotting job"""
    if plotter.state != PlotterState.BUSY:
        raise HTTPException(status_code=400, detail="No active job to pause")
    
    success = await plotter.pause()
    if not success:
        raise HTTPException(status_code=501, detail="Pause not implemented yet")
    
    return {"message": "Plotter paused"}


@router.post("/resume")
async def resume_plotter():
    """Resume paused plotting job"""
    if plotter.state != PlotterState.PAUSED:
        raise HTTPException(status_code=400, detail="Plotter is not paused")
    
    success = await plotter.resume()
    if not success:
        raise HTTPException(status_code=501, detail="Resume not implemented yet")
    
    return {"message": "Plotter resumed"}


@router.post("/cancel")
async def cancel_current_job():
    """Cancel current plotting job"""
    if plotter.state not in [PlotterState.BUSY, PlotterState.PAUSED]:
        raise HTTPException(status_code=400, detail="No active job to cancel")
    
    success = await plotter.cancel()
    if not success:
        raise HTTPException(status_code=501, detail="Cancel not implemented yet")
    
    return {"message": "Job cancelled"}
