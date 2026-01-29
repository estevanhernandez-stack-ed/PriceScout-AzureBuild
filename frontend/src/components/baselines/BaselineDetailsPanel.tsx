/**
 * Baseline Details Panel
 *
 * Shows ALL individual baselines in a granular, sortable/filterable table.
 * Allows users to verify specific baselines before trusting aggregated views.
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Target,
  Search,
  Loader2,
  AlertCircle,
  Download,
  ArrowUpDown,
  Tag,
  Film,
  Trash2,
} from 'lucide-react';
import { useBaselines, useCompanyProfiles, useDeduplicateBaselines, type SavedBaseline, type DiscountDayInfo } from '@/hooks/api';
import { useToast } from '@/hooks/use-toast';

type SortField = 'theater_name' | 'ticket_type' | 'format' | 'daypart' | 'baseline_price' | 'sample_count' | 'variance_percent';
type SortDirection = 'asc' | 'desc';

export function BaselineDetailsPanel() {
  const { toast } = useToast();

  // Filters
  const [theaterFilter, setTheaterFilter] = useState('');
  const [ticketTypeFilter, setTicketTypeFilter] = useState<string>('all');
  const [formatFilter, setFormatFilter] = useState<string>('all');
  const [daypartFilter, setDaypartFilter] = useState<string>('all');

  // State for deduplication confirmation
  const [pendingDedup, setPendingDedup] = useState<{ toDelete: number; wouldRemain: number } | null>(null);

  // Sorting
  const [sortField, setSortField] = useState<SortField>('theater_name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Fetch all active baselines
  const { data: baselines, isLoading } = useBaselines({ activeOnly: true });

  // Fetch company profiles for discount day detection
  const { data: profilesData } = useCompanyProfiles();

  // Deduplication mutation
  const deduplicateMutation = useDeduplicateBaselines();

  // Build a map of circuit -> discount days for quick lookup
  const discountDayMap = useMemo(() => {
    const map = new Map<string, DiscountDayInfo[]>();
    if (profilesData?.profiles) {
      for (const profile of profilesData.profiles) {
        if (profile.has_discount_days && profile.discount_days.length > 0) {
          map.set(profile.circuit_name.toLowerCase(), profile.discount_days);
        }
      }
    }
    return map;
  }, [profilesData]);

  // Extract unique values for filters
  const filterOptions = useMemo(() => {
    if (!baselines) return { ticketTypes: [], formats: [], dayparts: [] };

    const ticketTypes = [...new Set(baselines.map((b) => b.ticket_type))].sort();
    const formats = [...new Set(baselines.map((b) => b.format || 'Standard'))].sort();
    const dayparts = [...new Set(baselines.map((b) => b.daypart).filter(Boolean))].sort() as string[];

    return { ticketTypes, formats, dayparts };
  }, [baselines]);

  // Filter and sort baselines
  const filteredBaselines = useMemo(() => {
    if (!baselines) return [];

    let result = baselines.filter((b) => {
      // Theater name filter (case-insensitive)
      if (theaterFilter && !b.theater_name.toLowerCase().includes(theaterFilter.toLowerCase())) {
        return false;
      }

      // Ticket type filter
      if (ticketTypeFilter !== 'all' && b.ticket_type !== ticketTypeFilter) {
        return false;
      }

      // Format filter
      if (formatFilter !== 'all') {
        const baselineFormat = b.format || 'Standard';
        if (baselineFormat !== formatFilter) {
          return false;
        }
      }

      // Daypart filter
      if (daypartFilter !== 'all') {
        const baselineDaypart = b.daypart || 'all';
        if (baselineDaypart !== daypartFilter) {
          return false;
        }
      }

      return true;
    });

    // Sort
    result.sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortField) {
        case 'theater_name':
          aVal = a.theater_name;
          bVal = b.theater_name;
          break;
        case 'ticket_type':
          aVal = a.ticket_type;
          bVal = b.ticket_type;
          break;
        case 'format':
          aVal = a.format || 'Standard';
          bVal = b.format || 'Standard';
          break;
        case 'daypart':
          aVal = a.daypart || '';
          bVal = b.daypart || '';
          break;
        case 'baseline_price':
          aVal = a.baseline_price;
          bVal = b.baseline_price;
          break;
        case 'sample_count':
          aVal = a.sample_count ?? 0;
          bVal = b.sample_count ?? 0;
          break;
        case 'variance_percent':
          aVal = a.variance_percent ?? 0;
          bVal = b.variance_percent ?? 0;
          break;
        default:
          return 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortDirection === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return result;
  }, [baselines, theaterFilter, ticketTypeFilter, formatFilter, daypartFilter, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const handleExportCsv = () => {
    if (!filteredBaselines.length) return;

    const headers = ['Theater', 'Ticket Type', 'Format', 'Daypart', 'Baseline Price', 'Avg Price', 'Samples', 'Variance %'];
    const rows = filteredBaselines.map((b) => [
      b.theater_name,
      b.ticket_type,
      b.format || 'Standard',
      b.daypart || 'All',
      b.baseline_price.toFixed(2),
      b.avg_price?.toFixed(2) ?? '',
      b.sample_count ?? '',
      b.variance_percent?.toFixed(1) ?? '',
    ]);

    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `baselines-export-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDeduplicate = async (dryRun: boolean) => {
    try {
      const result = await deduplicateMutation.mutateAsync(dryRun);
      if (dryRun) {
        if (result.to_delete === 0) {
          toast({
            title: 'No duplicates found',
            description: `${result.total_baselines} baselines are unique`,
          });
          setPendingDedup(null);
        } else {
          toast({
            title: `Found ${result.duplicate_groups} duplicate groups`,
            description: `Would remove ${result.to_delete} duplicates, keeping ${result.would_remain} unique baselines. Click "Remove Duplicates" to proceed.`,
          });
          setPendingDedup({ toDelete: result.to_delete ?? 0, wouldRemain: result.would_remain ?? 0 });
        }
      } else {
        toast({
          title: 'Duplicates removed',
          description: `Removed ${result.deleted} duplicates. ${result.after} baselines remaining.`,
        });
        setPendingDedup(null);
      }
    } catch (error) {
      toast({
        title: 'Failed to deduplicate',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const getSortIcon = (field: SortField) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 opacity-50" />;
    return <ArrowUpDown className={`h-3 w-3 ${sortDirection === 'asc' ? 'rotate-180' : ''}`} />;
  };

  // Check if a baseline is on a discount day and get the program info
  const getDiscountDayInfo = (baseline: SavedBaseline): DiscountDayInfo | null => {
    if (baseline.day_of_week === null) return null;

    // Extract circuit from theater name (first word, or known multi-word circuits)
    const theaterName = baseline.theater_name.toLowerCase();
    let circuit = baseline.theater_name.split(' ')[0].toLowerCase();

    // Handle known multi-word circuits
    if (theaterName.startsWith('movie tavern')) circuit = 'movie tavern';
    else if (theaterName.startsWith('studio movie')) circuit = 'studio movie grill';

    // Look up discount days from company profile
    const discountDays = discountDayMap.get(circuit);
    if (discountDays) {
      const discountDay = discountDays.find(dd => dd.day_of_week === baseline.day_of_week);
      if (discountDay) return discountDay;
    }

    // Fallback: Detect Tuesday with low variance as potential discount day
    if (baseline.day_of_week === 1 && (baseline.variance_percent ?? 100) < 3) {
      return {
        day_of_week: 1,
        day: 'Tuesday',
        price: baseline.baseline_price,
        program: 'Discount Tuesday',
        sample_count: baseline.sample_count ?? 0,
        variance_pct: baseline.variance_percent ?? 0,
        below_avg_pct: 0,
      };
    }

    return null;
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-blue-500" />
            Filter Baselines
          </CardTitle>
          <CardDescription>
            View and filter all individual baseline prices
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <Label>Theater Name</Label>
              <Input
                placeholder="Search theaters..."
                value={theaterFilter}
                onChange={(e) => setTheaterFilter(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>Ticket Type</Label>
              <Select value={ticketTypeFilter} onValueChange={setTicketTypeFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  {filterOptions.ticketTypes.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Format</Label>
              <Select value={formatFilter} onValueChange={setFormatFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All formats" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Formats</SelectItem>
                  {filterOptions.formats.map((format) => (
                    <SelectItem key={format} value={format}>
                      {format}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Daypart</Label>
              <Select value={daypartFilter} onValueChange={setDaypartFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All dayparts" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Dayparts</SelectItem>
                  {filterOptions.dayparts.map((daypart) => (
                    <SelectItem key={daypart} value={daypart}>
                      {daypart.charAt(0).toUpperCase() + daypart.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              Showing {filteredBaselines.length} of {baselines?.length ?? 0} baselines
            </div>
            <div className="flex items-center gap-2">
              {pendingDedup ? (
                <>
                  <span className="text-sm text-orange-600">
                    {pendingDedup.toDelete} duplicates found
                  </span>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDeduplicate(false)}
                    disabled={deduplicateMutation.isPending}
                  >
                    {deduplicateMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4 mr-2" />
                    )}
                    Remove Duplicates
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPendingDedup(null)}
                    disabled={deduplicateMutation.isPending}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDeduplicate(true)}
                  disabled={deduplicateMutation.isPending || !baselines?.length}
                >
                  {deduplicateMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Check Duplicates
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={handleExportCsv} disabled={!filteredBaselines.length}>
                <Download className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-green-500" />
            Baseline Details
            {filteredBaselines.length > 0 && (
              <Badge variant="secondary">{filteredBaselines.length}</Badge>
            )}
          </CardTitle>
          <CardDescription>
            All individual baselines with granular detail. Click column headers to sort.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredBaselines.length > 0 ? (
            <div className="rounded-md border max-h-[600px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleSort('theater_name')}
                    >
                      <div className="flex items-center gap-1">
                        Theater
                        {getSortIcon('theater_name')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleSort('ticket_type')}
                    >
                      <div className="flex items-center gap-1">
                        Ticket Type
                        {getSortIcon('ticket_type')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleSort('format')}
                    >
                      <div className="flex items-center gap-1">
                        Format
                        {getSortIcon('format')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleSort('daypart')}
                    >
                      <div className="flex items-center gap-1">
                        Daypart
                        {getSortIcon('daypart')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50 text-right"
                      onClick={() => handleSort('sample_count')}
                    >
                      <div className="flex items-center justify-end gap-1">
                        Samples
                        {getSortIcon('sample_count')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50 text-right"
                      onClick={() => handleSort('baseline_price')}
                    >
                      <div className="flex items-center justify-end gap-1">
                        Baseline
                        {getSortIcon('baseline_price')}
                      </div>
                    </TableHead>
                    <TableHead
                      className="cursor-pointer hover:bg-muted/50 text-right"
                      onClick={() => handleSort('variance_percent')}
                    >
                      <div className="flex items-center justify-end gap-1">
                        Variance
                        {getSortIcon('variance_percent')}
                      </div>
                    </TableHead>
                    <TableHead className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        Effective
                      </div>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredBaselines.slice(0, 200).map((baseline) => (
                    <TableRow key={baseline.baseline_id}>
                      <TableCell className="font-medium max-w-[200px] truncate">
                        {baseline.theater_name}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 flex-wrap">
                          {baseline.ticket_type}
                          {(() => {
                            const discountInfo = getDiscountDayInfo(baseline);
                            if (discountInfo) {
                              return (
                                <Badge
                                  variant="secondary"
                                  className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 text-xs"
                                  title={`${discountInfo.program} - $${discountInfo.price.toFixed(2)}`}
                                >
                                  <Tag className="h-2 w-2 mr-1" />
                                  {discountInfo.program.length > 15
                                    ? discountInfo.program.slice(0, 12) + '...'
                                    : discountInfo.program}
                                </Badge>
                              );
                            }
                            return null;
                          })()}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          {baseline.format || 'Standard'}
                          {baseline.is_premium && (
                            <Badge variant="outline" className="text-xs">
                              <Film className="h-2 w-2 mr-1" />
                              PLF
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {baseline.daypart ? (
                          <Badge
                            variant={
                              baseline.daypart === 'matinee'
                                ? 'secondary'
                                : baseline.daypart === 'evening'
                                ? 'default'
                                : 'outline'
                            }
                            className="text-xs"
                          >
                            {baseline.daypart === 'matinee'
                              ? 'Matinee'
                              : baseline.daypart === 'evening'
                              ? 'Evening'
                              : baseline.daypart === 'late'
                              ? 'Late'
                              : baseline.daypart}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground text-xs">All</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {baseline.sample_count ?? '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono font-bold">
                        ${baseline.baseline_price.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        {baseline.variance_percent != null ? (
                          <span
                            className={
                              baseline.variance_percent < 3
                                ? 'text-green-600'
                                : baseline.variance_percent > 15
                                ? 'text-orange-500'
                                : ''
                            }
                          >
                            {baseline.variance_percent.toFixed(1)}%
                          </span>
                        ) : (
                          '-'
                        )}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {baseline.effective_from ? baseline.effective_from.slice(0, 10) : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <AlertCircle className="h-12 w-12 mb-4" />
              <p>No baselines found</p>
              <p className="text-sm">
                {baselines?.length === 0
                  ? 'Discover baselines from My Markets or Company Profiles'
                  : 'Try adjusting your filters'}
              </p>
            </div>
          )}

          {filteredBaselines.length > 200 && (
            <p className="text-sm text-muted-foreground mt-2 text-center">
              Showing first 200 of {filteredBaselines.length} baselines. Use filters to narrow results.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Legend / Help */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Understanding the Table</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 text-xs">
              <Tag className="h-2 w-2 mr-1" />
              $5 Tuesdays
            </Badge>
            <span>Detected discount day program from Company Profile (hover for details)</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              <Film className="h-2 w-2 mr-1" />
              PLF
            </Badge>
            <span>Premium Large Format (IMAX, Dolby, etc.) - expect higher prices</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-green-600">Low Variance (&lt;3%)</span>
            <span>= Consistent pricing, high confidence baseline</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-orange-500">High Variance (&gt;15%)</span>
            <span>= Variable pricing, may need review</span>
          </div>
          {discountDayMap.size > 0 && (
            <div className="mt-3 pt-3 border-t">
              <div className="font-medium text-foreground mb-1">Detected Discount Programs:</div>
              <div className="flex flex-wrap gap-2">
                {Array.from(discountDayMap.entries()).map(([circuit, days]) => (
                  <span key={circuit} className="text-xs">
                    <strong className="capitalize">{circuit}:</strong>{' '}
                    {days.map(d => d.program).join(', ')}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
