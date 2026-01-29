/**
 * Baseline Browser Component
 *
 * Hierarchical browser for viewing baselines by market and location.
 * Market -> Circuit -> Theater -> Individual Baselines
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useBaselineMarkets,
  useMarketDetail,
  useTheaterBaselines,
} from '@/hooks/api/useBaselines';
import {
  ChevronDown,
  ChevronRight,
  MapPin,
  Building2,
  Store,
  Search,
  RefreshCw,
  X,
} from 'lucide-react';

// Day type labels
const DAY_TYPE_LABELS: Record<string, string> = {
  weekday: 'Weekday',
  weekend: 'Weekend',
};

// Day of week labels (0=Monday, 6=Sunday)
const DAY_OF_WEEK_LABELS: Record<number, string> = {
  0: 'Mon',
  1: 'Tue',
  2: 'Wed',
  3: 'Thu',
  4: 'Fri',
  5: 'Sat',
  6: 'Sun',
};

// Daypart labels
const DAYPART_LABELS: Record<string, string> = {
  matinee: 'Matinee',
  evening: 'Evening',
  late: 'Late Night',
};

export function BaselineBrowser() {
  // State
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);
  const [expandedCircuits, setExpandedCircuits] = useState<Set<string>>(new Set());
  const [selectedTheater, setSelectedTheater] = useState<string | null>(null);

  // Data fetching
  const { data: markets, isLoading: marketsLoading, refetch: refetchMarkets } = useBaselineMarkets();
  const { data: marketDetail, isLoading: marketDetailLoading } = useMarketDetail(selectedMarket);
  const { data: theaterBaselines, isLoading: theaterLoading } = useTheaterBaselines(selectedTheater);

  // Filter markets by search term
  const filteredMarkets = markets?.filter(m =>
    m.market.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

  // Toggle circuit expansion
  const toggleCircuit = (circuitName: string) => {
    setExpandedCircuits(prev => {
      const next = new Set(prev);
      if (next.has(circuitName)) {
        next.delete(circuitName);
      } else {
        next.add(circuitName);
      }
      return next;
    });
  };

  // Handle market selection
  const handleMarketSelect = (market: string) => {
    if (selectedMarket === market) {
      setSelectedMarket(null);
      setSelectedTheater(null);
    } else {
      setSelectedMarket(market);
      setSelectedTheater(null);
      setExpandedCircuits(new Set());
    }
  };

  // Handle theater selection
  const handleTheaterSelect = (theaterName: string) => {
    setSelectedTheater(theaterName);
  };

  // Render circuit/theater tree for a specific market
  const renderMarketDetail = (marketName: string) => {
    if (selectedMarket !== marketName) return null;

    if (marketDetailLoading) {
      return (
        <div className="space-y-2 p-4 pl-8 bg-slate-50/50">
          {[1, 2, 3].map(i => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      );
    }

    if (!marketDetail || marketDetail.circuits.length === 0) {
      return (
        <div className="p-4 pl-8 bg-slate-50/50 text-slate-500">
          <p className="text-sm">No circuits found in this market.</p>
        </div>
      );
    }

    return (
      <div className="bg-slate-50/50">
        <div className="p-3 pl-8 border-b bg-white/50">
          <p className="text-sm text-slate-600">
            <strong>{marketDetail.total_theaters}</strong> theaters with{' '}
            <strong>{marketDetail.total_baselines.toLocaleString()}</strong> baselines
          </p>
        </div>
        {marketDetail.circuits.map((circuit) => (
          <div key={circuit.circuit_name} className="border-b last:border-b-0">
            {/* Circuit header */}
            <div
              className="p-3 pl-12 cursor-pointer hover:bg-slate-100 flex items-center justify-between"
              onClick={(e) => {
                e.stopPropagation();
                toggleCircuit(circuit.circuit_name);
              }}
            >
              <div className="flex items-center gap-2">
                {expandedCircuits.has(circuit.circuit_name) ? (
                  <ChevronDown className="h-4 w-4 text-slate-500" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-slate-400" />
                )}
                <Building2 className="h-4 w-4 text-slate-400" />
                <span className="font-medium text-slate-800">{circuit.circuit_name}</span>
              </div>
              <div className="flex gap-2">
                <Badge variant="outline" className="text-xs">
                  {circuit.theater_count} theaters
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {circuit.baseline_count.toLocaleString()} baselines
                </Badge>
              </div>
            </div>

            {/* Theaters list */}
            {expandedCircuits.has(circuit.circuit_name) && (
              <div className="bg-white border-t">
                {circuit.theaters.map((theater) => (
                  <div
                    key={theater.theater_name}
                    className={`p-2 pl-16 cursor-pointer hover:bg-blue-50 border-b last:border-b-0 ${
                      selectedTheater === theater.theater_name ? 'bg-blue-100' : ''
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTheaterSelect(theater.theater_name);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Store className="h-4 w-4 text-slate-400" />
                        <span className="text-sm text-slate-700">{theater.theater_name}</span>
                      </div>
                      <div className="flex gap-2 items-center">
                        {theater.formats.length > 0 && (
                          <div className="flex gap-1">
                            {theater.formats.slice(0, 3).map(f => (
                              <Badge key={f} variant="outline" className="text-[10px] px-1.5 py-0">
                                {f}
                              </Badge>
                            ))}
                            {theater.formats.length > 3 && (
                              <span className="text-[10px] text-slate-400">+{theater.formats.length - 3}</span>
                            )}
                          </div>
                        )}
                        <Badge variant="secondary" className="text-xs">
                          {theater.baseline_count} baselines
                        </Badge>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  // Render market list with inline detail expansion
  const renderMarketList = () => {
    if (marketsLoading) {
      return (
        <div className="space-y-2 p-4">
          {[1, 2, 3, 4, 5].map(i => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      );
    }

    if (!markets || markets.length === 0) {
      return (
        <div className="p-8 text-center text-slate-500">
          <MapPin className="h-12 w-12 mx-auto mb-4 text-slate-300" />
          <p className="font-medium">No Markets Found</p>
          <p className="text-sm mt-1">Run baseline discovery first to populate markets.</p>
        </div>
      );
    }

    return (
      <div className="divide-y divide-slate-100">
        {filteredMarkets.map((market) => (
          <div key={market.market}>
            {/* Market row */}
            <div
              className={`p-3 cursor-pointer transition-colors hover:bg-slate-50 ${
                selectedMarket === market.market ? 'bg-blue-50 border-l-4 border-blue-500' : ''
              }`}
              onClick={() => handleMarketSelect(market.market)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {selectedMarket === market.market ? (
                    <ChevronDown className="h-4 w-4 text-blue-500" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-slate-400" />
                  )}
                  <MapPin className="h-4 w-4 text-slate-400" />
                  <span className="font-medium text-slate-900">{market.market}</span>
                </div>
                <div className="flex gap-2">
                  <Badge variant="outline" className="text-xs">
                    {market.theater_count} theaters
                  </Badge>
                  <Badge className="text-xs bg-blue-100 text-blue-700 hover:bg-blue-100">
                    {market.baseline_count.toLocaleString()} baselines
                  </Badge>
                </div>
              </div>
            </div>
            {/* Market detail (circuits/theaters) - rendered inline when expanded */}
            {renderMarketDetail(market.market)}
          </div>
        ))}
      </div>
    );
  };

  // Render theater baselines detail
  const renderTheaterBaselines = () => {
    if (!selectedTheater) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400">
          <Store className="h-16 w-16 mb-4 text-slate-200" />
          <p className="font-medium text-slate-600">Select a Theater</p>
          <p className="text-sm mt-1">Choose a theater from the browser to view its baselines.</p>
        </div>
      );
    }

    if (theaterLoading) {
      return (
        <div className="p-4 space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
        </div>
      );
    }

    if (!theaterBaselines) {
      return (
        <div className="p-8 text-center text-slate-500">
          <p>No baselines found for this theater.</p>
        </div>
      );
    }

    return (
      <div className="h-full overflow-auto">
        {/* Header */}
        <div className="p-4 border-b bg-slate-50 sticky top-0 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-lg text-slate-900">{theaterBaselines.theater_name}</h3>
              <div className="flex gap-2 mt-1 text-sm text-slate-600">
                {theaterBaselines.circuit_name && (
                  <span>{theaterBaselines.circuit_name}</span>
                )}
                {theaterBaselines.market && (
                  <>
                    <span className="text-slate-300">|</span>
                    <span>{theaterBaselines.market}</span>
                  </>
                )}
              </div>
            </div>
            <Badge className="bg-blue-500">{theaterBaselines.total_baselines} Baselines</Badge>
          </div>
        </div>

        {/* Baselines table */}
        <div className="p-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticket Type</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Day</TableHead>
                <TableHead>Daypart</TableHead>
                <TableHead className="text-right">Baseline Price</TableHead>
                <TableHead className="text-right">Price Range</TableHead>
                <TableHead className="text-right">Samples</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {theaterBaselines.baselines.map((baseline, idx) => (
                <TableRow key={baseline.baseline_id || idx}>
                  <TableCell className="font-medium">{baseline.ticket_type}</TableCell>
                  <TableCell>
                    {baseline.format ? (
                      <Badge variant="outline" className="text-xs">{baseline.format}</Badge>
                    ) : (
                      <span className="text-slate-400">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {baseline.day_of_week !== null && baseline.day_of_week !== undefined ? (
                      <Badge variant="secondary" className="text-xs">
                        {DAY_OF_WEEK_LABELS[baseline.day_of_week] || `Day ${baseline.day_of_week}`}
                      </Badge>
                    ) : baseline.day_type ? (
                      <Badge variant="secondary" className="text-xs">
                        {DAY_TYPE_LABELS[baseline.day_type] || baseline.day_type}
                      </Badge>
                    ) : (
                      <span className="text-slate-400">All</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {baseline.daypart ? (
                      <Badge variant="secondary" className="text-xs">
                        {DAYPART_LABELS[baseline.daypart] || baseline.daypart}
                      </Badge>
                    ) : (
                      <span className="text-slate-400">All</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-semibold">
                    ${baseline.baseline_price.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right text-sm text-slate-600">
                    {baseline.min_price && baseline.max_price ? (
                      `$${baseline.min_price.toFixed(2)} - $${baseline.max_price.toFixed(2)}`
                    ) : (
                      <span className="text-slate-400">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-sm text-slate-600">
                    {baseline.sample_count || '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    );
  };

  return (
    <div className="h-[calc(100vh-280px)] min-h-[600px]">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 h-full">
        {/* Left panel: Market/Theater browser */}
        <Card className="flex flex-col overflow-hidden">
          <CardHeader className="border-b py-3 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <MapPin className="h-5 w-5 text-blue-500" />
                  Browse by Market
                </CardTitle>
                <CardDescription>
                  {markets?.length || 0} markets with baseline data
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchMarkets()}
                disabled={marketsLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${marketsLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
          </CardHeader>

          {/* Search */}
          <div className="p-3 border-b flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search markets..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 pr-9"
              />
              {searchTerm && (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  onClick={() => setSearchTerm('')}
                >
                  <X className="h-4 w-4 text-slate-400 hover:text-slate-600" />
                </button>
              )}
            </div>
          </div>

          {/* Market list with inline detail */}
          <CardContent className="p-0 flex-1 overflow-auto">
            {renderMarketList()}
          </CardContent>
        </Card>

        {/* Right panel: Theater baselines */}
        <Card className="flex flex-col overflow-hidden">
          <CardHeader className="border-b py-3 flex-shrink-0">
            <CardTitle className="text-lg flex items-center gap-2">
              <Store className="h-5 w-5 text-green-500" />
              Theater Baselines
            </CardTitle>
            <CardDescription>
              {selectedTheater ? 'Viewing baselines for selected theater' : 'Select a theater to view baselines'}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-hidden">
            {renderTheaterBaselines()}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
