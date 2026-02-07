"""
Zero Showtime Detection Service

Analyzes operating hours history to identify theaters consistently returning
zero showtimes from Fandango, indicating they may have moved to their own
ticketing sites.

Usage:
    from app.zero_showtime_service import ZeroShowtimeService

    service = ZeroShowtimeService(company_id=1)
    results = service.analyze_theaters(["Marcus Arnold Cinema", "AMC Mayfair Mall"])
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

from sqlalchemy import func, and_, desc

from app.db_session import get_session
from app.db_models import OperatingHours

logger = logging.getLogger(__name__)


@dataclass
class ZeroShowtimeResult:
    """Analysis result for a single theater's showtime history."""
    theater_name: str
    total_scrapes: int
    zero_count: int
    last_nonzero_date: Optional[str]  # ISO date string or None
    consecutive_zeros: int
    last_scrape_date: Optional[str]  # ISO date string or None
    classification: str  # "likely_off_fandango" | "warning" | "normal"

    def to_dict(self) -> dict:
        return asdict(self)


class ZeroShowtimeService:
    """Detects theaters that consistently return zero showtimes."""

    # Classification thresholds
    LIKELY_OFF_FANDANGO_THRESHOLD = 3  # consecutive zero-showtime dates
    WARNING_THRESHOLD = 2  # consecutive zeros for warning

    def __init__(self, company_id: int):
        self.company_id = company_id

    def analyze_theaters(
        self,
        theater_names: List[str],
        lookback_days: int = 30
    ) -> List[ZeroShowtimeResult]:
        """
        Analyze operating hours history for the given theaters.

        Returns a ZeroShowtimeResult for each theater that has any operating
        hours data in the lookback window. Theaters with no data at all are
        excluded (they haven't been scraped yet).
        """
        if not theater_names:
            return []

        cutoff = date.today() - timedelta(days=lookback_days)
        results = []

        with get_session() as session:
            # Get all operating hours records for these theaters in the window
            records = session.query(
                OperatingHours.theater_name,
                OperatingHours.scrape_date,
                OperatingHours.showtime_count,
            ).filter(
                and_(
                    OperatingHours.company_id == self.company_id,
                    OperatingHours.theater_name.in_(theater_names),
                    OperatingHours.scrape_date >= cutoff,
                )
            ).order_by(
                OperatingHours.theater_name,
                desc(OperatingHours.scrape_date),
            ).all()

            if not records:
                return []

            # Group by theater
            theater_records: Dict[str, list] = {}
            for rec in records:
                theater_records.setdefault(rec.theater_name, []).append(rec)

            for theater_name, recs in theater_records.items():
                # recs are ordered by scrape_date DESC (most recent first)
                total_scrapes = len(recs)
                zero_count = sum(1 for r in recs if (r.showtime_count or 0) == 0)

                # Find last non-zero date
                last_nonzero = None
                for r in recs:
                    if (r.showtime_count or 0) > 0:
                        last_nonzero = r.scrape_date
                        break

                # Calculate consecutive zeros from most recent
                consecutive_zeros = 0
                for r in recs:
                    if (r.showtime_count or 0) == 0:
                        consecutive_zeros += 1
                    else:
                        break

                last_scrape = recs[0].scrape_date if recs else None

                # Classify
                if consecutive_zeros >= self.LIKELY_OFF_FANDANGO_THRESHOLD:
                    classification = "likely_off_fandango"
                elif consecutive_zeros >= self.WARNING_THRESHOLD:
                    classification = "warning"
                else:
                    classification = "normal"

                results.append(ZeroShowtimeResult(
                    theater_name=theater_name,
                    total_scrapes=total_scrapes,
                    zero_count=zero_count,
                    last_nonzero_date=last_nonzero.isoformat() if last_nonzero else None,
                    consecutive_zeros=consecutive_zeros,
                    last_scrape_date=last_scrape.isoformat() if last_scrape else None,
                    classification=classification,
                ))

        # Sort: likely_off_fandango first, then warning, then normal
        priority = {"likely_off_fandango": 0, "warning": 1, "normal": 2}
        results.sort(key=lambda r: (priority.get(r.classification, 9), r.theater_name))

        logger.info(
            f"Zero showtime analysis for {len(theater_names)} theaters: "
            f"{sum(1 for r in results if r.classification == 'likely_off_fandango')} likely off Fandango, "
            f"{sum(1 for r in results if r.classification == 'warning')} warnings"
        )

        return results
