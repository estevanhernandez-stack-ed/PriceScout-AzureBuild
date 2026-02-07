"""
Market Scope Service

Resolves which theaters are in Marcus's competitive markets using the
curated markets.json file (204 theaters across 57 markets, 6 directors).

The JSON structure:
  {"Marcus Theatres": {"Director": {"Market ZIP": {"theaters": [{"name", "zip"}]}}}}

Theater names in markets.json may not exactly match EntTelligence names
(e.g. "Cinemas" vs "Cinema" vs "Cine"), so we apply normalization and
match against theater_metadata for canonical DB names.
"""

import json
import os
import re
import time
import logging
from typing import Set, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MARCUS_NAME_PATTERNS = ['marcus', 'movie tavern']

# Module-level cache with TTL
_cache: Dict = {
    'in_market_theaters': None,
    'marcus_theaters': None,
    'markets_json_raw': None,
    'unmatched': None,
    'match_log': None,
    'timestamp': 0,
}
_CACHE_TTL = 600  # 10 minutes


def _is_cache_valid() -> bool:
    return _cache['timestamp'] > 0 and (time.time() - _cache['timestamp']) < _CACHE_TTL


def _load_markets_json() -> List[Dict]:
    """Load and flatten markets.json into a list of theater dicts."""
    markets_path = os.path.join(
        _PROJECT_ROOT, 'data', 'Marcus Theatres', 'markets.json'
    )

    with open(markets_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    theaters = []
    for _company, directors in data.items():
        for director, markets in directors.items():
            for market_name, market_data in markets.items():
                for theater in market_data.get('theaters', []):
                    name = (theater.get('name') or '').strip()
                    if not name:
                        continue
                    is_marcus = any(p in name.lower() for p in MARCUS_NAME_PATTERNS)
                    theaters.append({
                        'name': name,
                        'zip': theater.get('zip', ''),
                        'director': director,
                        'market': market_name,
                        'is_marcus': is_marcus,
                        'status': theater.get('status'),
                    })
    return theaters


def _normalize_name(name: str) -> str:
    """Normalize a theater name for fuzzy matching.

    Handles common variants:
      - "Cinemas" / "Cinema" / "Cine" / "Theatre" / "Theater" → all map to "cinema"
      - "at" / "of" removed from compound names
      - Apostrophes removed (Eagles' → Eagles)
      - IMAX/XD format suffixes stripped
      - Extra whitespace collapsed
    """
    n = name.strip().lower()
    # Remove apostrophes (Eagles' Landing → Eagles Landing)
    n = n.replace("'", "").replace("\u2019", "")
    # Remove "at" and "of" as standalone words
    n = re.sub(r'\b(at|of)\b', '', n)
    # Unify venue-type words: theatre/theater/cinemas/cine → cinema
    n = re.sub(r'\btheatres?\b', 'cinema', n)
    n = re.sub(r'\btheaters?\b', 'cinema', n)
    n = re.sub(r'\bcinemas\b', 'cinema', n)
    n = re.sub(r'\bcine\b', 'cinema', n)
    # Remove format suffixes for matching (+ IMAX, & XD, etc.)
    n = re.sub(r'\s*[\+&]\s*(imax|xd|rpx|4dx|screenx)\b', '', n, flags=re.IGNORECASE)
    # Collapse whitespace
    n = ' '.join(n.split())
    return n


def _refresh_cache():
    """Load markets.json and resolve names against theater_metadata."""
    from app.db_session import get_session
    from app.db_models import TheaterMetadata

    # Step 1: Load markets.json theaters
    json_theaters = _load_markets_json()

    # Step 2: Load all theater_metadata names for matching
    with get_session() as session:
        db_rows = session.query(TheaterMetadata.theater_name).filter(
            TheaterMetadata.company_id == 1,
        ).all()
        db_names = {row.theater_name for row in db_rows}

    # Step 3: Build normalized lookup from DB names
    # {normalized_name: original_db_name}
    db_norm_lookup: Dict[str, str] = {}
    for db_name in db_names:
        norm = _normalize_name(db_name)
        # Keep first match (shouldn't have collisions in practice)
        if norm not in db_norm_lookup:
            db_norm_lookup[norm] = db_name

    # Step 4: Match each markets.json theater to a DB name
    in_market: Set[str] = set()
    marcus_own: Set[str] = set()
    match_log: Dict[str, Optional[str]] = {}
    unmatched: Set[str] = set()

    for t in json_theaters:
        name = t['name']

        # Exact match against DB
        if name in db_names:
            in_market.add(name)
            if t['is_marcus']:
                marcus_own.add(name)
            match_log[name] = name
            continue

        # Normalized match
        norm = _normalize_name(name)
        if norm in db_norm_lookup:
            resolved = db_norm_lookup[norm]
            in_market.add(resolved)
            if t['is_marcus']:
                marcus_own.add(resolved)
            match_log[name] = resolved
            continue

        # No DB match — include original name anyway
        # (may still match in enttelligence_price_cache even if not in metadata)
        in_market.add(name)
        if t['is_marcus']:
            marcus_own.add(name)
        match_log[name] = None
        unmatched.add(name)

    # Step 5: Fuzzy substring fallback for remaining unmatched
    # If a normalized markets.json name is a substring of a DB name (or vice versa)
    # and the match is close (>= 75% length), accept if unambiguous.
    still_unmatched = set(unmatched)
    for name in still_unmatched:
        norm = _normalize_name(name)
        candidates = []
        for db_norm, db_name in db_norm_lookup.items():
            if norm in db_norm or db_norm in norm:
                shorter = min(len(norm), len(db_norm))
                longer = max(len(norm), len(db_norm))
                if shorter / longer >= 0.75:
                    candidates.append(db_name)

        if len(candidates) == 1:
            resolved = candidates[0]
            is_marcus = any(p in name.lower() for p in MARCUS_NAME_PATTERNS)
            in_market.discard(name)
            in_market.add(resolved)
            if is_marcus:
                marcus_own.discard(name)
                marcus_own.add(resolved)
            match_log[name] = resolved
            unmatched.discard(name)
            logger.debug(f"[MarketScope] Substring match: {name!r} → {resolved!r}")

    # Step 6: Word-set matching for remaining unmatched
    # Handles word-order differences (e.g. "Marcus Cinema Renaissance" vs "Marcus Renaissance Cinema")
    # and extra words (e.g. "Marcus Gurnee Mills Cinema" vs "Marcus Gurnee Cinema")
    still_unmatched = set(unmatched)
    for name in still_unmatched:
        norm_words = set(_normalize_name(name).split())
        candidates = []
        for db_norm, db_name in db_norm_lookup.items():
            db_words = set(db_norm.split())
            if norm_words == db_words:
                candidates.append(db_name)
            elif norm_words.issubset(db_words) or db_words.issubset(norm_words):
                smaller = min(len(norm_words), len(db_words))
                larger = max(len(norm_words), len(db_words))
                if smaller / larger >= 0.75:
                    candidates.append(db_name)

        if len(candidates) == 1:
            resolved = candidates[0]
            is_marcus = any(p in name.lower() for p in MARCUS_NAME_PATTERNS)
            in_market.discard(name)
            in_market.add(resolved)
            if is_marcus:
                marcus_own.discard(name)
                marcus_own.add(resolved)
            match_log[name] = resolved
            unmatched.discard(name)
            logger.debug(f"[MarketScope] Word-set match: {name!r} → {resolved!r}")

    _cache['in_market_theaters'] = in_market
    _cache['marcus_theaters'] = marcus_own
    _cache['markets_json_raw'] = json_theaters
    _cache['match_log'] = match_log
    _cache['unmatched'] = unmatched
    _cache['timestamp'] = time.time()

    matched = len(match_log) - len(unmatched)
    logger.info(
        f"[MarketScope] Loaded markets.json: {len(json_theaters)} entries, "
        f"{matched} matched, {len(unmatched)} unmatched → "
        f"{len(in_market)} in-market theaters ({len(marcus_own)} Marcus)"
    )
    if unmatched:
        logger.warning(f"[MarketScope] Unmatched theaters: {sorted(unmatched)}")


# ============================================================================
# Public API
# ============================================================================

def get_in_market_theater_names() -> Set[str]:
    """Get all theater names in Marcus's markets (own + competitors).

    Sources from data/Marcus Theatres/markets.json, with name normalization
    to resolve Cinema/Cinemas/Cine variants against theater_metadata.
    """
    if not _is_cache_valid():
        _refresh_cache()
    return _cache['in_market_theaters']


def get_marcus_theater_names() -> Set[str]:
    """Get just Marcus/Movie Tavern theater names."""
    if not _is_cache_valid():
        _refresh_cache()
    return _cache['marcus_theaters']


def is_marcus_theater(theater_name: str) -> bool:
    """Check if a theater is Marcus-owned."""
    return theater_name in get_marcus_theater_names()


def get_market_scope_summary() -> dict:
    """Return summary stats about the market scope for UI display."""
    in_market = get_in_market_theater_names()
    marcus = get_marcus_theater_names()
    unmatched = _cache.get('unmatched') or set()
    return {
        'source': 'markets.json',
        'total_in_market_theaters': len(in_market),
        'marcus_theaters': len(marcus),
        'competitor_theaters': len(in_market) - len(marcus),
        'unmatched_count': len(unmatched),
    }


def get_match_diagnostics() -> dict:
    """Detailed matching diagnostics for debugging."""
    if not _is_cache_valid():
        _refresh_cache()
    log = _cache.get('match_log') or {}
    return {
        'total_json_theaters': len(log),
        'matched_count': len([v for v in log.values() if v is not None]),
        'unmatched': sorted(_cache.get('unmatched') or set()),
        'match_log': {k: v for k, v in sorted(log.items()) if v != k},  # Only show non-trivial matches
    }


# Module-level cache for EntTelligence name resolution
_ent_cache: Dict = {
    'ent_names': None,
    'timestamp': 0,
}


def get_in_market_enttelligence_names(conn) -> Set[str]:
    """Resolve market theater names against enttelligence_price_cache theater names.

    Takes the 204 theaters from markets.json and finds their corresponding names
    in enttelligence_price_cache using exact + normalized matching.

    Args:
        conn: sqlite3.Connection to the pricescout database.

    Returns:
        Set of EntTelligence theater_name values that are in our markets.
    """
    if _ent_cache['timestamp'] > 0 and (time.time() - _ent_cache['timestamp']) < _CACHE_TTL:
        return _ent_cache['ent_names']

    # Known aliases: markets.json name → EntTelligence name
    # These theaters use shopping center names in EntTelligence instead of city names.
    _KNOWN_ALIASES = {
        'Movie Tavern Tucker Cinema': 'Movie Tavern Northlake Festival',
        'Movie Tavern Roswell': 'Movie Tavern at Sandy Plains Village',
        'Movie Tavern Williamsburg': 'Movie Tavern at High Street',
        'Movie Tavern Collegeville Cinema': 'Movie Tavern Providence Town Center',
        'Movie Tavern Covington': 'Movie Tavern Northshore',
        'Marcus Palace Cinema': 'Marcus Palace of Sun Prairie',
    }

    # Step 1: Get our 204 market theater names (resolved against theater_metadata)
    market_names = get_in_market_theater_names()

    # Step 2: Get all distinct theater names from EntTelligence cache
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT theater_name FROM enttelligence_price_cache")
    ent_names_all = {row[0] for row in cursor.fetchall() if row[0]}

    # Step 3: Build normalized lookup for EntTelligence names
    ent_norm_lookup: Dict[str, str] = {}
    for ent_name in ent_names_all:
        norm = _normalize_name(ent_name)
        if norm not in ent_norm_lookup:
            ent_norm_lookup[norm] = ent_name

    # Step 4: Build a "deep normalized" lookup that strips more aggressively
    # for fallback matching: remove dashes, the filler word "cinema", trailing
    # numbers, and expand known abbreviations.
    def _deep_norm(n: str) -> str:
        """Aggressive normalization for fallback matching."""
        n = _normalize_name(n)
        # Expand abbreviations before stripping
        n = re.sub(r'\bsmg\b', 'studio movie grill', n)
        n = re.sub(r'\bthr\b', 'cinema', n)
        # Replace unicode dashes (en dash, em dash) with space
        n = n.replace('\u2013', ' ').replace('\u2014', ' ').replace('\ufffd', ' ')
        # Remove dashes used as separators
        n = n.replace(' - ', ' ').replace('-', ' ')
        # Normalize ampersand spacing (B&B vs B & B)
        n = re.sub(r'\s*&\s*', '&', n)
        # Remove AMC sub-brand names (Classic/Starplex are same theaters)
        n = re.sub(r'\b(classic|starplex)\b', '', n)
        # Remove the unified "cinema" word (noise after normalization)
        n = re.sub(r'\bcinema\b', '', n)
        # Remove noise words
        n = re.sub(r'\b(usa|and|the|in)\b', '', n)
        # Remove trailing numbers (screen counts like "10", "14", "16")
        n = re.sub(r'\b\d+\b', '', n)
        # Remove parenthetical content (e.g. "(Permanently Closed)")
        n = re.sub(r'\([^)]*\)', '', n)
        # Remove special chars (@ , .)
        n = re.sub(r'[@,.]', '', n)
        return ' '.join(n.split())

    ent_deep_lookup: Dict[str, str] = {}
    for ent_name in ent_names_all:
        deep = _deep_norm(ent_name)
        if deep and deep not in ent_deep_lookup:
            ent_deep_lookup[deep] = ent_name

    # Step 5: Match each market theater to an EntTelligence name
    matched: Set[str] = set()
    unmatched_names = []

    for market_name in market_names:
        # Known alias (hand-verified mapping)
        if market_name in _KNOWN_ALIASES:
            alias = _KNOWN_ALIASES[market_name]
            if alias in ent_names_all:
                matched.add(alias)
                continue

        # Exact match
        if market_name in ent_names_all:
            matched.add(market_name)
            continue

        # Normalized match
        norm = _normalize_name(market_name)
        if norm in ent_norm_lookup:
            matched.add(ent_norm_lookup[norm])
            continue

        # Deep normalized match (strips dashes, "cinema", numbers, abbreviations)
        deep = _deep_norm(market_name)
        if deep in ent_deep_lookup:
            matched.add(ent_deep_lookup[deep])
            continue

        # Substring match
        candidates = []
        for ent_norm, ent_name in ent_norm_lookup.items():
            if norm in ent_norm or ent_norm in norm:
                shorter = min(len(norm), len(ent_norm))
                longer = max(len(norm), len(ent_norm))
                if shorter / longer >= 0.60:
                    candidates.append(ent_name)
        if len(candidates) == 1:
            matched.add(candidates[0])
            continue

        # Word-set match
        norm_words = set(norm.split())
        candidates = []
        for ent_norm, ent_name in ent_norm_lookup.items():
            ent_words = set(ent_norm.split())
            if norm_words == ent_words:
                candidates.append(ent_name)
            elif norm_words.issubset(ent_words) or ent_words.issubset(norm_words):
                smaller = min(len(norm_words), len(ent_words))
                larger = max(len(norm_words), len(ent_words))
                if smaller / larger >= 0.60:
                    candidates.append(ent_name)
        if len(candidates) == 1:
            matched.add(candidates[0])
            continue

        # Deep word-set match (after aggressive normalization)
        deep_words = set(deep.split())
        if len(deep_words) >= 2:
            candidates = []
            for ent_deep, ent_name in ent_deep_lookup.items():
                ent_dw = set(ent_deep.split())
                if deep_words == ent_dw:
                    candidates.append(ent_name)
                elif len(deep_words) >= 2 and len(ent_dw) >= 2:
                    overlap = deep_words & ent_dw
                    # Require brand word + location word to both match
                    if len(overlap) >= 2 and overlap == deep_words:
                        candidates.append(ent_name)
                    elif len(overlap) >= 2 and overlap == ent_dw:
                        candidates.append(ent_name)
            if len(candidates) == 1:
                matched.add(candidates[0])
                continue

        unmatched_names.append(market_name)

    _ent_cache['ent_names'] = matched
    _ent_cache['timestamp'] = time.time()

    logger.info(
        f"[MarketScope] EntTelligence name resolution: {len(market_names)} market theaters → "
        f"{len(matched)} matched, {len(unmatched_names)} unmatched"
    )
    if unmatched_names:
        logger.warning(f"[MarketScope] Unmatched in EntTelligence: {sorted(unmatched_names)}")

    return matched
