"""
Scrapes API Router — decomposed into sub-modules.

Re-exports a single `router` that combines all sub-routers:
  - jobs: trigger, status, cancel, list, collision check
  - fetch: theater search, showtime fetch, operating hours, save
  - verification: price verification, showtime comparison, zero-showtime analysis
"""

from fastapi import APIRouter

from .jobs import router as jobs_router
from .fetch import router as fetch_router
from .verification import router as verification_router

router = APIRouter()
router.include_router(jobs_router)
router.include_router(fetch_router)
router.include_router(verification_router)
