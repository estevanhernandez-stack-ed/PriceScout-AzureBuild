#!/usr/bin/env python
"""
Director Price Scrape Coverage Chart Generator

Generates a markdown table showing price scrape counts per director
from last Friday through today.

Usage:
    python scripts/director_price_coverage.py

Output:
    - Prints chart to console
    - Saves to data/Marcus Theatres/director_price_coverage.md
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

def main():
    # Determine paths relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)

    db_path = os.path.join(project_dir, 'pricescout.db')
    markets_path = os.path.join(project_dir, 'data', 'Marcus Theatres', 'markets.json')
    output_path = os.path.join(project_dir, 'data', 'Marcus Theatres', 'director_price_coverage.md')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Load hierarchy to get director -> theaters mapping
    with open(markets_path, 'r') as f:
        hierarchy = json.load(f)

    # Build theater -> director mapping (Marcus + Movie Tavern only)
    theater_to_director = {}
    for company, directors in hierarchy.items():
        for director, markets in directors.items():
            for market, market_data in markets.items():
                for t in market_data.get('theaters', []):
                    if t['name'].startswith('Marcus') or t['name'].startswith('Movie Tavern'):
                        theater_to_director[t['name']] = director

    # Find last Friday
    today = datetime.now().date()
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7  # If today is Friday, go back a week
    last_friday = today - timedelta(days=days_since_friday)

    # Get dates from last Friday to today
    dates = []
    d = last_friday
    while d <= today:
        dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    output = []
    output.append('# Director Price Scrape Coverage')
    output.append('')
    output.append(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    output.append(f'Date Range: {dates[0]} (Fri) to {dates[-1]}')
    output.append('')

    directors = sorted(set(theater_to_director.values()))

    # Build header
    header = '| Director | ' + ' | '.join([d[-5:] for d in dates]) + ' | Total |'
    separator = '|' + '|'.join(['-' * 10 for _ in range(len(dates) + 2)]) + '|'

    output.append(header)
    output.append(separator)

    for director in directors:
        dir_theaters = [t for t, d in theater_to_director.items() if d == director]

        row_data = [director]
        total = 0

        for date in dates:
            placeholders = ','.join(['?' for _ in dir_theaters])
            cursor.execute(f'''
                SELECT COUNT(DISTINCT p.price_id)
                FROM prices p
                JOIN showings s ON p.showing_id = s.showing_id
                WHERE DATE(p.created_at) = ? AND s.theater_name IN ({placeholders})
            ''', [date] + dir_theaters)
            count = cursor.fetchone()[0]
            row_data.append(str(count))
            total += count

        row_data.append(str(total))
        output.append('| ' + ' | '.join(row_data) + ' |')

    output.append('')
    output.append('---')
    output.append('')
    output.append('## How to Update This Chart')
    output.append('')
    output.append('Run this command from the pricescout-react directory:')
    output.append('')
    output.append('```bash')
    output.append('python scripts/director_price_coverage.py')
    output.append('```')
    output.append('')
    output.append('**Data Sources:**')
    output.append('- `prices` table joined with `showings` table in `pricescout.db`')
    output.append('- `data/Marcus Theatres/markets.json` for director -> theater mapping')
    output.append('')
    output.append('**Includes:** Marcus + Movie Tavern theaters only')

    conn.close()

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(output))

    # Print to console
    print('\n'.join(output))
    print(f'\nSaved to: {output_path}')

if __name__ == '__main__':
    main()
