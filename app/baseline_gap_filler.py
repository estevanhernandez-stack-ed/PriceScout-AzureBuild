"""
Baseline Gap Filler Service

Analyzes coverage gaps and proposes baselines from available data sources
(EntTelligence cache, circuit averages) to fill missing baseline coverage.

Uses a propose-then-apply pattern: users review proposals before they become
baselines, ensuring data quality and human oversight.

Usage:
    from app.baseline_gap_filler import BaselineGapFillerService

    service = BaselineGapFillerService(company_id=1)
    proposals = service.analyze_and_propose("Marcus Arnold Cinema")
    created = service.apply_fills(proposals, min_confidence=0.7)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import logging
import statistics

from app.db_session import get_session
from app.db_models import (
    PriceBaseline, EntTelligencePriceCache, CompanyProfile
)
from app.coverage_gaps_service import CoverageGapsService, CoverageReport, GapInfo
from app.simplified_baseline_service import normalize_daypart, normalize_ticket_type

logger = logging.getLogger(__name__)


@dataclass
class ProposedGapFill:
    """A proposed baseline to fill a coverage gap."""
    theater_name: str
    ticket_type: str
    format: str
    daypart: Optional[str] = None
    day_type: Optional[str] = None
    proposed_price: float = 0.0
    source: str = ''  # 'enttelligence', 'circuit_average'
    sample_count: int = 0
    confidence: float = 0.0  # 0-1
    gap_type: str = ''  # matches GapInfo.gap_type
    gap_description: str = ''


class BaselineGapFillerService:
    """Service for proposing and applying baseline gap fills from available data."""

    # Confidence thresholds
    MIN_SAMPLES_ENTTELLIGENCE = 3  # Minimum samples from EntTelligence cache
    MIN_SAMPLES_CIRCUIT_AVG = 2  # Minimum other theaters for circuit average
    MAX_CONFIDENCE_CIRCUIT_AVG = 0.5  # Circuit averages are lower confidence
    DEFAULT_MIN_CONFIDENCE = 0.7  # Default threshold for auto-apply

    # Lookback for EntTelligence cache data
    CACHE_LOOKBACK_DAYS = 60

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.coverage_service = CoverageGapsService(company_id)

    def analyze_and_propose(
        self,
        theater_name: str,
        lookback_days: int = 90,
        min_samples: int = 3
    ) -> List[ProposedGapFill]:
        """
        Analyze coverage gaps and propose fills from available data.

        Strategy:
        1. Get current gaps from CoverageGapsService
        2. For each gap, search EntTelligence cache for matching data
        3. Fallback: use circuit average from other theaters' baselines
        4. Return proposals sorted by confidence (highest first)
        """
        # Get coverage report
        report = self.coverage_service.analyze_theater(theater_name, lookback_days)

        if not report.gaps:
            logger.info(f"No coverage gaps found for {theater_name}")
            return []

        proposals = []
        circuit_name = report.circuit_name

        with get_session() as session:
            # Strategy 1: Fill from EntTelligence cache
            ent_proposals = self._propose_from_enttelligence(
                session, theater_name, report, min_samples
            )
            proposals.extend(ent_proposals)

            # Strategy 2: Fill from circuit averages (lower confidence)
            if circuit_name:
                circuit_proposals = self._propose_from_circuit_average(
                    session, theater_name, circuit_name, report, min_samples
                )
                # Only add circuit proposals for gaps not already filled by EntTelligence
                filled_keys = {(p.ticket_type, p.format, p.gap_type) for p in ent_proposals}
                for cp in circuit_proposals:
                    if (cp.ticket_type, cp.format, cp.gap_type) not in filled_keys:
                        proposals.append(cp)

        # Sort by confidence descending
        proposals.sort(key=lambda p: p.confidence, reverse=True)

        logger.info(
            f"Gap fill analysis for {theater_name}: "
            f"{len(report.gaps)} gaps found, {len(proposals)} fill proposals "
            f"({len(ent_proposals)} from EntTelligence, "
            f"{len(proposals) - len(ent_proposals)} from circuit avg)"
        )

        return proposals

    def apply_fills(
        self,
        proposals: List[ProposedGapFill],
        min_confidence: float = 0.7,
        created_by_user_id: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Apply gap fill proposals as new PriceBaseline records.

        Args:
            proposals: List of ProposedGapFill to apply
            min_confidence: Only apply proposals at or above this confidence
            created_by_user_id: User ID for audit trail

        Returns:
            Tuple of (baselines_created, baselines_skipped)
        """
        created = 0
        skipped = 0

        with get_session() as session:
            for proposal in proposals:
                if proposal.confidence < min_confidence:
                    skipped += 1
                    continue

                # Normalize proposal values before checking/inserting
                norm_ticket = normalize_ticket_type(proposal.ticket_type) or proposal.ticket_type
                norm_daypart = normalize_daypart(proposal.daypart)

                # Check if baseline already exists
                existing = session.query(PriceBaseline).filter(
                    PriceBaseline.company_id == self.company_id,
                    PriceBaseline.theater_name == proposal.theater_name,
                    PriceBaseline.ticket_type == norm_ticket,
                    PriceBaseline.format == proposal.format,
                ).first()

                if existing:
                    logger.debug(
                        f"Baseline already exists for {proposal.theater_name} "
                        f"{norm_ticket} {proposal.format}, skipping"
                    )
                    skipped += 1
                    continue

                source_tag = f"gap_fill_{proposal.source}"
                baseline = PriceBaseline(
                    company_id=self.company_id,
                    theater_name=proposal.theater_name,
                    ticket_type=norm_ticket,
                    format=proposal.format,
                    daypart=norm_daypart,
                    day_type=proposal.day_type,
                    baseline_price=Decimal(str(round(proposal.proposed_price, 2))),
                    effective_from=date.today(),
                    source=source_tag,
                    created_by=created_by_user_id or 0,
                )
                session.add(baseline)
                created += 1

            if created > 0:
                session.commit()
                logger.info(
                    f"Applied {created} gap fills for {proposals[0].theater_name if proposals else 'unknown'} "
                    f"(skipped {skipped})"
                )

        return created, skipped

    def _propose_from_enttelligence(
        self,
        session,
        theater_name: str,
        report: CoverageReport,
        min_samples: int
    ) -> List[ProposedGapFill]:
        """Search EntTelligence cache for data to fill gaps."""
        from sqlalchemy import func, and_

        proposals = []
        cutoff = date.today() - timedelta(days=self.CACHE_LOOKBACK_DAYS)

        # Query EntTelligence cache aggregated by ticket_type and format
        cache_data = session.query(
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
            func.count().label('sample_count'),
            func.avg(EntTelligencePriceCache.price).label('avg_price'),
            func.min(EntTelligencePriceCache.price).label('min_price'),
            func.max(EntTelligencePriceCache.price).label('max_price'),
        ).filter(
            and_(
                EntTelligencePriceCache.company_id == self.company_id,
                EntTelligencePriceCache.theater_name == theater_name,
                EntTelligencePriceCache.play_date >= cutoff,
            )
        ).group_by(
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
        ).having(
            func.count() >= min_samples
        ).all()

        if not cache_data:
            return proposals

        # Build set of existing baselines for this theater
        existing_baselines = set()
        for bl in report.healthy_baselines:
            key = (bl.get('ticket_type', ''), bl.get('format', ''))
            existing_baselines.add(key)

        for row in cache_data:
            ticket_type = row.ticket_type
            fmt = row.format or 'Standard'
            key = (ticket_type, fmt)

            # Skip if we already have a healthy baseline for this combination
            if key in existing_baselines:
                continue

            sample_count = row.sample_count
            avg_price = float(row.avg_price)
            min_price = float(row.min_price)
            max_price = float(row.max_price)

            # Calculate confidence based on sample count and price variance
            variance_ratio = (max_price - min_price) / avg_price if avg_price > 0 else 1.0
            sample_confidence = min(sample_count / 20.0, 1.0)  # Max at 20 samples
            variance_penalty = max(0, 1.0 - variance_ratio)  # Penalize high variance
            confidence = round(sample_confidence * 0.6 + variance_penalty * 0.4, 2)

            # Use 25th percentile as proposed price (conservative, matches discovery pattern)
            # For small samples, use average
            if sample_count >= 5:
                all_prices = [
                    float(p.price) for p in session.query(EntTelligencePriceCache.price).filter(
                        and_(
                            EntTelligencePriceCache.company_id == self.company_id,
                            EntTelligencePriceCache.theater_name == theater_name,
                            EntTelligencePriceCache.ticket_type == ticket_type,
                            EntTelligencePriceCache.format == (row.format if row.format else None),
                            EntTelligencePriceCache.play_date >= cutoff,
                        )
                    ).all()
                ]
                all_prices.sort()
                idx = max(0, len(all_prices) // 4 - 1)
                proposed_price = all_prices[idx]
            else:
                proposed_price = avg_price

            # Match to the most relevant gap
            gap_type = self._match_gap(report.gaps, ticket_type, fmt)

            proposals.append(ProposedGapFill(
                theater_name=theater_name,
                ticket_type=ticket_type,
                format=fmt,
                proposed_price=round(proposed_price, 2),
                source='enttelligence',
                sample_count=sample_count,
                confidence=confidence,
                gap_type=gap_type,
                gap_description=f"From {sample_count} EntTelligence cache samples "
                               f"(${min_price:.2f}-${max_price:.2f})",
            ))

        return proposals

    def _propose_from_circuit_average(
        self,
        session,
        theater_name: str,
        circuit_name: str,
        report: CoverageReport,
        min_samples: int
    ) -> List[ProposedGapFill]:
        """Fill gaps using averages from other theaters in the same circuit."""
        from sqlalchemy import func, and_

        proposals = []

        # Get baselines from other theaters in the same circuit
        circuit_baselines = session.query(
            PriceBaseline.ticket_type,
            PriceBaseline.format,
            func.count().label('theater_count'),
            func.avg(PriceBaseline.baseline_price).label('avg_price'),
            func.min(PriceBaseline.baseline_price).label('min_price'),
            func.max(PriceBaseline.baseline_price).label('max_price'),
        ).filter(
            and_(
                PriceBaseline.company_id == self.company_id,
                PriceBaseline.theater_name != theater_name,
            )
        ).group_by(
            PriceBaseline.ticket_type,
            PriceBaseline.format,
        ).having(
            func.count() >= self.MIN_SAMPLES_CIRCUIT_AVG
        ).all()

        if not circuit_baselines:
            return proposals

        # Filter to only baselines from theaters in the same circuit
        # First, get theater names in the same circuit
        from app.db_models import TheaterMetadata
        circuit_theaters = session.query(TheaterMetadata.theater_name).filter(
            and_(
                TheaterMetadata.company_id == self.company_id,
                TheaterMetadata.circuit_name == circuit_name,
                TheaterMetadata.theater_name != theater_name,
            )
        ).all()
        circuit_theater_names = {t.theater_name for t in circuit_theaters}

        if not circuit_theater_names:
            # Fallback: try matching circuit name in baselines via CompanyProfile
            # This handles cases where TheaterMetadata isn't populated
            return proposals

        # Re-query with circuit filter
        circuit_baselines = session.query(
            PriceBaseline.ticket_type,
            PriceBaseline.format,
            func.count(func.distinct(PriceBaseline.theater_name)).label('theater_count'),
            func.avg(PriceBaseline.baseline_price).label('avg_price'),
            func.min(PriceBaseline.baseline_price).label('min_price'),
            func.max(PriceBaseline.baseline_price).label('max_price'),
        ).filter(
            and_(
                PriceBaseline.company_id == self.company_id,
                PriceBaseline.theater_name.in_(circuit_theater_names),
            )
        ).group_by(
            PriceBaseline.ticket_type,
            PriceBaseline.format,
        ).having(
            func.count(func.distinct(PriceBaseline.theater_name)) >= self.MIN_SAMPLES_CIRCUIT_AVG
        ).all()

        # Build set of existing baselines
        existing_baselines = set()
        for bl in report.healthy_baselines:
            key = (bl.get('ticket_type', ''), bl.get('format', ''))
            existing_baselines.add(key)

        for row in circuit_baselines:
            ticket_type = row.ticket_type
            fmt = row.format or 'Standard'
            key = (ticket_type, fmt)

            if key in existing_baselines:
                continue

            theater_count = row.theater_count
            avg_price = float(row.avg_price)
            min_price = float(row.min_price)
            max_price = float(row.max_price)

            # Circuit averages capped at MAX_CONFIDENCE_CIRCUIT_AVG
            variance_ratio = (max_price - min_price) / avg_price if avg_price > 0 else 1.0
            theater_confidence = min(theater_count / 5.0, 1.0)  # Max at 5 theaters
            variance_penalty = max(0, 1.0 - variance_ratio * 0.5)
            raw_confidence = theater_confidence * 0.5 + variance_penalty * 0.5
            confidence = round(min(raw_confidence, self.MAX_CONFIDENCE_CIRCUIT_AVG), 2)

            gap_type = self._match_gap(report.gaps, ticket_type, fmt)

            proposals.append(ProposedGapFill(
                theater_name=theater_name,
                ticket_type=ticket_type,
                format=fmt,
                proposed_price=round(avg_price, 2),
                source='circuit_average',
                sample_count=theater_count,
                confidence=confidence,
                gap_type=gap_type,
                gap_description=f"Average of {theater_count} {circuit_name} theaters "
                               f"(${min_price:.2f}-${max_price:.2f})",
            ))

        return proposals

    def _match_gap(self, gaps: List[GapInfo], ticket_type: str, fmt: str) -> str:
        """Find the most relevant gap type for a proposed fill."""
        for gap in gaps:
            details = gap.details or {}
            if gap.gap_type == 'missing_format' and details.get('format') == fmt:
                return 'missing_format'
            if gap.gap_type == 'low_samples':
                if details.get('ticket_type') == ticket_type and details.get('format') == fmt:
                    return 'low_samples'
            if gap.gap_type == 'missing_day':
                return 'missing_day'
        return 'general_gap'
