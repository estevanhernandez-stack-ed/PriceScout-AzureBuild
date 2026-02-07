/**
 * CompetitorComparisonPanel - Side-by-side pricing comparison within a market
 *
 * Dynamically discovers ALL unique ticket type/format/daypart combinations
 * from actual baselines, normalizing names so equivalent categories merge
 * across circuits (e.g., "General Admission" → "Adult").
 */

import { useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TrendingUp, TrendingDown, Minus, Tag, Building2, Target } from 'lucide-react';
import type { CompanyProfile } from '@/hooks/api/useCompanyProfiles';
import type { SavedBaseline } from '@/hooks/api/useBaselines';

interface Theater {
  name: string;
  isYours: boolean;
}

interface CompetitorComparisonPanelProps {
  theaters: Theater[];
  baselines: SavedBaseline[];
  profiles: Record<string, CompanyProfile>;
}

// Get circuit name from theater name
function getCircuit(theaterName: string): string {
  const words = theaterName.split(' ');
  const multiWord: Record<string, string> = {
    'Movie Tavern': 'Movie Tavern',
    'Studio Movie': 'Studio Movie Grill',
  };
  if (words.length >= 2) {
    const key = `${words[0]} ${words[1]}`;
    if (multiWord[key]) return multiWord[key];
  }
  return words[0] || theaterName;
}

// ---------------------------------------------------------------------------
// Normalization: merge equivalent names from different data sources
// ---------------------------------------------------------------------------

// Ticket type aliases — maps variant names to a canonical name.
// "General Admission", "General 13+", etc. all become "Adult".
const TICKET_TYPE_ALIASES: Record<string, string> = {
  'general admission': 'Adult',
  'general 13+': 'Adult',
  'general': 'Adult',
  'admission': 'Adult',
  'adults': 'Adult',
  'admission v': 'Adult',
  'children': 'Child',
  'kid': 'Child',
  'kids': 'Child',
  'kids ages 2-12': 'Child',
  'seniors': 'Senior',
  'event senior': 'Senior',
  'early': 'Early Bird',
  'early bird': 'Early Bird',
  'lfx early bird': 'Early Bird',
  'bargain': 'Matinee',
  'bargain wednesday': 'Discount Day',
  'wednesday 50off': 'Discount Day',
  'rcc value day': 'Discount Day',
  '3d discount day': 'Discount Day',
  // Marcus Loyalty Member pricing IS their discount day pricing ($5 Tuesdays + tax)
  'loyalty member': 'Discount Day',
  'ac loyalty member': 'Discount Day',
  'tues mat': 'Matinee',
  'matine': 'Matinee',
  'matine prime': 'Matinee',
};

function normalizeTicketType(ticketType: string): string {
  const alias = TICKET_TYPE_ALIASES[ticketType.toLowerCase().trim()];
  if (alias) return alias;
  // Title-case the first letter
  return ticketType.charAt(0).toUpperCase() + ticketType.slice(1);
}

// Daypart normalization — collapse to two core dayparts: Matinee and Prime.
// Late Night and Twilight are the same price as Prime for most circuits.
// EntTelligence uses lowercase ("matinee", "evening", "late").
// Fandango uses title-case ("Matinee", "Prime", "Twilight", "Late Night").
const DAYPART_ALIASES: Record<string, string> = {
  matinee: 'Matinee',
  evening: 'Prime',
  prime: 'Prime',
  twilight: 'Prime',
  late: 'Prime',
  'late night': 'Prime',
};

function normalizeDaypart(daypart: string | null): string {
  if (!daypart || daypart === 'None') return '-';
  const alias = DAYPART_ALIASES[daypart.toLowerCase().trim()];
  return alias || daypart;
}

// Format normalization — merge "2D" and "Standard" into "Standard".
function normalizeFormat(format: string | null): string {
  if (!format) return 'Standard';
  const lower = format.toLowerCase();
  if (lower === '2d' || lower === 'standard') return 'Standard';
  if (lower === 'premium format') return 'Premium Format';
  return format;
}

// Circuit-specific ticket types that only make sense for the originating circuit.
// These go into a separate section, not the main cross-circuit comparison.
const CIRCUIT_SPECIFIC_TYPES = new Set([
  'discount day',
  'special event',
  'event',
]);

function isCircuitSpecific(normalizedType: string): boolean {
  return CIRCUIT_SPECIFIC_TYPES.has(normalizedType.toLowerCase());
}

// Build a human-readable label for a category
function buildCategoryLabel(ticketType: string, format: string, daypart: string): string {
  const parts: string[] = [ticketType];
  if (format !== 'Standard') parts.push(format);
  if (daypart && daypart !== '-') parts.push(`(${daypart})`);
  return parts.join(' ');
}

// Sort order for ticket types
const TICKET_TYPE_ORDER: Record<string, number> = {
  adult: 0,
  child: 1,
  senior: 2,
  matinee: 3,
  'early bird': 3,
  military: 4,
  student: 5,
  'loyalty member': 8,
  'ac loyalty member': 8,
  'discount day': 9,
};

// Sort order for formats
const FORMAT_ORDER: Record<string, number> = {
  standard: 0,
  'premium format': 1,
  imax: 2,
  'dolby cinema': 3,
  dolby: 3,
  '3d': 4,
  'imax 3d': 5,
  rpx: 6,
  screenx: 7,
  '35mm': 8,
  '70mm': 8,
};

// Sort order for dayparts
const DAYPART_ORDER: Record<string, number> = {
  '-': 0,
  matinee: 1,
  prime: 2,
};

function getCategorySortKey(ticketType: string, format: string, daypart: string): number {
  const tt = TICKET_TYPE_ORDER[ticketType.toLowerCase()] ?? 10;
  const fmt = FORMAT_ORDER[format.toLowerCase()] ?? 10;
  const dp = DAYPART_ORDER[daypart.toLowerCase()] ?? 10;
  return tt * 10000 + fmt * 100 + dp;
}

interface ComparisonRow {
  key: string;
  label: string;
  ticketType: string;
  format: string;
  daypart: string;
  prices: Record<string, { price: number | null; samples: number }>;
  minPrice: number | null;
  maxPrice: number | null;
  sortKey: number;
  isCircuitSpecific: boolean;
}

export function CompetitorComparisonPanel({
  theaters,
  baselines,
  profiles,
}: CompetitorComparisonPanelProps) {
  // Dynamically discover all categories from baselines and build comparison
  const comparisonData = useMemo(() => {
    // Group baselines by theater
    const baselinesByTheater: Record<string, SavedBaseline[]> = {};
    theaters.forEach((t) => {
      baselinesByTheater[t.name] = baselines.filter((bl) => bl.theater_name === t.name);
    });

    // Discover all unique NORMALIZED (ticket_type, format, daypart) combos
    const categorySet = new Set<string>();
    const categoryMeta: Record<string, { ticketType: string; format: string; daypart: string }> = {};

    theaters.forEach((t) => {
      const theaterBaselines = baselinesByTheater[t.name] || [];
      theaterBaselines.forEach((bl) => {
        const ticketType = normalizeTicketType(bl.ticket_type);
        const format = normalizeFormat(bl.format);
        const daypart = normalizeDaypart(bl.daypart);
        const key = `${ticketType}|${format}|${daypart}`;
        if (!categorySet.has(key)) {
          categorySet.add(key);
          categoryMeta[key] = { ticketType, format, daypart };
        }
      });
    });

    // Build rows for each discovered category
    const rows: ComparisonRow[] = [];

    categorySet.forEach((catKey) => {
      const meta = categoryMeta[catKey];
      const prices: Record<string, { price: number | null; samples: number }> = {};
      let minPrice: number | null = null;
      let maxPrice: number | null = null;

      theaters.forEach((theater) => {
        const theaterBaselines = baselinesByTheater[theater.name] || [];
        // Match baselines after normalizing their fields
        const matching = theaterBaselines.filter((bl) => {
          return (
            normalizeTicketType(bl.ticket_type) === meta.ticketType &&
            normalizeFormat(bl.format) === meta.format &&
            normalizeDaypart(bl.daypart) === meta.daypart
          );
        });

        if (matching.length > 0) {
          const avgPrice = matching.reduce((sum, bl) => sum + bl.baseline_price, 0) / matching.length;
          const totalSamples = matching.reduce((sum, bl) => sum + (bl.sample_count ?? 0), 0);
          prices[theater.name] = { price: avgPrice, samples: totalSamples };

          if (minPrice === null || avgPrice < minPrice) minPrice = avgPrice;
          if (maxPrice === null || avgPrice > maxPrice) maxPrice = avgPrice;
        } else {
          prices[theater.name] = { price: null, samples: 0 };
        }
      });

      rows.push({
        key: catKey,
        label: buildCategoryLabel(meta.ticketType, meta.format, meta.daypart),
        ticketType: meta.ticketType,
        format: meta.format,
        daypart: meta.daypart,
        prices,
        minPrice,
        maxPrice,
        sortKey: getCategorySortKey(meta.ticketType, meta.format, meta.daypart),
        isCircuitSpecific: isCircuitSpecific(meta.ticketType),
      });
    });

    // Sort: ticket type → format → daypart
    rows.sort((a, b) => a.sortKey - b.sortKey);

    return rows;
  }, [theaters, baselines]);

  // Split rows: comparable, circuit-specific (non-discount), and discount day
  // Discount Day rows are handled by the dedicated Discount Day section at the bottom.
  const comparableRows = comparisonData.filter((r) => !r.isCircuitSpecific);
  const circuitSpecificRows = comparisonData.filter(
    (r) => r.isCircuitSpecific && r.ticketType.toLowerCase() !== 'discount day'
  );

  // Get discount day info per theater — merge company profile with discovered baselines.
  // Profile provides the day name; baselines (Loyalty Member, Discount Day types) provide
  // the actual observed price if available.
  const discountDays = useMemo(() => {
    const result: Record<string, { day: string; price: number | null; source: string } | null> = {};
    theaters.forEach((t) => {
      const circuit = getCircuit(t.name);
      const profile = profiles[circuit];

      // Check if any "Discount Day" baselines exist for this theater
      const discountBaselines = baselines.filter(
        (bl) =>
          bl.theater_name === t.name &&
          normalizeTicketType(bl.ticket_type) === 'Discount Day'
      );
      const avgDiscountPrice =
        discountBaselines.length > 0
          ? discountBaselines.reduce((s, bl) => s + bl.baseline_price, 0) / discountBaselines.length
          : null;

      if (profile?.has_discount_days && profile.discount_days.length > 0) {
        const dd = profile.discount_days[0];
        result[t.name] = {
          day: dd.day.slice(0, 3),
          price: avgDiscountPrice ?? dd.price,
          source: avgDiscountPrice !== null ? 'baseline' : 'profile',
        };
      } else if (avgDiscountPrice !== null) {
        // No profile discount day configured, but baselines found (e.g., Loyalty Member)
        result[t.name] = { day: '?', price: avgDiscountPrice, source: 'baseline' };
      } else {
        result[t.name] = null;
      }
    });
    return result;
  }, [theaters, baselines, profiles]);

  // Separate your theaters and competitors
  const yourTheaters = theaters.filter((t) => t.isYours);
  const competitors = theaters.filter((t) => !t.isYours);
  const allTheaters = [...yourTheaters, ...competitors];

  if (theaters.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-orange-500" />
            Competitor Comparison
          </CardTitle>
          <CardDescription>Select a market to compare pricing across theaters</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const renderPriceCell = (row: ComparisonRow, theater: Theater) => {
    const data = row.prices[theater.name];
    const price = data?.price;
    const isMin = price !== null && price === row.minPrice && row.minPrice !== row.maxPrice;
    const isMax = price !== null && price === row.maxPrice && row.minPrice !== row.maxPrice;

    return (
      <TableCell key={theater.name} className="text-center">
        {price !== null ? (
          <div className="flex flex-col items-center gap-0.5">
            <span
              className={`font-semibold ${
                isMin ? 'text-green-600' : isMax ? 'text-red-600' : ''
              }`}
            >
              ${price.toFixed(2)}
              {isMin && <TrendingDown className="inline h-3 w-3 ml-1" />}
              {isMax && <TrendingUp className="inline h-3 w-3 ml-1" />}
            </span>
            {(data.samples ?? 0) > 0 && (
              <span className="text-xs text-muted-foreground">n={data.samples}</span>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground">
            <Minus className="h-4 w-4 inline" />
          </span>
        )}
      </TableCell>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5 text-orange-500" />
          Competitor Pricing Comparison
        </CardTitle>
        <CardDescription>
          Side-by-side baseline price comparison for {theaters.length} theaters in this market
          — {comparableRows.length} pricing categories
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-background z-10 min-w-[220px]">
                  Category
                </TableHead>
                {allTheaters.map((theater) => (
                  <TableHead key={theater.name} className="text-center min-w-[120px]">
                    <div className="flex flex-col items-center gap-1">
                      {theater.isYours ? (
                        <Badge variant="outline" className="bg-purple-100 text-purple-700 text-xs">
                          <Building2 className="h-3 w-3 mr-1" />
                          Yours
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">Competitor</Badge>
                      )}
                      <span className="text-xs font-normal truncate max-w-[100px]" title={theater.name}>
                        {getCircuit(theater.name)}
                      </span>
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {/* Main comparable rows */}
              {comparableRows.map((row) => {
                const hasAnyData = Object.values(row.prices).some((p) => p.price !== null);
                if (!hasAnyData) return null;

                return (
                  <TableRow key={row.key}>
                    <TableCell className="sticky left-0 bg-background z-10">
                      <div>
                        <span className="font-medium">{row.label}</span>
                        {row.format !== 'Standard' && (
                          <Badge variant="outline" className="ml-1.5 text-xs py-0">
                            {row.format}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    {allTheaters.map((theater) => renderPriceCell(row, theater))}
                  </TableRow>
                );
              })}

              {/* Circuit-specific rows (Loyalty Member, etc.) */}
              {circuitSpecificRows.length > 0 && (
                <>
                  <TableRow>
                    <TableCell
                      colSpan={allTheaters.length + 1}
                      className="sticky left-0 bg-muted/50 z-10 text-xs text-muted-foreground font-medium py-1.5"
                    >
                      Circuit-Specific Pricing
                    </TableCell>
                  </TableRow>
                  {circuitSpecificRows.map((row) => {
                    const hasAnyData = Object.values(row.prices).some((p) => p.price !== null);
                    if (!hasAnyData) return null;

                    return (
                      <TableRow key={row.key} className="opacity-75">
                        <TableCell className="sticky left-0 bg-background z-10">
                          <div>
                            <span className="font-medium text-muted-foreground">{row.label}</span>
                            {row.format !== 'Standard' && (
                              <Badge variant="outline" className="ml-1.5 text-xs py-0">
                                {row.format}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        {allTheaters.map((theater) => renderPriceCell(row, theater))}
                      </TableRow>
                    );
                  })}
                </>
              )}

              {/* Discount Day Row */}
              <TableRow className="bg-blue-50/50 dark:bg-blue-950/20">
                <TableCell className="sticky left-0 bg-blue-50 dark:bg-blue-950/20 z-10 font-medium">
                  <div className="flex items-center gap-1">
                    <Tag className="h-4 w-4 text-blue-600" />
                    Discount Day
                  </div>
                </TableCell>
                {allTheaters.map((theater) => {
                  const dd = discountDays[theater.name];
                  return (
                    <TableCell key={theater.name} className="text-center">
                      {dd ? (
                        <div className="flex flex-col items-center gap-0.5">
                          <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                            {dd.day} {dd.price !== null ? `$${dd.price.toFixed(2)}` : ''}
                          </Badge>
                          {dd.source === 'baseline' && (
                            <span className="text-[10px] text-muted-foreground">from baselines</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-sm">None</span>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            </TableBody>
          </Table>
        </div>

        {/* Legend */}
        <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <TrendingDown className="h-4 w-4 text-green-600" />
            Lowest in market
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp className="h-4 w-4 text-red-600" />
            Highest in market
          </span>
          <span>All prices tax-inclusive (estimated tax applied where needed)</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default CompetitorComparisonPanel;
