"""Run Alternative Content detection and show results."""
from app.db_session import get_session
from app.alternative_content_service import AlternativeContentService
from app.db_models import AlternativeContentFilm

print("Running Alternative Content Detection...")
print("=" * 60)

with get_session() as session:
    service = AlternativeContentService(session, company_id=1)

    # Run full detection
    results = service.run_full_detection(lookback_days=90)

    print(f"\nDetection Results:")
    print(f"  Title-based detection: {results['title_detected']} films")
    print(f"  Ticket type detection: {results['ticket_type_detected']} films")
    print(f"  Total unique films: {results['total_unique']}")
    print(f"  New films saved: {results['new_saved']}")

    # Show what was detected
    print("\n" + "=" * 60)
    print("DETECTED ALTERNATIVE CONTENT FILMS")
    print("=" * 60)

    ac_films = session.query(AlternativeContentFilm).filter(
        AlternativeContentFilm.is_active == True
    ).order_by(
        AlternativeContentFilm.content_type,
        AlternativeContentFilm.film_title
    ).all()

    current_type = None
    for film in ac_films:
        if film.content_type != current_type:
            print(f"\n--- {film.content_type.upper().replace('_', ' ')} ---")
            current_type = film.content_type

        confidence = f"{float(film.detection_confidence)*100:.0f}%" if film.detection_confidence else "?"
        source = f" ({film.content_source})" if film.content_source else ""
        print(f"  [{confidence}] {film.film_title}{source}")
        if film.detection_reason:
            print(f"         Reason: {film.detection_reason[:60]}...")

    print(f"\n\nTotal AC films in database: {len(ac_films)}")
