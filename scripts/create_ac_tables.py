"""Create Alternative Content tables in the database."""
from app.db_session import get_engine
from app.db_models import AlternativeContentFilm, CircuitACPricing, Base

engine = get_engine()

# Create only the new tables
AlternativeContentFilm.__table__.create(engine, checkfirst=True)
CircuitACPricing.__table__.create(engine, checkfirst=True)

print("Created tables:")
print("  - alternative_content_films")
print("  - circuit_ac_pricing")
