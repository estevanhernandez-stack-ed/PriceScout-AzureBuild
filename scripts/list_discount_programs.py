"""List all discount programs in the database."""
from app.db_session import get_session
from app.db_models import DiscountDayProgram

day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

with get_session() as session:
    programs = session.query(DiscountDayProgram).filter(
        DiscountDayProgram.is_active == True
    ).order_by(
        DiscountDayProgram.circuit_name, DiscountDayProgram.day_of_week
    ).all()

    print(f"\n=== ALL DISCOUNT PROGRAMS ({len(programs)}) ===")

    current_circuit = None
    for p in programs:
        if p.circuit_name != current_circuit:
            print(f"\n{p.circuit_name}:")
            current_circuit = p.circuit_name

        day = day_names[p.day_of_week]
        if p.discount_type == "flat_price":
            value = f"${p.discount_value:.2f} flat"
        elif p.discount_type == "percentage_off":
            value = f"{p.discount_value}% off"
        else:
            value = f"${p.discount_value:.2f} off"

        applies = ""
        if p.applicable_ticket_types_list:
            applies = f" (applies to: {', '.join(p.applicable_ticket_types_list)})"

        source = f" [{p.source}]" if p.source else ""

        print(f"  {day}: {p.program_name} - {value}{applies}{source}")
