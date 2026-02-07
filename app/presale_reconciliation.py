"""
Presale Reconciliation Service

Aggregates per-showtime capacity/sales data from EntTelligence cache
into circuit-level daily snapshots in the circuit_presales table.

Also provides presale compliance analysis: how far in advance each
circuit posts showtimes compared to others.

Data flow:
  EntTelligence API  ->  enttelligence_price_cache (per showtime)
                               |
                     presale_reconciliation.sync_presales()
                               |
                         circuit_presales (daily snapshots per circuit/film)

EntTelligence data model:
  capacity  = total auditorium seats
  available = seats still on sale
  blocked   = seats NOT available (sold + house-holds + ADA, etc.)

Invariant from the API: capacity = available + blocked  (always).
Therefore:  tickets_sold = capacity - available  (== blocked).
We do NOT subtract blocked — blocked IS the sold/reserved count.
"""

import logging
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from typing import Dict, List, Optional, Set
from collections import defaultdict

from sqlalchemy import and_, func, distinct, case

from app.db_session import get_session
from app.db_models import EntTelligencePriceCache, CircuitPresale

logger = logging.getLogger(__name__)

# Premium format keywords for classification
FORMAT_CATEGORIES = {
    'imax': ['IMAX', 'imax'],
    'dolby': ['Dolby', 'dolby', 'DOLBY'],
    '3d': ['3D', '3d'],
    'premium': ['PLF', 'Premium', 'XD', 'RPX', 'BigD', '4DX', 'ScreenX', 'D-BOX',
                'GTX', 'UltraAVX', 'UltraScreen', 'SuperScreen'],
}


def _classify_format(fmt: Optional[str]) -> str:
    """Classify a format string into a ticket category."""
    if not fmt:
        return 'standard'
    fmt_upper = fmt.upper()
    for category, keywords in FORMAT_CATEGORIES.items():
        if any(kw.upper() in fmt_upper for kw in keywords):
            return category
    return 'standard'


def sync_presales(company_id: int = 1) -> Dict:
    """
    Aggregate presale data from EntTelligence cache into circuit_presales.

    For each circuit + film with a known release_date, computes:
    - total_tickets_sold (capacity - available, summed; blocked IS the sold count)
    - total_revenue estimate (tickets * avg_price)
    - total_showtimes and theaters
    - format breakdown (IMAX, Dolby, 3D, premium, standard)
    - capacity and fill rate

    Upserts one row per (circuit, film, snapshot_date=today) into circuit_presales.

    Returns:
        Dict with sync statistics
    """
    today = date.today()
    snapshot_date = today

    logger.info(f"[PresaleSync] Starting presale reconciliation for company {company_id}")

    stats = {
        'snapshot_date': str(snapshot_date),
        'circuits_updated': 0,
        'films_processed': 0,
        'total_rows_upserted': 0,
        'total_tickets': 0,
        'errors': 0,
    }

    with get_session() as session:
        # Query all Adult-priced records that have capacity data and a release_date.
        # We use ticket_type='Adult' to avoid double-counting across ticket types.
        query = session.query(
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.release_date,
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.play_date,
            EntTelligencePriceCache.showtime,
            EntTelligencePriceCache.format,
            EntTelligencePriceCache.price,
            EntTelligencePriceCache.capacity,
            EntTelligencePriceCache.available,
            EntTelligencePriceCache.blocked,
        ).filter(
            and_(
                EntTelligencePriceCache.company_id == company_id,
                EntTelligencePriceCache.ticket_type == 'Adult',
                EntTelligencePriceCache.release_date.isnot(None),
                EntTelligencePriceCache.release_date != '',
                EntTelligencePriceCache.capacity.isnot(None),
                EntTelligencePriceCache.capacity > 0,
            )
        )

        # Group by circuit + film
        # Structure: {(circuit, film, release_date): [row_data]}
        grouped = defaultdict(list)
        for row in query.all():
            circuit = row.circuit_name or 'Unknown'
            key = (circuit, row.film_title, row.release_date)
            grouped[key].append(row)

        logger.info(f"[PresaleSync] Found {len(grouped)} circuit/film combinations with capacity data")

        circuits_seen = set()
        films_seen = set()

        for (circuit_name, film_title, release_date_str), rows in grouped.items():
            try:
                # Parse release date
                try:
                    rel_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    continue

                days_before = (rel_date - today).days

                # Aggregate metrics
                theaters = set()
                showtime_keys = set()
                total_capacity = 0
                total_available = 0
                total_tickets = 0
                prices = []

                # Format breakdown
                format_tickets = defaultdict(int)

                for row in rows:
                    theaters.add(row.theater_name)
                    st_key = f"{row.theater_name}|{row.play_date}|{row.showtime}"
                    showtime_keys.add(st_key)

                    cap = row.capacity or 0
                    avail = row.available or 0
                    # blocked = capacity - available (always), so:
                    # tickets_sold = capacity - available
                    sold = max(0, cap - avail)

                    total_capacity += cap
                    total_available += avail
                    total_tickets += sold

                    if row.price and float(row.price) > 0:
                        prices.append(float(row.price))

                    # Classify format
                    fmt_cat = _classify_format(row.format)
                    format_tickets[fmt_cat] += sold

                total_showtimes = len(showtime_keys)
                total_theaters = len(theaters)
                avg_price = sum(prices) / len(prices) if prices else 0.0
                total_revenue = total_tickets * avg_price

                avg_tickets_per_show = total_tickets / total_showtimes if total_showtimes > 0 else 0.0
                avg_tickets_per_theater = total_tickets / total_theaters if total_theaters > 0 else 0.0
                fill_rate = (total_tickets / total_capacity * 100) if total_capacity > 0 else 0.0

                # Upsert into circuit_presales
                existing = session.query(CircuitPresale).filter_by(
                    circuit_name=circuit_name,
                    film_title=film_title,
                    snapshot_date=snapshot_date,
                ).first()

                if existing:
                    existing.release_date = rel_date
                    existing.days_before_release = days_before
                    existing.total_tickets_sold = total_tickets
                    existing.total_revenue = Decimal(str(round(total_revenue, 2)))
                    existing.total_showtimes = total_showtimes
                    existing.total_theaters = total_theaters
                    existing.avg_tickets_per_show = round(avg_tickets_per_show, 1)
                    existing.avg_tickets_per_theater = round(avg_tickets_per_theater, 1)
                    existing.avg_ticket_price = Decimal(str(round(avg_price, 2)))
                    existing.tickets_imax = format_tickets.get('imax', 0)
                    existing.tickets_dolby = format_tickets.get('dolby', 0)
                    existing.tickets_3d = format_tickets.get('3d', 0)
                    existing.tickets_premium = format_tickets.get('premium', 0)
                    existing.tickets_standard = format_tickets.get('standard', 0)
                    existing.total_capacity = total_capacity
                    existing.total_available = total_available
                    existing.fill_rate_percent = round(fill_rate, 1)
                else:
                    new_row = CircuitPresale(
                        circuit_name=circuit_name,
                        film_title=film_title,
                        release_date=rel_date,
                        snapshot_date=snapshot_date,
                        days_before_release=days_before,
                        total_tickets_sold=total_tickets,
                        total_revenue=Decimal(str(round(total_revenue, 2))),
                        total_showtimes=total_showtimes,
                        total_theaters=total_theaters,
                        avg_tickets_per_show=round(avg_tickets_per_show, 1),
                        avg_tickets_per_theater=round(avg_tickets_per_theater, 1),
                        avg_ticket_price=Decimal(str(round(avg_price, 2))),
                        tickets_imax=format_tickets.get('imax', 0),
                        tickets_dolby=format_tickets.get('dolby', 0),
                        tickets_3d=format_tickets.get('3d', 0),
                        tickets_premium=format_tickets.get('premium', 0),
                        tickets_standard=format_tickets.get('standard', 0),
                        total_capacity=total_capacity,
                        total_available=total_available,
                        fill_rate_percent=round(fill_rate, 1),
                        data_source='enttelligence',
                    )
                    session.add(new_row)

                circuits_seen.add(circuit_name)
                films_seen.add(film_title)
                stats['total_rows_upserted'] += 1
                stats['total_tickets'] += total_tickets

            except Exception as e:
                stats['errors'] += 1
                if stats['errors'] <= 5:
                    logger.error(f"[PresaleSync] Error processing {circuit_name}/{film_title}: {e}")

        session.flush()

    stats['circuits_updated'] = len(circuits_seen)
    stats['films_processed'] = len(films_seen)

    logger.info(
        f"[PresaleSync] Done: {stats['total_rows_upserted']} rows upserted, "
        f"{stats['circuits_updated']} circuits, {stats['films_processed']} films, "
        f"{stats['total_tickets']} total tickets"
    )

    return stats


def get_presale_compliance(company_id: int = 1, theater_names: Optional[Set[str]] = None) -> Dict:
    """
    Analyze presale posting compliance across circuits.

    For each upcoming film, determines how far in advance each circuit
    has showtimes posted (measured by the earliest play_date in the cache
    relative to the release_date).

    Returns:
        {
            "films": [
                {
                    "film_title": "...",
                    "release_date": "2026-03-01",
                    "days_until_release": 27,
                    "circuits": {
                        "Marcus Theatres Corporation": {
                            "days_posted_ahead": 14,
                            "total_showtimes": 120,
                            "total_theaters": 8,
                            "earliest_showtime_date": "2026-02-15",
                        },
                        "AMC Entertainment Inc": { ... },
                    },
                    "marcus_rank": 3,          # rank among circuits by days_posted_ahead
                    "avg_days_ahead": 18.5,    # average across all circuits
                    "marcus_delta": -4.5,      # marcus vs average (negative = behind)
                }
            ]
        }
    """
    today = date.today()

    with get_session() as session:
        # Get all films with their earliest play_date per circuit
        query = session.query(
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.release_date,
            func.min(EntTelligencePriceCache.play_date).label('earliest_play_date'),
            func.count().label('total_showtimes'),
            func.count(distinct(EntTelligencePriceCache.theater_name)).label('total_theaters'),
        ).filter(
            and_(
                EntTelligencePriceCache.company_id == company_id,
                EntTelligencePriceCache.ticket_type == 'Adult',
                EntTelligencePriceCache.release_date.isnot(None),
                EntTelligencePriceCache.release_date != '',
            )
        )

        # Optional market scope filter: restrict to specific theaters
        if theater_names:
            query = query.filter(
                EntTelligencePriceCache.theater_name.in_(theater_names)
            )

        query = query.group_by(
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.release_date,
        )

        # Build film -> circuit data
        film_data = defaultdict(lambda: {
            'release_date': None,
            'circuits': {},
        })

        for row in query.all():
            circuit = row.circuit_name or 'Unknown'
            film = row.film_title

            try:
                rel_date = datetime.strptime(row.release_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue

            days_until = (rel_date - today).days
            if days_until < -7:
                continue  # Skip films that released more than a week ago

            film_data[film]['release_date'] = row.release_date
            film_data[film]['days_until_release'] = days_until

            # Days ahead = release_date - earliest_play_date
            earliest = row.earliest_play_date
            if isinstance(earliest, str):
                earliest = datetime.strptime(earliest, '%Y-%m-%d').date()

            days_posted_ahead = (rel_date - earliest).days if earliest else 0

            film_data[film]['circuits'][circuit] = {
                'days_posted_ahead': days_posted_ahead,
                'total_showtimes': row.total_showtimes,
                'total_theaters': row.total_theaters,
                'earliest_showtime_date': str(earliest) if earliest else None,
            }

        # Compute rankings and Marcus comparison
        films_result = []
        marcus_labels = ['marcus', 'movie tavern', 'spotlight']

        for film_title, data in film_data.items():
            circuits = data['circuits']
            if not circuits:
                continue

            # Find Marcus circuit(s)
            marcus_circuit = None
            for circuit_name in circuits:
                if any(label in circuit_name.lower() for label in marcus_labels):
                    marcus_circuit = circuit_name
                    break

            # Rank circuits by days_posted_ahead
            ranked = sorted(
                circuits.items(),
                key=lambda x: x[1]['days_posted_ahead'],
                reverse=True,
            )

            all_days = [c['days_posted_ahead'] for c in circuits.values()]
            avg_days = sum(all_days) / len(all_days) if all_days else 0

            marcus_days = circuits[marcus_circuit]['days_posted_ahead'] if marcus_circuit else None
            marcus_rank = None
            if marcus_circuit:
                for i, (name, _) in enumerate(ranked):
                    if name == marcus_circuit:
                        marcus_rank = i + 1
                        break

            films_result.append({
                'film_title': film_title,
                'release_date': data['release_date'],
                'days_until_release': data.get('days_until_release', 0),
                'circuits': circuits,
                'circuit_ranking': [(name, info['days_posted_ahead']) for name, info in ranked[:10]],
                'marcus_rank': marcus_rank,
                'marcus_days_ahead': marcus_days,
                'avg_days_ahead': round(avg_days, 1),
                'marcus_delta': round(marcus_days - avg_days, 1) if marcus_days is not None else None,
                'total_circuits': len(circuits),
            })

        # Sort by days_until_release ascending (most imminent first)
        films_result.sort(key=lambda x: x['days_until_release'])

        return {
            'snapshot_date': str(today),
            'total_films': len(films_result),
            'films': films_result,
        }


