"""
Guarded Baseline Refresh Service

Protects baselines from being corrupted by bad scrape data.
When auto-refreshing, new baselines are compared against existing ones.
Only changes within a configurable drift tolerance are applied automatically.
Changes outside tolerance are flagged for manual review.

This ensures that a single bad scrape batch (mis-scraped prices, site errors,
temporary promotions) cannot silently overwrite correct baseline prices.
"""

from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import logging

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import PriceBaseline
from app.baseline_discovery import BaselineDiscoveryService
from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

logger = logging.getLogger(__name__)

# Maximum allowed price drift before a baseline update is flagged (not applied)
# 15% means: if old baseline is $10.00, new value must be between $8.50-$11.50
MAX_DRIFT_PERCENT = 15.0

# Minimum samples required for auto-refresh (higher bar than manual discovery)
AUTO_REFRESH_MIN_SAMPLES = 8


def guarded_refresh(
    company_id: int,
    source: str = "fandango",
    max_drift_percent: float = MAX_DRIFT_PERCENT,
    min_samples: int = AUTO_REFRESH_MIN_SAMPLES,
    lookback_days: int = 60,
    dry_run: bool = False,
) -> Dict:
    """
    Perform a guarded baseline refresh.

    Discovers new baselines from fresh data, compares each against the
    existing stored baseline, and only applies changes within the drift
    tolerance. Large changes are flagged for manual review.

    Args:
        company_id: Company ID
        source: Data source ("fandango" or "enttelligence")
        max_drift_percent: Maximum allowed price change (%) before flagging
        min_samples: Minimum sample count for new baselines
        lookback_days: Days of history to analyze
        dry_run: If True, compute and compare but don't write anything

    Returns:
        Dict with:
            applied: number of baselines updated
            new: number of new baselines created
            flagged: number of baselines that exceeded drift tolerance
            unchanged: number of baselines within tolerance but same value
            flagged_details: list of {theater, ticket_type, format, old_price, new_price, drift_pct}
            source: data source used
    """
    result = {
        "applied": 0,
        "new": 0,
        "flagged": 0,
        "unchanged": 0,
        "skipped_low_samples": 0,
        "flagged_details": [],
        "source": source,
        "dry_run": dry_run,
        "max_drift_percent": max_drift_percent,
    }

    # Discover new baselines from fresh data
    if source == "fandango":
        service = BaselineDiscoveryService(company_id)
        new_baselines = service.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
        )
    elif source == "enttelligence":
        service = EntTelligenceBaselineDiscoveryService(company_id)
        new_baselines = service.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
        )
    else:
        logger.error(f"Unknown source: {source}")
        return result

    if not new_baselines:
        logger.info(f"Guarded refresh: no baselines discovered from {source}")
        return result

    logger.info(
        f"Guarded refresh: discovered {len(new_baselines)} candidate baselines "
        f"from {source} (min_samples={min_samples}, lookback={lookback_days}d)"
    )

    with get_session() as session:
        for bl in new_baselines:
            # Enforce higher sample bar for auto-refresh
            sample_count = bl.get("sample_count", 0)
            if sample_count < min_samples:
                result["skipped_low_samples"] += 1
                continue

            new_price = float(bl["baseline_price"])

            # Look up existing active baseline for this combination
            existing = _find_existing_baseline(
                session, company_id, bl
            )

            if existing is None:
                # No existing baseline — create new
                if not dry_run:
                    _create_baseline(session, company_id, bl)
                result["new"] += 1
                continue

            old_price = float(existing.baseline_price)

            # Calculate drift
            if old_price > 0:
                drift_pct = abs(new_price - old_price) / old_price * 100
            else:
                drift_pct = 100.0 if new_price > 0 else 0.0

            if drift_pct < 0.5:
                # Effectively the same price (< 0.5% change) — skip
                result["unchanged"] += 1
                continue

            if drift_pct > max_drift_percent:
                # Too much drift — flag for manual review, don't overwrite
                result["flagged"] += 1
                result["flagged_details"].append({
                    "theater_name": bl["theater_name"],
                    "ticket_type": bl["ticket_type"],
                    "format": bl.get("format"),
                    "daypart": bl.get("daypart"),
                    "old_price": old_price,
                    "new_price": new_price,
                    "drift_percent": round(drift_pct, 1),
                    "sample_count": sample_count,
                })
                logger.warning(
                    f"Baseline drift FLAGGED: {bl['theater_name']} "
                    f"{bl['ticket_type']} {bl.get('format', 'Standard')}: "
                    f"${old_price:.2f} → ${new_price:.2f} "
                    f"({drift_pct:+.1f}%, exceeds {max_drift_percent}%)"
                )
                continue

            # Within tolerance — apply update
            if not dry_run:
                existing.baseline_price = Decimal(str(round(new_price, 2)))
                existing.sample_count = sample_count
                existing.last_discovery_at = datetime.now(UTC)
                existing.source = source
            result["applied"] += 1
            logger.debug(
                f"Baseline updated: {bl['theater_name']} "
                f"{bl['ticket_type']}: ${old_price:.2f} → ${new_price:.2f} "
                f"({drift_pct:+.1f}%)"
            )

        if not dry_run:
            session.flush()

    logger.info(
        f"Guarded refresh complete ({source}): "
        f"{result['applied']} applied, {result['new']} new, "
        f"{result['flagged']} flagged, {result['unchanged']} unchanged"
    )

    return result


def _find_existing_baseline(
    session: Session,
    company_id: int,
    bl: Dict,
) -> Optional[PriceBaseline]:
    """Find the active baseline matching this combination."""
    filters = [
        PriceBaseline.company_id == company_id,
        PriceBaseline.theater_name == bl["theater_name"],
        PriceBaseline.ticket_type == bl["ticket_type"],
        PriceBaseline.effective_to.is_(None),  # Active only
    ]

    # Handle nullable fields
    for field in ("format", "daypart", "day_type"):
        val = bl.get(field)
        if val is None:
            filters.append(getattr(PriceBaseline, field).is_(None))
        else:
            filters.append(getattr(PriceBaseline, field) == val)

    day_of_week = bl.get("day_of_week")
    if day_of_week is None:
        filters.append(PriceBaseline.day_of_week.is_(None))
    else:
        filters.append(PriceBaseline.day_of_week == day_of_week)

    return session.query(PriceBaseline).filter(and_(*filters)).first()


def _create_baseline(
    session: Session,
    company_id: int,
    bl: Dict,
) -> None:
    """Create a new baseline record."""
    new_baseline = PriceBaseline(
        company_id=company_id,
        theater_name=bl["theater_name"],
        ticket_type=bl["ticket_type"],
        format=bl.get("format"),
        daypart=bl.get("daypart"),
        day_type=bl.get("day_type"),
        day_of_week=bl.get("day_of_week"),
        baseline_price=Decimal(str(bl["baseline_price"])),
        effective_from=date.today(),
        effective_to=None,
        source=bl.get("source", "fandango"),
        tax_status="inclusive",
        sample_count=bl.get("sample_count"),
        last_discovery_at=datetime.now(UTC),
    )
    session.add(new_baseline)


def trigger_post_scrape_refresh(company_id: int, source: str = "fandango") -> Dict:
    """
    Called automatically after a scrape completes.
    Runs a guarded refresh with conservative settings.

    Returns the refresh result dict.
    """
    logger.info(f"Post-scrape baseline auto-refresh triggered (source={source})")

    try:
        result = guarded_refresh(
            company_id=company_id,
            source=source,
            max_drift_percent=MAX_DRIFT_PERCENT,
            min_samples=AUTO_REFRESH_MIN_SAMPLES,
            lookback_days=60,
        )

        if result["flagged"] > 0:
            logger.warning(
                f"Post-scrape refresh: {result['flagged']} baselines flagged "
                f"for manual review (drift > {MAX_DRIFT_PERCENT}%)"
            )

        return result

    except Exception as e:
        logger.error(f"Post-scrape baseline refresh failed: {e}", exc_info=True)
        return {
            "error": str(e),
            "applied": 0,
            "new": 0,
            "flagged": 0,
        }
