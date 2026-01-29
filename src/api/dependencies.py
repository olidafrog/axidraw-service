"""API dependencies for authentication and common dependencies"""
import secrets
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from src.config import settings

# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify API key from request header.
    
    Raises 403 if API key is configured and invalid/missing.
    If no API key is configured in settings, authentication is skipped.
    Uses constant-time comparison to prevent timing attacks.
    """
    # If no API key configured, skip authentication (backward compatibility)
    if settings.api_key is None:
        return None
    
    # API key configured - require valid key with constant-time comparison
    if not api_key or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Provide X-API-Key header."
        )
    
    return api_key
