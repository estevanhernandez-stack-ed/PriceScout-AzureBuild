"""
PLF Calibration Service

Uses Fandango's Premium Format baselines as the source of truth for PLF pricing.
EntTelligence lumps PLF into "2D" without distinction, so this service provides
price thresholds to classify EntTelligence prices as standard vs PLF.

Architecture:
    Fandango scrapes  →  Standard baselines ($11.43 matinee, $14.70 prime)
                      →  Premium Format baselines ($15.79, $19.05)
    EntTelligence     →  "2D" prices ($10.50, $13.50, $14.50, $17.50)
                          ↓
    This service      →  PLF threshold per theater (midpoint between Standard max and PF min)
                      →  classify_price() → "standard" or "plf"
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from sqlalchemy import and_, or_
from app.db_models import PriceBaseline, TheaterAmenities
from app.db_session import get_session
from api.services.tax_estimation import (
    get_tax_config,
    get_tax_rate_for_theater,
    bulk_get_theater_states,
)

logger = logging.getLogger(__name__)

# Fallback tax rate only used when tax_estimation service has no config
DEFAULT_TAX_RATE = 0.075


def build_plf_thresholds(
    company_id: int,
    tax_rate: Optional[float] = None,
) -> Dict[str, Dict]:
    """
    Build PLF price thresholds for all theaters that have both Standard/2D
    and Premium Format Fandango baselines.

    For each theater, computes a price threshold above which an EntTelligence
    "2D" price is likely a PLF showing rather than standard.

    The threshold = midpoint between the highest Standard baseline and the
    lowest Premium Format baseline, converted to pre-tax (EntTelligence prices
    are pre-tax, Fandango baselines are tax-inclusive).

    Args:
        company_id: Company ID
        tax_rate: Override tax rate for all theaters (default: per-theater from tax config)

    Returns:
        Dict keyed by theater_name: {
            "plf_threshold_pretax": float,  # Pre-tax price above which = likely PLF
            "standard_ceiling_pretax": float,  # Highest standard baseline (pre-tax)
            "plf_floor_pretax": float,  # Lowest PLF baseline (pre-tax)
            "has_plf_screens": bool,  # From theater_amenities
            "plf_screen_count": int,  # Number of PLF screens
        }
    """
    # Load per-theater tax config for accurate pre-tax/post-tax conversion
    tax_config_data = get_tax_config(company_id)

    with get_session() as session:
        # Load active baselines for Standard and Premium Format
        today = date.today()
        baselines = session.query(PriceBaseline).filter(
            PriceBaseline.company_id == company_id,
            PriceBaseline.effective_from <= today,
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= today,
            ),
            PriceBaseline.format.in_(['Standard', 'Premium Format', '2D']),
        ).all()

        # Group by theater → format → list of baseline prices
        theater_formats: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for bl in baselines:
            fmt = bl.format or '2D'
            price = float(bl.baseline_price) if bl.baseline_price else 0
            if price > 0:
                theater_formats[bl.theater_name][fmt].append(price)

        # Load theater amenity data for PLF screen counts
        amenities = session.query(TheaterAmenities).filter(
            TheaterAmenities.company_id == company_id,
        ).all()

        amenity_lookup = {}
        for a in amenities:
            amenity_lookup[a.theater_name] = {
                "has_plf_screens": (a.premium_screen_count or 0) > 0,
                "plf_screen_count": a.premium_screen_count or 0,
            }

        # Build thresholds
        # Strategy: PLF threshold = Standard ceiling + 5% buffer (pre-tax).
        # Any EntTelligence "2D" price above this is likely from a PLF screen.
        #
        # Why not use min(PLF prices)? Because PLF baselines include discount day
        # prices (e.g., Marcus $5 Tuesday on UltraScreen = $5.45 with tax), which
        # makes the PLF floor unreasonably low.
        #
        # Using the Standard ceiling as the anchor is robust because:
        # 1. Fandango Standard baselines are clean (not contaminated by PLF)
        # 2. The 5% buffer accounts for minor price variations and rounding
        # 3. Works even if PLF baselines are sparse or include discount day pricing
        PLF_BUFFER_PERCENT = 0.05  # 5% above standard ceiling

        # Batch-lookup theater states for per-theater tax rate resolution
        all_theater_names = list(theater_formats.keys())
        theater_states = bulk_get_theater_states(company_id, all_theater_names)

        thresholds = {}
        for theater_name, formats in theater_formats.items():
            # Standard/2D baselines (tax-inclusive from Fandango)
            standard_prices = formats.get('Standard', []) + formats.get('2D', [])
            plf_prices = formats.get('Premium Format', [])

            if not standard_prices or not plf_prices:
                continue  # Need both to confirm theater has PLF

            # Per-theater tax rate for accurate pre-tax conversion
            rate = tax_rate if tax_rate is not None else get_tax_rate_for_theater(
                tax_config_data, theater_states.get(theater_name), theater_name=theater_name
            )
            if rate <= 0:
                rate = DEFAULT_TAX_RATE  # Fallback for tax-inclusive circuits

            # Convert to pre-tax
            standard_ceiling_posttax = max(standard_prices)
            standard_ceiling_pretax = standard_ceiling_posttax / (1 + rate)

            # PLF floor = 75th percentile of PLF baselines (ignores discount day outliers)
            plf_prices_sorted = sorted(plf_prices)
            plf_p75_idx = max(0, int(len(plf_prices_sorted) * 0.25))  # 25th percentile (low end, conservative)
            plf_floor_posttax = plf_prices_sorted[plf_p75_idx]
            plf_floor_pretax = plf_floor_posttax / (1 + rate)

            # Threshold = standard ceiling + buffer
            # But if the PLF 25th percentile is above standard ceiling, use midpoint
            threshold_pretax = standard_ceiling_pretax * (1 + PLF_BUFFER_PERCENT)
            if plf_floor_pretax > threshold_pretax:
                # Clear gap — use midpoint for a tighter threshold
                threshold_pretax = (standard_ceiling_pretax + plf_floor_pretax) / 2

            amenity_info = amenity_lookup.get(theater_name, {
                "has_plf_screens": False,
                "plf_screen_count": 0,
            })

            thresholds[theater_name] = {
                "plf_threshold_pretax": round(threshold_pretax, 2),
                "standard_ceiling_pretax": round(standard_ceiling_pretax, 2),
                "plf_floor_pretax": round(plf_floor_pretax, 2),
                "standard_ceiling_posttax": round(standard_ceiling_posttax, 2),
                "plf_floor_posttax": round(plf_floor_posttax, 2),
                "has_plf_screens": amenity_info["has_plf_screens"],
                "plf_screen_count": amenity_info["plf_screen_count"],
            }

        theaters_with_thresholds = len(thresholds)
        theaters_with_plf_screens = sum(
            1 for t in thresholds.values() if t["has_plf_screens"]
        )
        logger.info(
            f"Built PLF thresholds for {theaters_with_thresholds} theaters "
            f"({theaters_with_plf_screens} with confirmed PLF screens)"
        )

        return thresholds


def classify_price(
    theater_name: str,
    price: float,
    format_type: str,
    thresholds: Dict[str, Dict],
) -> str:
    """
    Classify an EntTelligence price as 'standard' or 'plf'.

    Only applies to "2D" format prices (EntTelligence's catch-all).
    Other formats (3D, 70MM, 35MM) pass through as-is.

    Args:
        theater_name: Theater name
        price: Pre-tax price from EntTelligence
        format_type: Format string from EntTelligence
        thresholds: PLF thresholds from build_plf_thresholds()

    Returns:
        'standard' or 'plf'
    """
    # Only classify "2D" — other formats are already specific
    if format_type and format_type not in ('2D', None):
        return 'standard'

    theater_info = thresholds.get(theater_name)
    if not theater_info:
        return 'standard'  # No threshold data — assume standard

    if price >= theater_info["plf_threshold_pretax"]:
        return 'plf'

    return 'standard'


def filter_plf_from_prices(
    prices: List[float],
    theater_name: str,
    format_type: str,
    thresholds: Dict[str, Dict],
) -> Tuple[List[float], List[float]]:
    """
    Split a list of EntTelligence prices into standard and PLF buckets.

    Args:
        prices: List of pre-tax prices
        theater_name: Theater name
        format_type: Format string
        thresholds: PLF thresholds

    Returns:
        Tuple of (standard_prices, plf_prices)
    """
    if format_type and format_type not in ('2D', None):
        return prices, []

    theater_info = thresholds.get(theater_name)
    if not theater_info:
        return prices, []

    threshold = theater_info["plf_threshold_pretax"]
    standard = [p for p in prices if p < threshold]
    plf = [p for p in prices if p >= threshold]

    return standard, plf


def refresh_plf_calibration(company_id: int) -> Dict:
    """
    Refresh PLF calibration data.

    This is the main entry point for the scheduled task. It:
    1. Builds PLF thresholds from current Fandango baselines
    2. Reports stats on how many theaters have PLF data
    3. Identifies theaters with PLF screens but no Fandango PLF baselines (gaps)

    Args:
        company_id: Company ID

    Returns:
        Dict with calibration results and gap analysis
    """
    thresholds = build_plf_thresholds(company_id)

    # Find theaters with PLF screens but no PLF thresholds (coverage gaps)
    with get_session() as session:
        plf_theaters = session.query(TheaterAmenities).filter(
            TheaterAmenities.company_id == company_id,
            TheaterAmenities.premium_screen_count > 0,
        ).all()

        plf_gaps = []
        for theater in plf_theaters:
            if theater.theater_name not in thresholds:
                plf_gaps.append({
                    "theater_name": theater.theater_name,
                    "plf_screen_count": theater.premium_screen_count,
                    "reason": "No Fandango Premium Format baselines found",
                })

    # Sample stats
    avg_threshold = 0
    if thresholds:
        avg_threshold = sum(
            t["plf_threshold_pretax"] for t in thresholds.values()
        ) / len(thresholds)

    return {
        "theaters_calibrated": len(thresholds),
        "theaters_with_plf_screens": len(plf_theaters),
        "coverage_gaps": len(plf_gaps),
        "gap_details": plf_gaps[:20],  # Limit to 20
        "avg_plf_threshold_pretax": round(avg_threshold, 2),
        "thresholds": thresholds,
    }
