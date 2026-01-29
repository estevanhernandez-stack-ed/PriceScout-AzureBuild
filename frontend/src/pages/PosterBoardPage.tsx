import { useState, useMemo } from 'react';
import { useMarketsHierarchy } from '@/hooks/api/useMarkets';
import { usePriceChecks } from '@/hooks/api/usePriceChecks';
import { useFilms, useDiscoverFandango, useTriggerScrape, useScrapeStatus } from '@/hooks/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Film,
  Calendar,
  Building2,
  RefreshCw,
  Download,
  Grid3X3,
  List,
  Clock,
  ChevronRight,
  ChevronLeft,
  Check,
  CheckCircle2,
  Circle,
  Search,
  AlertTriangle,
  Play,
  X,
  Sparkles,
} from 'lucide-react';
import { format, addDays, subDays, isToday, getHours } from 'date-fns';

type WizardStep = 'films' | 'dates' | 'theaters' | 'confirm';

interface FilmSummary {
  title: string;
  theaters: number;
  showtimes: number;
  avgPrice: number;
  formats: string[];
  latestDate: string;
  selected: boolean;
  poster_url?: string;
  rating?: string;
  runtime?: string;
  plot?: string;
}

// Check if company is Marcus-owned
const isMarcusCompany = (company: string) => {
  const lower = company.toLowerCase();
  return lower.includes('marcus') || lower.includes('movie tavern') || lower.includes('spotlight');
};

// Get format emoji
const getFormatEmoji = (formatStr: string) => {
  const lower = formatStr.toLowerCase();
  if (lower.includes('imax')) return '📽️';
  if (lower.includes('dolby') || lower.includes('atmos')) return '🔊';
  if (lower.includes('4dx')) return '💨';
  if (lower.includes('3d')) return '👓';
  if (lower.includes('d-box') || lower.includes('dbox')) return '💺';
  return '🎬';
};

const WIZARD_STEPS: { key: WizardStep; label: string; icon: React.ElementType }[] = [
  { key: 'films', label: 'Select Films', icon: Film },
  { key: 'dates', label: 'Choose Dates', icon: Calendar },
  { key: 'theaters', label: 'Select Theaters', icon: Building2 },
  { key: 'confirm', label: 'Confirm & Run', icon: Play },
];

export function PosterBoardPage() {
  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('films');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  // Film selection state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFilms, setSelectedFilms] = useState<Set<string>>(new Set());

  // Date selection state
  const [selectedStartDate, setSelectedStartDate] = useState<Date>(new Date());
  const [selectedEndDate, setSelectedEndDate] = useState<Date>(new Date());

  // Theater selection state
  const [selectedCompany, setSelectedCompany] = useState<string>('');
  const [selectedDirector, setSelectedDirector] = useState<string>('');
  const [selectedMarkets, setSelectedMarkets] = useState<Set<string>>(new Set());
  const [selectedTheaters, setSelectedTheaters] = useState<Set<string>>(new Set());

  const { data: hierarchyData, isLoading: hierarchyLoading } = useMarketsHierarchy();

  // Fetch price data to populate film list
  const dateStr = format(new Date(), 'yyyy-MM-dd');
  const { data: dbFilms, isLoading: filmsLoading } = useFilms();
  const discoverMutation = useDiscoverFandango();
  
  const triggerScrape = useTriggerScrape();
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const { data: scrapeStatus } = useScrapeStatus(activeJobId || 0, {
    enabled: !!activeJobId,
    refetchInterval: 5000
  });

  const {
    data: priceData,
    isLoading: priceLoading,
  } = usePriceChecks({
    dateFrom: format(subDays(new Date(), 30), 'yyyy-MM-dd'),
    dateTo: dateStr,
    limit: 1000,
  });

  const isLoading = hierarchyLoading || priceLoading || filmsLoading;

  // Build hierarchy dropdowns
  const companies = useMemo(() => {
    if (!hierarchyData) return [];
    return Object.keys(hierarchyData).sort();
  }, [hierarchyData]);

  const directors = useMemo(() => {
    if (!hierarchyData || !selectedCompany) return [];
    return Object.keys(hierarchyData[selectedCompany] || {}).sort();
  }, [hierarchyData, selectedCompany]);

  const marketsInDirector = useMemo(() => {
    if (!hierarchyData || !selectedCompany || !selectedDirector) return [];
    return Object.keys(hierarchyData[selectedCompany]?.[selectedDirector] || {}).sort();
  }, [hierarchyData, selectedCompany, selectedDirector]);

  const theatersInMarkets = useMemo(() => {
    if (!hierarchyData || !selectedCompany || !selectedDirector) return [];
    const theaters: { name: string; market: string }[] = [];
    selectedMarkets.forEach(market => {
      const marketData = hierarchyData[selectedCompany]?.[selectedDirector]?.[market];
      if (marketData?.theaters) {
        marketData.theaters.forEach(t => {
          // Filter out permanently closed theaters
          if (!t.name.includes('(Permanently Closed)')) {
            theaters.push({ name: t.name, market });
          }
        });
      }
    });
    return theaters;
  }, [hierarchyData, selectedCompany, selectedDirector, selectedMarkets]);

  // Combine DB films with price data
  const films = useMemo((): FilmSummary[] => {
    // Start with films from the database
    const filmSummaries: Record<string, FilmSummary> = {};
    
    if (dbFilms) {
      dbFilms.forEach(f => {
        filmSummaries[f.film_title] = {
          title: f.film_title,
          theaters: 0,
          showtimes: 0,
          avgPrice: 0,
          formats: f.genre ? [f.genre] : [], // Reusing genre for now or just empty
          latestDate: f.release_date || '',
          selected: selectedFilms.has(f.film_title),
          poster_url: f.poster_url,
          rating: f.mpaa_rating,
          runtime: f.runtime,
          plot: f.plot
        };
      });
    }

    // Augment with price data stats
    if (priceData?.price_checks) {
      const priceStats: Record<string, { theaters: Set<string>, showtimes: number, prices: number[], formats: Set<string>, latest: string }> = {};
      
      priceData.price_checks.forEach(check => {
        const title = check.film_title;
        if (!priceStats[title]) {
          priceStats[title] = { theaters: new Set(), showtimes: 0, prices: [], formats: new Set(), latest: check.play_date };
        }
        priceStats[title].theaters.add(check.theater_name);
        priceStats[title].showtimes += 1;
        priceStats[title].prices.push(check.price);
        if (check.format) priceStats[title].formats.add(check.format);
        if (check.play_date > priceStats[title].latest) priceStats[title].latest = check.play_date;
      });

      Object.entries(priceStats).forEach(([title, stats]) => {
        if (!filmSummaries[title]) {
          filmSummaries[title] = {
            title,
            theaters: stats.theaters.size,
            showtimes: stats.showtimes,
            avgPrice: stats.prices.reduce((a, b) => a + b, 0) / stats.prices.length,
            formats: Array.from(stats.formats),
            latestDate: stats.latest,
            selected: selectedFilms.has(title)
          };
        } else {
          filmSummaries[title].theaters = stats.theaters.size;
          filmSummaries[title].showtimes = stats.showtimes;
          filmSummaries[title].avgPrice = stats.prices.reduce((a, b) => a + b, 0) / stats.prices.length;
          // Merge formats
          const mergedFormats = new Set([...(filmSummaries[title].formats || []), ...stats.formats]);
          filmSummaries[title].formats = Array.from(mergedFormats);
        }
      });
    }

    return Object.values(filmSummaries)
      .sort((a, b) => (b.showtimes || 0) - (a.showtimes || 0));
  }, [dbFilms, priceData, selectedFilms]);

  // Filter films by search
  const filteredFilms = useMemo(() => {
    if (!searchQuery) return films;
    return films.filter(f =>
      f.title.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [films, searchQuery]);

  // Check for same-day after 4PM warning
  const sameDayWarning = useMemo(() => {
    if (!isToday(selectedStartDate)) return false;
    return getHours(new Date()) >= 16;
  }, [selectedStartDate]);

  // Calculate summary stats
  const summaryStats = useMemo(() => ({
    filmsShowing: films.length,
    selectedFilms: selectedFilms.size,
    selectedTheaters: selectedTheaters.size,
    dateRange: selectedStartDate.getTime() === selectedEndDate.getTime()
      ? format(selectedStartDate, 'MMM d, yyyy')
      : `${format(selectedStartDate, 'MMM d')} - ${format(selectedEndDate, 'MMM d, yyyy')}`,
  }), [films, selectedFilms, selectedTheaters, selectedStartDate, selectedEndDate]);

  // Film selection handlers
  const toggleFilmSelection = (title: string) => {
    const newSet = new Set(selectedFilms);
    if (newSet.has(title)) {
      newSet.delete(title);
    } else {
      newSet.add(title);
    }
    setSelectedFilms(newSet);
  };

  const selectAllFilms = () => {
    setSelectedFilms(new Set(filteredFilms.map(f => f.title)));
  };

  const deselectAllFilms = () => {
    setSelectedFilms(new Set());
  };

  // Market selection handlers
  const toggleMarketSelection = (market: string) => {
    const newMarkets = new Set(selectedMarkets);
    const newTheaters = new Set(selectedTheaters);

    if (newMarkets.has(market)) {
      newMarkets.delete(market);
      // Remove theaters from this market
      const marketTheaters = hierarchyData?.[selectedCompany]?.[selectedDirector]?.[market]?.theaters || [];
      marketTheaters.forEach(t => newTheaters.delete(t.name));
    } else {
      newMarkets.add(market);
      // Add all theaters from this market
      const marketTheaters = hierarchyData?.[selectedCompany]?.[selectedDirector]?.[market]?.theaters || [];
      marketTheaters.forEach(t => {
        if (!t.name.includes('(Permanently Closed)')) {
          newTheaters.add(t.name);
        }
      });
    }

    setSelectedMarkets(newMarkets);
    setSelectedTheaters(newTheaters);
  };

  const toggleTheaterSelection = (theaterName: string) => {
    const newSet = new Set(selectedTheaters);
    if (newSet.has(theaterName)) {
      newSet.delete(theaterName);
    } else {
      newSet.add(theaterName);
    }
    setSelectedTheaters(newSet);
  };

  const selectAllTheaters = () => {
    setSelectedTheaters(new Set(theatersInMarkets.map(t => t.name)));
  };

  // Scrape handler
  const handleStartScrape = async () => {
    if (selectedFilms.size === 0 || selectedTheaters.size === 0) return;

    // Build theater list for API
    const theaterList = Array.from(selectedTheaters).map(name => {
      // Find the theater in hierarchy Data to get its URL?
      let url = '';
      if (hierarchyData) {
        // Walk the hierarchy to find the URL
        Object.values(hierarchyData).forEach(directors => {
          Object.values(directors).forEach(markets => {
            Object.values(markets).forEach((market: any) => {
              const found = market.theaters?.find((t: any) => t.name === name);
              if (found) url = found.url;
            });
          });
        });
      }
      return { name, url };
    }).filter(t => t.url);

    if (theaterList.length === 0) {
      alert("Could not find URLs for selected theaters. Please try selecting again.");
      return;
    }

    try {
      const result = await triggerScrape.mutateAsync({
        mode: 'poster',
        theaters: theaterList,
        dates: [format(selectedStartDate, 'yyyy-MM-dd'), format(selectedEndDate, 'yyyy-MM-dd')],
        // We might want to pass selected films as well if the backend supports it in TriggerScrapeRequest
        // The TriggerScrapeRequest in scrapes.py doesn't have a 'films' list currently.
        // But we can add it or handle it in the backend logic for 'poster' mode.
      });

      if (result.job_id) {
        setActiveJobId(result.job_id);
      }
    } catch (err) {
      console.error("Failed to trigger scrape:", err);
    }
  };

  // Navigation
  const goToStep = (step: WizardStep) => {
    setCurrentStep(step);
  };

  const nextStep = () => {
    const idx = WIZARD_STEPS.findIndex(s => s.key === currentStep);
    if (idx < WIZARD_STEPS.length - 1) {
      setCurrentStep(WIZARD_STEPS[idx + 1].key);
    }
  };

  const prevStep = () => {
    const idx = WIZARD_STEPS.findIndex(s => s.key === currentStep);
    if (idx > 0) {
      setCurrentStep(WIZARD_STEPS[idx - 1].key);
    }
  };

  // Export
  const handleExportCsv = () => {
    if (films.length === 0) return;

    const headers = ['Film', 'Theaters', 'Showtimes', 'Avg Price', 'Formats', 'Selected'];
    const rows = films.map((f) => [
      `"${f.title}"`,
      f.theaters,
      f.showtimes,
      f.avgPrice.toFixed(2),
      `"${f.formats.join('; ')}"`,
      selectedFilms.has(f.title) ? 'Yes' : 'No',
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `poster-board-${format(new Date(), 'yyyy-MM-dd')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Check if step is complete
  const isStepComplete = (step: WizardStep) => {
    switch (step) {
      case 'films': return selectedFilms.size > 0;
      case 'dates': return true; // Always valid since we have defaults
      case 'theaters': return selectedTheaters.size > 0;
      case 'confirm': return false;
    }
  };

  const canProceed = () => {
    switch (currentStep) {
      case 'films': return selectedFilms.size > 0;
      case 'dates': return true;
      case 'theaters': return selectedTheaters.size > 0;
      case 'confirm': return selectedFilms.size > 0 && selectedTheaters.size > 0;
    }
  };

  if (isLoading && films.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Poster Board</h1>
          <p className="text-muted-foreground">
            Select films, dates, and theaters for price scraping
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleExportCsv} disabled={films.length === 0}>
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center justify-between bg-muted/50 rounded-lg p-4">
        {WIZARD_STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isActive = currentStep === step.key;
          const isComplete = isStepComplete(step.key);
          const isPast = WIZARD_STEPS.findIndex(s => s.key === currentStep) > idx;

          return (
            <div key={step.key} className="flex items-center">
              <button
                onClick={() => goToStep(step.key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : isPast || isComplete
                    ? 'bg-green-500/10 text-green-600 hover:bg-green-500/20'
                    : 'hover:bg-muted'
                }`}
              >
                <div className="relative">
                  <Icon className="h-5 w-5" />
                  {isComplete && !isActive && (
                    <CheckCircle2 className="h-3 w-3 absolute -top-1 -right-1 text-green-500" />
                  )}
                </div>
                <span className="font-medium">{step.label}</span>
              </button>
              {idx < WIZARD_STEPS.length - 1 && (
                <ChevronRight className="h-5 w-5 mx-2 text-muted-foreground" />
              )}
            </div>
          );
        })}
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-4 gap-4">
        <Card className={selectedFilms.size > 0 ? 'border-green-500/50' : ''}>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Film className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Films</span>
              </div>
              <Badge variant={selectedFilms.size > 0 ? 'default' : 'secondary'}>
                {selectedFilms.size} selected
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Dates</span>
              </div>
              <span className="text-sm font-medium">{summaryStats.dateRange}</span>
            </div>
          </CardContent>
        </Card>
        <Card className={selectedTheaters.size > 0 ? 'border-green-500/50' : ''}>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Theaters</span>
              </div>
              <Badge variant={selectedTheaters.size > 0 ? 'default' : 'secondary'}>
                {selectedTheaters.size} selected
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">Available</span>
              </div>
              <span className="text-sm font-medium">{summaryStats.filmsShowing} films</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Step Content */}
      {currentStep === 'films' && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Select Films</CardTitle>
                <CardDescription>
                  Choose films to include in the price scrape
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button 
                   variant="outline" 
                   size="sm" 
                   onClick={() => discoverMutation.mutate()}
                   disabled={discoverMutation.isPending}
                >
                  <Sparkles className={`h-4 w-4 mr-1 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />
                  Discover New
                </Button>
                <div className="w-px h-8 bg-border mx-1" />
                <Button
                  variant={viewMode === 'grid' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setViewMode('grid')}
                >
                  <Grid3X3 className="h-4 w-4" />
                </Button>
                <Button
                  variant={viewMode === 'list' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setViewMode('list')}
                >
                  <List className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Search and bulk actions */}
            <div className="flex items-center justify-between mb-4">
              <div className="relative w-64">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search films..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8"
                />
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={selectAllFilms}>
                  <Check className="h-4 w-4 mr-1" />
                  Select All
                </Button>
                <Button variant="outline" size="sm" onClick={deselectAllFilms}>
                  <X className="h-4 w-4 mr-1" />
                  Clear
                </Button>
              </div>
            </div>

            {/* Film display */}
            {filteredFilms.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                <Film className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No films found. Run some price scrapes to populate the poster board.</p>
              </div>
            ) : viewMode === 'grid' ? (
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 max-h-[500px] overflow-y-auto">
                {filteredFilms.map((film) => (
                  <div
                    key={film.title}
                    onClick={() => toggleFilmSelection(film.title)}
                    className={`cursor-pointer rounded-lg overflow-hidden border-2 transition-all group ${
                      film.selected
                        ? 'border-primary ring-2 ring-primary/20'
                        : 'border-transparent hover:border-muted-foreground/20'
                    }`}
                  >
                    <div className="aspect-[2/3] bg-muted relative flex items-center justify-center overflow-hidden">
                      {film.poster_url ? (
                        <img 
                          src={film.poster_url} 
                          alt={film.title} 
                          className="w-full h-full object-cover transition-transform group-hover:scale-105"
                        />
                      ) : (
                        <div className="flex flex-col items-center gap-2 opacity-30">
                          <Film className="h-12 w-12" />
                          <span className="text-[10px] uppercase font-bold tracking-widest text-center px-2">
                            {film.title}
                          </span>
                        </div>
                      )}
                      
                      {/* Overlay Info */}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-2 flex flex-col justify-end">
                        {film.rating && <Badge variant="secondary" className="w-fit text-[8px] mb-1">{film.rating}</Badge>}
                        <p className="text-[8px] text-white line-clamp-3">{film.plot}</p>
                      </div>

                      {film.selected && (
                        <div className="absolute top-2 left-2 shadow-lg rounded-full">
                          <CheckCircle2 className="h-6 w-6 text-primary bg-background rounded-full" />
                        </div>
                      )}
                      {film.formats && film.formats.length > 0 && (
                        <div className="absolute top-2 right-2 flex flex-col gap-1 items-end">
                          {film.formats.slice(0, 3).map((fmt) => (
                            <span 
                                key={fmt} 
                                title={fmt}
                                className="bg-black/40 backdrop-blur-sm rounded-md px-1 py-0.5 text-[10px]"
                            >
                                {getFormatEmoji(fmt)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="p-2 bg-card border-t">
                      <h3 className="font-bold text-[10px] truncate" title={film.title}>
                        {film.title}
                      </h3>
                      <div className="flex items-center justify-between mt-1 text-[8px] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Building2 className="h-3 w-3" />
                          {film.theaters || 0}
                        </span>
                        <span className="font-medium text-foreground">
                          {film.avgPrice ? `$${film.avgPrice.toFixed(0)}` : 'N/A'}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="max-h-[500px] overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12"></TableHead>
                      <TableHead>Film</TableHead>
                      <TableHead>Formats</TableHead>
                      <TableHead className="text-right">Theaters</TableHead>
                      <TableHead className="text-right">Showtimes</TableHead>
                      <TableHead className="text-right">Avg Price</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredFilms.map((film) => (
                      <TableRow
                        key={film.title}
                        className={`cursor-pointer ${film.selected ? 'bg-primary/5' : ''}`}
                        onClick={() => toggleFilmSelection(film.title)}
                      >
                        <TableCell>
                          {film.selected ? (
                            <CheckCircle2 className="h-5 w-5 text-primary" />
                          ) : (
                            <Circle className="h-5 w-5 text-muted-foreground" />
                          )}
                        </TableCell>
                        <TableCell className="font-medium">{film.title}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {film.formats.map(fmt => (
                              <span key={fmt} title={fmt}>{getFormatEmoji(fmt)}</span>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">{film.theaters}</TableCell>
                        <TableCell className="text-right">{film.showtimes}</TableCell>
                        <TableCell className="text-right">${film.avgPrice.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {currentStep === 'dates' && (
        <Card>
          <CardHeader>
            <CardTitle>Choose Dates</CardTitle>
            <CardDescription>
              Select the date range for showtime scraping
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Same-day warning */}
            {sameDayWarning && (
              <div className="flex items-center gap-3 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-yellow-500" />
                <div>
                  <p className="font-medium text-yellow-600">Late Same-Day Scrape Warning</p>
                  <p className="text-sm text-muted-foreground">
                    It's after 4 PM. Same-day scrapes may have limited showtime availability.
                  </p>
                </div>
              </div>
            )}

            {/* Quick date buttons */}
            <div>
              <Label className="mb-2 block">Quick Select</Label>
              <div className="flex gap-2 flex-wrap">
                {[0, 1, 2, 3, 4, 5, 6].map((offset) => {
                  const date = addDays(new Date(), offset);
                  const isSelected = format(date, 'yyyy-MM-dd') === format(selectedStartDate, 'yyyy-MM-dd');
                  return (
                    <Button
                      key={offset}
                      variant={isSelected ? 'default' : 'outline'}
                      onClick={() => {
                        setSelectedStartDate(date);
                        setSelectedEndDate(date);
                      }}
                    >
                      {offset === 0 ? 'Today' : offset === 1 ? 'Tomorrow' : format(date, 'EEE MMM d')}
                    </Button>
                  );
                })}
              </div>
            </div>

            {/* Date range inputs */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="startDate">Start Date</Label>
                <Input
                  id="startDate"
                  type="date"
                  value={format(selectedStartDate, 'yyyy-MM-dd')}
                  onChange={(e) => setSelectedStartDate(new Date(e.target.value))}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="endDate">End Date</Label>
                <Input
                  id="endDate"
                  type="date"
                  value={format(selectedEndDate, 'yyyy-MM-dd')}
                  onChange={(e) => setSelectedEndDate(new Date(e.target.value))}
                  className="mt-1"
                  min={format(selectedStartDate, 'yyyy-MM-dd')}
                />
              </div>
            </div>

            {/* Date range summary */}
            <div className="p-4 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground">Selected Range</p>
              <p className="text-lg font-semibold">{summaryStats.dateRange}</p>
              {selectedStartDate.getTime() !== selectedEndDate.getTime() && (
                <p className="text-sm text-muted-foreground mt-1">
                  {Math.ceil((selectedEndDate.getTime() - selectedStartDate.getTime()) / (1000 * 60 * 60 * 24)) + 1} days
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {currentStep === 'theaters' && (
        <Card>
          <CardHeader>
            <CardTitle>Select Theaters</CardTitle>
            <CardDescription>
              Choose theaters for the price scrape using the hierarchy
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Hierarchy selection */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="company">Company</Label>
                <select
                  id="company"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={selectedCompany}
                  onChange={(e) => {
                    setSelectedCompany(e.target.value);
                    setSelectedDirector('');
                    setSelectedMarkets(new Set());
                    setSelectedTheaters(new Set());
                  }}
                >
                  <option value="">Select Company</option>
                  {companies.map((company) => (
                    <option key={company} value={company}>
                      {company} {isMarcusCompany(company) ? '⭐' : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="director">Director / Region</Label>
                <select
                  id="director"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={selectedDirector}
                  onChange={(e) => {
                    setSelectedDirector(e.target.value);
                    setSelectedMarkets(new Set());
                    setSelectedTheaters(new Set());
                  }}
                  disabled={!selectedCompany}
                >
                  <option value="">Select Director</option>
                  {directors.map((director) => (
                    <option key={director} value={director}>
                      {director}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Market selection */}
            {selectedDirector && marketsInDirector.length > 0 && (
              <div>
                <Label className="mb-2 block">Markets</Label>
                <div className="flex flex-wrap gap-2">
                  {marketsInDirector.map((market) => {
                    const isSelected = selectedMarkets.has(market);
                    return (
                      <Button
                        key={market}
                        variant={isSelected ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => toggleMarketSelection(market)}
                      >
                        {isSelected && <Check className="h-3 w-3 mr-1" />}
                        {market}
                      </Button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Theater selection */}
            {theatersInMarkets.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Theaters ({theatersInMarkets.length} available)</Label>
                  <Button variant="outline" size="sm" onClick={selectAllTheaters}>
                    <Check className="h-4 w-4 mr-1" />
                    Select All
                  </Button>
                </div>
                <div className="max-h-64 overflow-y-auto border rounded-lg">
                  {theatersInMarkets.map((theater) => {
                    const isSelected = selectedTheaters.has(theater.name);
                    return (
                      <div
                        key={theater.name}
                        className={`flex items-center justify-between p-2 border-b last:border-0 cursor-pointer hover:bg-muted/50 ${
                          isSelected ? 'bg-primary/5' : ''
                        }`}
                        onClick={() => toggleTheaterSelection(theater.name)}
                      >
                        <div className="flex items-center gap-2">
                          {isSelected ? (
                            <CheckCircle2 className="h-4 w-4 text-primary" />
                          ) : (
                            <Circle className="h-4 w-4 text-muted-foreground" />
                          )}
                          <span className="text-sm">{theater.name}</span>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {theater.market}
                        </Badge>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {!selectedCompany && (
              <div className="text-center text-muted-foreground py-8">
                <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Select a company to view available theaters</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {currentStep === 'confirm' && (
        <Card>
          <CardHeader>
            <CardTitle>Confirm & Run</CardTitle>
            <CardDescription>
              Review your selections before starting the scrape
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Film className="h-5 w-5 text-muted-foreground" />
                  <span className="font-medium">Films</span>
                </div>
                <p className="text-3xl font-bold">{selectedFilms.size}</p>
                <div className="mt-2 max-h-24 overflow-y-auto">
                  {Array.from(selectedFilms).slice(0, 5).map(film => (
                    <Badge key={film} variant="secondary" className="mr-1 mb-1 text-xs">
                      {film.substring(0, 20)}{film.length > 20 ? '...' : ''}
                    </Badge>
                  ))}
                  {selectedFilms.size > 5 && (
                    <span className="text-xs text-muted-foreground">+{selectedFilms.size - 5} more</span>
                  )}
                </div>
              </div>

              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="h-5 w-5 text-muted-foreground" />
                  <span className="font-medium">Date Range</span>
                </div>
                <p className="text-xl font-bold">{summaryStats.dateRange}</p>
                {sameDayWarning && (
                  <Badge className="mt-2 bg-yellow-500/10 text-yellow-600">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    After 4 PM
                  </Badge>
                )}
              </div>

              <div className="p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Building2 className="h-5 w-5 text-muted-foreground" />
                  <span className="font-medium">Theaters</span>
                </div>
                <p className="text-3xl font-bold">{selectedTheaters.size}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {selectedMarkets.size} markets
                </p>
              </div>
            </div>

            {/* Validation */}
            {(selectedFilms.size === 0 || selectedTheaters.size === 0) && (
              <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-red-500" />
                <div>
                  <p className="font-medium text-red-600">Missing Selections</p>
                  <p className="text-sm text-muted-foreground">
                    {selectedFilms.size === 0 && 'No films selected. '}
                    {selectedTheaters.size === 0 && 'No theaters selected.'}
                  </p>
                </div>
              </div>
            )}

            {/* Action button */}
            <div className="space-y-4">
              {activeJobId && scrapeStatus?.status && scrapeStatus.status !== 'completed' && scrapeStatus.status !== 'failed' && (
                <div className="p-4 border rounded-lg bg-primary/5 space-y-2">
                   <div className="flex items-center justify-between text-sm">
                      <span className="font-medium flex items-center gap-2">
                         <RefreshCw className="h-4 w-4 animate-spin" />
                         Scraping in progress...
                      </span>
                      <span>{Math.round(scrapeStatus.progress * 100)}%</span>
                   </div>
                   <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                      <div 
                         className="bg-primary h-full transition-all duration-500" 
                         style={{ width: `${scrapeStatus.progress * 100}%` }}
                      />
                   </div>
                   {scrapeStatus.current_theater && (
                     <p className="text-xs text-muted-foreground">
                        Current: <span className="text-foreground">{scrapeStatus.current_theater}</span>
                     </p>
                   )}
                </div>
              )}

              <Button
                className="w-full"
                size="lg"
                onClick={handleStartScrape}
                disabled={selectedFilms.size === 0 || selectedTheaters.size === 0 || (activeJobId !== null && scrapeStatus?.status === 'running')}
              >
                {activeJobId && scrapeStatus?.status === 'running' ? (
                  <>
                    <RefreshCw className="h-5 w-5 mr-2 animate-spin" />
                    Running Scrape...
                  </>
                ) : (
                  <>
                    <Play className="h-5 w-5 mr-2" />
                    Start Price Scrape
                  </>
                )}
              </Button>
            </div>

            <p className="text-center text-sm text-muted-foreground">
              This will fetch showtimes and prices for the selected films and theaters
            </p>
          </CardContent>
        </Card>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={prevStep}
          disabled={currentStep === 'films'}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
        {currentStep !== 'confirm' ? (
          <Button
            onClick={nextStep}
            disabled={!canProceed()}
          >
            Next
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}
