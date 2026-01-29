# Director Price Scrape Coverage

Generated: 2026-01-25 08:27
Date Range: 2026-01-23 (Fri) to 2026-01-25

| Director | 01-23 | 01-24 | 01-25 | Total |
|----------|----------|----------|----------|----------|
| Brian Shander | 3015 | 122 | 0 | 3137 |
| Garrett Rawson | 3372 | 0 | 0 | 3372 |
| Jason Buckland | 185 | 1102 | 0 | 1287 |
| Roy VanHorn | 459 | 0 | 1298 | 1757 |
| Tim Ward | 1073 | 2801 | 0 | 3874 |

---

## How to Update This Chart

Run this command from the pricescout-react directory:

```bash
python scripts/director_price_coverage.py
```

**Data Sources:**
- `prices` table joined with `showings` table in `pricescout.db`
- `data/Marcus Theatres/markets.json` for director -> theater mapping

**Includes:** Marcus + Movie Tavern theaters only