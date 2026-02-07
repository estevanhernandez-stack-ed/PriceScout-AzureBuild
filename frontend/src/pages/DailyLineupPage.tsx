import React, { useState, useMemo, useEffect } from 'react';
import { useMarketsHierarchy, useTheaterCache } from '@/hooks/api/useMarkets';
import { useDailyLineup, useOperatingHours } from '@/hooks/api/useReports';
import { useTriggerScrape, useScrapeStatus, useLiveScrapeJobs } from '@/hooks/api/useScrapes';
import { useDemandLookup, buildDemandMap, computeDemandSummary, getFillRateColor, demandKey, type DemandMetric } from '@/hooks/api/useDemandLookup';
import { useBoxOfficeBoard, downloadBoardHtml, downloadBoardImage, RESOLUTION_LABELS, type BoardResolution } from '@/hooks/api/useBoxOfficeBoard';
import { api } from '@/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  MapPin,
  Building2,
  Calendar,
  Film,
  Clock,
  RefreshCw,
  RefreshCcw,
  Play,
  Users,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  Printer,
  AlertCircle,
  Wand2,
  TrendingUp,
  Flame,
  Monitor,
  Download,
} from 'lucide-react';
import { format, addDays } from 'date-fns';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';

// LocalStorage key for persisting scrape job ID
const LINEUP_JOB_STORAGE_KEY = 'pricescout_lineup_scrape_job';

interface TheaterEntry {
  name: string;
  zip?: string;
  status?: string;
}

interface ShowtimeEntry {
  film_title: string;
  showtime: string;
  format?: string;
  daypart?: string;
  is_plf?: boolean;
  runtime?: number;
  out_time?: string;
}

// Format emoji mapping
const getFormatEmoji = (format: string, isPlf?: boolean) => {
  if (!format) return isPlf ? '🌟' : '';
  const formatLower = format.toLowerCase();
  if (formatLower.includes('imax')) return '📽️';
  if (formatLower.includes('dolby') || formatLower.includes('atmos')) return '🔊';
  if (formatLower.includes('4dx')) return '💨';
  if (formatLower.includes('screenx')) return '🖼️';
  if (formatLower.includes('3d')) return '🕶️';
  if (formatLower.includes('d-box') || formatLower.includes('dbox')) return '💺';
  if (formatLower.includes('dfx') || formatLower.includes('xd') || formatLower.includes('rpx')) return '✨';
  if (formatLower.includes('plf') || formatLower.includes('superscreen') || isPlf) return '🌟';
  return '';
};

// Compact film title helper
const compactFilmTitle = (
  title: string,
  options: {
    removeYear?: boolean;
    removeArticles?: boolean;
    maxWords?: number;
  }
) => {
  if (!title) return title;

  let result = title.trim();

  // Remove bracketed year at end (e.g., "(2024)", "(2025)")
  if (options.removeYear) {
    result = result.replace(/\s*\(\d{4}\)\s*$/, '');
  }

  // Optionally remove leading articles
  if (options.removeArticles) {
    result = result.replace(/^(The|A|An)\s+/i, '');
  }

  // Limit to max words if specified
  if (options.maxWords && options.maxWords > 0) {
    const words = result.split(/\s+/);
    if (words.length > options.maxWords) {
      result = words.slice(0, options.maxWords).join(' ');
    }
  }

  return result.trim();
};

// Format minutes since midnight to time string
const formatShowtimeMinutes = (
  totalMinutes: number,
  options: {
    useMilitaryTime?: boolean;
    showAmPm?: boolean;
  }
) => {
  const hours = Math.floor(totalMinutes / 60) % 24;
  const minutes = totalMinutes % 60;

  if (options.useMilitaryTime) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }

  const period = hours >= 12 ? 'PM' : 'AM';
  let hour12 = hours % 12;
  if (hour12 === 0) hour12 = 12;

  return `${hour12}:${String(minutes).padStart(2, '0')}${options.showAmPm ? ` ${period}` : ''}`;
};

// Format showtime string
const formatShowtime = (
  timeStr: string,
  options: {
    useMilitaryTime?: boolean;
    showAmPm?: boolean;
  }
) => {
  try {
    const totalMinutes = parseShowtimeForSort(timeStr);
    return formatShowtimeMinutes(totalMinutes, options);
  } catch {
    return timeStr;
  }
};

// Parse showtime string to sortable value
const parseShowtimeForSort = (timeStr: string): number => {
  if (!timeStr) return 0;

  // Handle various time formats
  const time = timeStr.trim().toUpperCase();

  // Try to parse "HH:MM AM/PM" format
  const match12 = time.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  if (match12) {
    let hours = parseInt(match12[1], 10);
    const minutes = parseInt(match12[2], 10);
    const period = match12[3]?.toUpperCase();

    if (period === 'PM' && hours !== 12) hours += 12;
    if (period === 'AM' && hours === 12) hours = 0;

    return hours * 60 + minutes;
  }

  // Try to parse "H:MM" format (24-hour)
  const match24 = time.match(/^(\d{1,2}):(\d{2})$/);
  if (match24) {
    const hours = parseInt(match24[1], 10);
    const minutes = parseInt(match24[2], 10);
    return hours * 60 + minutes;
  }

  return 0;
};

// Calculate out-time based on showtime and runtime
const calculateOutTime = (
  showtime: string,
  runtime?: number | string,
  options?: { useMilitaryTime?: boolean; showAmPm?: boolean; trailerTime?: number }
): string | undefined => {
  if (!runtime) return undefined;

  let runtimeMinutes = 0;
  if (typeof runtime === 'number') {
    runtimeMinutes = runtime;
  } else if (typeof runtime === 'string') {
    // Extract numbers from strings like "120 min" or just "120"
    const match = runtime.match(/(\d+)/);
    if (match) {
      runtimeMinutes = parseInt(match[1], 10);
    }
  }

  if (!runtimeMinutes || runtimeMinutes <= 0) return undefined;

  try {
    const timeValue = parseShowtimeForSort(showtime);
    if (timeValue === 0) return undefined;

    const trailerOffset = options?.trailerTime || 0;
    const endMinutes = timeValue + runtimeMinutes + trailerOffset;
    return formatShowtimeMinutes(endMinutes, options || { useMilitaryTime: false, showAmPm: true });
  } catch {
    return undefined;
  }
};

// Get format badge variant
const getFormatBadgeClass = (formatStr?: string, isPlf?: boolean) => {
  if (!formatStr && !isPlf) return '';
  const formatLower = (formatStr || '').toLowerCase();
  if (formatLower.includes('imax')) return 'bg-purple-500/20 text-purple-400 border-purple-500/30 font-bold';
  if (formatLower.includes('dolby') || formatLower.includes('atmos')) return 'bg-blue-500/20 text-blue-400 border-blue-500/30 font-bold';
  if (formatLower.includes('4dx')) return 'bg-orange-500/20 text-orange-400 border-orange-500/30 font-bold';
  if (formatLower.includes('3d')) return 'bg-green-500/20 text-green-400 border-green-500/30 font-bold';
  if (formatLower.includes('screenx')) return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30 font-bold';
  if (isPlf || formatLower.includes('dfx') || formatLower.includes('xd') || formatLower.includes('rpx')) return 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30 font-bold italic';
  return 'bg-muted/50 text-muted-foreground border-border';
};

// Normalize format for display (e.g., "Premium Format" -> "PLF")
const normalizeFormatDisplay = (format?: string, isPlf?: boolean): string => {
  if (!format && !isPlf) return '';
  
  const formatLower = (format || '').toLowerCase();
  
  // Hide standard/2D formats
  if (formatLower === 'standard' || formatLower === '2d' || formatLower === 'standard 2d' || formatLower.includes('standard')) {
    return '';
  }
  
  // Normalize PLF variants
  if (formatLower === 'premium format' || formatLower.includes('premium')) {
    return 'PLF';
  }
  
  // Return as-is for named formats
  if (isPlf && !format) return 'PLF';
  return format || '';
};

export function DailyLineupPage() {
  const { user } = useAuthStore();
  const selectedCompany = user?.company || 'Marcus Theatres';

  // Hierarchy state (Director → Market → Theater)
  const [selectedDirector, setSelectedDirector] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedTheater, setSelectedTheater] = useState<string>('');

  // Date state
  const [selectedDate, setSelectedDate] = useState<string>(format(addDays(new Date(), 1), 'yyyy-MM-dd'));

  // Workflow state
  const [step, setStep] = useState<'select' | 'results'>('select');

  // Query state
  const [queryTheater, setQueryTheater] = useState<string>('');
  const [queryDate, setQueryDate] = useState<string>('');

  // View mode
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');

  // Box Office Board state
  const [boardResolution, setBoardResolution] = useState<BoardResolution>('1080p');
  const [boardDownloading, setBoardDownloading] = useState(false);
  const [showBoard, setShowBoard] = useState(false);

  // Display options state
  const [compactTitles, setCompactTitles] = useState(true);
  const [removeArticles, setRemoveArticles] = useState(false);
  const [maxWords, setMaxWords] = useState(3);
  const [showOutTime, setShowOutTime] = useState(true);
  const [trailerTime, setTrailerTime] = useState(20);
  const [useMilitaryTime, setUseMilitaryTime] = useState(false);
  const [showAmPm, setShowAmPm] = useState(true);

  // Expanded sections
  const [expandedFilms, setExpandedFilms] = useState<Set<string>>(new Set());

  // Scraper status
  const [isScraping, setIsScraping] = useState(false);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  const { toast } = useToast();
  const { data: jobStatus, error: jobStatusError } = useScrapeStatus(activeJobId || 0, {
    enabled: !!activeJobId,
    refetchInterval: isScraping ? 2000 : false,
  });

  // Check for running scrapes (used to restore state on page load)
  const { data: liveScrapeJobs } = useLiveScrapeJobs();

  // Handle stale job IDs (e.g., server restarted and job no longer exists)
  useEffect(() => {
    if (jobStatusError && activeJobId) {
      const isNotFound = jobStatusError && 'response' in jobStatusError && (jobStatusError as { response?: { status?: number } }).response?.status === 404;
      if (isNotFound) {
        console.log('[DailyLineup] Job not found (server may have restarted), clearing stale job ID:', activeJobId);
        localStorage.removeItem(LINEUP_JOB_STORAGE_KEY);
        setActiveJobId(null);
        setIsScraping(false);
        toast({
          title: 'Session Expired',
          description: 'The previous scrape session is no longer available. Please start a new scrape.',
          variant: 'destructive',
        });
      }
    }
  }, [jobStatusError, activeJobId, toast]);

  // Restore scrape state from localStorage or API on mount
  useEffect(() => {
    // Check localStorage first
    const savedJobId = localStorage.getItem(LINEUP_JOB_STORAGE_KEY);
    if (savedJobId) {
      const parsedJobId = parseInt(savedJobId, 10);
      if (!isNaN(parsedJobId)) {
        console.log('[DailyLineup] Restoring job ID from localStorage:', parsedJobId);
        setActiveJobId(parsedJobId);
        setIsScraping(true);
        toast({
          title: 'Reconnecting to Scrape',
          description: `Found an active scrape job (ID: ${parsedJobId}). Restoring progress...`,
        });
        return;
      }
    }

    // Check API for any running scrapes
    if (liveScrapeJobs && liveScrapeJobs.length > 0) {
      const activeJob = liveScrapeJobs.find(j => j.status === 'running' || j.status === 'pending');
      if (activeJob) {
        console.log('[DailyLineup] Found active job from API:', activeJob.job_id);
        setActiveJobId(activeJob.job_id);
        setIsScraping(true);
        localStorage.setItem(LINEUP_JOB_STORAGE_KEY, String(activeJob.job_id));
        toast({
          title: 'Active Scrape Found',
          description: `Reconnected to running scrape job (ID: ${activeJob.job_id})`,
        });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveScrapeJobs]);

  // Save job ID to localStorage when it changes
  useEffect(() => {
    if (activeJobId) {
      localStorage.setItem(LINEUP_JOB_STORAGE_KEY, String(activeJobId));
      console.log('[DailyLineup] Saved job ID to localStorage:', activeJobId);
    }
  }, [activeJobId]);

  // Clear localStorage when scrape completes
  useEffect(() => {
    if (jobStatus?.status === 'completed' || jobStatus?.status === 'failed') {
      setIsScraping(false);
      const timeout = setTimeout(() => {
        localStorage.removeItem(LINEUP_JOB_STORAGE_KEY);
        console.log('[DailyLineup] Cleared job ID from localStorage (job completed)');
      }, 5 * 60 * 1000);
      return () => clearTimeout(timeout);
    }
  }, [jobStatus?.status]);

  // Fetch hierarchy and cache data
  const { data: hierarchyData, isLoading: hierarchyLoading } = useMarketsHierarchy();
  const { data: cacheData } = useTheaterCache();

  // Fetch lineup when we have selected theater and date
  const {
    data: lineupData,
    isLoading,
    isError,
    error,
    refetch,
  } = useDailyLineup({
    theater: queryTheater,
    date: queryDate,
  }, {
    refetchInterval: isScraping ? 3000 : 0,
    // Ensure we don't clear data while polling
    keepPreviousData: true
  });

  // Get available date range from operating hours (helper for the user)
  const { data: ohData } = useOperatingHours({ limit: 1 });
  const dateRange = ohData?.date_range;

  // Fetch demand data (EntTelligence capacity/sales) for the selected theater + date
  const hasLineupData = !!(lineupData as { theater?: string; showtimes?: ShowtimeEntry[] } | undefined)?.showtimes?.length;
  const { data: demandData } = useDemandLookup(
    queryTheater ? [queryTheater] : [],
    queryDate,
    undefined,
    undefined,
    hasLineupData && !!queryTheater && !!queryDate,
  );

  // Build demand lookup map and summary
  const demandMap = useMemo(() => {
    if (!demandData || demandData.length === 0) return new Map<string, DemandMetric>();
    return buildDemandMap(demandData);
  }, [demandData]);

  const demandSummary = useMemo(() => {
    if (!demandData || demandData.length === 0) return null;
    return computeDemandSummary(demandData);
  }, [demandData]);

  // Box Office Board HTML
  const { data: boardHtml, isLoading: boardLoading } = useBoxOfficeBoard(
    queryTheater,
    queryDate,
    boardResolution,
    showBoard && hasLineupData && !!queryTheater && !!queryDate,
  );

  // Stop scraping/polling when showtimes arrive
  React.useEffect(() => {
    const data = lineupData as { showtimes?: ShowtimeEntry[] } | undefined;
    if (data?.showtimes && data.showtimes.length > 0) {
      setIsScraping(false);
    }
  }, [lineupData]);

  type MarketEntry = { theaters?: { name: string; url: string }[] };
  type HierarchyLevel = Record<string, Record<string, MarketEntry>>;

  // Get company-level data
  const companyData = useMemo(() => {
    if (!hierarchyData || !selectedCompany) return null;
    return (hierarchyData as Record<string, HierarchyLevel>)[selectedCompany] || null;
  }, [hierarchyData, selectedCompany]);

  // Helper to determine if a theater is company-owned
  const isCompanyTheater = (name: string) => {
    const lowerName = name.toLowerCase();
    return lowerName.includes('marcus') || lowerName.includes('movie tavern');
  };

  // Get directors from hierarchy (only those with company theaters)
  const directors = useMemo(() => {
    if (!companyData) return [];
    return Object.keys(companyData).filter(dir => {
      const directorEntry = companyData[dir];
      return Object.values(directorEntry).some((marketEntry: MarketEntry) =>
        marketEntry.theaters?.some((t) => isCompanyTheater(t.name))
      );
    }).sort();
  }, [companyData]);

  // Get markets for selected director (only those with company theaters)
  const markets = useMemo(() => {
    if (!companyData || !selectedDirector) return [];
    const directorEntry = companyData[selectedDirector] || {};
    return Object.keys(directorEntry).filter(mkt => {
      const marketEntry = directorEntry[mkt];
      return marketEntry.theaters?.some((t) => isCompanyTheater(t.name));
    }).sort();
  }, [companyData, selectedDirector]);

  // Get theaters for selected market (filtered to company stores)
  const theaters = useMemo(() => {
    if (!companyData || !selectedDirector || !selectedMarket) return [];
    const marketEntry = companyData[selectedDirector]?.[selectedMarket];
    if (!marketEntry?.theaters) return [];
    
    return marketEntry.theaters
      .filter((t: { name: string }) => isCompanyTheater(t.name))
      .sort((a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name));
  }, [companyData, selectedDirector, selectedMarket]);

  // Process lineup data with out-times and sorting
  const processedShowtimes = useMemo(() => {
    const data = lineupData as { showtimes?: ShowtimeEntry[] } | undefined;
    if (!data?.showtimes) return [];

    let showtimes: ShowtimeEntry[] = data.showtimes.map((show) => ({
      ...show,
      showtime: formatShowtime(show.showtime, { useMilitaryTime, showAmPm }),
      out_time: showOutTime ? calculateOutTime(show.showtime, show.runtime, { useMilitaryTime, showAmPm, trailerTime }) : undefined,
    }));

    // Apply title compacting
    showtimes = showtimes.map((show) => {
      let title = compactFilmTitle(show.film_title, {
        removeYear: compactTitles,
        removeArticles,
        maxWords: maxWords > 0 ? maxWords : undefined
      });

      // Append format if not standard/2D
      const displayFormat = normalizeFormatDisplay(show.format, show.is_plf);
      if (displayFormat) {
        title = `${title} [${displayFormat}]`;
      }

      return { ...show, film_title: title };
    });

    // Sort chronologically by original showtime
    showtimes.sort((a, b) => {
      const timeA = parseShowtimeForSort(a.showtime);
      const timeB = parseShowtimeForSort(b.showtime);
      return timeA - timeB;
    });

    return showtimes;
  }, [lineupData, compactTitles, removeArticles, maxWords, showOutTime, useMilitaryTime, showAmPm, trailerTime]);

  // Group lineup by film
  const lineupByFilm = useMemo(() => {
    if (!processedShowtimes.length) return {};

    const grouped: Record<string, { showtimes: ShowtimeEntry[]; format?: string; runtime?: number; is_plf?: boolean }> = {};

    processedShowtimes.forEach((show) => {
      const filmTitle = show.film_title;
      if (!grouped[filmTitle]) {
        grouped[filmTitle] = {
          showtimes: [],
          format: show.format,
          runtime: show.runtime,
          is_plf: show.is_plf,
        };
      }
      grouped[filmTitle].showtimes.push(show);
    });

    return grouped;
  }, [processedShowtimes]);

  // Calculate operating hours (first showtime start → last showtime start)
  // Note: Uses last showtime START, not end time with runtime added
  const operatingHours = useMemo(() => {
    if (!processedShowtimes.length) return null;

    const firstShow = processedShowtimes[0];
    const lastShow = processedShowtimes[processedShowtimes.length - 1];

    return {
      open: firstShow.showtime,
      close: lastShow.showtime,
    };
  }, [processedShowtimes]);

  // Scrape mutation
  const triggerScrapeMutation = useTriggerScrape();

  // Enrich mutation
  const [isEnriching, setIsEnriching] = useState<string | null>(null);

  const handleEnrichFilm = async (title: string) => {
    setIsEnriching(title);
    try {
      await api.post(`/films/enrich-single?film_title=${encodeURIComponent(title)}`);
      refetch();
    } catch (error) {
      console.error('Failed to enrich film:', error);
    } finally {
      setIsEnriching(null);
    }
  };

  const handleTriggerScrape = async () => {
    if (!selectedTheater) return;

    // Find theater URL from cache
    let theaterUrl = '';
    if (cacheData?.markets) {
      for (const marketName in cacheData.markets) {
        const t = cacheData.markets[marketName].theaters.find(
          (theater: { name: string; url: string }) => theater.name === selectedTheater
        );
        if (t) {
          theaterUrl = t.url;
          break;
        }
      }
    }

    const theatersToScrape = [{ name: selectedTheater, url: theaterUrl }];

    try {
      const result = await triggerScrapeMutation.mutateAsync({
        mode: 'lineup',
        theaters: theatersToScrape,
        dates: [selectedDate],
      });
      
      if (result?.job_id) {
        setActiveJobId(result.job_id);
      }
      
      // Poll for data after some time or rely on the user to refetch
      setTimeout(refetch, 5000); 
    } catch (error) {
      console.error('Scrape failed:', error);
    }
  };

  const handleFetchLineup = async () => {
    if (!selectedTheater) return;

    setQueryTheater(selectedTheater);
    setQueryDate(selectedDate);
    setStep('results');
    
    // Check if we need to trigger a scrape
    // If no data exists yet, we MUST trigger
    // useDailyLineup hook will handle the initial fetch concurrently
    setIsScraping(true);
    handleTriggerScrape();
  };

  const handleReset = () => {
    setStep('select');
    setQueryTheater('');
    setQueryDate('');
    setExpandedFilms(new Set());
    setIsScraping(false);
    setActiveJobId(null);
    // Clear localStorage
    localStorage.removeItem(LINEUP_JOB_STORAGE_KEY);
    console.log('[DailyLineup] Cleared job ID from localStorage (user reset)');
  };

  const handleExportCsv = () => {
    if (!processedShowtimes.length) return;

    const headers = ['Theater #', 'Film', 'Format', 'In-Time', 'Out-Time', 'Runtime'];
    const rows = processedShowtimes.map((show) => [
      '', // Theater # - left blank for manual entry
      show.film_title,
      show.format || 'Standard',
      show.showtime,
      show.out_time || '',
      show.runtime ? `${show.runtime} min` : '',
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `lineup_${selectedTheater.replace(/\s+/g, '_')}_${queryDate}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const handlePrint = () => {
    window.print();
  };

  const toggleFilmExpand = (film: string) => {
    const newExpanded = new Set(expandedFilms);
    if (newExpanded.has(film)) {
      newExpanded.delete(film);
    } else {
      newExpanded.add(film);
    }
    setExpandedFilms(newExpanded);
  };

  const isLoadingHierarchy = hierarchyLoading;

  if (isLoadingHierarchy) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Daily Lineup</h1>
          <p className="text-muted-foreground">
            View and print all films and showtimes for a specific theater and day
          </p>
        </div>
        {step === 'results' && (
          <Button variant="outline" onClick={handleReset}>
            <RefreshCw className="mr-2 h-4 w-4" />
            New Search
          </Button>
        )}
      </div>

      {step === 'select' && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Director Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Users className="h-5 w-5" />
                Director/Region
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {directors.map((director) => (
                  <Button
                    key={director}
                    variant={selectedDirector === director ? 'default' : 'ghost'}
                    className="w-full justify-start text-sm"
                    onClick={() => {
                      setSelectedDirector(director);
                      setSelectedMarket('');
                      setSelectedTheater('');
                    }}
                  >
                    {director}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Market Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <MapPin className="h-5 w-5" />
                Market
              </CardTitle>
            </CardHeader>
            <CardContent>
              {selectedDirector ? (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {markets.map((market) => (
                    <Button
                      key={market}
                      variant={selectedMarket === market ? 'default' : 'ghost'}
                      className="w-full justify-start text-sm"
                      onClick={() => {
                        setSelectedMarket(market);
                        setSelectedTheater('');
                        }}
                    >
                      {market}
                    </Button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Select a director first</p>
              )}
            </CardContent>
          </Card>

          {/* Theater Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Building2 className="h-5 w-5" />
                Theater
              </CardTitle>
            </CardHeader>
            <CardContent>
              {selectedMarket ? (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {theaters.map((theater: TheaterEntry) => (
                    <Button
                      key={theater.name}
                      variant={selectedTheater === theater.name ? 'default' : 'ghost'}
                      className="w-full justify-start text-sm"
                      onClick={() => setSelectedTheater(theater.name)}
                    >
                      {theater.name}
                    </Button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Select a market first</p>
              )}
            </CardContent>
          </Card>

          {/* Date Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Calendar className="h-5 w-5" />
                Date
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />

              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant={selectedDate === format(new Date(), 'yyyy-MM-dd') ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedDate(format(new Date(), 'yyyy-MM-dd'))}
                >
                  Today
                </Button>
                <Button
                  variant={selectedDate === format(addDays(new Date(), 1), 'yyyy-MM-dd') ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedDate(format(addDays(new Date(), 1), 'yyyy-MM-dd'))}
                >
                  Tomorrow
                </Button>
              </div>

              {dateRange?.earliest && (
                <div className="pt-2">
                  <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">Available Data Range</p>
                  <p className="text-xs font-medium text-primary/80">
                    {format(new Date(dateRange.earliest + 'T00:00:00'), 'MMM d, yyyy')} - {format(new Date(dateRange.latest + 'T00:00:00'), 'MMM d, yyyy')}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Display & Processing Options */}
          <Card className="lg:col-span-4">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Clock className="h-5 w-5" />
                Lineup Options
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Compact Titles</label>
                    <input
                      type="checkbox"
                      checked={compactTitles}
                      onChange={(e) => setCompactTitles(e.target.checked)}
                      className="h-4 w-4"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Remove Articles</label>
                    <input
                      type="checkbox"
                      checked={removeArticles}
                      onChange={(e) => setRemoveArticles(e.target.checked)}
                      className="h-4 w-4"
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Max Words</label>
                    <select
                      value={maxWords}
                      onChange={(e) => setMaxWords(parseInt(e.target.value, 10))}
                      className="text-sm border rounded p-1 bg-background"
                    >
                      <option value={0}>No limit</option>
                      <option value={2}>2 words</option>
                      <option value={3}>3 words</option>
                      <option value={4}>4 words</option>
                      <option value={5}>5 words</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Show Out-Time</label>
                    <input
                      type="checkbox"
                      checked={showOutTime}
                      onChange={(e) => setShowOutTime(e.target.checked)}
                      className="h-4 w-4"
                    />
                  </div>
                  {showOutTime && (
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium">Trailer Time (min)</label>
                      <Input
                        type="number"
                        value={trailerTime}
                        onChange={(e) => setTrailerTime(parseInt(e.target.value, 10) || 0)}
                        className="h-8 w-20 text-xs text-right"
                      />
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">24-Hour Time</label>
                    <input
                      type="checkbox"
                      checked={useMilitaryTime}
                      onChange={(e) => setUseMilitaryTime(e.target.checked)}
                      className="h-4 w-4"
                    />
                  </div>
                  {!useMilitaryTime && (
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium">Show AM/PM</label>
                      <input
                        type="checkbox"
                        checked={showAmPm}
                        onChange={(e) => setShowAmPm(e.target.checked)}
                        className="h-4 w-4"
                      />
                    </div>
                  )}
                </div>

                <div className="flex items-end gap-2">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={handleTriggerScrape}
                    disabled={!selectedTheater || triggerScrapeMutation.isPending}
                  >
                    <RefreshCcw className={cn("mr-2 h-4 w-4", triggerScrapeMutation.isPending && "animate-spin")} />
                    Scrape Latest
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={handleFetchLineup}
                    disabled={!selectedTheater}
                  >
                    <Play className="mr-2 h-4 w-4" />
                    Get Lineup
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {step === 'results' && (
        <div className="space-y-6">
          {isLoading ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <RefreshCw className="h-5 w-5 animate-spin" />
                  Loading Lineup
                </CardTitle>
                <CardDescription>
                  Fetching showtimes for {queryTheater}...
                </CardDescription>
              </CardHeader>
            </Card>
          ) : isError ? (
            <Card className="border-red-500/20 bg-red-500/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-red-500">
                  <AlertCircle className="h-5 w-5" />
                  No Data Found
                </CardTitle>
                <CardDescription className="text-red-400/80">
                  {isScraping 
                    ? `Our robots are currently visiting Fandango to fetch the latest showtimes for ${queryTheater}. Results will appear automatically in a few moments...`
                    : error && 'response' in error && (error as { response?: { status?: number } }).response?.status === 404 
                      ? `No showtimes were found for ${queryTheater} on ${format(new Date(selectedDate + 'T00:00:00'), 'MMM d, yyyy')}. This theater may not have been scraped for this date yet.`
                      : `Could not fetch showtimes for ${queryTheater}. Please try again later.`
                  }
                </CardDescription>
                {isScraping && (
                  <div className="mt-4 space-y-4">
                    <div className="flex items-center gap-3 text-sm text-primary">
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      {jobStatus?.status === 'running' 
                        ? `Visiting Fandango: ${jobStatus.progress}% complete...` 
                        : 'Contacting Scrape Hub...'}
                    </div>
                    {jobStatus?.progress !== undefined && (
                      <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                        <div 
                          className="bg-primary h-full transition-all duration-500" 
                          style={{ width: `${jobStatus.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                )}
              </CardHeader>
              {dateRange?.latest && (
                <CardContent>
                  <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
                    <p className="text-xs text-orange-400 font-medium flex items-center gap-2">
                      <Wand2 className="h-3 w-3" />
                      Tip: Try selecting a date between {format(new Date(dateRange.earliest + 'T00:00:00'), 'MMM d')} and {format(new Date(dateRange.latest + 'T00:00:00'), 'MMM d, yyyy')} where we have historical data.
                    </p>
                  </div>
                </CardContent>
              )}
            </Card>
          ) : (
            <>
              {/* Summary Bar */}
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="flex items-center gap-3 flex-wrap">
                  <Badge variant="secondary" className="text-sm py-1 px-3">
                    <Building2 className="mr-1 h-3 w-3" />
                    {(lineupData as { theater?: string; showtimes?: ShowtimeEntry[] } | undefined)?.theater || queryTheater}
                  </Badge>
                  <Badge variant="secondary" className="text-sm py-1 px-3">
                    <Calendar className="mr-1 h-3 w-3" />
                    {format(new Date(selectedDate + 'T00:00:00'), 'EEEE, MMMM d, yyyy')}
                  </Badge>
                  <Badge variant="secondary" className="text-sm py-1 px-3">
                    <Film className="mr-1 h-3 w-3" />
                    {Object.keys(lineupByFilm).length} films
                  </Badge>
                  <Badge variant="secondary" className="text-sm py-1 px-3">
                    <Clock className="mr-1 h-3 w-3" />
                    {processedShowtimes.length} showtimes
                  </Badge>
                  {operatingHours && (
                    <Badge className="text-sm py-1 px-3 bg-green-500/20 text-green-400 border-green-500/30">
                      <Clock className="mr-1 h-3 w-3" />
                      {operatingHours.open} - {operatingHours.close}
                    </Badge>
                  )}
                  {demandSummary && demandSummary.highDemandCount > 0 && (
                    <Badge className="text-sm py-1 px-3 bg-red-500/20 text-red-400 border-red-500/30 animate-pulse">
                      <Flame className="mr-1 h-3 w-3" />
                      {demandSummary.highDemandCount} high-demand showtime{demandSummary.highDemandCount !== 1 ? 's' : ''}
                    </Badge>
                  )}
                  {demandSummary && demandSummary.highDemandCount === 0 && demandSummary.totalShowtimes > 0 && (
                    <Badge className="text-sm py-1 px-3 bg-blue-500/20 text-blue-400 border-blue-500/30">
                      <TrendingUp className="mr-1 h-3 w-3" />
                      {demandSummary.avgFillRate}% avg fill
                    </Badge>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'cards' | 'table')}>
                    <TabsList className="h-8">
                      <TabsTrigger value="cards" className="text-xs px-2">Cards</TabsTrigger>
                      <TabsTrigger value="table" className="text-xs px-2">Table</TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <Button variant="outline" size="sm" onClick={handleExportCsv}>
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                    CSV
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePrint}>
                    <Printer className="mr-2 h-4 w-4" />
                    Print
                  </Button>
                </div>
              </div>

              {/* Card View */}
              {viewMode === 'cards' && (
                <Card>
                  <CardHeader>
                    <CardTitle>{(lineupData as { theater?: string; showtimes?: ShowtimeEntry[] } | undefined)?.theater || queryTheater}</CardTitle>
                    <CardDescription>
                      {Object.keys(lineupByFilm).length} films showing on {format(new Date(selectedDate + 'T00:00:00'), 'MMM d, yyyy')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {Object.keys(lineupByFilm).length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">
                        No showtimes found for this theater and date.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {Object.entries(lineupByFilm).map(([filmTitle, data]) => {
                          const isExpanded = expandedFilms.has(filmTitle);
                          const formatEmoji = getFormatEmoji(data.format || '', data.is_plf);
                          const formatClass = getFormatBadgeClass(data.format, data.is_plf);
                          // Check if any showtime for this film has high demand
                          const filmDemandMetrics = data.showtimes
                            .map(s => demandMap.get(demandKey(queryTheater, filmTitle, s.showtime)))
                            .filter((d): d is DemandMetric => !!d);
                          const maxFillRate = filmDemandMetrics.length > 0
                            ? Math.max(...filmDemandMetrics.map(d => d.fill_rate_pct))
                            : 0;
                          const totalSold = filmDemandMetrics.reduce((sum, d) => sum + d.tickets_sold, 0);

                          return (
                            <div key={filmTitle} className={cn(
                              "border rounded-lg",
                              maxFillRate >= 75 ? "border-red-500/30" : ""
                            )}>
                              <button
                                onClick={() => toggleFilmExpand(filmTitle)}
                                className="w-full flex items-center justify-between p-4 hover:bg-muted/50"
                              >
                                <div className="flex items-center gap-3">
                                  {isExpanded ? (
                                    <ChevronDown className="h-4 w-4" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4" />
                                  )}
                                  <Film className="h-4 w-4 text-muted-foreground" />
                                  <span className="font-medium">{filmTitle}</span>
                                  {(data.format || data.is_plf) && (
                                    <Badge variant="outline" className={cn('text-[10px] h-5 px-1.5 uppercase', formatClass)}>
                                      {formatEmoji} {data.format || (data.is_plf ? 'PLF' : '')}
                                    </Badge>
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  {data.runtime && (
                                    <Badge variant="secondary" className="text-xs">
                                      {data.runtime} min
                                    </Badge>
                                  )}
                                  <Badge variant="secondary" className="text-xs">
                                    {data.showtimes.length} showings
                                  </Badge>
                                  {totalSold > 0 && (
                                    <Badge className={cn("text-xs",
                                      maxFillRate >= 75 ? "bg-red-500/20 text-red-400 border-red-500/30" :
                                      maxFillRate >= 50 ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" :
                                      "bg-blue-500/20 text-blue-400 border-blue-500/30"
                                    )}>
                                      {maxFillRate >= 75 && <Flame className="mr-1 h-3 w-3" />}
                                      {totalSold} sold
                                    </Badge>
                                  )}
                                </div>
                              </button>

                              {isExpanded && (
                                <div className="px-4 pb-4">
                                  <div className="flex flex-wrap gap-2 mt-4">
                                    {data.showtimes.map((show, idx) => {
                                      const demand = demandMap.get(demandKey(queryTheater, filmTitle, show.showtime));
                                      return (
                                      <div key={idx} className={cn(
                                        "flex flex-col items-center p-2 rounded-md border min-w-[100px]",
                                        demand && demand.fill_rate_pct >= 75
                                          ? "bg-red-500/10 border-red-500/30"
                                          : demand && demand.fill_rate_pct >= 50
                                            ? "bg-yellow-500/10 border-yellow-500/30"
                                            : "bg-secondary/50 border-border"
                                      )}>
                                        <span className="text-sm font-bold">{show.showtime}</span>
                                        {show.out_time && showOutTime && (
                                          <span className="text-xs text-muted-foreground whitespace-nowrap">
                                            out: {show.out_time}
                                          </span>
                                        )}
                                        {demand && (
                                          <span className={cn("text-[10px] font-medium mt-0.5", getFillRateColor(demand.fill_rate_pct))}>
                                            {demand.tickets_sold}/{demand.capacity} ({demand.fill_rate_pct}%)
                                          </span>
                                        )}
                                        {!show.out_time && showOutTime && show.runtime === undefined && !demand && (
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 px-1 text-[10px] mt-1"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleEnrichFilm(filmTitle);
                                            }}
                                            disabled={isEnriching === filmTitle}
                                          >
                                            {isEnriching === filmTitle ? <RefreshCcw className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3 mr-1" />}
                                            Enrich
                                          </Button>
                                        )}
                                      </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {viewMode === 'table' && (
                <Card className="print:shadow-none print:border-0">
                  <CardHeader className="print:pb-2">
                    <CardTitle className="print:text-2xl">{(lineupData as { theater?: string; showtimes?: ShowtimeEntry[] } | undefined)?.theater || queryTheater}</CardTitle>
                    <CardDescription className="print:text-lg print:text-black">
                      {format(new Date(selectedDate + 'T00:00:00'), 'EEEE, MMMM d, yyyy')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {processedShowtimes.length === 0 ? (
                      <p className="text-center text-muted-foreground py-8">
                        No showtimes found for this theater and date.
                      </p>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-20">Theater #</TableHead>
                            <TableHead>Film</TableHead>
                            <TableHead className="w-24">Format</TableHead>
                            <TableHead className="w-24">In-Time</TableHead>
                            <TableHead className="w-24">Out-Time</TableHead>
                            {demandData && demandData.length > 0 && (
                              <TableHead className="w-28 print:hidden">Sold</TableHead>
                            )}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {processedShowtimes.map((show, idx) => {
                            const demand = demandMap.get(demandKey(queryTheater, show.film_title, show.showtime));
                            return (
                              <TableRow key={idx} className={cn(
                                demand && demand.fill_rate_pct >= 75 ? "bg-red-500/5" :
                                demand && demand.fill_rate_pct >= 50 ? "bg-yellow-500/5" : ""
                              )}>
                                <TableCell className="font-mono"></TableCell>
                                <TableCell className="font-medium">{show.film_title}</TableCell>
                                <TableCell className="font-mono">
                                  {normalizeFormatDisplay(show.format, show.is_plf)}
                                </TableCell>
                                <TableCell className="font-mono">{show.showtime}</TableCell>
                                <TableCell className="font-mono text-muted-foreground">
                                  {show.out_time || '—'}
                                </TableCell>
                                {demandData && demandData.length > 0 && (
                                  <TableCell className="print:hidden">
                                    {demand ? (
                                      <div className="flex items-center gap-2">
                                        <Progress
                                          value={demand.fill_rate_pct}
                                          className={cn("h-2 w-16",
                                            demand.fill_rate_pct >= 75 ? "[&>div]:bg-red-500" :
                                            demand.fill_rate_pct >= 50 ? "[&>div]:bg-yellow-500" :
                                            "[&>div]:bg-green-500"
                                          )}
                                        />
                                        <span className={cn("text-xs font-mono", getFillRateColor(demand.fill_rate_pct))}>
                                          {demand.tickets_sold}/{demand.capacity}
                                        </span>
                                      </div>
                                    ) : (
                                      <span className="text-xs text-muted-foreground">—</span>
                                    )}
                                  </TableCell>
                                )}
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    )}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      )}

      {/* Box Office Board — separate section below lineup */}
      {hasLineupData && step === 'results' && (
        <Card className="mt-4">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Button
                  variant={showBoard ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setShowBoard(!showBoard)}
                >
                  <Monitor className="mr-2 h-4 w-4" />
                  {showBoard ? 'Hide Board' : 'Box Office Board'}
                </Button>
                {showBoard && (
                  <CardDescription className="ml-1">
                    Display-ready schedule for screens or printing
                  </CardDescription>
                )}
              </div>
              {showBoard && (
                <div className="flex items-center gap-2">
                  {/* Resolution selector */}
                  <select
                    value={boardResolution}
                    onChange={(e) => setBoardResolution(e.target.value as BoardResolution)}
                    className="text-xs border rounded-md px-2 py-1.5 bg-background"
                  >
                    {(Object.entries(RESOLUTION_LABELS) as [BoardResolution, string][]).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>

                  {/* Download buttons */}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={boardDownloading || !boardHtml}
                    onClick={async () => {
                      setBoardDownloading(true);
                      try {
                        await downloadBoardHtml(queryTheater, queryDate, boardResolution);
                      } finally {
                        setBoardDownloading(false);
                      }
                    }}
                  >
                    <Download className="mr-1 h-3.5 w-3.5" />
                    Screen Display
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={boardDownloading || !boardHtml}
                    onClick={async () => {
                      setBoardDownloading(true);
                      try {
                        await downloadBoardImage(queryTheater, queryDate, boardResolution);
                      } finally {
                        setBoardDownloading(false);
                      }
                    }}
                  >
                    <Download className="mr-1 h-3.5 w-3.5" />
                    Generate Image
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!boardHtml}
                    onClick={() => {
                      if (!boardHtml) return;
                      const printWindow = window.open('', '_blank');
                      if (printWindow) {
                        printWindow.document.write(boardHtml);
                        printWindow.document.close();
                        printWindow.onload = () => {
                          printWindow.print();
                        };
                      }
                    }}
                  >
                    <Printer className="mr-1 h-3.5 w-3.5" />
                    Printer Friendly
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          {showBoard && (
            <CardContent>
              {boardLoading ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                  <RefreshCw className="h-5 w-5 animate-spin mr-2" />
                  Generating board...
                </div>
              ) : boardHtml ? (
                <div className="border rounded-lg overflow-hidden bg-muted/20">
                  <iframe
                    srcDoc={boardHtml}
                    title="Box Office Board Preview"
                    className="w-full border-0"
                    style={{
                      height: boardResolution === 'letter' ? '500px' :
                             boardResolution === '720p' ? '450px' : '540px',
                    }}
                  />
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No schedule data available for the board.
                </div>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* Print Styles */}
      <style>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .print\\:shadow-none,
          .print\\:shadow-none * {
            visibility: visible;
          }
          .print\\:shadow-none {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
          }
        }
      `}</style>
    </div>
  );
}
