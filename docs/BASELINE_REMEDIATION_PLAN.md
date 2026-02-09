# Baseline Remediation Plan

**Created**: 2026-02-08
**Status**: Implementation in progress
**Goal**: Clean up 292K duplicated baseline rows, fix taxonomy, and prevent future duplication — ready for surge detection.

---

## Problem Statement

The `price_baselines` table has 292,011 rows for ~54,385 distinct combinations (5.4x duplication). Root causes:

1. **Append-only inserts**: EntTelligence discovery service's `save_discovered_baselines()` ends old baselines and creates new ones (instead of updating in place), adding rows on every run.
2. **day_of_week fan-out**: Fandango discovery creates 7 separate rows per combo (one per day of week), but `day_of_week` is deprecated for matching per the model docstring.
3. **No dedup in API endpoint**: `POST /price-baselines` creates blindly without checking for existing records.
4. **Multiple effective_from epochs**: Multiple discovery runs at different dates all create new "active" baselines.

### Tax Status Issues

- **AMC/Regal/SMG**: EntTelligence prices are tax-inclusive (match Fandango exactly, $0.00 diff).
- **Marcus/Movie Tavern/Cinemark**: EntTelligence prices are pre-tax (~7.6% lower than Fandango).
- EntTelligence discovery service *tries* to apply estimated tax before saving (via `tax_estimation.py`), but whether this succeeds depends on the tax config being set up for the company. Rows where tax was not applied are mislabeled `tax_status='inclusive'`.

---

## Phase 1: Dedup Migration Script

Create `migrations/dedup_baselines.py` that:

1. For each unique `(company_id, theater_name, ticket_type, COALESCE(format,''), COALESCE(daypart,''), source)`:
   - Keep the row with `effective_to IS NULL` (active) and highest `sample_count`
   - If tied, keep the latest `effective_from`
   - Delete all other rows in that group
2. **Collapse day_of_week**: For surviving rows, SET `day_of_week = NULL`, `day_type = NULL` (deprecated per model docstring). Then re-dedup any new duplicates created by this collapse.
3. Log before/after counts per source.

**Expected result**: 292K → ~15-30K rows.

---

## Phase 2: Fix Tax Labels

After dedup, update tax labels for EntTelligence baselines based on circuit:

```sql
-- Marcus / Movie Tavern / Cinemark ENT baselines where tax was NOT applied
-- These are pre-tax prices labeled 'inclusive' incorrectly
UPDATE price_baselines
SET tax_status = 'exclusive'
WHERE source = 'enttelligence'
  AND tax_status = 'inclusive'
  AND (theater_name LIKE 'Marcus%'
       OR theater_name LIKE 'Movie Tavern%'
       OR theater_name LIKE 'Cinemark%')
```

Note: AMC/Regal/SMG EntTelligence baselines are correctly labeled `inclusive` (prices match Fandango exactly).

---

## Phase 3: Fix Discovery Services (UPSERT)

### 3a. EntTelligence discovery (`app/enttelligence_baseline_discovery.py`)

Change `save_discovered_baselines()`:
- When `overwrite=True` and an existing baseline is found: **update in place** (price, sample_count, last_discovery_at) instead of ending old + creating new.
- This matches what `BaselineDiscoveryService.save_discovered_baselines()` already does.

### 3b. Fandango discovery (`app/fandango_baseline_discovery.py`)

Change `save_baselines()`:
- When `overwrite=True`: update in place instead of ending old + creating new.
- Default `split_by_day_of_week=False` (was `True`) — day_of_week is deprecated.

### 3c. Base discovery (`app/baseline_discovery.py`)

Already uses in-place update for overwrite — no change needed.

---

## Phase 4: Fix API Endpoint

`POST /price-baselines` in `api/routers/price_alerts.py`:
- Before creating, check for existing active baseline with matching (company_id, theater_name, ticket_type, format, daypart).
- If found, update the existing record instead of creating a duplicate.

---

## Phase 5: Verification

1. Run dedup migration
2. Run all backend tests (510+ must pass)
3. Verify baseline counts per source/theater are reasonable
4. Run a discovery cycle and confirm no new duplicates created

---

## Files Modified

| File | Change |
|------|--------|
| `migrations/dedup_baselines.py` | NEW — migration script |
| `app/enttelligence_baseline_discovery.py` | UPSERT in save_discovered_baselines |
| `app/fandango_baseline_discovery.py` | UPSERT in save_baselines, default split_by_day_of_week=False |
| `api/routers/price_alerts.py` | Dedup check in POST /price-baselines |

## Files NOT Modified

| File | Reason |
|------|--------|
| `app/baseline_discovery.py` | Already uses in-place update |
| `app/baseline_gap_filler.py` | Already checks for existing (4-dimension check is sufficient for gap fills) |
| `app/simplified_baseline_service.py` | Read-only service, no writes |
| `app/db_models.py` | Schema is fine, just needs data cleanup |
