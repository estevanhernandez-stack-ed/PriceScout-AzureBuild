"""
Add AMC's "50% Off Tuesdays & Wednesdays" discount programs.

This is a member-only (AMC Stubs) discount that isn't captured by the Fandango scraper,
so we add it manually since we know it exists from AMC marketing.
"""
from app.db_session import get_session
from app.db_models import DiscountDayProgram, CompanyProfile
from datetime import datetime, timezone
from decimal import Decimal

def add_amc_discounts():
    with get_session() as session:
        # Find AMC profile
        amc = session.query(CompanyProfile).filter(CompanyProfile.circuit_name == 'AMC').first()
        if not amc:
            print('AMC profile not found')
            return

        print(f'Found AMC profile: {amc.circuit_name}')

        # Check if already exists
        existing = session.query(DiscountDayProgram).filter(
            DiscountDayProgram.circuit_name == 'AMC',
            DiscountDayProgram.program_name.like('%Stubs%')
        ).all()

        if existing:
            print(f'AMC Stubs discounts already exist ({len(existing)} programs)')
            for p in existing:
                print(f'  - {p.program_name}')
            return

        # Create Tuesday discount (day_of_week=1)
        tuesday = DiscountDayProgram(
            company_id=1,
            circuit_name='AMC',
            program_name='AMC Stubs 50% Off Tuesdays',
            day_of_week=1,  # Tuesday
            discount_type='percentage_off',
            discount_value=Decimal('50.0'),
            is_active=True,
            source='manual',
            confidence_score=Decimal('1.0'),
            discovered_at=datetime.now(timezone.utc),
            last_verified_at=datetime.now(timezone.utc),
            sample_count=0
        )
        tuesday.applicable_ticket_types_list = ['Adult']
        tuesday.applicable_dayparts_list = ['Prime', 'Late']

        # Create Wednesday discount (day_of_week=2)
        wednesday = DiscountDayProgram(
            company_id=1,
            circuit_name='AMC',
            program_name='AMC Stubs 50% Off Wednesdays',
            day_of_week=2,  # Wednesday
            discount_type='percentage_off',
            discount_value=Decimal('50.0'),
            is_active=True,
            source='manual',
            confidence_score=Decimal('1.0'),
            discovered_at=datetime.now(timezone.utc),
            last_verified_at=datetime.now(timezone.utc),
            sample_count=0
        )
        wednesday.applicable_ticket_types_list = ['Adult']
        wednesday.applicable_dayparts_list = ['Prime', 'Late']

        session.add(tuesday)
        session.add(wednesday)
        session.commit()
        print('Created AMC discount programs!')

        # Verify
        all_programs = session.query(DiscountDayProgram).filter(
            DiscountDayProgram.circuit_name == 'AMC'
        ).all()
        print(f'\nAMC discount programs ({len(all_programs)}):')
        for p in all_programs:
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            print(f'  - {p.program_name} ({day_names[p.day_of_week]}): {p.discount_value}% off')

if __name__ == '__main__':
    add_amc_discounts()
