/**
 * Coverage Gaps Panel
 *
 * Shows coverage gaps for theater price data.
 * Supports two views:
 * - All Theaters: Flat list with filters
 * - By Market: Hierarchical drill-down (Director -> Market -> Theater)
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Search,
  Loader2,
  ChevronDown,
  ChevronRight,
  Calendar,
  Target,
  BarChart3,
  MapPin,
  Users,
  Building2,
  Globe,
  ExternalLink,
  XCircle,
  ClipboardList,
  Wrench,
} from 'lucide-react';
import {
  useAllTheaterCoverage,
  useTheaterCoverage,
  useCoverageHierarchy,
  getCoverageColor,
  type TheaterCoverageSummary,
  type GapInfo,
  type DirectorCoverage,
  type MarketCoverage,
  type TheaterCoverageDetail,
  type CoverageReport,
} from '@/hooks/api';
import { useTheaterCache } from '@/hooks/api/useMarkets';
import { useMarkTheaterStatus } from '@/hooks/api/useZeroShowtimes';
import { useToast } from '@/hooks/use-toast';

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function CoverageGapsPanel() {
  const [viewMode, setViewMode] = useState<'all' | 'hierarchy'>('hierarchy');

  return (
    <div className="space-y-4">
      <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'all' | 'hierarchy')}>
        <TabsList>
          <TabsTrigger value="hierarchy">
            <MapPin className="h-4 w-4 mr-2" />
            By Market
          </TabsTrigger>
          <TabsTrigger value="all">
            <BarChart3 className="h-4 w-4 mr-2" />
            All Theaters
          </TabsTrigger>
        </TabsList>

        <TabsContent value="hierarchy" className="space-y-4 mt-4">
          <HierarchyView />
        </TabsContent>

        <TabsContent value="all" className="space-y-4 mt-4">
          <AllTheatersView />
        </TabsContent>
      </Tabs>

      {/* Help */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Understanding Coverage Gaps</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <span><strong>Error:</strong> Critical gap - very few samples (&lt;3), data unreliable</span>
          </div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
            <span><strong>Warning:</strong> Low samples (3-9), needs more data for confidence</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span><strong>Healthy:</strong> 10+ samples, baseline is reliable</span>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-blue-500" />
            <span><strong>Missing Day:</strong> No price data for that day of week</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// HIERARCHY VIEW
// =============================================================================

function HierarchyView() {
  const [expandedDirectors, setExpandedDirectors] = useState<Set<string>>(new Set());
  const [expandedMarkets, setExpandedMarkets] = useState<Set<string>>(new Set());
  const [selectedTheater, setSelectedTheater] = useState<string | null>(null);

  const { data: hierarchy, isLoading } = useCoverageHierarchy({ lookbackDays: 90 });
  const { data: theaterDetail, isLoading: isLoadingDetail } = useTheaterCoverage(selectedTheater, {
    lookbackDays: 90,
  });

  const toggleDirector = (directorName: string) => {
    const newSet = new Set(expandedDirectors);
    if (newSet.has(directorName)) {
      newSet.delete(directorName);
    } else {
      newSet.add(directorName);
    }
    setExpandedDirectors(newSet);
  };

  const toggleMarket = (marketKey: string) => {
    const newSet = new Set(expandedMarkets);
    if (newSet.has(marketKey)) {
      newSet.delete(marketKey);
    } else {
      newSet.add(marketKey);
    }
    setExpandedMarkets(newSet);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!hierarchy || Object.keys(hierarchy).length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center justify-center text-muted-foreground">
            <MapPin className="h-12 w-12 mb-4" />
            <p>No markets configured</p>
            <p className="text-sm">Configure markets.json to see hierarchical coverage</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary Stats */}
      {Object.entries(hierarchy).map(([companyName, companyCoverage]) => (
        <Card key={companyName}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-purple-500" />
              {companyName}
            </CardTitle>
            <CardDescription>
              {companyCoverage.total_theaters} theaters • {companyCoverage.total_gaps} gaps •{' '}
              <span className={getCoverageColor(companyCoverage.avg_coverage_score)}>
                {Math.round(companyCoverage.avg_coverage_score)}% avg coverage
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(companyCoverage.directors).map(([directorName, directorCoverage]) => (
              <DirectorRow
                key={directorName}
                directorName={directorName}
                coverage={directorCoverage}
                isExpanded={expandedDirectors.has(directorName)}
                onToggle={() => toggleDirector(directorName)}
                expandedMarkets={expandedMarkets}
                onToggleMarket={toggleMarket}
                selectedTheater={selectedTheater}
                onSelectTheater={setSelectedTheater}
              />
            ))}
          </CardContent>
        </Card>
      ))}

      {/* Theater Detail Panel */}
      {selectedTheater && (
        <TheaterDetailPanel
          theaterName={selectedTheater}
          detail={theaterDetail}
          isLoading={isLoadingDetail}
          onClose={() => setSelectedTheater(null)}
        />
      )}
    </div>
  );
}

interface DirectorRowProps {
  directorName: string;
  coverage: DirectorCoverage;
  isExpanded: boolean;
  onToggle: () => void;
  expandedMarkets: Set<string>;
  onToggleMarket: (key: string) => void;
  selectedTheater: string | null;
  onSelectTheater: (name: string | null) => void;
}

function DirectorRow({
  directorName,
  coverage,
  isExpanded,
  onToggle,
  expandedMarkets,
  onToggleMarket,
  selectedTheater,
  onSelectTheater,
}: DirectorRowProps) {
  const scoreColor = getCoverageColor(coverage.avg_coverage_score);

  return (
    <div className="border rounded-lg">
      <div
        className="p-3 cursor-pointer hover:bg-muted/50 flex items-center justify-between"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          <Users className="h-4 w-4 text-blue-500" />
          <div>
            <div className="font-medium">{directorName}</div>
            <div className="text-xs text-muted-foreground">
              {Object.keys(coverage.markets).length} markets • {coverage.total_theaters} theaters
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {coverage.total_gaps > 0 && (
            <Badge variant="outline" className="text-yellow-600 border-yellow-300">
              <AlertTriangle className="h-3 w-3 mr-1" />
              {coverage.total_gaps} gaps
            </Badge>
          )}
          <div className={`font-bold ${scoreColor}`}>
            {Math.round(coverage.avg_coverage_score)}%
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t px-4 py-2 space-y-2 bg-muted/20">
          {Object.entries(coverage.markets).map(([marketName, marketCoverage]) => (
            <MarketRow
              key={marketName}
              marketName={marketName}
              coverage={marketCoverage}
              isExpanded={expandedMarkets.has(`${directorName}/${marketName}`)}
              onToggle={() => onToggleMarket(`${directorName}/${marketName}`)}
              selectedTheater={selectedTheater}
              onSelectTheater={onSelectTheater}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface MarketRowProps {
  marketName: string;
  coverage: MarketCoverage;
  isExpanded: boolean;
  onToggle: () => void;
  selectedTheater: string | null;
  onSelectTheater: (name: string | null) => void;
}

function MarketRow({
  marketName,
  coverage,
  isExpanded,
  onToggle,
  selectedTheater,
  onSelectTheater,
}: MarketRowProps) {
  const scoreColor = getCoverageColor(coverage.avg_coverage_score);

  return (
    <div className="border rounded-md bg-background">
      <div
        className="p-2 cursor-pointer hover:bg-muted/50 flex items-center justify-between"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <MapPin className="h-3 w-3 text-green-500" />
          <span className="font-medium text-sm">{marketName}</span>
          <span className="text-xs text-muted-foreground">
            ({coverage.total_theaters} theaters)
          </span>
        </div>
        <div className="flex items-center gap-3">
          {coverage.theaters_with_gaps > 0 && (
            <Badge variant="outline" className="text-yellow-600 border-yellow-300 text-xs">
              {coverage.theaters_with_gaps} with gaps
            </Badge>
          )}
          <span className={`text-sm font-bold ${scoreColor}`}>
            {Math.round(coverage.avg_coverage_score)}%
          </span>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t px-2 py-1 space-y-1 bg-muted/10">
          {coverage.theaters.map((theater) => (
            <TheaterRow
              key={theater.theater_name}
              theater={theater}
              isSelected={selectedTheater === theater.theater_name}
              onSelect={() =>
                onSelectTheater(
                  selectedTheater === theater.theater_name ? null : theater.theater_name
                )
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface TheaterRowProps {
  theater: TheaterCoverageDetail;
  isSelected: boolean;
  onSelect: () => void;
}

function TheaterRow({ theater, isSelected, onSelect }: TheaterRowProps) {
  const scoreColor = getCoverageColor(theater.coverage_score);

  return (
    <div
      className={`p-2 rounded cursor-pointer transition-colors text-sm ${
        isSelected ? 'bg-primary/10 border border-primary' : 'hover:bg-muted/50'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-3 w-3 text-muted-foreground" />
          <span className={isSelected ? 'font-medium' : ''}>{theater.theater_name}</span>
          <span className="text-xs text-muted-foreground">
            {theater.total_samples} samples
          </span>
        </div>
        <div className="flex items-center gap-2">
          {theater.gap_count > 0 && (
            <Badge variant="outline" className="text-yellow-600 border-yellow-300 text-xs py-0">
              {theater.gap_count}
            </Badge>
          )}
          <span className={`font-bold text-xs ${scoreColor}`}>
            {Math.round(theater.coverage_score)}%
          </span>
        </div>
      </div>
      {theater.days_missing.length > 0 && (
        <div className="mt-1 text-xs text-muted-foreground pl-5">
          Missing: {theater.days_missing.join(', ')}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// ALL THEATERS VIEW
// =============================================================================

function AllTheatersView() {
  const [theaterFilter, setTheaterFilter] = useState('');
  const [circuitFilter, setCircuitFilter] = useState<string>('all');
  const [coverageFilter, setCoverageFilter] = useState<string>('all');
  const [selectedTheater, setSelectedTheater] = useState<string | null>(null);

  const { data: coverageData, isLoading } = useAllTheaterCoverage({
    lookbackDays: 90,
    minSamples: 1,
  });

  const { data: theaterDetail, isLoading: isLoadingDetail } = useTheaterCoverage(selectedTheater, {
    lookbackDays: 90,
  });

  const circuits = useMemo(() => {
    if (!coverageData?.theaters) return [];
    const uniqueCircuits = new Set(
      coverageData.theaters.map((t) => t.circuit_name).filter(Boolean) as string[]
    );
    return Array.from(uniqueCircuits).sort();
  }, [coverageData]);

  const filteredTheaters = useMemo(() => {
    if (!coverageData?.theaters) return [];

    return coverageData.theaters.filter((t) => {
      if (theaterFilter && !t.theater_name.toLowerCase().includes(theaterFilter.toLowerCase())) {
        return false;
      }
      if (circuitFilter !== 'all' && t.circuit_name !== circuitFilter) {
        return false;
      }
      if (coverageFilter === 'poor' && t.coverage_score >= 50) return false;
      if (coverageFilter === 'fair' && (t.coverage_score < 50 || t.coverage_score >= 70)) return false;
      if (coverageFilter === 'good' && (t.coverage_score < 70 || t.coverage_score >= 90)) return false;
      if (coverageFilter === 'excellent' && t.coverage_score < 90) return false;
      if (coverageFilter === 'with_gaps' && t.gap_count === 0) return false;
      return true;
    });
  }, [coverageData, theaterFilter, circuitFilter, coverageFilter]);

  const stats = useMemo(() => {
    if (!coverageData?.theaters) return null;
    const theaters = coverageData.theaters;
    const withGaps = theaters.filter((t) => t.gap_count > 0);
    const avgScore = theaters.reduce((sum, t) => sum + t.coverage_score, 0) / theaters.length;
    const poorCoverage = theaters.filter((t) => t.coverage_score < 50);
    return {
      total: theaters.length,
      withGaps: withGaps.length,
      avgScore: Math.round(avgScore),
      poorCoverage: poorCoverage.length,
    };
  }, [coverageData]);

  return (
    <>
      {/* Summary Stats */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Theaters
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Theaters with Gaps
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-600">{stats.withGaps}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Avg Coverage Score
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${getCoverageColor(stats.avgScore)}`}>
                {stats.avgScore}%
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Poor Coverage (&lt;50%)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{stats.poorCoverage}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-blue-500" />
            Filter Theaters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Theater Name</Label>
              <Input
                placeholder="Search theaters..."
                value={theaterFilter}
                onChange={(e) => setTheaterFilter(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Circuit</Label>
              <Select value={circuitFilter} onValueChange={setCircuitFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All circuits" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Circuits</SelectItem>
                  {circuits.map((circuit) => (
                    <SelectItem key={circuit} value={circuit}>
                      {circuit}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Coverage Level</Label>
              <Select value={coverageFilter} onValueChange={setCoverageFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="with_gaps">With Gaps Only</SelectItem>
                  <SelectItem value="poor">Poor (&lt;50%)</SelectItem>
                  <SelectItem value="fair">Fair (50-69%)</SelectItem>
                  <SelectItem value="good">Good (70-89%)</SelectItem>
                  <SelectItem value="excellent">Excellent (90%+)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="text-sm text-muted-foreground">
            Showing {filteredTheaters.length} of {coverageData?.total ?? 0} theaters
          </div>
        </CardContent>
      </Card>

      {/* Theater List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-purple-500" />
            Theater Coverage
            {filteredTheaters.length > 0 && (
              <Badge variant="secondary">{filteredTheaters.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredTheaters.length > 0 ? (
            <div className="space-y-2 max-h-[500px] overflow-auto">
              {filteredTheaters.slice(0, 50).map((theater) => (
                <TheaterCoverageRow
                  key={theater.theater_name}
                  theater={theater}
                  isSelected={selectedTheater === theater.theater_name}
                  onSelect={() =>
                    setSelectedTheater(
                      selectedTheater === theater.theater_name ? null : theater.theater_name
                    )
                  }
                />
              ))}
              {filteredTheaters.length > 50 && (
                <p className="text-sm text-muted-foreground text-center py-2">
                  Showing first 50 of {filteredTheaters.length} theaters.
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <CheckCircle2 className="h-12 w-12 mb-4 text-green-500" />
              <p>No theaters with gaps found</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Theater Detail Panel */}
      {selectedTheater && (
        <TheaterDetailPanel
          theaterName={selectedTheater}
          detail={theaterDetail}
          isLoading={isLoadingDetail}
          onClose={() => setSelectedTheater(null)}
        />
      )}
    </>
  );
}

interface TheaterCoverageRowProps {
  theater: TheaterCoverageSummary;
  isSelected: boolean;
  onSelect: () => void;
}

function TheaterCoverageRow({ theater, isSelected, onSelect }: TheaterCoverageRowProps) {
  const scoreColor = getCoverageColor(theater.coverage_score);

  return (
    <div
      className={`p-3 rounded-md border cursor-pointer transition-colors ${
        isSelected ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {isSelected ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <div>
            <div className="font-medium">{theater.theater_name}</div>
            <div className="text-xs text-muted-foreground">
              {theater.circuit_name} • {theater.total_samples} samples
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {theater.gap_count > 0 && (
            <Badge variant="outline" className="text-yellow-600 border-yellow-300">
              <AlertTriangle className="h-3 w-3 mr-1" />
              {theater.gap_count} gaps
            </Badge>
          )}
          <div className="text-right">
            <div className={`font-bold ${scoreColor}`}>{Math.round(theater.coverage_score)}%</div>
            <div className="text-xs text-muted-foreground">coverage</div>
          </div>
        </div>
      </div>
      {theater.days_missing.length > 0 && (
        <div className="mt-2 text-xs text-muted-foreground">
          <Calendar className="h-3 w-3 inline mr-1" />
          Missing: {theater.days_missing.join(', ')}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// THEATER DETAIL PANEL
// =============================================================================

interface TheaterDetailPanelProps {
  theaterName: string;
  detail: CoverageReport | null | undefined;
  isLoading: boolean;
  onClose: () => void;
}

function TheaterDetailPanel({ theaterName, detail, isLoading, onClose }: TheaterDetailPanelProps) {
  const { toast } = useToast();
  const { data: theaterCache } = useTheaterCache();
  const markStatusMutation = useMarkTheaterStatus();

  const [editingStatus, setEditingStatus] = useState(false);
  const [statusAction, setStatusAction] = useState<'not_on_fandango' | 'closed' | 'active'>('not_on_fandango');
  const [statusUrl, setStatusUrl] = useState('');

  // Look up theater in cache to determine current market and status
  const theaterCacheInfo = useMemo(() => {
    if (!theaterCache?.markets) return null;
    for (const [marketName, marketData] of Object.entries(theaterCache.markets)) {
      const found = marketData.theaters?.find(
        (t) => t.name === theaterName
      );
      if (found) {
        return {
          market: marketName,
          url: found.url,
          notOnFandango: found.not_on_fandango === true,
          status: found.status,
          company: found.company,
        };
      }
    }
    return null;
  }, [theaterCache, theaterName]);

  const currentStatus = useMemo(() => {
    if (!theaterCacheInfo) return 'unknown';
    if (theaterName.includes('(Permanently Closed)')) return 'closed';
    if (theaterCacheInfo.notOnFandango) return 'not_on_fandango';
    return 'active';
  }, [theaterCacheInfo, theaterName]);

  const handleSaveStatus = async () => {
    if (!theaterCacheInfo?.market) {
      toast({ title: 'Error', description: 'Could not determine market for this theater.', variant: 'destructive' });
      return;
    }
    try {
      await markStatusMutation.mutateAsync({
        theater_name: theaterName,
        market: theaterCacheInfo.market,
        status: statusAction,
        external_url: statusAction === 'not_on_fandango' ? statusUrl || undefined : undefined,
        reason: 'Updated from Coverage Gaps panel',
      });
      toast({ title: 'Status Updated', description: `${theaterName} marked as ${statusAction.replace(/_/g, ' ')}.` });
      setEditingStatus(false);
      setStatusUrl('');
    } catch {
      toast({ title: 'Error', description: 'Failed to update theater status.', variant: 'destructive' });
    }
  };

  const getGapIcon = (gap: GapInfo) => {
    if (gap.severity === 'error') {
      return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
    return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
  };

  const getRemediationSuggestion = (gap: GapInfo): string => {
    const isNotOnFandango = currentStatus === 'not_on_fandango';

    switch (gap.gap_type) {
      case 'no_data':
        return isNotOnFandango
          ? 'Theater not on Fandango — manual entry required. See guidance below.'
          : 'No price data found. Run a Fandango scrape for this theater via Market Mode.';
      case 'missing_day':
        return `Missing data for this day. Schedule a scrape that covers this day of the week.`;
      case 'missing_format':
        return `No data for this format. Ensure this format is selected when running scrapes.`;
      case 'low_samples':
        return `Low sample count — data may be unreliable. Run additional scrapes to collect more data points.`;
      default:
        return 'Run a price scrape for this theater to fill this gap.';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-green-500" />
            {theaterName}
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <CardDescription>Detailed coverage analysis</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : detail ? (
          <div className="space-y-4">
            {/* Coverage Score */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Overall Coverage</span>
                <span className={`font-bold ${getCoverageColor(detail.overall_coverage_score)}`}>
                  {Math.round(detail.overall_coverage_score)}%
                </span>
              </div>
              <Progress value={detail.overall_coverage_score} className="h-2" />
            </div>

            {/* Data Summary */}
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              <div>
                <span className="text-muted-foreground">Total Samples:</span>{' '}
                <strong>{detail.total_samples}</strong>
              </div>
              <div>
                <span className="text-muted-foreground">Formats:</span>{' '}
                <strong>{detail.unique_formats?.join(', ') || 'None'}</strong>
              </div>
              <div>
                <span className="text-muted-foreground">Ticket Types:</span>{' '}
                <strong>{detail.unique_ticket_types?.length || 0}</strong>
              </div>
            </div>

            {/* Day Coverage */}
            <div>
              <span className="text-sm font-medium">Days with Data:</span>
              <div className="flex gap-1 mt-1">
                {DAY_NAMES.map((day, idx) => (
                  <Badge
                    key={day}
                    variant={detail.days_with_data?.includes(idx) ? 'default' : 'outline'}
                    className={
                      detail.days_with_data?.includes(idx)
                        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                        : 'text-muted-foreground'
                    }
                  >
                    {day}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Gaps */}
            {detail.gaps?.length > 0 && (
              <div>
                <span className="text-sm font-medium">Coverage Gaps ({detail.gap_count}):</span>
                <div className="mt-2 space-y-2 max-h-[200px] overflow-auto">
                  {detail.gaps.map((gap: GapInfo, idx: number) => (
                    <div
                      key={idx}
                      className="flex items-start gap-2 text-sm p-2 rounded-md bg-muted/50"
                    >
                      {getGapIcon(gap)}
                      <span>{gap.description}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ============================================================ */}
            {/* Theater Status */}
            {/* ============================================================ */}
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Globe className="h-4 w-4 text-blue-500" />
                  <span className="text-sm font-medium">Theater Status</span>
                </div>
                <div className="flex items-center gap-2">
                  {currentStatus === 'active' && (
                    <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                      Active
                    </Badge>
                  )}
                  {currentStatus === 'not_on_fandango' && (
                    <Badge className="bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200">
                      Not on Fandango
                    </Badge>
                  )}
                  {currentStatus === 'closed' && (
                    <Badge variant="secondary">
                      <XCircle className="h-3 w-3 mr-1" />
                      Closed
                    </Badge>
                  )}
                  {currentStatus === 'unknown' && (
                    <Badge variant="outline" className="text-muted-foreground">
                      Unknown
                    </Badge>
                  )}
                </div>
              </div>

              {theaterCacheInfo?.url && theaterCacheInfo.url !== 'N/A' && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <ExternalLink className="h-3 w-3" />
                  <a
                    href={theaterCacheInfo.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:underline truncate"
                  >
                    {theaterCacheInfo.url}
                  </a>
                </div>
              )}

              {theaterCacheInfo?.market && (
                <div className="text-xs text-muted-foreground">
                  Market: {theaterCacheInfo.market}
                  {theaterCacheInfo.company && ` | ${theaterCacheInfo.company}`}
                </div>
              )}

              {!editingStatus ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setStatusAction(currentStatus === 'active' ? 'not_on_fandango' : 'active');
                    setStatusUrl(theaterCacheInfo?.url || '');
                    setEditingStatus(true);
                  }}
                  disabled={!theaterCacheInfo?.market}
                >
                  Update Status
                </Button>
              ) : (
                <div className="space-y-3 border-t pt-3">
                  <div className="space-y-2">
                    <Label className="text-sm">New Status</Label>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant={statusAction === 'not_on_fandango' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setStatusAction('not_on_fandango')}
                      >
                        Not on Fandango
                      </Button>
                      <Button
                        variant={statusAction === 'closed' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setStatusAction('closed')}
                      >
                        Permanently Closed
                      </Button>
                      <Button
                        variant={statusAction === 'active' ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setStatusAction('active')}
                      >
                        Active
                      </Button>
                    </div>
                  </div>

                  {statusAction === 'not_on_fandango' && (
                    <div className="space-y-2">
                      <Label className="text-sm">Theater Ticketing URL (optional)</Label>
                      <Input
                        placeholder="https://www.theater-website.com/tickets"
                        value={statusUrl}
                        onChange={(e) => setStatusUrl(e.target.value)}
                      />
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={handleSaveStatus}
                      disabled={markStatusMutation.isPending}
                    >
                      {markStatusMutation.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : null}
                      Save
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingStatus(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {/* ============================================================ */}
            {/* Remediation Actions */}
            {/* ============================================================ */}
            {detail.gaps?.length > 0 && (
              <div className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Wrench className="h-4 w-4 text-purple-500" />
                  <span className="text-sm font-medium">Remediation Actions</span>
                </div>
                <div className="space-y-2">
                  {detail.gaps.map((gap: GapInfo, idx: number) => (
                    <div
                      key={idx}
                      className="text-sm p-2 rounded-md bg-muted/30 border-l-2 border-purple-300"
                    >
                      <div className="flex items-start gap-2">
                        {getGapIcon(gap)}
                        <div>
                          <div className="text-muted-foreground text-xs">{gap.description}</div>
                          <div className="mt-1 font-medium">{getRemediationSuggestion(gap)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ============================================================ */}
            {/* Manual Entry Guidance (only for not-on-fandango theaters) */}
            {/* ============================================================ */}
            {currentStatus === 'not_on_fandango' && (
              <div className="border rounded-lg p-4 space-y-3 border-orange-200 bg-orange-50/50 dark:bg-orange-950/20 dark:border-orange-800">
                <div className="flex items-center gap-2">
                  <ClipboardList className="h-4 w-4 text-orange-600" />
                  <span className="text-sm font-medium text-orange-800 dark:text-orange-300">
                    Manual Entry Guide
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  This theater is not on Fandango. To fill baseline gaps, collect pricing
                  from the theater&apos;s own website or ticketing system:
                </p>
                <ol className="text-sm space-y-1.5 list-decimal list-inside text-muted-foreground">
                  {theaterCacheInfo?.url && theaterCacheInfo.url !== 'N/A' ? (
                    <li>
                      Visit the theater&apos;s website:{' '}
                      <a
                        href={theaterCacheInfo.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-500 hover:underline"
                      >
                        {theaterCacheInfo.url}
                      </a>
                    </li>
                  ) : (
                    <li>Find the theater&apos;s website or ticketing page</li>
                  )}
                  <li>
                    Look up ticket prices for:
                    <ul className="list-disc list-inside ml-4 mt-1 space-y-0.5">
                      <li>Adult, Child, Senior tickets</li>
                      <li>Premium formats (IMAX, Dolby, etc.) if applicable</li>
                      <li>Matinee vs prime time pricing</li>
                      <li>Weekend vs weekday differences</li>
                    </ul>
                  </li>
                  <li>Record showtimes to determine operating hours</li>
                  <li>Note any discount programs (e.g., discount Tuesdays)</li>
                </ol>
                <p className="text-xs text-muted-foreground border-t pt-2">
                  Use the <strong>Baseline Details</strong> tab to manually create baselines with this data.
                </p>
              </div>
            )}

            {/* Healthy Baselines */}
            {detail.healthy_baselines?.length > 0 && (
              <div>
                <span className="text-sm font-medium">
                  Healthy Baselines ({detail.healthy_count}):
                </span>
                <div className="mt-2 rounded-md border max-h-[200px] overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Ticket Type</TableHead>
                        <TableHead>Format</TableHead>
                        <TableHead>Day</TableHead>
                        <TableHead className="text-right">Samples</TableHead>
                        <TableHead className="text-right">Avg Price</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.healthy_baselines.slice(0, 20).map((b, idx: number) => (
                        <TableRow key={idx}>
                          <TableCell>{b.ticket_type}</TableCell>
                          <TableCell>{b.format}</TableCell>
                          <TableCell>
                            <Badge variant="secondary" className="text-xs">
                              {b.day_name}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">{b.sample_count}</TableCell>
                          <TableCell className="text-right font-mono">
                            ${b.avg_price?.toFixed(2)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-muted-foreground">No data available</p>
        )}
      </CardContent>
    </Card>
  );
}
