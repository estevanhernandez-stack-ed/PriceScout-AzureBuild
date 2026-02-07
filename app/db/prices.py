"""
Price data management: saving scraped prices, retrieving price history.
"""

import pandas as pd
from sqlalchemy import and_
from app.db_session import get_session
from app.db_models import Showing, Price
from app.simplified_baseline_service import normalize_format
from app import config


def save_prices(run_id: int, df: pd.DataFrame, company_id: int = None, batch_size: int = 50):
    """Save scraped prices to database with batch commits for crash resilience.

    Args:
        run_id: The scrape run ID
        df: DataFrame with price data
        company_id: Company ID (defaults to config or 1)
        batch_size: Number of prices to commit at once (default 50)
    """
    import datetime as dt
    print(f"  [DB] save_prices called with {len(df)} rows, run_id={run_id}, batch_size={batch_size}")
    if 'play_date' not in df.columns or df['play_date'].isnull().all():
        print("  [DB] [ERROR] save_prices called with missing 'play_date'. Aborting.")
        return

    # Ensure play_date is a date object, not string
    if df['play_date'].dtype == 'object':
        def to_date(val):
            if isinstance(val, str):
                return dt.datetime.strptime(val, "%Y-%m-%d").date()
            elif isinstance(val, dt.datetime):
                return val.date()
            return val
        df = df.copy()
        df['play_date'] = df['play_date'].apply(to_date)
        print(f"  [DB] Converted play_date strings to date objects")

    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1

        prices_saved = 0
        prices_in_batch = 0
        prices_skipped_no_showing = 0
        prices_skipped_duplicate = 0
        prices_skipped_error = 0
        batches_committed = 0

        for idx, row in df.iterrows():
            showing = session.query(Showing).filter(
                and_(
                    Showing.company_id == company_id,
                    Showing.play_date == row['play_date'],
                    Showing.theater_name == row['Theater Name'],
                    Showing.film_title == row['Film Title'],
                    Showing.showtime == row['Showtime'],
                    Showing.format == (normalize_format(row['Format']) or row['Format'])
                )
            ).first()

            if showing:
                try:
                    price_value = float(str(row['Price']).replace('$', ''))
                    ticket_type = row['Ticket Type']

                    existing_price = session.query(Price).filter(
                        and_(
                            Price.showing_id == showing.showing_id,
                            Price.ticket_type == ticket_type
                        )
                    ).first()

                    if existing_price:
                        prices_skipped_duplicate += 1
                        continue

                    price = Price(
                        company_id=company_id,
                        run_id=run_id,
                        showing_id=showing.showing_id,
                        ticket_type=ticket_type,
                        price=price_value,
                        capacity=row.get('Capacity'),
                        play_date=row['play_date']
                    )
                    session.add(price)
                    prices_saved += 1
                    prices_in_batch += 1

                    if prices_in_batch >= batch_size:
                        session.commit()
                        batches_committed += 1
                        print(f"  [DB] Committed batch {batches_committed} ({prices_saved} prices so far)")
                        prices_in_batch = 0

                except (ValueError, KeyError) as e:
                    print(f"  [DB] [WARN] Skipping price: {e}")
                    prices_skipped_error += 1
            else:
                prices_skipped_no_showing += 1
                if prices_skipped_no_showing <= 3:
                    print(f"  [DB] [WARN] No matching showing for: {row['Theater Name']} | {row['Film Title']} | {row['Showtime']} | {row['Format']} | {row['play_date']}")

        if prices_skipped_no_showing > 3:
            print(f"  [DB] [WARN] ... and {prices_skipped_no_showing - 3} more prices skipped (no matching showing)")

        if prices_in_batch > 0:
            session.commit()
            batches_committed += 1
            print(f"  [DB] Final batch {batches_committed} committed")

        print(f"  [DB] Saved {prices_saved} prices for run ID {run_id} in {batches_committed} batches. Skipped: {prices_skipped_no_showing} (no showing), {prices_skipped_duplicate} (duplicates), {prices_skipped_error} (errors)")


def get_prices_for_run(run_id):
    """Get all prices for a specific scrape run"""
    with get_session() as session:
        query = session.query(
            Price.price,
            Price.ticket_type,
            Showing.play_date,
            Showing.theater_name,
            Showing.film_title,
            Showing.showtime,
            Showing.format,
            Showing.daypart
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(Price.run_id == run_id)

        df = pd.read_sql(query.statement, session.bind)
        return df
