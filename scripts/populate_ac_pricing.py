"""Populate circuit AC pricing strategies from discovered data."""
from app.db_session import get_session
from app.db_models import CircuitACPricing, PriceBaseline
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import func

def populate_marcus_ac_pricing():
    """Populate Marcus AC pricing strategy based on discovered ticket types."""
    with get_session() as session:
        # Check if already exists
        existing = session.query(CircuitACPricing).filter(
            CircuitACPricing.circuit_name == 'Marcus'
        ).first()

        if existing:
            print("Marcus AC pricing already exists, skipping...")
            return

        # Get AC Loyalty Member price stats from baselines
        ac_stats = session.query(
            func.min(PriceBaseline.baseline_price).label('min_price'),
            func.max(PriceBaseline.baseline_price).label('max_price'),
            func.avg(PriceBaseline.baseline_price).label('avg_price'),
            func.count(PriceBaseline.baseline_id).label('count')
        ).filter(
            PriceBaseline.ticket_type == 'AC Loyalty Member'
        ).first()

        print(f"AC Loyalty Member stats: min=${ac_stats.min_price}, max=${ac_stats.max_price}, avg=${ac_stats.avg_price:.2f}, count={ac_stats.count}")

        # Create Marcus AC pricing entry
        marcus_ac = CircuitACPricing(
            company_id=1,
            circuit_name='Marcus',
            content_type='all',  # Applies to all AC types

            # Ticket type mappings
            # Marcus uses 'AC Loyalty Member' for discounted Alternative Content
            # Standard AC Adult ticket would be the non-loyalty AC price
            standard_ticket_type=None,  # Need to discover this
            discount_ticket_type='AC Loyalty Member',

            # Pricing patterns from data
            typical_price_min=Decimal(str(ac_stats.min_price)) if ac_stats.min_price else None,
            typical_price_max=Decimal(str(ac_stats.max_price)) if ac_stats.max_price else None,

            # Discount day behavior - yes, Marcus applies discount to AC
            discount_day_applies=True,
            discount_day_ticket_type='AC Loyalty Member',
            discount_day_price=Decimal(str(ac_stats.avg_price)) if ac_stats.avg_price else None,

            # Premium format behavior
            premium_surcharge_applies=True,

            notes='Marcus uses AC Loyalty Member ticket type for discounted Alternative Content on discount days. Need to discover standard AC ticket type.',
            source='auto_discovery'
        )

        session.add(marcus_ac)
        session.commit()
        print("Created Marcus AC pricing strategy")


def populate_bb_ac_pricing():
    """Populate B&B Theatres AC pricing strategy."""
    with get_session() as session:
        # Check if already exists
        existing = session.query(CircuitACPricing).filter(
            CircuitACPricing.circuit_name == 'B&B Theatres'
        ).first()

        if existing:
            print("B&B Theatres AC pricing already exists, skipping...")
            return

        # B&B has 'B&B Event $14' ticket type
        bb_ac = CircuitACPricing(
            company_id=1,
            circuit_name='B&B Theatres',
            content_type='all',

            # B&B uses flat $14 event pricing
            standard_ticket_type='B&B Event $14',
            discount_ticket_type=None,  # No discount AC ticket

            # Flat pricing
            typical_price_min=Decimal('14.00'),
            typical_price_max=Decimal('14.00'),

            # No discount day for AC
            discount_day_applies=False,
            discount_day_ticket_type=None,
            discount_day_price=None,

            premium_surcharge_applies=False,  # Flat price includes everything

            notes='B&B uses flat $14 event pricing for all Alternative Content regardless of format or day.',
            source='auto_discovery'
        )

        session.add(bb_ac)
        session.commit()
        print("Created B&B Theatres AC pricing strategy")


if __name__ == '__main__':
    populate_marcus_ac_pricing()
    populate_bb_ac_pricing()

    # Verify
    with get_session() as session:
        all_strategies = session.query(CircuitACPricing).order_by(CircuitACPricing.circuit_name).all()
        print(f"\n=== CIRCUIT AC PRICING STRATEGIES ({len(all_strategies)}) ===\n")
        for s in all_strategies:
            print(f"{s.circuit_name}:")
            print(f"  Content Type: {s.content_type}")
            print(f"  Standard Ticket: {s.standard_ticket_type or 'Unknown'}")
            print(f"  Discount Ticket: {s.discount_ticket_type or 'N/A'}")
            print(f"  Price Range: ${s.typical_price_min or '?'} - ${s.typical_price_max or '?'}")
            print(f"  Discount Day Applies: {s.discount_day_applies}")
            print(f"  Notes: {s.notes}")
            print()
