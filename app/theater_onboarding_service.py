"""
Theater Onboarding Service

Manages the 5-step onboarding workflow for new theaters into the baseline system:
1. Add to market (step_market_added)
2. Initial price collection (step_initial_scrape)
3. Baseline discovery (step_baseline_discovered)
4. Link to company profile (step_profile_linked)
5. Review and confirm baselines (step_baseline_confirmed)

Usage:
    from app.theater_onboarding_service import TheaterOnboardingService

    service = TheaterOnboardingService(session, company_id)
    status = service.start_onboarding('Marcus Majestic Cinema', 'Marcus', 'Milwaukee')
    service.complete_step(status.theater_name, 'scrape', source='enttelligence', count=150)
"""

from datetime import datetime, date, UTC
from decimal import Decimal
from typing import Optional, List, Dict, Any
import json

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.db_models import (
    TheaterOnboardingStatus, PriceBaseline, CompanyProfile,
    EntTelligencePriceCache, TheaterMetadata, Showing, TheaterAmenities
)
from app.simplified_baseline_service import SimplifiedBaselineService, KNOWN_CIRCUITS
from app.theater_amenity_discovery import TheaterAmenityDiscoveryService


class TheaterOnboardingService:
    """
    Service for managing theater onboarding into the baseline system.

    Tracks progress through 5 steps and provides coverage indicators
    to help users understand when theaters are fully onboarded.
    """

    def __init__(self, session: Session, company_id: int):
        self.session = session
        self.company_id = company_id
        self.baseline_service = SimplifiedBaselineService(session, company_id)

    def get_or_create_status(self, theater_name: str) -> TheaterOnboardingStatus:
        """Get existing status or create new one for a theater."""
        status = self.session.query(TheaterOnboardingStatus).filter(
            TheaterOnboardingStatus.company_id == self.company_id,
            TheaterOnboardingStatus.theater_name == theater_name
        ).first()

        if not status:
            status = TheaterOnboardingStatus(
                company_id=self.company_id,
                theater_name=theater_name,
                onboarding_status='not_started'
            )
            self.session.add(status)
            self.session.flush()

        return status

    def start_onboarding(
        self,
        theater_name: str,
        circuit_name: Optional[str] = None,
        market: Optional[str] = None
    ) -> TheaterOnboardingStatus:
        """
        Start the onboarding process for a new theater.

        This completes Step 1 (add to market) and initializes tracking.

        Args:
            theater_name: Name of the theater
            circuit_name: Circuit/chain name (e.g., 'Marcus', 'AMC')
            market: Market name (e.g., 'Milwaukee', 'Chicago')

        Returns:
            TheaterOnboardingStatus object
        """
        status = self.get_or_create_status(theater_name)

        # Detect circuit if not provided
        if not circuit_name:
            circuit_name = self._detect_circuit(theater_name)

        status.circuit_name = circuit_name
        status.market = market
        status.step_market_added = True
        status.step_market_added_at = datetime.now(UTC)
        status.onboarding_status = 'in_progress'
        status.last_updated_at = datetime.now(UTC)

        self.session.commit()
        return status

    def _detect_circuit(self, theater_name: str) -> Optional[str]:
        """Detect circuit name from theater name."""
        theater_lower = theater_name.lower()
        for circuit in KNOWN_CIRCUITS:
            if theater_lower.startswith(circuit.lower()):
                return circuit
        return None

    def record_initial_scrape(
        self,
        theater_name: str,
        source: str,
        count: int,
        discover_amenities: bool = True
    ) -> TheaterOnboardingStatus:
        """
        Record that initial price collection has been completed.

        Also discovers theater amenities (formats, screen counts) from showings data.

        Args:
            theater_name: Name of the theater
            source: Data source ('fandango' or 'enttelligence')
            count: Number of price records collected
            discover_amenities: Whether to auto-discover amenities (default True)

        Returns:
            Updated TheaterOnboardingStatus
        """
        status = self.get_or_create_status(theater_name)

        status.step_initial_scrape = True
        status.step_initial_scrape_at = datetime.now(UTC)
        status.step_initial_scrape_source = source
        status.step_initial_scrape_count = count
        status.last_updated_at = datetime.now(UTC)

        if status.onboarding_status == 'not_started':
            status.onboarding_status = 'in_progress'

        # Auto-discover theater amenities from showings data
        if discover_amenities:
            try:
                amenity_service = TheaterAmenityDiscoveryService(self.company_id)
                amenity_service.update_theater_amenities(
                    theater_name,
                    circuit_name=status.circuit_name,
                    lookback_days=30
                )
            except Exception as e:
                # Don't fail the scrape recording if amenity discovery fails
                import logging
                logging.getLogger(__name__).warning(
                    f"Amenity discovery failed for {theater_name}: {e}"
                )

        self.session.commit()
        return status

    def discover_baselines(
        self,
        theater_name: str,
        lookback_days: int = 30,
        min_samples: int = 5
    ) -> Dict[str, Any]:
        """
        Discover baselines for a theater from collected price data.

        This uses the SimplifiedBaselineService to discover baselines
        without day_of_week granularity.

        Args:
            theater_name: Name of the theater
            lookback_days: Days to look back for price data
            min_samples: Minimum samples required per baseline

        Returns:
            Dictionary with discovery results
        """
        status = self.get_or_create_status(theater_name)

        # Discover baselines using simplified service
        discovered = self.baseline_service.discover_simplified_baselines(
            [theater_name],
            lookback_days=lookback_days,
            min_samples=min_samples,
            source=status.step_initial_scrape_source or 'enttelligence'
        )

        if not discovered:
            return {
                'success': False,
                'message': 'No baselines discovered - insufficient price data',
                'baselines_created': 0
            }

        # Create baselines
        baselines_created = 0
        formats_discovered = set()
        ticket_types_discovered = set()
        dayparts_discovered = set()

        for d in discovered:
            # Check if baseline already exists
            existing = self.session.query(PriceBaseline).filter(
                PriceBaseline.company_id == self.company_id,
                PriceBaseline.theater_name == d['theater_name'],
                PriceBaseline.ticket_type == d['ticket_type'],
                PriceBaseline.format == d.get('format'),
                PriceBaseline.daypart == d.get('daypart'),
                or_(
                    PriceBaseline.effective_to.is_(None),
                    PriceBaseline.effective_to >= date.today()
                )
            ).first()

            if not existing:
                baseline = PriceBaseline(
                    company_id=self.company_id,
                    theater_name=d['theater_name'],
                    ticket_type=d['ticket_type'],
                    format=d.get('format'),
                    daypart=d.get('daypart'),
                    baseline_price=Decimal(str(d['baseline_price'])),
                    effective_from=date.today(),
                    source=d['source'],
                    tax_status=d['tax_status'],
                    sample_count=d['sample_count'],
                    last_discovery_at=datetime.now(UTC)
                )
                self.session.add(baseline)
                baselines_created += 1

            # Track discovered dimensions
            if d.get('format'):
                formats_discovered.add(d['format'])
            if d.get('ticket_type'):
                ticket_types_discovered.add(d['ticket_type'])
            if d.get('daypart'):
                dayparts_discovered.add(d['daypart'])

        # Update status
        status.step_baseline_discovered = True
        status.step_baseline_discovered_at = datetime.now(UTC)
        status.step_baseline_count = baselines_created
        status.formats_discovered_list = list(formats_discovered)
        status.ticket_types_discovered_list = list(ticket_types_discovered)
        status.dayparts_discovered_list = list(dayparts_discovered)
        status.last_updated_at = datetime.now(UTC)

        # Calculate coverage score
        coverage = self.baseline_service.get_coverage_indicators(theater_name)
        status.coverage_score = Decimal(str(coverage['overall_score']))

        self.session.commit()

        return {
            'success': True,
            'baselines_created': baselines_created,
            'formats_discovered': list(formats_discovered),
            'ticket_types_discovered': list(ticket_types_discovered),
            'dayparts_discovered': list(dayparts_discovered),
            'coverage_score': coverage['overall_score'],
            'gaps': coverage['gaps']
        }

    def link_to_profile(
        self,
        theater_name: str,
        circuit_name: Optional[str] = None
    ) -> TheaterOnboardingStatus:
        """
        Link a theater to a company profile.

        If no profile exists for the circuit, one will be created.

        Args:
            theater_name: Name of the theater
            circuit_name: Circuit name (auto-detected if not provided)

        Returns:
            Updated TheaterOnboardingStatus
        """
        status = self.get_or_create_status(theater_name)

        # Use status circuit or detect
        circuit = circuit_name or status.circuit_name or self._detect_circuit(theater_name)
        if not circuit:
            raise ValueError(f"Cannot determine circuit for theater: {theater_name}")

        # Find or create profile
        profile = self.session.query(CompanyProfile).filter(
            CompanyProfile.company_id == self.company_id,
            CompanyProfile.circuit_name == circuit,
            CompanyProfile.is_current == True
        ).first()

        if not profile:
            # Create new profile
            profile = CompanyProfile(
                company_id=self.company_id,
                circuit_name=circuit,
                version=1,
                is_current=True,
                discovered_at=datetime.now(UTC),
                theater_count=1,
                sample_count=status.step_initial_scrape_count or 0
            )
            self.session.add(profile)
            self.session.flush()
        else:
            # Update theater count
            profile.theater_count = (profile.theater_count or 0) + 1
            profile.last_updated_at = datetime.now(UTC)

        status.step_profile_linked = True
        status.step_profile_linked_at = datetime.now(UTC)
        status.step_profile_id = profile.profile_id
        status.circuit_name = circuit
        status.last_updated_at = datetime.now(UTC)

        self.session.commit()
        return status

    def confirm_baselines(
        self,
        theater_name: str,
        user_id: int,
        notes: Optional[str] = None
    ) -> TheaterOnboardingStatus:
        """
        Confirm baselines after user review.

        This completes the onboarding process for the theater.

        Args:
            theater_name: Name of the theater
            user_id: ID of the user confirming
            notes: Optional notes about the confirmation

        Returns:
            Updated TheaterOnboardingStatus
        """
        status = self.get_or_create_status(theater_name)

        status.step_baseline_confirmed = True
        status.step_baseline_confirmed_at = datetime.now(UTC)
        status.step_baseline_confirmed_by = user_id
        status.onboarding_status = 'complete'
        status.last_updated_at = datetime.now(UTC)

        if notes:
            status.notes = notes

        self.session.commit()
        return status

    def get_onboarding_status(self, theater_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed onboarding status for a theater.

        Returns:
            Dictionary with status details or None if not found
        """
        status = self.session.query(TheaterOnboardingStatus).filter(
            TheaterOnboardingStatus.company_id == self.company_id,
            TheaterOnboardingStatus.theater_name == theater_name
        ).first()

        if not status:
            return None

        return {
            'theater_name': status.theater_name,
            'circuit_name': status.circuit_name,
            'market': status.market,
            'onboarding_status': status.onboarding_status,
            'progress_percent': status.progress_percent,
            'completed_steps': status.completed_steps,
            'total_steps': status.total_steps,
            'steps': {
                'market_added': {
                    'completed': status.step_market_added,
                    'timestamp': status.step_market_added_at.isoformat() if status.step_market_added_at else None
                },
                'initial_scrape': {
                    'completed': status.step_initial_scrape,
                    'timestamp': status.step_initial_scrape_at.isoformat() if status.step_initial_scrape_at else None,
                    'source': status.step_initial_scrape_source,
                    'count': status.step_initial_scrape_count
                },
                'baseline_discovered': {
                    'completed': status.step_baseline_discovered,
                    'timestamp': status.step_baseline_discovered_at.isoformat() if status.step_baseline_discovered_at else None,
                    'count': status.step_baseline_count
                },
                'profile_linked': {
                    'completed': status.step_profile_linked,
                    'timestamp': status.step_profile_linked_at.isoformat() if status.step_profile_linked_at else None,
                    'profile_id': status.step_profile_id
                },
                'baseline_confirmed': {
                    'completed': status.step_baseline_confirmed,
                    'timestamp': status.step_baseline_confirmed_at.isoformat() if status.step_baseline_confirmed_at else None,
                    'confirmed_by': status.step_baseline_confirmed_by
                }
            },
            'coverage': {
                'formats_discovered': status.formats_discovered_list,
                'ticket_types_discovered': status.ticket_types_discovered_list,
                'dayparts_discovered': status.dayparts_discovered_list,
                'score': float(status.coverage_score) if status.coverage_score else 0.0
            },
            'notes': status.notes,
            'last_updated_at': status.last_updated_at.isoformat() if status.last_updated_at else None
        }

    def list_pending_theaters(self) -> List[Dict[str, Any]]:
        """
        List all theaters with incomplete onboarding.

        Returns:
            List of theater status dictionaries
        """
        pending = self.session.query(TheaterOnboardingStatus).filter(
            TheaterOnboardingStatus.company_id == self.company_id,
            TheaterOnboardingStatus.onboarding_status != 'complete'
        ).order_by(
            TheaterOnboardingStatus.last_updated_at.desc()
        ).all()

        return [
            {
                'theater_name': s.theater_name,
                'circuit_name': s.circuit_name,
                'market': s.market,
                'onboarding_status': s.onboarding_status,
                'progress_percent': s.progress_percent,
                'next_step': self._get_next_step(s),
                'last_updated_at': s.last_updated_at.isoformat() if s.last_updated_at else None
            }
            for s in pending
        ]

    def _get_next_step(self, status: TheaterOnboardingStatus) -> str:
        """Determine the next step for a theater."""
        if not status.step_market_added:
            return 'market_added'
        if not status.step_initial_scrape:
            return 'initial_scrape'
        if not status.step_baseline_discovered:
            return 'discover_baselines'
        if not status.step_profile_linked:
            return 'link_profile'
        if not status.step_baseline_confirmed:
            return 'confirm_baselines'
        return 'complete'

    def get_coverage_indicators(self, theater_name: str) -> Dict[str, Any]:
        """
        Get detailed coverage indicators for a theater.

        Delegates to SimplifiedBaselineService.
        """
        return self.baseline_service.get_coverage_indicators(theater_name)

    def list_theaters_by_market(self, market: str) -> List[Dict[str, Any]]:
        """
        List all theaters in a market with their onboarding status.
        """
        statuses = self.session.query(TheaterOnboardingStatus).filter(
            TheaterOnboardingStatus.company_id == self.company_id,
            TheaterOnboardingStatus.market == market
        ).all()

        return [
            {
                'theater_name': s.theater_name,
                'circuit_name': s.circuit_name,
                'onboarding_status': s.onboarding_status,
                'progress_percent': s.progress_percent,
                'coverage_score': float(s.coverage_score) if s.coverage_score else 0.0
            }
            for s in statuses
        ]

    def bulk_start_onboarding(
        self,
        theaters: List[Dict[str, Any]],
        market: str
    ) -> List[TheaterOnboardingStatus]:
        """
        Start onboarding for multiple theaters at once.

        Args:
            theaters: List of dicts with 'name' and optional 'circuit' keys
            market: Market name for all theaters

        Returns:
            List of created TheaterOnboardingStatus objects
        """
        statuses = []
        for theater in theaters:
            status = self.start_onboarding(
                theater_name=theater['name'],
                circuit_name=theater.get('circuit'),
                market=market
            )
            statuses.append(status)

        return statuses

    # =========================================================================
    # AMENITY DISCOVERY & BACKFILL
    # =========================================================================

    def discover_theater_amenities(
        self,
        theater_name: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Discover amenities for a specific theater from showings data.

        Args:
            theater_name: Name of the theater
            lookback_days: Days of showings data to analyze

        Returns:
            Dictionary with discovery results
        """
        status = self.get_or_create_status(theater_name)

        amenity_service = TheaterAmenityDiscoveryService(self.company_id)

        # Discover formats
        formats = amenity_service.discover_theater_formats(theater_name, lookback_days)

        # Estimate screen counts
        screen_counts = amenity_service.estimate_screen_counts(
            theater_name, lookback_days=lookback_days
        )

        # Update amenities record
        amenities = amenity_service.update_theater_amenities(
            theater_name,
            circuit_name=status.circuit_name,
            lookback_days=lookback_days
        )

        return {
            'theater_name': theater_name,
            'formats_discovered': formats,
            'screen_counts': screen_counts,
            'amenities_updated': amenities is not None,
            'amenity_id': amenities.id if amenities else None
        }

    def backfill_amenities_for_existing_theaters(
        self,
        circuit_name: Optional[str] = None,
        market: Optional[str] = None,
        lookback_days: int = 30,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Discover and populate amenities for all existing theaters with showings data.

        This is a backfill operation for theaters that were scraped before
        amenity discovery was integrated into onboarding.

        Args:
            circuit_name: Optional circuit filter
            market: Optional market filter
            lookback_days: Days of showings data to analyze
            force_refresh: If True, refresh existing amenities records (not just missing ones)

        Returns:
            Dictionary with backfill results
        """
        from datetime import timedelta
        from sqlalchemy import distinct

        cutoff_date = date.today() - timedelta(days=lookback_days)

        # Find all theaters with showings data
        query = self.session.query(distinct(Showing.theater_name)).filter(
            Showing.company_id == self.company_id,
            Showing.play_date >= cutoff_date
        )

        # Apply circuit filter if provided
        if circuit_name:
            query = query.filter(Showing.theater_name.ilike(f"%{circuit_name}%"))

        theaters_with_showings = [r[0] for r in query.all()]

        # Filter by market if provided (need onboarding status)
        if market:
            market_theaters = []
            for theater in theaters_with_showings:
                status = self.session.query(TheaterOnboardingStatus).filter(
                    TheaterOnboardingStatus.company_id == self.company_id,
                    TheaterOnboardingStatus.theater_name == theater,
                    TheaterOnboardingStatus.market == market
                ).first()
                if status:
                    market_theaters.append(theater)
            theaters_with_showings = market_theaters

        # Find theaters missing amenities (or all theaters if force_refresh)
        theaters_needing_amenities = []
        for theater in theaters_with_showings:
            existing = self.session.query(TheaterAmenities).filter(
                TheaterAmenities.company_id == self.company_id,
                TheaterAmenities.theater_name == theater
            ).first()
            if not existing or force_refresh:
                theaters_needing_amenities.append(theater)

        # Discover amenities for each
        results = {
            'theaters_checked': len(theaters_with_showings),
            'theaters_needing_amenities': len(theaters_needing_amenities),
            'theaters_updated': 0,
            'theaters_failed': 0,
            'details': []
        }

        amenity_service = TheaterAmenityDiscoveryService(self.company_id)

        for theater in theaters_needing_amenities:
            try:
                # Get or create onboarding status to capture circuit
                status = self.get_or_create_status(theater)

                amenities = amenity_service.update_theater_amenities(
                    theater,
                    circuit_name=status.circuit_name,
                    lookback_days=lookback_days
                )

                results['theaters_updated'] += 1
                results['details'].append({
                    'theater': theater,
                    'success': True,
                    'has_imax': amenities.has_imax if amenities else None,
                    'has_dolby': amenities.has_dolby_cinema if amenities else None,
                    'screen_count': amenities.screen_count if amenities else None,
                    'imax_screens': amenities.imax_screen_count if amenities else None,
                    'dolby_screens': amenities.dolby_screen_count if amenities else None,
                    'circuit_plf': amenities.get_circuit_plf() if amenities else None,
                })
            except Exception as e:
                results['theaters_failed'] += 1
                results['details'].append({
                    'theater': theater,
                    'success': False,
                    'error': str(e)
                })

        return results

    def get_theaters_missing_amenities(
        self,
        circuit_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List theaters that have showings data but no amenities record.

        Args:
            circuit_name: Optional circuit filter

        Returns:
            List of theaters needing amenity discovery
        """
        from datetime import timedelta
        from sqlalchemy import distinct

        cutoff_date = date.today() - timedelta(days=30)

        # Find theaters with recent showings
        query = self.session.query(
            Showing.theater_name,
            func.count(Showing.showing_id).label('showing_count'),
            func.count(distinct(Showing.format)).label('format_count')
        ).filter(
            Showing.company_id == self.company_id,
            Showing.play_date >= cutoff_date
        ).group_by(Showing.theater_name)

        if circuit_name:
            query = query.filter(Showing.theater_name.ilike(f"%{circuit_name}%"))

        theater_stats = query.all()

        # Find which have amenities
        results = []
        for theater_name, showing_count, format_count in theater_stats:
            existing = self.session.query(TheaterAmenities).filter(
                TheaterAmenities.company_id == self.company_id,
                TheaterAmenities.theater_name == theater_name
            ).first()

            if not existing:
                # Get onboarding status for additional context
                status = self.session.query(TheaterOnboardingStatus).filter(
                    TheaterOnboardingStatus.company_id == self.company_id,
                    TheaterOnboardingStatus.theater_name == theater_name
                ).first()

                results.append({
                    'theater_name': theater_name,
                    'circuit_name': status.circuit_name if status else self._detect_circuit(theater_name),
                    'market': status.market if status else None,
                    'showing_count': showing_count,
                    'format_count': format_count,
                    'onboarding_status': status.onboarding_status if status else 'unknown'
                })

        return sorted(results, key=lambda x: x['showing_count'], reverse=True)
