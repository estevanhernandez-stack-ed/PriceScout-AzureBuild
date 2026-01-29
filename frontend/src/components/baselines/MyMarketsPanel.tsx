/**
 * My Markets Panel
 *
 * Shows markets in an expandable hierarchy view:
 * Company → Director → Market → Theater
 *
 * Similar to Coverage Gaps panel but focused on baseline discovery and management.
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  ChevronDown,
  ChevronRight,
  Users,
  MapPin,
  Building2,
  Loader2,
  Search,
  Target,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import {
  useMarketsHierarchy,
  useBaselines,
  useCompanyProfiles,
  useMarketCoverage,
  useDiscoverFandangoBaselinesForTheaters,
  type CompanyProfile,
  type TheaterCoverageDetail,
} from '@/hooks/api';
import { useToast } from '@/hooks/use-toast';
import { TheaterProfileCard, getCircuitFromTheaterName } from './TheaterProfileCard';
import { CompetitorComparisonPanel } from './CompetitorComparisonPanel';

// =============================================================================
// TYPES
// =============================================================================

interface TheaterInfo {
  name: string;
  fandango_id?: string;
  address?: string;
  is_your_theater?: boolean;
}

interface MarketData {
  theaters: TheaterInfo[];
}

interface DirectorMarkets {
  [marketName: string]: MarketData;
}

interface CompanyHierarchy {
  [directorName: string]: DirectorMarkets;
}

interface MarketsHierarchyData {
  [companyName: string]: CompanyHierarchy;
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function MyMarketsPanel() {
  const { toast } = useToast();
  const [expandedDirectors, setExpandedDirectors] = useState<Set<string>>(new Set());
  const [expandedMarkets, setExpandedMarkets] = useState<Set<string>>(new Set());
  const [selectedMarket, setSelectedMarket] = useState<{
    director: string;
    market: string;
    theaters: TheaterInfo[];
  } | null>(null);

  // Data fetching
  const { data: marketsHierarchy, isLoading: marketsLoading } = useMarketsHierarchy();
  const { data: savedBaselines } = useBaselines({ activeOnly: true });
  const { data: profilesData } = useCompanyProfiles();
  const { data: marketCoverageData } = useMarketCoverage(
    selectedMarket?.director || null,
    selectedMarket?.market || null,
    { lookbackDays: 90 }
  );
  const discoverForTheaters = useDiscoverFandangoBaselinesForTheaters();

  // Build profile lookup map
  const profilesByCircuit = useMemo(() => {
    const map: Record<string, CompanyProfile> = {};
    if (profilesData?.profiles) {
      for (const profile of profilesData.profiles) {
        map[profile.circuit_name.toLowerCase()] = profile;
      }
    }
    return map;
  }, [profilesData]);

  // Build coverage lookup map
  const coverageByTheater = useMemo(() => {
    const map: Record<string, TheaterCoverageDetail> = {};
    if (marketCoverageData?.theaters) {
      for (const theater of marketCoverageData.theaters) {
        map[theater.theater_name] = theater;
      }
    }
    return map;
  }, [marketCoverageData]);

  // Calculate stats for a set of theaters
  const getTheaterStats = (theaters: TheaterInfo[]) => {
    const theaterNames = theaters.map((t) => t.name);
    const baselines = savedBaselines?.filter((bl) => theaterNames.includes(bl.theater_name)) || [];
    const theatersWithBaselines = new Set(baselines.map((bl) => bl.theater_name)).size;
    const yourTheaters = theaters.filter(
      (t) => t.name.startsWith('Marcus') || t.name.startsWith('Movie Tavern')
    ).length;

    return {
      total: theaters.length,
      yourTheaters,
      competitors: theaters.length - yourTheaters,
      withBaselines: theatersWithBaselines,
      baselineCount: baselines.length,
      coveragePercent: theaters.length > 0 ? Math.round((theatersWithBaselines / theaters.length) * 100) : 0,
    };
  };

  const toggleDirector = (key: string) => {
    const newSet = new Set(expandedDirectors);
    if (newSet.has(key)) {
      newSet.delete(key);
    } else {
      newSet.add(key);
    }
    setExpandedDirectors(newSet);
  };

  const toggleMarket = (key: string) => {
    const newSet = new Set(expandedMarkets);
    if (newSet.has(key)) {
      newSet.delete(key);
    } else {
      newSet.add(key);
    }
    setExpandedMarkets(newSet);
  };

  const handleDiscoverBaselines = (theaters: TheaterInfo[]) => {
    const theaterNames = theaters.map((t) => t.name);
    discoverForTheaters.mutate(
      { theaters: theaterNames, save: true, minSamples: 3, lookbackDays: 90 },
      {
        onSuccess: (data) => {
          toast({
            title: 'Baselines Discovered',
            description: `Found ${data.discovered_count} baselines for ${data.theater_count} theaters. ${data.saved_count ?? 0} saved.`,
          });
        },
        onError: () => {
          toast({
            title: 'Discovery Failed',
            description: 'Could not discover baselines. Make sure you have scraped prices.',
            variant: 'destructive',
          });
        },
      }
    );
  };

  if (marketsLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!marketsHierarchy || Object.keys(marketsHierarchy).length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center justify-center text-muted-foreground">
            <MapPin className="h-12 w-12 mb-4" />
            <p>No markets configured</p>
            <p className="text-sm">Configure markets.json to see your market hierarchy</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const hierarchy = marketsHierarchy as MarketsHierarchyData;

  return (
    <div className="space-y-4">
      {Object.entries(hierarchy).map(([companyName, directors]) => {
        // Calculate company-level stats
        const allTheaters = Object.values(directors).flatMap((markets) =>
          Object.values(markets).flatMap((m) => m.theaters || [])
        );
        const companyStats = getTheaterStats(allTheaters);

        return (
          <Card key={companyName}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-purple-500" />
                {companyName}
              </CardTitle>
              <CardDescription>
                {companyStats.total} theaters • {companyStats.yourTheaters} yours •{' '}
                {companyStats.competitors} competitors •{' '}
                <span className={companyStats.coveragePercent >= 80 ? 'text-green-600' : 'text-yellow-600'}>
                  {companyStats.coveragePercent}% with baselines
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(directors).map(([directorName, markets]) => {
                const directorKey = `${companyName}/${directorName}`;
                const isDirectorExpanded = expandedDirectors.has(directorKey);
                const directorTheaters = Object.values(markets).flatMap((m) => m.theaters || []);
                const directorStats = getTheaterStats(directorTheaters);

                return (
                  <div key={directorName} className="border rounded-lg">
                    {/* Director Row */}
                    <div
                      className="p-3 cursor-pointer hover:bg-muted/50 flex items-center justify-between"
                      onClick={() => toggleDirector(directorKey)}
                    >
                      <div className="flex items-center gap-3">
                        {isDirectorExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        <Users className="h-4 w-4 text-blue-500" />
                        <div>
                          <div className="font-medium">{directorName}</div>
                          <div className="text-xs text-muted-foreground">
                            {Object.keys(markets).length} markets • {directorStats.total} theaters
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Progress value={directorStats.coveragePercent} className="w-20 h-2" />
                        <span className="text-sm font-medium w-12 text-right">
                          {directorStats.coveragePercent}%
                        </span>
                      </div>
                    </div>

                    {/* Markets (when director expanded) */}
                    {isDirectorExpanded && (
                      <div className="border-t px-4 py-2 space-y-2 bg-muted/20">
                        {Object.entries(markets).map(([marketName, marketData]) => {
                          const marketKey = `${directorKey}/${marketName}`;
                          const isMarketExpanded = expandedMarkets.has(marketKey);
                          const marketStats = getTheaterStats(marketData.theaters || []);

                          return (
                            <div key={marketName} className="border rounded-lg bg-background">
                              {/* Market Row */}
                              <div
                                className="p-3 cursor-pointer hover:bg-muted/50 flex items-center justify-between"
                                onClick={() => {
                                  toggleMarket(marketKey);
                                  if (!expandedMarkets.has(marketKey)) {
                                    setSelectedMarket({
                                      director: directorName,
                                      market: marketName,
                                      theaters: marketData.theaters || [],
                                    });
                                  }
                                }}
                              >
                                <div className="flex items-center gap-3">
                                  {isMarketExpanded ? (
                                    <ChevronDown className="h-4 w-4" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4" />
                                  )}
                                  <MapPin className="h-4 w-4 text-green-500" />
                                  <div>
                                    <div className="font-medium">{marketName}</div>
                                    <div className="text-xs text-muted-foreground">
                                      {marketStats.yourTheaters} yours • {marketStats.competitors} competitors
                                    </div>
                                  </div>
                                </div>
                                <div className="flex items-center gap-3">
                                  {marketStats.coveragePercent >= 100 ? (
                                    <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
                                      <CheckCircle2 className="h-3 w-3 mr-1" />
                                      Complete
                                    </Badge>
                                  ) : marketStats.coveragePercent > 0 ? (
                                    <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
                                      <Target className="h-3 w-3 mr-1" />
                                      {marketStats.withBaselines}/{marketStats.total}
                                    </Badge>
                                  ) : (
                                    <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
                                      <AlertCircle className="h-3 w-3 mr-1" />
                                      No Data
                                    </Badge>
                                  )}
                                </div>
                              </div>

                              {/* Theaters (when market expanded) */}
                              {isMarketExpanded && (
                                <div className="border-t p-4 space-y-4 bg-muted/10">
                                  {/* Quick Stats */}
                                  <div className="grid gap-4 md:grid-cols-3">
                                    <div className="border rounded-md p-3">
                                      <div className="text-sm text-muted-foreground">Your Theaters</div>
                                      <div className="text-2xl font-bold text-purple-600">{marketStats.yourTheaters}</div>
                                    </div>
                                    <div className="border rounded-md p-3">
                                      <div className="text-sm text-muted-foreground">Competitors</div>
                                      <div className="text-2xl font-bold text-orange-600">{marketStats.competitors}</div>
                                    </div>
                                    <div className="border rounded-md p-3">
                                      <div className="text-sm text-muted-foreground">Baselines Set</div>
                                      <div className="text-2xl font-bold text-green-600">{marketStats.baselineCount}</div>
                                    </div>
                                  </div>

                                  {/* Discover Button */}
                                  <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
                                    <div className="flex-1">
                                      <h4 className="font-medium">Discover Baselines</h4>
                                      <p className="text-sm text-muted-foreground">
                                        Create baselines for all {marketStats.total} theaters using Fandango data
                                      </p>
                                    </div>
                                    <Button
                                      onClick={() => handleDiscoverBaselines(marketData.theaters || [])}
                                      disabled={discoverForTheaters.isPending}
                                    >
                                      {discoverForTheaters.isPending ? (
                                        <>
                                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                          Discovering...
                                        </>
                                      ) : (
                                        <>
                                          <Search className="h-4 w-4 mr-2" />
                                          Discover & Save
                                        </>
                                      )}
                                    </Button>
                                  </div>

                                  {/* Theater Cards */}
                                  <TheaterCardsGrid
                                    theaters={marketData.theaters || []}
                                    savedBaselines={savedBaselines || []}
                                    profilesByCircuit={profilesByCircuit}
                                    coverageByTheater={coverageByTheater}
                                  />

                                  {/* Competitor Comparison */}
                                  {marketStats.competitors > 0 && (() => {
                                    const theaterNames = (marketData.theaters || []).map((t) => t.name);
                                    const marketBaselines = savedBaselines?.filter((bl) =>
                                      theaterNames.includes(bl.theater_name)
                                    ) || [];
                                    const theaters = (marketData.theaters || []).map((t) => ({
                                      name: t.name,
                                      isYours: t.name.startsWith('Marcus') || t.name.startsWith('Movie Tavern'),
                                    }));
                                    return (
                                      <CompetitorComparisonPanel
                                        theaters={theaters}
                                        baselines={marketBaselines}
                                        profiles={profilesByCircuit}
                                      />
                                    );
                                  })()}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// =============================================================================
// THEATER CARDS GRID
// =============================================================================

interface TheaterCardsGridProps {
  theaters: TheaterInfo[];
  savedBaselines: { theater_name: string; ticket_type: string; daypart?: string | null; day_of_week?: number | null }[];
  profilesByCircuit: Record<string, CompanyProfile>;
  coverageByTheater: Record<string, TheaterCoverageDetail>;
}

function TheaterCardsGrid({
  theaters,
  savedBaselines,
  profilesByCircuit,
  coverageByTheater,
}: TheaterCardsGridProps) {
  const yourTheaters = theaters.filter(
    (t) => t.name.startsWith('Marcus') || t.name.startsWith('Movie Tavern')
  );
  const competitors = theaters.filter(
    (t) => !t.name.startsWith('Marcus') && !t.name.startsWith('Movie Tavern')
  );

  const renderTheaterCard = (theater: TheaterInfo, isYours: boolean) => {
    const theaterBaselines = savedBaselines.filter((bl) => bl.theater_name === theater.name);
    const ticketTypes = new Set(theaterBaselines.map((bl) => bl.ticket_type)).size;
    const daypartSet = new Set(theaterBaselines.filter((bl) => bl.daypart).map((bl) => bl.daypart as string));
    const daypartsList = Array.from(daypartSet).sort();
    const days = new Set(
      theaterBaselines.filter((bl) => bl.day_of_week !== null).map((bl) => bl.day_of_week)
    ).size;
    const circuitName = getCircuitFromTheaterName(theater.name);
    const profile = profilesByCircuit[circuitName.toLowerCase()] || null;
    const coverage = coverageByTheater[theater.name] || null;

    return (
      <TheaterProfileCard
        key={theater.name}
        theaterName={theater.name}
        baselineCount={theaterBaselines.length}
        ticketTypeCount={ticketTypes}
        daypartCount={daypartsList.length}
        dayparts={daypartsList}
        dayCount={days}
        profile={profile}
        coverage={coverage}
        isYourTheater={isYours}
      />
    );
  };

  return (
    <div className="space-y-6">
      {/* Your Theaters */}
      {yourTheaters.length > 0 && (
        <div>
          <h4 className="font-medium mb-3 flex items-center gap-2">
            <Building2 className="h-4 w-4 text-purple-500" />
            Your Theaters ({yourTheaters.length})
          </h4>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {yourTheaters.map((theater) => renderTheaterCard(theater, true))}
          </div>
        </div>
      )}

      {/* Competitors */}
      {competitors.length > 0 && (
        <div>
          <h4 className="font-medium mb-3 flex items-center gap-2">
            <Building2 className="h-4 w-4 text-orange-500" />
            Competitors ({competitors.length})
          </h4>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {competitors.map((theater) => renderTheaterCard(theater, false))}
          </div>
        </div>
      )}
    </div>
  );
}

export default MyMarketsPanel;
