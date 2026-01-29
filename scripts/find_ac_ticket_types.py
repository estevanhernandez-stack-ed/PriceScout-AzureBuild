"""Find Alternative Content ticket types in the database."""
from app.db_session import get_session
from app.db_models import Price, Showing, TheaterMetadata, CompanyProfile
from sqlalchemy import func, distinct

with get_session() as session:
    # First, get all unique ticket types from price_baselines (has circuit via company_profiles)
    print("=== ALL TICKET TYPES FROM PRICE BASELINES ===\n")

    from app.db_models import PriceBaseline

    # Get ticket types grouped by joining baselines with profiles
    results = session.query(
        CompanyProfile.circuit_name,
        PriceBaseline.ticket_type,
        func.count(PriceBaseline.baseline_id).label('count')
    ).join(
        PriceBaseline,
        CompanyProfile.circuit_name == session.query(
            TheaterMetadata.circuit_name
        ).filter(
            TheaterMetadata.theater_name == PriceBaseline.theater_name
        ).correlate(PriceBaseline).scalar_subquery()
    ).group_by(
        CompanyProfile.circuit_name,
        PriceBaseline.ticket_type
    ).order_by(
        CompanyProfile.circuit_name,
        func.count(PriceBaseline.baseline_id).desc()
    ).all()

    if not results:
        # Simpler approach - just get from baselines directly
        print("Trying simpler query...")
        results = session.query(
            PriceBaseline.ticket_type,
            func.count(PriceBaseline.baseline_id).label('count')
        ).group_by(
            PriceBaseline.ticket_type
        ).order_by(
            func.count(PriceBaseline.baseline_id).desc()
        ).all()

        print(f"\nAll ticket types in baselines ({len(results)}):")
        for ticket_type, count in results:
            marker = " <-- AC?" if any(kw in ticket_type.lower() for kw in ['ac ', ' ac', 'loyalty', 'alternative', 'event', 'special']) else ""
            print(f"  - {ticket_type} ({count:,}){marker}")
    else:
        current_circuit = None
        for circuit, ticket_type, count in results:
            if circuit != current_circuit:
                print(f"\n{circuit}:")
                current_circuit = circuit
            marker = " <-- AC?" if any(kw in ticket_type.lower() for kw in ['ac ', ' ac', 'loyalty', 'alternative', 'event', 'special']) else ""
            print(f"  - {ticket_type} ({count:,}){marker}")

    # Now check what's in company profiles' discovered ticket types
    print("\n\n=== TICKET TYPES FROM COMPANY PROFILES ===\n")

    profiles = session.query(CompanyProfile).order_by(CompanyProfile.circuit_name).all()
    for profile in profiles:
        types = profile.ticket_types_list or []
        print(f"\n{profile.circuit_name} ({profile.theater_count} theaters):")
        for t in types:
            marker = " <-- AC?" if any(kw in t.lower() for kw in ['ac ', ' ac', 'loyalty', 'alternative', 'event', 'special']) else ""
            print(f"  - {t}{marker}")
