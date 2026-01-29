"""
PriceScout API - Authentication Utilities

Shared authentication utilities for API key verification and rate limiting.
"""

import os
from typing import Optional
from fastapi import HTTPException, status, Request


async def verify_api_key(api_key: str) -> bool:
    """
    Verify if the provided API key is valid.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        True if valid, False otherwise
    """
    # Get valid API keys from environment or config
    valid_api_keys = os.getenv("API_KEYS", "").split(",")
    valid_api_keys = [k.strip() for k in valid_api_keys if k.strip()]
    
    if not valid_api_keys:
        return False
        
    return api_key in valid_api_keys


async def check_rate_limit(request: Request) -> None:
    """
    Check rate limits for the current request.
    
    This is a placeholder implementation. In production, you'd use Redis
    or a proper rate limiting service.
    
    Args:
        request: FastAPI request object
        
    Raises:
        HTTPException: 429 if rate limited
    """
    # For now, this is a no-op
    # Actual rate limiting is implemented in auth_rate_limiter
    pass
