"""
Coverage Gaps Detection Service

Analyzes price data to identify gaps in baseline coverage for theaters.
Helps users understand what data is missing before relying on surge detection.

Usage:
    from app.coverage_gaps_service import CoverageGapsService

    service = CoverageGapsService(company_id=1)
    gaps = service.analyze_theater("Marcus Arnold Cinema")
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from app.db_session import get_session
from app.db_models import Showing, Price, PriceBaseline, CompanyProfile

logger = logging.getLogger(__name__)


@dataclass
class GapInfo:
    """Information about a specific coverage gap."""
    gap_type: str  # 'missing_day', 'missing_format', 'low_samples', 'missing_ticket_type'
    severity: str  # 'warning', 'error'
    description: str
    details: Dict = field(default_factory=dict)


@dataclass
class CoverageReport:
    """Complete coverage report for a theater."""
    theater_name: str
    circuit_name: Optional[str]

    # What we found
    total_samples: int
    unique_ticket_types: List[str]
    unique_formats: List[str]
    days_with_data: List[int]  # 0=Monday, 6=Sunday
    date_range_start: Optional[date]
    date_range_end: Optional[date]

    # Gaps found
    gaps: List[GapInfo]

    # Summary scores
    day_coverage_pct: float  # 0-100
    format_coverage_pct: float  # 0-100
    overall_coverage_score: float  # 0-100

    # Healthy baselines
    healthy_baselines: List[Dict]  # Baselines with good sample counts


class CoverageGapsService:
    """Service for detecting coverage gaps in price baseline data."""

    # Days of week
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Minimum samples for a "healthy" baseline
    MIN_SAMPLES_HEALTHY = 10
    MIN_SAMPLES_WARNING = 5

    # Common formats we expect to see
    STANDARD_FORMATS = ['Standard', '2D']
    PREMIUM_FORMATS = ['IMAX', 'Dolby Cinema', 'Dolby Atmos', 'ScreenX', '4DX', 'RPX', 'UltraScreen DLX', 'SuperScreen DLX']

    def __init__(self, company_id: int):
        self.company_id = company_id

    def analyze_theater(
        self,
        theater_name: str,
        lookback_days: int = 90,
        include_ent_cache: bool = False
    ) -> CoverageReport:
        """
        Analyze coverage gaps for a specific theater.

        Args:
            theater_name: Name of the theater to analyze
            lookback_days: Days of historical data to consider
            include_ent_cache: Whether to include EntTelligence cache in analysis

        Returns:
            CoverageReport with gaps and healthy baselines
        """
        from sqlalchemy import func, distinct, and_, extract

        with get_session() as session:
            cutoff_date = date.today() - timedelta(days=lookback_days)

            # Get all price data for this theater
            price_data = session.query(
                Showing.format,
                Price.ticket_type,
                extract('dow', Showing.play_date).label('day_of_week'),
                Showing.play_date,
                Price.price,
            ).join(
                Price, Showing.showing_id == Price.showing_id
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date >= cutoff_date
                )
            ).all()

            if not price_data:
                return CoverageReport(
                    theater_name=theater_name,
                    circuit_name=self._get_circuit_name(theater_name),
                    total_samples=0,
                    unique_ticket_types=[],
                    unique_formats=[],
                    days_with_data=[],
                    date_range_start=None,
                    date_range_end=None,
                    gaps=[GapInfo(
                        gap_type='no_data',
                        severity='error',
                        description=f'No price data found for {theater_name} in the last {lookback_days} days'
                    )],
                    day_coverage_pct=0,
                    format_coverage_pct=0,
                    overall_coverage_score=0,
                    healthy_baselines=[]
                )

            # Analyze the data
            formats_seen: Set[str] = set()
            ticket_types_seen: Set[str] = set()
            days_seen: Set[int] = set()
            dates_seen: Set[date] = set()

            # Group data for baseline analysis: (format, ticket_type, day) -> [prices]
            baseline_samples: Dict[Tuple[str, str, int], List[float]] = defaultdict(list)

            for row in price_data:
                fmt = row.format or 'Standard'
                ticket_type = row.ticket_type
                # SQLite returns day_of_week as 0=Sunday, PostgreSQL as 0=Monday
                # Normalize to 0=Monday
                dow = int(row.day_of_week)
                # In SQLite extract('dow', ...) returns 0=Sunday, so we convert
                dow = (dow - 1) % 7 if dow > 0 else 6

                formats_seen.add(fmt)
                ticket_types_seen.add(ticket_type)
                days_seen.add(dow)
                dates_seen.add(row.play_date)

                baseline_samples[(fmt, ticket_type, dow)].append(float(row.price))

            # Calculate metrics
            total_samples = len(price_data)
            unique_formats = sorted(list(formats_seen))
            unique_ticket_types = sorted(list(ticket_types_seen))
            days_with_data = sorted(list(days_seen))
            date_range_start = min(dates_seen) if dates_seen else None
            date_range_end = max(dates_seen) if dates_seen else None

            # Find gaps
            gaps = []
            healthy_baselines = []

            # 1. Missing days
            missing_days = [d for d in range(7) if d not in days_seen]
            for missing_day in missing_days:
                gaps.append(GapInfo(
                    gap_type='missing_day',
                    severity='warning',
                    description=f'No data for {self.DAYS[missing_day]}',
                    details={'day_of_week': missing_day, 'day_name': self.DAYS[missing_day]}
                ))

            # 2. Check each baseline combination for low samples
            for (fmt, ticket_type, dow), prices in baseline_samples.items():
                sample_count = len(prices)
                avg_price = sum(prices) / len(prices) if prices else 0
                variance_pct = (max(prices) - min(prices)) / avg_price * 100 if avg_price > 0 and len(prices) > 1 else 0

                baseline_info = {
                    'format': fmt,
                    'ticket_type': ticket_type,
                    'day_of_week': dow,
                    'day_name': self.DAYS[dow],
                    'sample_count': sample_count,
                    'avg_price': round(avg_price, 2),
                    'variance_pct': round(variance_pct, 1)
                }

                if sample_count < self.MIN_SAMPLES_WARNING:
                    gaps.append(GapInfo(
                        gap_type='low_samples',
                        severity='error' if sample_count < 3 else 'warning',
                        description=f'{ticket_type} / {fmt} on {self.DAYS[dow]}: only {sample_count} samples (need {self.MIN_SAMPLES_HEALTHY}+)',
                        details=baseline_info
                    ))
                else:
                    healthy_baselines.append(baseline_info)

            # 3. Check for missing premium formats (if theater has any premium data)
            has_premium = any(f in self.PREMIUM_FORMATS for f in formats_seen)
            if has_premium:
                # Get expected formats from CompanyProfile if available
                circuit_name = self._get_circuit_name(theater_name)
                expected_formats = self._get_expected_formats(session, circuit_name)

                for expected_format in expected_formats:
                    if expected_format not in formats_seen:
                        gaps.append(GapInfo(
                            gap_type='missing_format',
                            severity='warning',
                            description=f'No data for {expected_format} format (expected based on circuit profile)',
                            details={'format': expected_format, 'circuit': circuit_name}
                        ))

            # Calculate coverage scores
            day_coverage_pct = (len(days_with_data) / 7) * 100

            # Format coverage: consider both standard and premium
            total_expected_formats = len(formats_seen) if formats_seen else 1
            format_coverage_pct = (len([f for f in formats_seen if any(p in baseline_samples for p in baseline_samples.keys() if p[0] == f)]) / total_expected_formats) * 100

            # Overall score: weighted combination
            healthy_ratio = len(healthy_baselines) / max(1, len(baseline_samples))
            overall_coverage_score = (day_coverage_pct * 0.3 + format_coverage_pct * 0.2 + healthy_ratio * 100 * 0.5)

            return CoverageReport(
                theater_name=theater_name,
                circuit_name=self._get_circuit_name(theater_name),
                total_samples=total_samples,
                unique_ticket_types=unique_ticket_types,
                unique_formats=unique_formats,
                days_with_data=days_with_data,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                gaps=gaps,
                day_coverage_pct=round(day_coverage_pct, 1),
                format_coverage_pct=round(format_coverage_pct, 1),
                overall_coverage_score=round(overall_coverage_score, 1),
                healthy_baselines=healthy_baselines
            )

    def analyze_circuit(
        self,
        circuit_name: str,
        lookback_days: int = 90
    ) -> Dict:
        """
        Analyze coverage gaps across all theaters in a circuit.

        Returns aggregated gaps and per-theater breakdown.
        """
        from sqlalchemy import func, distinct

        with get_session() as session:
            # Find all theaters in this circuit
            theaters = session.query(
                distinct(Showing.theater_name)
            ).filter(
                Showing.company_id == self.company_id,
                Showing.theater_name.like(f'{circuit_name}%')
            ).all()

            theater_names = [t[0] for t in theaters]

            theater_reports = []
            total_gaps = 0
            total_healthy = 0

            for theater_name in theater_names:
                report = self.analyze_theater(theater_name, lookback_days)
                theater_reports.append({
                    'theater_name': theater_name,
                    'total_samples': report.total_samples,
                    'gap_count': len(report.gaps),
                    'healthy_count': len(report.healthy_baselines),
                    'coverage_score': report.overall_coverage_score,
                    'gaps': [{'type': g.gap_type, 'severity': g.severity, 'description': g.description} for g in report.gaps]
                })
                total_gaps += len(report.gaps)
                total_healthy += len(report.healthy_baselines)

            return {
                'circuit_name': circuit_name,
                'theater_count': len(theater_names),
                'total_gaps': total_gaps,
                'total_healthy_baselines': total_healthy,
                'avg_coverage_score': sum(r['coverage_score'] for r in theater_reports) / len(theater_reports) if theater_reports else 0,
                'theaters': theater_reports
            }

    def get_all_theater_coverage(
        self,
        lookback_days: int = 90,
        min_samples: int = 1
    ) -> List[Dict]:
        """
        Get coverage summary for all theaters.

        Returns a list of theaters with their coverage scores and gap counts.
        """
        from sqlalchemy import func, distinct

        with get_session() as session:
            # Get all theaters with sample counts
            theaters = session.query(
                Showing.theater_name,
                func.count(Price.price_id).label('sample_count')
            ).join(
                Price, Showing.showing_id == Price.showing_id
            ).filter(
                Showing.company_id == self.company_id,
                Showing.play_date >= date.today() - timedelta(days=lookback_days)
            ).group_by(
                Showing.theater_name
            ).having(
                func.count(Price.price_id) >= min_samples
            ).order_by(
                Showing.theater_name
            ).all()

            results = []
            for theater_name, sample_count in theaters:
                report = self.analyze_theater(theater_name, lookback_days)
                results.append({
                    'theater_name': theater_name,
                    'circuit_name': report.circuit_name,
                    'total_samples': report.total_samples,
                    'gap_count': len(report.gaps),
                    'healthy_count': len(report.healthy_baselines),
                    'coverage_score': report.overall_coverage_score,
                    'day_coverage_pct': report.day_coverage_pct,
                    'days_missing': [self.DAYS[d] for d in range(7) if d not in report.days_with_data],
                    'formats': report.unique_formats,
                    'ticket_types': report.unique_ticket_types
                })

            return results

    def _get_circuit_name(self, theater_name: str) -> Optional[str]:
        """Extract circuit name from theater name (first word typically)."""
        if not theater_name:
            return None

        # Known multi-word circuits
        multi_word = {
            'Movie Tavern': 'Movie Tavern',
            'Studio Movie': 'Studio Movie Grill',
        }

        for prefix, circuit in multi_word.items():
            if theater_name.startswith(prefix):
                return circuit

        # Default: first word
        return theater_name.split()[0] if theater_name else None

    def _get_expected_formats(self, session, circuit_name: Optional[str]) -> List[str]:
        """Get expected formats from company profile."""
        if not circuit_name:
            return []

        profile = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == self.company_id,
            CompanyProfile.circuit_name == circuit_name
        ).first()

        if profile:
            return profile.premium_formats_list

        return []

    def get_markets_hierarchy_coverage(
        self,
        lookback_days: int = 90
    ) -> Dict:
        """
        Get coverage organized by the markets.json hierarchy:
        { company: { director: { market: { stats, theaters: [...] } } } }

        Returns aggregated coverage at each level.
        """
        import json
        import glob
        import os
        from app.config import DATA_DIR

        # Load markets hierarchy
        markets_data = {}
        for market_file in glob.glob(os.path.join(DATA_DIR, '*', 'markets.json')):
            with open(market_file, 'r') as f:
                try:
                    markets_data.update(json.load(f))
                except json.JSONDecodeError:
                    pass

        # Build coverage hierarchy
        result = {}

        for company_name, directors in markets_data.items():
            result[company_name] = {
                'total_theaters': 0,
                'total_gaps': 0,
                'avg_coverage_score': 0,
                'directors': {}
            }

            company_scores = []

            for director_name, markets in directors.items():
                result[company_name]['directors'][director_name] = {
                    'total_theaters': 0,
                    'total_gaps': 0,
                    'avg_coverage_score': 0,
                    'markets': {}
                }

                director_scores = []

                for market_name, market_data in markets.items():
                    theaters = market_data.get('theaters', [])
                    theater_names = [t.get('name') for t in theaters if t.get('name')]

                    market_result = {
                        'total_theaters': len(theater_names),
                        'total_gaps': 0,
                        'total_samples': 0,
                        'avg_coverage_score': 0,
                        'theaters_with_gaps': 0,
                        'theaters': []
                    }

                    market_scores = []

                    for theater_name in theater_names:
                        try:
                            report = self.analyze_theater(theater_name, lookback_days)
                            theater_info = {
                                'theater_name': theater_name,
                                'total_samples': report.total_samples,
                                'gap_count': len(report.gaps),
                                'healthy_count': len(report.healthy_baselines),
                                'coverage_score': report.overall_coverage_score,
                                'day_coverage_pct': report.day_coverage_pct,
                                'days_missing': [self.DAYS[d] for d in range(7) if d not in report.days_with_data],
                                'formats': report.unique_formats
                            }
                            market_result['theaters'].append(theater_info)
                            market_result['total_gaps'] += len(report.gaps)
                            market_result['total_samples'] += report.total_samples
                            if len(report.gaps) > 0:
                                market_result['theaters_with_gaps'] += 1
                            market_scores.append(report.overall_coverage_score)
                        except Exception as e:
                            logger.warning(f"Error analyzing theater {theater_name}: {e}")
                            market_result['theaters'].append({
                                'theater_name': theater_name,
                                'total_samples': 0,
                                'gap_count': 1,
                                'healthy_count': 0,
                                'coverage_score': 0,
                                'day_coverage_pct': 0,
                                'days_missing': self.DAYS.copy(),
                                'formats': [],
                                'error': str(e)
                            })

                    market_result['avg_coverage_score'] = sum(market_scores) / len(market_scores) if market_scores else 0
                    result[company_name]['directors'][director_name]['markets'][market_name] = market_result

                    # Aggregate to director level
                    result[company_name]['directors'][director_name]['total_theaters'] += market_result['total_theaters']
                    result[company_name]['directors'][director_name]['total_gaps'] += market_result['total_gaps']
                    director_scores.extend(market_scores)

                result[company_name]['directors'][director_name]['avg_coverage_score'] = (
                    sum(director_scores) / len(director_scores) if director_scores else 0
                )

                # Aggregate to company level
                result[company_name]['total_theaters'] += result[company_name]['directors'][director_name]['total_theaters']
                result[company_name]['total_gaps'] += result[company_name]['directors'][director_name]['total_gaps']
                company_scores.extend(director_scores)

            result[company_name]['avg_coverage_score'] = sum(company_scores) / len(company_scores) if company_scores else 0

        return result

    def get_market_coverage(
        self,
        director_name: str,
        market_name: str,
        lookback_days: int = 90
    ) -> Dict:
        """
        Get coverage for a specific market within a director's territory.
        """
        import json
        import glob
        import os
        from app.config import DATA_DIR

        # Load markets hierarchy
        for market_file in glob.glob(os.path.join(DATA_DIR, '*', 'markets.json')):
            with open(market_file, 'r') as f:
                try:
                    markets_data = json.load(f)
                    for company_name, directors in markets_data.items():
                        if director_name in directors:
                            if market_name in directors[director_name]:
                                market_data = directors[director_name][market_name]
                                theaters = market_data.get('theaters', [])
                                theater_names = [t.get('name') for t in theaters if t.get('name')]

                                result = {
                                    'market_name': market_name,
                                    'director_name': director_name,
                                    'company_name': company_name,
                                    'total_theaters': len(theater_names),
                                    'total_gaps': 0,
                                    'total_samples': 0,
                                    'avg_coverage_score': 0,
                                    'theaters_with_gaps': 0,
                                    'theaters': []
                                }

                                scores = []
                                for theater_name in theater_names:
                                    try:
                                        report = self.analyze_theater(theater_name, lookback_days)
                                        theater_info = {
                                            'theater_name': theater_name,
                                            'total_samples': report.total_samples,
                                            'gap_count': len(report.gaps),
                                            'healthy_count': len(report.healthy_baselines),
                                            'coverage_score': report.overall_coverage_score,
                                            'day_coverage_pct': report.day_coverage_pct,
                                            'days_missing': [self.DAYS[d] for d in range(7) if d not in report.days_with_data],
                                            'formats': report.unique_formats,
                                            'gaps': [{'type': g.gap_type, 'severity': g.severity, 'description': g.description} for g in report.gaps]
                                        }
                                        result['theaters'].append(theater_info)
                                        result['total_gaps'] += len(report.gaps)
                                        result['total_samples'] += report.total_samples
                                        if len(report.gaps) > 0:
                                            result['theaters_with_gaps'] += 1
                                        scores.append(report.overall_coverage_score)
                                    except Exception as e:
                                        logger.warning(f"Error analyzing theater {theater_name}: {e}")

                                result['avg_coverage_score'] = sum(scores) / len(scores) if scores else 0
                                return result
                except json.JSONDecodeError:
                    pass

        return {'error': f'Market not found: {director_name}/{market_name}'}
