"""
PriceScout API - Pydantic Schemas

Shared Pydantic models for API request/response validation.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class SelectionAnalysisRequest(BaseModel):
    """Request schema for selection analysis report."""
    selected_showtimes: List[int] = Field(
        ...,
        description="List of showtime IDs for analysis"
    )


class ShowtimeViewRequest(BaseModel):
    """Request schema for showtime view reports (HTML/PDF)."""
    all_showings: List[Dict[str, Any]] = Field(
        ...,
        description="List of all showing data"
    )
    selected_films: List[str] = Field(
        ...,
        description="List of selected film titles"
    )
    theaters: List[str] = Field(
        ...,
        description="List of theater names"
    )
    date_start: str = Field(
        ...,
        description="Start date for the report (YYYY-MM-DD)"
    )
    date_end: str = Field(
        ...,
        description="End date for the report (YYYY-MM-DD)"
    )
    context_title: Optional[str] = Field(
        default="Showtime View Report",
        description="Title/context for the report"
    )
