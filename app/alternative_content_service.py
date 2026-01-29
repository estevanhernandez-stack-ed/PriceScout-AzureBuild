"""
Alternative Content Detection Service

Detects and classifies Alternative Content (special events) films:
- Fathom Events (classic films, documentaries, anime)
- Opera broadcasts (Met Opera, Royal Opera)
- Theater broadcasts (NT Live, Broadway HD)
- Concert films
- Anime events (Ghibli Fest, Crunchyroll)
- Sports events
- Classic re-releases
- Indian cinema (Telugu, Tamil, Hindi, Malayalam, etc.)

Detection methods:
1. Title-based: Pattern matching on film titles
2. Ticket type-based: Presence of "AC" ticket types
3. Price-based: High prices on standard formats
"""

import re
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.db_models import (
    AlternativeContentFilm, CircuitACPricing,
    Showing, Price, PriceBaseline, Film
)

logger = logging.getLogger(__name__)


# ============================================================================
# DETECTION PATTERNS
# ============================================================================

# Title patterns for content type detection
CONTENT_TYPE_PATTERNS = {
    'fathom_event': [
        r'\bfathom\b',
        r'\(fathom events?\)',
        r'fathom presents',
    ],
    'opera_broadcast': [
        r'\bmet opera\b',
        r'metropolitan opera',
        r'\broyal opera\b',
        r'\bopera\b.*\blive\b',
        # Common opera titles
        r'\bla traviata\b',
        r'\bcarmen\b',
        r'\btosca\b',
        r'\brigoletto\b',
        r'\bla boheme\b',
        r'\bmadama butterfly\b',
        r'\bthe magic flute\b',
        r'\bturandot\b',
        r'\baida\b',
        r'\bdon giovanni\b',
    ],
    'theater_broadcast': [
        r'\bnt live\b',
        r'national theatre live',
        r'\bbroadway hd\b',
        r'great performances',
        r'bolshoi ballet',
        r'royal ballet',
    ],
    'concert_film': [
        r'\bin concert\b',
        r'\bconcert film\b',
        r'\btour\b.*\bfilm\b',
        r'\beras tour\b',
        r'\brenaissance\b.*\btour\b',
        r'\blive from\b',
        r'\blive at\b',
    ],
    'anime_event': [
        r'\bghibli\b',
        r'ghibli fest',
        r'\bcrunchyroll\b',
        r'\bfunimation\b',
        r'\banime\b',
        r'\(subbed\)',
        r'\(dubbed\)',
        r'japanese animation',
        # Popular anime films
        r'\bdragon ball\b',
        r'\bnaruto\b',
        r'\bmy hero academia\b',
        r'\bdemon slayer\b',
        r'\bjujutsu kaisen\b',
        r'\bone piece\b',
    ],
    'sports_event': [
        r'\bnfl\b',
        r'\bwwe\b',
        r'\bufc\b',
        r'\bboxing\b',
        r'\bwrestlemania\b',
        r'sunday ticket',
        r'\besports\b',
    ],
    'classic_rerelease': [
        r'\d{2}th anniversary',
        r'\d{2}th anniversary',
        r'anniversary edition',
        r'\bremaster(ed)?\b',
        r'\bre-?release\b',
        r"director'?s cut",
        r'extended edition',
        r'special edition',
        r'\bclassic\b.*\bpresentation\b',
        r'\brestored\b',
        r'\b4k\b.*\brestoration\b',
    ],
    'marathon': [
        r'\bmarathon\b',
        r'\bdouble feature\b',
        r'\btriple feature\b',
        r'\btrilogy\b',
        r'\ball[- ]?day\b',
    ],
    'special_presentation': [
        r'special presentation',
        r'\bq\s*&\s*a\b',
        r'\bpremiere\b',
        r'advance screening',
        r'early access',
        r'fan event',
        r'sneak peek',
        r'opening night',
        r'imax experience',
        r'one night only',
        r'limited engagement',
    ],
    # Indian cinema (Telugu, Tamil, Hindi, etc.) - conservative patterns
    # Only match explicit language indicators or highly distinctive title patterns
    'indian_cinema': [
        # Explicit language tags in title (most reliable)
        r'\(telugu\)',
        r'\(tamil\)',
        r'\(hindi\)',
        r'\(malayalam\)',
        r'\(kannada\)',
        r'\(bengali\)',
        r'\(marathi\)',
        r'\(punjabi\)',
        r'\(gujarati\)',
        # Common Telugu title patterns (distinctive words)
        r'\boka\b.*\braju\b',           # "Oka Raju" pattern
        r'\banaganaga\b',               # "Anaganaga" (Once upon a time)
        r'\bchatha pacha\b',            # Known film
        r'\browdies\b',                 # Common in South Indian action films
        # Bollywood/Hindi distinctive patterns
        r'\byash raj\b',                # Yash Raj Films
        r'\bdharma\b.*\bproductions?\b',
        # South Indian action title patterns (high confidence)
        r'\bpushpa\b',
        r'\brrr\b',
        r'\bkalki\b',
        r'\bsalaar\b',
        r'\bdevara\b',
        r'\bkgf\b',
        # Telugu/Tamil suffix patterns (with word boundary to avoid false positives)
        r'\bpacha\b',                   # Common in Malayalam
    ],
}

# Keywords that indicate alternative content in ticket types
AC_TICKET_TYPE_KEYWORDS = [
    'ac ',
    ' ac',
    'alternative content',
    'event',
    'fathom',
    'special',
]

# Price threshold - films priced at or above this on standard 2D are likely AC
AC_PRICE_THRESHOLD = Decimal('15.00')


# ============================================================================
# DETECTION FUNCTIONS
# ============================================================================

def detect_content_type_from_title(title: str) -> Tuple[Optional[str], float, str]:
    """
    Detect content type from film title using pattern matching.

    Returns:
        Tuple of (content_type, confidence, reason)
        Returns (None, 0, '') if no match
    """
    title_lower = title.lower()

    for content_type, patterns in CONTENT_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return (
                    content_type,
                    0.85,  # High confidence for title match
                    f"Title matches pattern: {pattern}"
                )

    return (None, 0.0, '')


def detect_ac_from_ticket_type(ticket_type: str) -> bool:
    """Check if a ticket type indicates Alternative Content."""
    ticket_lower = ticket_type.lower()
    return any(kw in ticket_lower for kw in AC_TICKET_TYPE_KEYWORDS)


def get_content_source_from_title(title: str, content_type: str) -> Optional[str]:
    """Extract the content source (e.g., 'Fathom Events', 'Met Opera') from title."""
    title_lower = title.lower()

    if content_type == 'fathom_event':
        if 'fathom' in title_lower:
            return 'Fathom Events'
    elif content_type == 'opera_broadcast':
        if 'met opera' in title_lower or 'metropolitan opera' in title_lower:
            return 'Met Opera'
        if 'royal opera' in title_lower:
            return 'Royal Opera House'
    elif content_type == 'theater_broadcast':
        if 'nt live' in title_lower or 'national theatre' in title_lower:
            return 'National Theatre Live'
        if 'broadway' in title_lower:
            return 'Broadway HD'
    elif content_type == 'anime_event':
        if 'ghibli' in title_lower:
            return 'Studio Ghibli'
        if 'crunchyroll' in title_lower:
            return 'Crunchyroll'
        if 'funimation' in title_lower:
            return 'Funimation'
    elif content_type == 'indian_cinema':
        # Detect language/region from title
        if '(telugu)' in title_lower or 'anaganaga' in title_lower or 'oka' in title_lower:
            return 'Telugu Cinema'
        if '(tamil)' in title_lower:
            return 'Tamil Cinema'
        if '(hindi)' in title_lower or 'yash raj' in title_lower or 'dharma' in title_lower:
            return 'Bollywood'
        if '(malayalam)' in title_lower or 'pacha' in title_lower:
            return 'Malayalam Cinema'
        if '(kannada)' in title_lower:
            return 'Kannada Cinema'
        return 'Indian Cinema'  # Generic fallback

    return None


def normalize_title(title: str) -> str:
    """Normalize a film title for matching purposes."""
    # Remove common suffixes and qualifiers
    normalized = title.lower()

    # Remove content in parentheses
    normalized = re.sub(r'\([^)]*\)', '', normalized)

    # Remove common event qualifiers
    remove_patterns = [
        r'\bfathom events?\b',
        r'\bmet opera:?\b',
        r'\bnt live:?\b',
        r'\banniversary\b',
        r'\bremaster(ed)?\b',
        r'\bre-?release\b',
        r"director'?s cut",
        r'\bspecial presentation\b',
        r'\bin concert\b',
        r'\blive\b',
        r'\bsubbed\b',
        r'\bdubbed\b',
    ]

    for pattern in remove_patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Clean up whitespace
    normalized = ' '.join(normalized.split())
    normalized = normalized.strip(' -:')

    return normalized


class AlternativeContentService:
    """Service for detecting and managing Alternative Content films."""

    def __init__(self, session: Session, company_id: int = 1):
        self.session = session
        self.company_id = company_id

    def detect_ac_films_from_showings(
        self,
        lookback_days: int = 30,
        min_confidence: float = 0.5
    ) -> List[Dict]:
        """
        Scan recent showings to detect Alternative Content films.

        Returns list of detected films with their classification.
        """
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)

        # Get distinct films from recent showings
        films = self.session.query(
            Showing.film_title,
            func.min(Showing.play_date).label('first_seen'),
            func.max(Showing.play_date).label('last_seen'),
            func.count(Showing.showing_id).label('showing_count')
        ).filter(
            Showing.company_id == self.company_id,
            Showing.play_date >= cutoff_date
        ).group_by(
            Showing.film_title
        ).all()

        detected = []

        for film in films:
            # Try title-based detection
            content_type, confidence, reason = detect_content_type_from_title(film.film_title)

            if content_type and confidence >= min_confidence:
                detected.append({
                    'film_title': film.film_title,
                    'normalized_title': normalize_title(film.film_title),
                    'content_type': content_type,
                    'content_source': get_content_source_from_title(film.film_title, content_type),
                    'detected_by': 'auto_title',
                    'detection_confidence': confidence,
                    'detection_reason': reason,
                    'first_seen': film.first_seen,
                    'last_seen': film.last_seen,
                    'occurrence_count': film.showing_count,
                })

        return detected

    def detect_ac_from_ticket_types(self, lookback_days: int = 30) -> List[Dict]:
        """
        Find films that have AC ticket types in their pricing.

        This catches films where the scraper captured AC-specific ticket types
        like 'AC Loyalty Member'.
        """
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)

        # Find showings with AC ticket types
        ac_showings = self.session.query(
            Showing.film_title,
            Price.ticket_type,
            func.count(Price.price_id).label('price_count')
        ).join(
            Price, Price.showing_id == Showing.showing_id
        ).filter(
            Showing.company_id == self.company_id,
            Showing.play_date >= cutoff_date,
            or_(
                Price.ticket_type.ilike('%ac %'),
                Price.ticket_type.ilike('% ac'),
                Price.ticket_type.ilike('%ac loyalty%'),
                Price.ticket_type.ilike('%alternative%'),
                Price.ticket_type.ilike('%event%'),
            )
        ).group_by(
            Showing.film_title,
            Price.ticket_type
        ).all()

        # Group by film
        films_with_ac = {}
        for showing in ac_showings:
            if showing.film_title not in films_with_ac:
                films_with_ac[showing.film_title] = {
                    'film_title': showing.film_title,
                    'ac_ticket_types': [],
                    'price_count': 0,
                }
            films_with_ac[showing.film_title]['ac_ticket_types'].append(showing.ticket_type)
            films_with_ac[showing.film_title]['price_count'] += showing.price_count

        detected = []
        for film_title, data in films_with_ac.items():
            # Check if we already detected this by title
            content_type, _, _ = detect_content_type_from_title(film_title)

            detected.append({
                'film_title': film_title,
                'normalized_title': normalize_title(film_title),
                'content_type': content_type or 'unknown',  # May need manual classification
                'content_source': None,
                'detected_by': 'auto_ticket_type',
                'detection_confidence': 0.90,  # High confidence - we have AC ticket types
                'detection_reason': f"Has AC ticket types: {', '.join(data['ac_ticket_types'])}",
                'ac_ticket_types': data['ac_ticket_types'],
                'price_count': data['price_count'],
            })

        return detected

    def save_detected_films(self, detected_films: List[Dict]) -> int:
        """
        Save detected Alternative Content films to the database.

        Returns count of new films added.
        """
        added = 0

        for film_data in detected_films:
            # Check if already exists
            existing = self.session.query(AlternativeContentFilm).filter(
                AlternativeContentFilm.company_id == self.company_id,
                AlternativeContentFilm.normalized_title == film_data['normalized_title']
            ).first()

            if existing:
                # Update last_seen and occurrence_count
                existing.last_seen_at = datetime.now(timezone.utc)
                existing.occurrence_count = (existing.occurrence_count or 0) + 1
                continue

            # Create new entry
            ac_film = AlternativeContentFilm(
                company_id=self.company_id,
                film_title=film_data['film_title'],
                normalized_title=film_data['normalized_title'],
                content_type=film_data['content_type'],
                content_source=film_data.get('content_source'),
                detected_by=film_data['detected_by'],
                detection_confidence=Decimal(str(film_data['detection_confidence'])),
                detection_reason=film_data.get('detection_reason'),
                first_seen_at=film_data.get('first_seen') or datetime.now(timezone.utc),
                last_seen_at=film_data.get('last_seen') or datetime.now(timezone.utc),
                occurrence_count=film_data.get('occurrence_count', 1),
            )

            self.session.add(ac_film)
            added += 1

        self.session.commit()
        return added

    def is_alternative_content(self, film_title: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a film is classified as Alternative Content.

        Returns (is_ac, content_type)
        """
        normalized = normalize_title(film_title)

        # Check database first
        existing = self.session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == self.company_id,
            AlternativeContentFilm.normalized_title == normalized,
            AlternativeContentFilm.is_active == True
        ).first()

        if existing:
            return (True, existing.content_type)

        # Fall back to title detection
        content_type, confidence, _ = detect_content_type_from_title(film_title)
        if content_type and confidence >= 0.7:
            return (True, content_type)

        return (False, None)

    def get_circuit_ac_pricing(self, circuit_name: str) -> Optional[CircuitACPricing]:
        """Get AC pricing strategy for a circuit."""
        return self.session.query(CircuitACPricing).filter(
            CircuitACPricing.company_id == self.company_id,
            CircuitACPricing.circuit_name == circuit_name
        ).first()

    def run_full_detection(self, lookback_days: int = 90) -> Dict:
        """
        Run full AC detection pipeline:
        1. Detect from titles
        2. Detect from ticket types
        3. Save to database

        Returns summary of detection results.
        """
        logger.info(f"Running AC detection for last {lookback_days} days")

        # Title-based detection
        title_detected = self.detect_ac_films_from_showings(lookback_days)
        logger.info(f"Title detection found {len(title_detected)} films")

        # Ticket type detection
        ticket_detected = self.detect_ac_from_ticket_types(lookback_days)
        logger.info(f"Ticket type detection found {len(ticket_detected)} films")

        # Merge results (ticket type detection takes precedence)
        all_detected = {f['normalized_title']: f for f in title_detected}
        for film in ticket_detected:
            if film['normalized_title'] in all_detected:
                # Update with ticket type info
                all_detected[film['normalized_title']].update({
                    'detected_by': 'auto_ticket_type',  # More reliable
                    'detection_confidence': film['detection_confidence'],
                    'detection_reason': film['detection_reason'],
                })
            else:
                all_detected[film['normalized_title']] = film

        # Save to database
        added = self.save_detected_films(list(all_detected.values()))

        return {
            'title_detected': len(title_detected),
            'ticket_type_detected': len(ticket_detected),
            'total_unique': len(all_detected),
            'new_saved': added,
        }
