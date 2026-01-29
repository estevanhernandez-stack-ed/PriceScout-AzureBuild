/**
 * CompetitorComparisonPanel - Side-by-side pricing comparison within a market
 *
 * Shows a comparison table of prices across theaters for common ticket types:
 * - Adult Standard
 * - Adult IMAX (or other PLF)
 * - Matinee
 * - Discount Day pricing
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

// Common categories to compare
const COMPARISON_CATEGORIES = [
  { key: 'adult_standard', label: 'Adult Standard', ticketTypes: ['Adult', 'General Admission'], format: 'Standard' },
  { key: 'child_standard', label: 'Child Standard', ticketTypes: ['Child', 'Kids'], format: 'Standard' },
  { key: 'senior_standard', label: 'Senior Standard', ticketTypes: ['Senior', 'Seniors'], format: 'Standard' },
  { key: 'matinee', label: 'Matinee', ticketTypes: ['Matinee', 'Early Bird', 'Bargain'], format: 'Standard' },
  { key: 'adult_imax', label: 'Adult IMAX', ticketTypes: ['Adult', 'General Admission'], format: 'IMAX' },
  { key: 'adult_dolby', label: 'Adult Dolby', ticketTypes: ['Adult', 'General Admission'], format: 'Dolby Cinema' },
];

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

export function CompetitorComparisonPanel({
  theaters,
  baselines,
  profiles,
}: CompetitorComparisonPanelProps) {
  // Build comparison data
  const comparisonData = useMemo(() => {
    // Group baselines by theater
    const baselinesByTheater: Record<string, SavedBaseline[]> = {};
    theaters.forEach((t) => {
      baselinesByTheater[t.name] = baselines.filter((bl) => bl.theater_name === t.name);
    });

    // For each category, find average prices per theater
    const results: Array<{
      category: string;
      label: string;
      prices: Record<string, { price: number | null; samples: number }>;
      minPrice: number | null;
      maxPrice: number | null;
    }> = [];

    COMPARISON_CATEGORIES.forEach((cat) => {
      const categoryPrices: Record<string, { price: number | null; samples: number }> = {};
      let minPrice: number | null = null;
      let maxPrice: number | null = null;

      theaters.forEach((theater) => {
        const theaterBaselines = baselinesByTheater[theater.name] || [];

        // Find matching baselines for this category
        const matching = theaterBaselines.filter((bl) => {
          const ticketMatch = cat.ticketTypes.some(
            (t) => bl.ticket_type.toLowerCase().includes(t.toLowerCase())
          );
          const formatMatch =
            cat.format === 'Standard'
              ? !bl.format || bl.format.toLowerCase() === 'standard' || bl.format.toLowerCase() === '2d'
              : bl.format?.toLowerCase().includes(cat.format.toLowerCase());
          return ticketMatch && formatMatch;
        });

        if (matching.length > 0) {
          const avgPrice = matching.reduce((sum, bl) => sum + bl.baseline_price, 0) / matching.length;
          const totalSamples = matching.reduce((sum, bl) => sum + (bl.sample_count ?? 0), 0);
          categoryPrices[theater.name] = { price: avgPrice, samples: totalSamples };

          if (minPrice === null || avgPrice < minPrice) minPrice = avgPrice;
          if (maxPrice === null || avgPrice > maxPrice) maxPrice = avgPrice;
        } else {
          categoryPrices[theater.name] = { price: null, samples: 0 };
        }
      });

      results.push({
        category: cat.key,
        label: cat.label,
        prices: categoryPrices,
        minPrice,
        maxPrice,
      });
    });

    return results;
  }, [theaters, baselines]);

  // Get discount day info per theater
  const discountDays = useMemo(() => {
    const result: Record<string, { day: string; price: number } | null> = {};
    theaters.forEach((t) => {
      const circuit = getCircuit(t.name);
      const profile = profiles[circuit];
      if (profile?.has_discount_days && profile.discount_days.length > 0) {
        const dd = profile.discount_days[0];
        result[t.name] = { day: dd.day.slice(0, 3), price: dd.price };
      } else {
        result[t.name] = null;
      }
    });
    return result;
  }, [theaters, profiles]);

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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5 text-orange-500" />
          Competitor Pricing Comparison
        </CardTitle>
        <CardDescription>
          Side-by-side baseline price comparison for {theaters.length} theaters in this market
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-background z-10 min-w-[140px]">Category</TableHead>
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
              {comparisonData.map((row) => {
                // Skip rows with no data
                const hasAnyData = Object.values(row.prices).some((p) => p.price !== null);
                if (!hasAnyData) return null;

                return (
                  <TableRow key={row.category}>
                    <TableCell className="sticky left-0 bg-background z-10 font-medium">
                      {row.label}
                    </TableCell>
                    {allTheaters.map((theater) => {
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
                                  isMin
                                    ? 'text-green-600'
                                    : isMax
                                    ? 'text-red-600'
                                    : ''
                                }`}
                              >
                                ${price.toFixed(2)}
                                {isMin && <TrendingDown className="inline h-3 w-3 ml-1" />}
                                {isMax && <TrendingUp className="inline h-3 w-3 ml-1" />}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                n={data.samples}
                              </span>
                            </div>
                          ) : (
                            <span className="text-muted-foreground">
                              <Minus className="h-4 w-4 inline" />
                            </span>
                          )}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                );
              })}

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
                        <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                          {dd.day} ${dd.price.toFixed(2)}
                        </Badge>
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
        <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <TrendingDown className="h-4 w-4 text-green-600" />
            Lowest in market
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp className="h-4 w-4 text-red-600" />
            Highest in market
          </span>
          <span>n = sample count</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default CompetitorComparisonPanel;
