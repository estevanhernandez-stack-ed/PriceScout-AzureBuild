# Special Events & Alternative Content Tracking Plan

## Problem Statement

The Discount Day Status panel shows 283 theaters with "pricing variance" - but many of these are **not compliance issues**. They're special events and alternative content that are intentionally priced differently:

- Fathom Events (classic films, documentaries, anime)
- Met Opera / NT Live broadcasts
- Concert films (Taylor Swift Eras Tour, Beyoncé, etc.)
- Sports events (NFL Sunday Ticket)
- Anime releases (Crunchyroll, Ghibli Fest)
- Anniversary re-releases (50th Anniversary, Director's Cut)

**Current State**: Runtime detection only via keywords in `alert_service.py`. No persistent tracking, no database fields, no way to analyze circuit pricing strategies for special content.

---

## Circuit Pricing Strategies (Known)

### Marcus Theatres
- **Alternative Content (AC)** - Standard ticket type for special events
- **Loyalty AC** - Discounted AC ticket for loyalty members (applies on discount days)
- Uses separate ticket types rather than just price adjustments

### AMC
- Prices Fathom Events at premium (~$15-18)
- AMC Stubs discount may or may not apply to special events
- Needs investigation

### Regal
- Fathom Events typically $15-18
- RCC Value Day discount usually doesn't apply to special events
- Needs investigation

### Cinemark
- XD surcharge applies to special content
- Discount Tuesday may have exclusions
- Needs investigation

---

## Database Schema Changes

### Option A: Add Fields to Existing Tables

```sql
-- Add to films table
ALTER TABLE films ADD COLUMN content_type VARCHAR(50) DEFAULT 'standard';
ALTER TABLE films ADD COLUMN is_alternative_content BOOLEAN DEFAULT FALSE;
ALTER TABLE films ADD COLUMN content_category VARCHAR(100); -- 'fathom', 'opera', 'concert', etc.
ALTER TABLE films ADD COLUMN special_event_source VARCHAR(100); -- 'Fathom Events', 'Met Opera', etc.

-- Add to prices table for historical tracking
ALTER TABLE prices ADD COLUMN is_alternative_content BOOLEAN DEFAULT FALSE;
```

### Option B: New Dedicated Table (Recommended)

```sql
CREATE TABLE alternative_content_films (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    film_title VARCHAR(500) NOT NULL,
    film_id INTEGER REFERENCES films(id),  -- Link if matched

    -- Classification
    content_type VARCHAR(50) NOT NULL,  -- 'fathom_event', 'opera', 'concert', 'anime', 'sports', 'classic_rerelease'
    content_source VARCHAR(100),  -- 'Fathom Events', 'Met Opera', 'NT Live', 'Crunchyroll'

    -- Detection
    detected_by VARCHAR(50),  -- 'auto_title', 'auto_price', 'manual'
    detection_confidence DECIMAL(3,2),  -- 0.00 to 1.00

    -- Tracking
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,

    -- Manual override
    manually_verified BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Track circuit pricing strategies for alternative content
CREATE TABLE circuit_ac_pricing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_name VARCHAR(200) NOT NULL,
    content_type VARCHAR(50) NOT NULL,

    -- Ticket types used
    standard_ticket_type VARCHAR(100),  -- 'AC Adult', 'Alternative Content'
    discount_ticket_type VARCHAR(100),  -- 'Loyalty AC', NULL if no discount

    -- Pricing patterns
    typical_price_min DECIMAL(10,2),
    typical_price_max DECIMAL(10,2),
    discount_day_applies BOOLEAN DEFAULT FALSE,
    discount_day_ticket_type VARCHAR(100),  -- What ticket type is used on discount days

    -- Notes
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## Content Type Categories

| Category | Examples | Detection Keywords |
|----------|----------|-------------------|
| `fathom_event` | Classic films, documentaries | "fathom", "fathom events" |
| `opera_broadcast` | Met Opera, Royal Opera | "met opera", "royal opera", "opera" |
| `theater_broadcast` | NT Live, Broadway HD | "nt live", "national theatre", "broadway" |
| `concert_film` | Eras Tour, Renaissance | "concert", "tour", "live in concert" |
| `anime_event` | Ghibli Fest, Crunchyroll | "ghibli", "anime", "crunchyroll", "funimation" |
| `sports_event` | NFL, WWE, UFC | "nfl", "wwe", "ufc", "boxing" |
| `classic_rerelease` | Anniversary editions | "anniversary", "25th", "50th", "remaster" |
| `marathon` | Double/triple features | "marathon", "double feature", "trilogy" |
| `special_presentation` | IMAX experiences, director Q&A | "special presentation", "q&a", "premiere" |

---

## Auto-Detection Logic

### Title-Based Detection
```python
CONTENT_TYPE_PATTERNS = {
    'fathom_event': [
        r'fathom',
        r'\(fathom events?\)',
    ],
    'opera_broadcast': [
        r'met opera',
        r'metropolitan opera',
        r'royal opera',
        r'la traviata|carmen|tosca|rigoletto',  # Common operas
    ],
    'theater_broadcast': [
        r'nt live',
        r'national theatre',
        r'broadway hd',
    ],
    'concert_film': [
        r'(in )?concert',
        r'the tour',
        r'eras tour',
        r'renaissance',
    ],
    'anime_event': [
        r'ghibli',
        r'crunchyroll',
        r'funimation',
        r'(subbed|dubbed)$',
    ],
    'classic_rerelease': [
        r'\d{2}th anniversary',
        r'remaster(ed)?',
        r're-?release',
        r"director'?s cut",
    ],
}
```

### Price-Based Detection
- Films with ALL ticket types priced ≥$15 on non-premium formats
- Significant price variance from circuit's standard pricing
- Missing standard ticket types (only "AC" types present)

### Ticket Type Detection
- Presence of "AC", "Alternative Content", "Event" in ticket type name
- Absence of standard "Adult/Child/Senior" with presence of special types

---

## UI Components Needed

### 1. Updated Discount Day Status Panel
```
┌─────────────────────────────────────────────────────────────┐
│ ◇ Discount Day Status                                       │
│ $7.05 Tuesdays (Loyalty Member) compliance check            │
│                                                             │
│ [Tab: Compliance Issues (45)] [Tab: Alternative Content (238)]│
│                                                             │
│ === Compliance Issues Tab ===                               │
│ Theater          │ Expected │ Actual │ Status │ Film        │
│ Marcus Addison   │ $7.05    │ $11.00 │ +$3.95 │ Avatar 2    │
│                                                             │
│ === Alternative Content Tab ===                             │
│ Theater          │ Content Type │ Price  │ Film             │
│ AMC Rosemont     │ Fathom Event │ $15.52 │ Wicked (25th)    │
│ AMC Yorktown     │ Opera        │ $14.16 │ Met Opera: Tosca │
└─────────────────────────────────────────────────────────────┘
```

### 2. New Special Events Management Panel
- List all detected alternative content films
- Allow manual classification/override
- Show detection confidence
- Filter by content type, circuit, date range

### 3. Circuit AC Pricing Strategy View
- Show each circuit's approach to alternative content
- Ticket types used (AC Adult, Loyalty AC, etc.)
- Whether discount days apply
- Typical price ranges by content type

---

## API Endpoints

```
# Alternative Content Films
GET    /api/v1/alternative-content                    # List all AC films
GET    /api/v1/alternative-content/{film_id}          # Get specific film
POST   /api/v1/alternative-content                    # Manually add AC film
PUT    /api/v1/alternative-content/{film_id}          # Update classification
DELETE /api/v1/alternative-content/{film_id}          # Remove from AC list

# Auto-detection
POST   /api/v1/alternative-content/detect             # Run detection on recent films
GET    /api/v1/alternative-content/detect/preview     # Preview what would be detected

# Circuit AC Pricing
GET    /api/v1/circuits/{circuit}/ac-pricing          # Get circuit's AC pricing strategy
PUT    /api/v1/circuits/{circuit}/ac-pricing          # Update strategy
GET    /api/v1/circuits/ac-pricing/compare            # Compare all circuits

# Updated Discount Day Compliance
GET    /api/v1/discount-compliance/{circuit}?exclude_ac=true  # Exclude AC from compliance
```

---

## Implementation Phases

### Phase 1: Database & Detection (Foundation)
- [ ] Create `alternative_content_films` table
- [ ] Create `circuit_ac_pricing` table
- [ ] Implement title-based auto-detection
- [ ] Implement price-based detection
- [ ] Add ticket type detection for "AC" patterns

### Phase 2: API & Backend
- [ ] Create alternative content API router
- [ ] Add auto-detection endpoint
- [ ] Update discount compliance endpoint to exclude AC
- [ ] Add circuit AC pricing endpoints

### Phase 3: UI Updates
- [ ] Split Discount Day Status into tabs (Compliance vs AC)
- [ ] Add Alternative Content management panel
- [ ] Add Circuit AC Strategy view
- [ ] Add manual classification UI

### Phase 4: Circuit Strategy Population
- [ ] Document Marcus AC pricing (AC Adult, Loyalty AC)
- [ ] Investigate and document AMC AC pricing
- [ ] Investigate and document Regal AC pricing
- [ ] Investigate and document Cinemark AC pricing

---

## Success Metrics

1. **False Positive Reduction**: Discount day "variances" should drop from 283 to <50 true compliance issues
2. **AC Film Coverage**: >90% of Fathom/Opera/Concert films auto-detected
3. **Circuit Strategy Documentation**: All major circuits have documented AC pricing strategies
4. **User Efficiency**: Operators can quickly distinguish true pricing issues from expected AC pricing

---

## Files to Create/Modify

### New Files
- `api/routers/alternative_content.py` - API endpoints
- `app/alternative_content_service.py` - Detection and classification logic
- `frontend/src/components/baselines/AlternativeContentPanel.tsx` - Management UI
- `frontend/src/hooks/api/useAlternativeContent.ts` - React Query hooks
- `migrations/add_alternative_content_tables.py` - Database migration

### Modified Files
- `app/db_models.py` - Add new tables
- `api/routers/company_profiles.py` - Update discount compliance endpoint
- `frontend/src/components/baselines/DiscountDayStatusPanel.tsx` - Add tabs for AC vs compliance
- `app/alert_service.py` - Use persistent AC classification instead of runtime-only

---

## Open Questions

1. Should AC classification be per-film or per-showing? (A film could be both standard and Fathom depending on screening)
2. How do we handle films that transition? (e.g., wide release → Fathom re-release months later)
3. Should we track AC pricing history over time to detect strategy changes?
4. Do we need integration with external sources (Fathom Events calendar, etc.)?

---

*Created: 2026-01-27*
*Status: Planning*
