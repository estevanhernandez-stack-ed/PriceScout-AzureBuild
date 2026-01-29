import { useState, useMemo, useEffect } from 'react';
import { useMarketsHierarchy, useTheaterCache } from '@/hooks/api/useMarkets';
import { useTriggerScrape, useScrapeStatus, useFetchShowtimes, useEstimateScrapeTime, useLiveScrapeJobs, useCompareShowtimeCounts, type Showing, type ScrapeConflictError, type TheaterCountComparison } from '@/hooks/api/useScrapes';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  MapPin,
  Building2,
  Film,
  Play,
  RefreshCw,
  Download,
  CheckCircle2,
  Clock,
  Calendar,
  Users,
  ChevronDown,
  ChevronRight,
  Timer,
} from 'lucide-react';
import { format, addDays } from 'date-fns';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';
import { useToast } from '@/hooks/use-toast';
import { AxiosError } from 'axios';
import { useTheaterMetadata, useMarketEvents, useSyncMarketContext } from '@/hooks/api/useMarketContext';
import { MarketHeatmap } from '@/components/market/MarketHeatmap';


type WorkflowStep = 'select-director' | 'select-market' | 'select-theaters' | 'select-dates' | 'select-showtimes' | 'running' | 'results';

// LocalStorage key for persisting scrape job ID
const SCRAPE_JOB_STORAGE_KEY = 'pricescout_market_scrape_job';

// Daypart definitions (same as Streamlit)
type Daypart = 'all' | 'matinee' | 'twilight' | 'prime' | 'late_night';

const DAYPART_LABELS: Record<Daypart, string> = {
  all: 'All Showtimes',
  matinee: 'Matinee (<4 PM)',
  twilight: 'Twilight (4-6 PM)',
  prime: 'Prime (6-9 PM)',
  late_night: 'Late Night (>9 PM)',
};

// Format emojis for PLF detection
const FORMAT_EMOJIS: Record<string, string> = {
  'IMAX': '📽️',
  'Dolby Cinema': '🔊',
  'Dolby': '🔊',
  '4DX': '💨',
  '3D': '👓',
  'D-BOX': '💺',
  'D-Box': '💺',
  'ScreenX': '🌐',
  'Premium': '✨',
  'PLF': '✨',
};

// Helper to get format emoji
function getFormatEmoji(format: string): string {
  for (const [key, emoji] of Object.entries(FORMAT_EMOJIS)) {
    if (format.toLowerCase().includes(key.toLowerCase())) {
      return emoji;
    }
  }
  return '';
}

// Helper to extract unique premium formats for a theater from showtime data
// Also tracks whether any showtime with that format is selected
function getTheaterFormats(
  theaterName: string,
  showtimesData: Record<string, Record<string, Showing[]>>,
  selectedShowtimes: Set<string>,
  makeKey: (date: string, theater: string, film: string, time: string, format: string) => string
): Array<{ format: string; emoji: string; hasSelected: boolean }> {
  const formatInfo = new Map<string, { emoji: string; hasSelected: boolean }>();

  Object.entries(showtimesData).forEach(([date, dateData]) => {
    const showings = dateData[theaterName] || [];
    showings.forEach((s) => {
      if (s.format && s.format.toLowerCase() !== 'standard') {
        const normalizedFormat = s.format.trim();
        const emoji = getFormatEmoji(normalizedFormat);
        if (emoji) {
          const key = makeKey(date, theaterName, s.film_title, s.showtime, s.format);
          const isSelected = selectedShowtimes.has(key);

          const existing = formatInfo.get(normalizedFormat);
          if (existing) {
            // If any showtime with this format is selected, mark it
            if (isSelected) existing.hasSelected = true;
          } else {
            formatInfo.set(normalizedFormat, { emoji, hasSelected: isSelected });
          }
        }
      }
    });
  });

  return Array.from(formatInfo.entries())
    .map(([format, info]) => ({ format, ...info }))
    .sort((a, b) => a.format.localeCompare(b.format));
}

// Helper to parse time string to hours (for daypart filtering)
function parseTimeToHours(timeStr: string): number {
  // Parse "12:30 PM" or "09:00 AM" format
  const match = timeStr.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
  if (!match) return 12; // Default to noon if can't parse

  let hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  const isPM = match[3].toUpperCase() === 'PM';

  if (isPM && hours !== 12) hours += 12;
  if (!isPM && hours === 12) hours = 0;

  return hours + minutes / 60;
}

// Get daypart for a showtime
function getDaypart(timeStr: string): string {
  const hours = parseTimeToHours(timeStr);
  if (hours < 16) return 'matinee';
  if (hours < 18) return 'twilight';
  if (hours < 21) return 'prime';
  return 'late_night';
}

// Format duration in seconds to human-readable string
function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  }

  return `${minutes}m ${secs}s`;
}

interface TheaterEntry {
  name: string;
  zip?: string;
  status?: string;
  url?: string;
  company?: string;
  not_on_fandango?: boolean;
}

// Selected showtime key: "date|theater|film|time|format"
type ShowtimeKey = string;

function makeShowtimeKey(date: string, theater: string, film: string, time: string, format: string = 'Standard'): ShowtimeKey {
  return `${date}|${theater}|${film}|${time}|${format}`;
}

// Parse showtime key back to components (useful for debugging or displaying)
function _parseShowtimeKey(key: ShowtimeKey): { date: string; theater: string; film: string; time: string; format: string } {
  const [date, theater, film, time, format] = key.split('|');
  return { date, theater, film, time, format: format || 'Standard' };
}
void _parseShowtimeKey; // Marked as intentionally unused for future use

export function MarketModePage() {
  const { user, setSuppressAutoLogout, pendingAuthIssue, clearPendingAuthIssue } = useAuthStore();
  const { toast } = useToast();
  const selectedCompany = user?.company || 'Marcus Theatres';

  // Workflow state
  const [step, setStep] = useState<WorkflowStep>('select-director');
  const [selectedDirector, setSelectedDirector] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedTheaters, setSelectedTheaters] = useState<string[]>([]);
  const [selectedDates, setSelectedDates] = useState<Date[]>([addDays(new Date(), 1)]);
  const [scrapeJobId, setScrapeJobId] = useState<number | null>(null);

  // Showtime selection state
  const [showtimesData, setShowtimesData] = useState<Record<string, Record<string, Showing[]>>>({});
  const [selectedShowtimes, setSelectedShowtimes] = useState<Set<ShowtimeKey>>(new Set());
  const [expandedTheaters, setExpandedTheaters] = useState<Set<string>>(new Set());
  const [showtimeFetchDuration, setShowtimeFetchDuration] = useState<number>(0);
  const [activeDayparts, setActiveDayparts] = useState<Set<Daypart>>(new Set());
  const [showtimesFetched, setShowtimesFetched] = useState<boolean>(false);
  const [selectedFilms, setSelectedFilms] = useState<Set<string>>(new Set());

  // Time estimation state
  const [timeEstimate, setTimeEstimate] = useState<{ seconds: number; formatted: string; hasData: boolean } | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Countdown timer state
  const [scrapeStartTime, setScrapeStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Scrape mode: false = Fresh Scrape (always Fandango), true = Quick Check (use cache)
  const [useCache, setUseCache] = useState(false);

  // Weather/closure monitoring: compare showtime counts vs previous scrape
  const [showCountComparison, setShowCountComparison] = useState(false);
  const [countComparisons, setCountComparisons] = useState<Record<string, TheaterCountComparison>>({});
  const [comparisonLoading, setComparisonLoading] = useState(false);

  // Polling control - separate from step to ensure React Query picks up interval correctly
  const [isScraping, setIsScraping] = useState(false);

  // API hooks
  const { data: marketsData, isLoading: marketsLoading, error: marketsError, refetch: refetchMarkets } = useMarketsHierarchy();
  const { data: cacheData, isLoading: cacheLoading, error: cacheError, refetch: refetchCache } = useTheaterCache();
  const triggerScrape = useTriggerScrape();
  const fetchShowtimes = useFetchShowtimes();
  const estimateTime = useEstimateScrapeTime();
  const compareShowtimeCounts = useCompareShowtimeCounts();

  // Check for running scrapes (used to restore state on page load)
  const { data: liveScrapeJobs } = useLiveScrapeJobs();

  // Scrape status - also poll when we have a job ID from localStorage restoration
  // Use isScraping for refetchInterval to ensure polling starts correctly after job ID is set
  const { data: scrapeStatus, error: scrapeStatusError, dataUpdatedAt } = useScrapeStatus(scrapeJobId ?? 0, {
    enabled: !!scrapeJobId && (step === 'running' || step === 'results'),
    refetchInterval: isScraping ? 2000 : false,
  });

  // Debug: Log scrape status updates
  useEffect(() => {
    if (scrapeStatus && isScraping) {
      console.log('[MarketMode] Scrape status update:', {
        jobId: scrapeStatus.job_id,
        status: scrapeStatus.status,
        progress: scrapeStatus.progress,
        showingsCompleted: scrapeStatus.showings_completed,
        showingsTotal: scrapeStatus.showings_total,
        dataUpdatedAt: new Date(dataUpdatedAt).toISOString(),
      });
    }
  }, [scrapeStatus, dataUpdatedAt, isScraping]);

  // Debug: Log cache data state changes
  useEffect(() => {
    console.log('[MarketMode] Theater cache state:', {
      isLoading: cacheLoading,
      hasError: !!cacheError,
      error: cacheError?.message || null,
      hasData: !!cacheData,
      marketCount: cacheData ? Object.keys(cacheData.markets || {}).length : 0,
      sampleMarkets: cacheData ? Object.keys(cacheData.markets || {}).slice(0, 5) : [],
    });
  }, [cacheData, cacheLoading, cacheError]);

  // Handle stale job IDs (e.g., server restarted and job no longer exists)
  useEffect(() => {
    if (scrapeStatusError && scrapeJobId) {
      // Check if it's a 404 error (job not found)
      const isNotFound = (scrapeStatusError as any)?.response?.status === 404;
      if (isNotFound) {
        console.log('[MarketMode] Job not found (server may have restarted), clearing stale job ID:', scrapeJobId);
        localStorage.removeItem(SCRAPE_JOB_STORAGE_KEY);
        setScrapeJobId(null);
        setStep('select-director');
        setIsScraping(false);
        toast({
          title: 'Session Expired',
          description: 'The previous scrape session is no longer available. Please start a new scrape.',
          variant: 'destructive',
        });
      }
    }
  }, [scrapeStatusError, scrapeJobId, toast]);

  // Suppress auto-logout while scraping to prevent interruption during long operations
  useEffect(() => {
    setSuppressAutoLogout(isScraping);
    console.log('[MarketMode] Auto-logout suppression:', isScraping ? 'enabled' : 'disabled');
  }, [isScraping, setSuppressAutoLogout]);

  // Show warning if there was an auth issue during the scrape
  useEffect(() => {
    if (pendingAuthIssue && !isScraping && step === 'results') {
      toast({
        title: 'Session Needs Attention',
        description: 'Your session had an authentication issue during the scrape. Results are saved, but you may need to log in again to continue.',
        variant: 'default',
      });
      clearPendingAuthIssue();
    }
  }, [pendingAuthIssue, isScraping, step, toast, clearPendingAuthIssue]);

  // State to track if we've attempted restoration
  const [restorationAttempted, setRestorationAttempted] = useState(false);

  // Restore scrape state from localStorage on mount (runs immediately)
  useEffect(() => {
    if (restorationAttempted) return; // Only run once

    const savedJobId = localStorage.getItem(SCRAPE_JOB_STORAGE_KEY);
    if (savedJobId) {
      const jobId = parseInt(savedJobId, 10);
      if (!isNaN(jobId)) {
        console.log('[MarketMode] Restoring job ID from localStorage:', jobId);
        setScrapeJobId(jobId);
        setStep('running'); // Will transition to 'results' if job is completed
        setIsScraping(true); // Start polling for restored job
        setRestorationAttempted(true);
        toast({
          title: 'Reconnecting to Scrape',
          description: `Found an active scrape job (ID: ${jobId}). Restoring progress...`,
        });
        return;
      }
    }
    setRestorationAttempted(true);
  }, [restorationAttempted, toast]);

  // Check API for running scrapes (fallback if localStorage is empty)
  useEffect(() => {
    if (!restorationAttempted) return; // Wait for localStorage check
    if (scrapeJobId) return; // Already have a job

    if (liveScrapeJobs && liveScrapeJobs.length > 0) {
      // Find the most recent running or pending job
      const activeJob = liveScrapeJobs.find(j => j.status === 'running' || j.status === 'pending');
      if (activeJob) {
        console.log('[MarketMode] Found active job from API:', activeJob.job_id);
        setScrapeJobId(activeJob.job_id);
        setStep('running');
        setIsScraping(true); // Start polling for restored job
        localStorage.setItem(SCRAPE_JOB_STORAGE_KEY, String(activeJob.job_id));
        toast({
          title: 'Active Scrape Found',
          description: `Reconnected to running scrape job (ID: ${activeJob.job_id})`,
        });
      }
    }
  }, [restorationAttempted, scrapeJobId, liveScrapeJobs, toast]);

  // Save job ID to localStorage when it changes
  useEffect(() => {
    if (scrapeJobId) {
      localStorage.setItem(SCRAPE_JOB_STORAGE_KEY, String(scrapeJobId));
      console.log('[MarketMode] Saved job ID to localStorage:', scrapeJobId);
    }
  }, [scrapeJobId]);

  // Clear localStorage when scrape completes or is reset
  useEffect(() => {
    if (scrapeStatus?.status === 'completed' || scrapeStatus?.status === 'failed') {
      // Keep job ID in localStorage for a short time so user can see results
      // Clear it after 5 minutes
      const timeout = setTimeout(() => {
        localStorage.removeItem(SCRAPE_JOB_STORAGE_KEY);
        console.log('[MarketMode] Cleared job ID from localStorage (job completed)');
      }, 5 * 60 * 1000);
      return () => clearTimeout(timeout);
    }
  }, [scrapeStatus?.status]);

  // Market Context hooks
  const { data: theaterMetadata } = useTheaterMetadata();
  const syncMetadata = useSyncMarketContext();
  const startDate = selectedDates[0] ? format(selectedDates[0], 'yyyy-MM-dd') : format(new Date(), 'yyyy-MM-dd');
  const endDate = selectedDates[selectedDates.length - 1] ? format(selectedDates[selectedDates.length - 1], 'yyyy-MM-dd') : startDate;
  const { data: marketEvents } = useMarketEvents(startDate, endDate, selectedMarket || undefined);

  // Sync theater metadata for the selected market
  const handleSyncMarket = async () => {
    const marketTheaters = theatersInMarket.map(t => t.name);
    if (marketTheaters.length === 0) return;

    try {
      toast({
        title: 'Syncing Market Data',
        description: `Fetching metadata for theaters in ${selectedMarket}...`,
      });
      await syncMetadata.mutateAsync(marketTheaters);
      toast({
        title: 'Sync Complete',
        description: 'Theater coordinates and market data updated.',
      });
    } catch (error) {
      toast({
        title: 'Sync Failed',
        description: 'Could not sync theater metadata from EntTelligence.',
        variant: 'destructive',
      });
    }
  };

  // Get company data
  const companyData = useMemo(() => {
    if (!marketsData) return null;
    return marketsData[selectedCompany] || null;
  }, [marketsData, selectedCompany]);

  // Get directors for the selected company
  const directors = useMemo(() => {
    if (!companyData) return [];
    return Object.keys(companyData).sort();
  }, [companyData]);

  // Get markets for the selected director
  const marketsInDirector = useMemo(() => {
    if (!companyData || !selectedDirector) return [];
    const directorData = companyData[selectedDirector];
    if (!directorData) return [];
    return Object.keys(directorData).sort();
  }, [companyData, selectedDirector]);

  // Get theaters in selected market (enriched with cache data)
  const theatersInMarket = useMemo(() => {
    if (!companyData || !selectedDirector || !selectedMarket) return [];
    const marketData = companyData[selectedDirector]?.[selectedMarket];
    if (!marketData?.theaters) return [];

    // Debug: Log cache lookup
    console.log('[MarketMode] Cache lookup:', {
      selectedMarket,
      cacheDataExists: !!cacheData,
      cacheMarketsKeys: cacheData ? Object.keys(cacheData.markets || {}).slice(0, 5) : [],
      marketExistsInCache: !!(cacheData?.markets?.[selectedMarket]),
      cacheTheaterCount: cacheData?.markets?.[selectedMarket]?.theaters?.length || 0,
    });

    // Enrich with cache data (URLs, company info)
    return marketData.theaters.map((t) => {
      const cacheTheater = cacheData?.markets?.[selectedMarket]?.theaters?.find(
        (ct) => ct.name === t.name
      );
      if (!cacheTheater?.url) {
        console.log(`[MarketMode] No URL for theater "${t.name}" in market "${selectedMarket}"`);
      }
      return {
        ...t,
        url: cacheTheater?.url,
        company: cacheTheater?.company || extractCompany(t.name),
        not_on_fandango: cacheTheater?.not_on_fandango,
      };
    });
  }, [companyData, selectedDirector, selectedMarket, cacheData]);

  // Helper to extract company from theater name
  function extractCompany(name: string): string {
    const prefixes = ['Marcus', 'AMC', 'Regal', 'Cinemark', 'Movie Tavern', 'Emagine', 'Alamo'];
    for (const prefix of prefixes) {
      if (name.toLowerCase().startsWith(prefix.toLowerCase())) {
        return prefix;
      }
    }
    return 'Other';
  }

  // Get all theaters in the selected director's region
  const allTheatersInDirector = useMemo(() => {
    if (!companyData || !selectedDirector) return [];
    const directorData = companyData[selectedDirector];
    if (!directorData) return [];

    const theaters: TheaterEntry[] = [];
    Object.entries(directorData).forEach(([marketName, marketData]) => {
      marketData.theaters.forEach((t) => {
        const cacheTheater = cacheData?.markets?.[marketName]?.theaters?.find(
          (ct) => ct.name === t.name
        );
        theaters.push({
          ...t,
          url: cacheTheater?.url,
          company: cacheTheater?.company || extractCompany(t.name),
          not_on_fandango: cacheTheater?.not_on_fandango,
        });
      });
    });
    return theaters;
  }, [companyData, selectedDirector, cacheData]);

  // Check if a theater is scrapeable (not closed, has Fandango)
  const isScrapeable = (theater: TheaterEntry): boolean => {
    if (theater.status === 'Permanently Closed') return false;
    if (theater.not_on_fandango) return false;
    return true;
  };

  // Get only scrapeable theaters from a list
  const getScrapeable = (theaters: TheaterEntry[]): TheaterEntry[] => {
    return theaters.filter(isScrapeable);
  };

  // Get theaters for a specific market
  const getTheatersInMarket = (market: string): TheaterEntry[] => {
    if (!companyData || !selectedDirector) return [];
    const marketData = companyData[selectedDirector]?.[market];
    if (!marketData?.theaters) return [];
    return marketData.theaters.map((t) => {
      const cacheTheater = cacheData?.markets?.[market]?.theaters?.find(
        (ct) => ct.name === t.name
      );
      return {
        ...t,
        url: cacheTheater?.url,
        company: cacheTheater?.company || extractCompany(t.name),
        not_on_fandango: cacheTheater?.not_on_fandango,
      };
    });
  };

  // Get selection status for a market: 'none' | 'partial' | 'all'
  const getMarketSelectionStatus = (market: string): 'none' | 'partial' | 'all' => {
    const theaters = getScrapeable(getTheatersInMarket(market));
    if (theaters.length === 0) return 'none';
    const selectedCount = theaters.filter(t => selectedTheaters.includes(t.name)).length;
    if (selectedCount === 0) return 'none';
    if (selectedCount === theaters.length) return 'all';
    return 'partial';
  };

  // Handlers
  const handleDirectorSelect = (director: string) => {
    setSelectedDirector(director);
    setSelectedMarket('');
    setSelectedTheaters([]);
    setStep('select-market');
  };

  const handleMarketSelect = (market: string) => {
    setSelectedMarket(market);
    setStep('select-theaters');
  };

  const handleTheaterToggle = (theaterName: string) => {
    setSelectedTheaters((prev) =>
      prev.includes(theaterName)
        ? prev.filter((t) => t !== theaterName)
        : [...prev, theaterName]
    );
  };

  // Bulk selection: Select all Marcus theaters in director
  const handleSelectAllCompanyInDirector = () => {
    const companyTheaters = allTheatersInDirector
      .filter((t) => extractCompany(t.name) === 'Marcus' && isScrapeable(t))
      .map((t) => t.name);

    const allSelected = companyTheaters.every((t) => selectedTheaters.includes(t));

    if (allSelected) {
      setSelectedTheaters((prev) => prev.filter((t) => !companyTheaters.includes(t)));
    } else {
      setSelectedTheaters((prev) => [...new Set([...prev, ...companyTheaters])]);
    }
  };

  // Bulk selection: Select all theaters in market
  const handleSelectAllInMarket = () => {
    const marketTheaters = getScrapeable(theatersInMarket).map((t) => t.name);
    const allSelected = marketTheaters.every((t) => selectedTheaters.includes(t));

    if (allSelected) {
      setSelectedTheaters((prev) => prev.filter((t) => !marketTheaters.includes(t)));
    } else {
      setSelectedTheaters((prev) => [...new Set([...prev, ...marketTheaters])]);
    }
  };

  // Bulk selection: Select all markets in director
  const handleSelectAllMarketsInDirector = () => {
    const allTheaters = getScrapeable(allTheatersInDirector).map((t) => t.name);
    const allSelected = allTheaters.every((t) => selectedTheaters.includes(t));

    if (allSelected) {
      setSelectedTheaters([]);
    } else {
      setSelectedTheaters(allTheaters);
    }
  };

  // Fetch showtimes for selected theaters and dates
  const handleFetchShowtimes = async () => {
    if (selectedTheaters.length === 0 || selectedDates.length === 0) return;

    // Get theater objects with URLs
    const theaters = allTheatersInDirector
      .filter((t) => selectedTheaters.includes(t.name) && t.url)
      .map((t) => ({ name: t.name, url: t.url! }));

    // Check if any selected theaters are missing URLs
    const theatersWithoutUrls = allTheatersInDirector
      .filter((t) => selectedTheaters.includes(t.name) && !t.url)
      .map((t) => t.name);

    if (theatersWithoutUrls.length > 0) {
      toast({
        title: 'Warning: Missing Theater URLs',
        description: `${theatersWithoutUrls.length} theater(s) have no Fandango URL and will be skipped: ${theatersWithoutUrls.slice(0, 3).join(', ')}${theatersWithoutUrls.length > 3 ? '...' : ''}`,
        variant: 'default',
      });
    }

    if (theaters.length === 0) {
      toast({
        title: 'No Valid Theaters',
        description: 'None of the selected theaters have Fandango URLs. Please select different theaters.',
        variant: 'destructive',
      });
      return;
    }

    try {
      setStep('select-showtimes');
      setShowtimesFetched(false);
      const result = await fetchShowtimes.mutateAsync({
        theaters,
        dates: selectedDates.map((d) => format(d, 'yyyy-MM-dd')),
      });
      setShowtimesData(result.showtimes);
      setShowtimeFetchDuration(result.duration_seconds);
      setShowtimesFetched(true);
      // Expand all theaters by default
      setExpandedTheaters(new Set(selectedTheaters));

      // Check if we got any showtimes
      const totalShowtimes = Object.values(result.showtimes).reduce((sum, dateData) => {
        return sum + Object.values(dateData).reduce((s, shows) => s + shows.length, 0);
      }, 0);

      if (totalShowtimes === 0) {
        toast({
          title: 'No Showtimes Found',
          description: 'The fetch completed but returned no showtimes. This could mean no films are scheduled for the selected dates.',
          variant: 'default',
        });
      }
    } catch (error) {
      console.error('Failed to fetch showtimes:', error);

      // Extract error message
      let errorMessage = 'An unexpected error occurred while fetching showtimes.';
      if (error instanceof AxiosError) {
        if (error.response?.status === 401) {
          errorMessage = 'Authentication failed. Please log out and log back in.';
        } else if (error.response?.status === 403) {
          errorMessage = 'You do not have permission to fetch showtimes.';
        } else if (error.response?.status === 500) {
          errorMessage = `Server error: ${error.response?.data?.detail || 'The scraper encountered an error. Check backend logs.'}`;
        } else if (error.response?.data?.detail) {
          errorMessage = error.response.data.detail;
        } else if (error.message) {
          errorMessage = error.message;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      toast({
        title: 'Showtime Fetch Failed',
        description: errorMessage,
        variant: 'destructive',
      });

      setStep('select-dates');
    }
  };

  // Get all unique films across all fetched showtimes
  const availableFilms = useMemo(() => {
    const films = new Set<string>();
    Object.values(showtimesData).forEach((dateData) => {
      Object.values(dateData).forEach((showings) => {
        showings.forEach((s) => films.add(s.film_title));
      });
    });
    return Array.from(films).sort();
  }, [showtimesData]);

  // Compute heatmap data from scrape results
  const heatmapData = useMemo(() => {
    if (!scrapeStatus?.results) return [];
    const theaterAggregation: Record<string, { total: number; count: number }> = {};
    scrapeStatus.results.forEach((r: any) => {
      const theater = r.theater_name;
      const price = parseFloat(r.price?.replace('$', '') || '0');
      if (!price) return;

      if (!theaterAggregation[theater]) {
        theaterAggregation[theater] = { total: 0, count: 0 };
      }
      theaterAggregation[theater].total += price;
      theaterAggregation[theater].count += 1;
    });

    return Object.entries(theaterAggregation).map(([name, stats]) => ({
      theater_name: name,
      avg_price: stats.total / stats.count,
    }));
  }, [scrapeStatus?.results]);

  // Apply daypart toggle selection
  // Daypart buttons work as toggles - clicking adds/removes showtimes in that daypart
  // If films are selected, only affects those films; otherwise affects all films
  const handleDaypartSelect = (daypart: Daypart) => {
    if (daypart === 'all') {
      // "All Showtimes" - select everything (or clear if all selected)
      const allKeys: ShowtimeKey[] = [];
      Object.entries(showtimesData).forEach(([date, dateData]) => {
        Object.entries(dateData).forEach(([theater, showings]) => {
          const filmsToProcess = selectedFilms.size > 0
            ? showings.filter(s => selectedFilms.has(s.film_title))
            : showings;
          filmsToProcess.forEach((s) => {
            allKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          });
        });
      });

      const allSelected = allKeys.every(k => selectedShowtimes.has(k));
      setSelectedShowtimes(prev => {
        const next = new Set(prev);
        if (allSelected) {
          // Deselect all
          allKeys.forEach(k => next.delete(k));
        } else {
          // Select all
          allKeys.forEach(k => next.add(k));
        }
        return next;
      });
      // Clear active dayparts when using "All"
      setActiveDayparts(new Set());
      return;
    }

    // Toggle this daypart
    const isActive = activeDayparts.has(daypart);

    // Get all showtime keys in this daypart (for selected films or all films)
    const daypartKeys: ShowtimeKey[] = [];
    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        const filmsToProcess = selectedFilms.size > 0
          ? showings.filter(s => selectedFilms.has(s.film_title))
          : showings;

        // Group by film, then find earliest showtime in this daypart
        const filmGroups: Record<string, Showing[]> = {};
        filmsToProcess.forEach((s) => {
          if (!filmGroups[s.film_title]) filmGroups[s.film_title] = [];
          filmGroups[s.film_title].push(s);
        });

        Object.entries(filmGroups).forEach(([_film, filmShowings]) => {
          // Filter to this daypart
          const inDaypart = filmShowings.filter((s) => getDaypart(s.showtime) === daypart);
          if (inDaypart.length === 0) return;

          // Find earliest time in daypart
          const earliestTime = inDaypart.reduce((earliest, s) => {
            const hours = parseTimeToHours(s.showtime);
            const earliestHours = parseTimeToHours(earliest.showtime);
            return hours < earliestHours ? s : earliest;
          }, inDaypart[0]).showtime;

          // Select ALL formats at that time (to get different prices)
          const atEarliestTime = inDaypart.filter((s) => s.showtime === earliestTime);
          atEarliestTime.forEach((s) => {
            daypartKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          });
        });
      });
    });

    // Toggle the showtimes
    setSelectedShowtimes(prev => {
      const next = new Set(prev);
      if (isActive) {
        // Deselect showtimes in this daypart
        daypartKeys.forEach(k => next.delete(k));
      } else {
        // Add showtimes in this daypart
        daypartKeys.forEach(k => next.add(k));
      }
      return next;
    });

    // Update active dayparts
    setActiveDayparts(prev => {
      const next = new Set(prev);
      if (isActive) {
        next.delete(daypart);
      } else {
        next.add(daypart);
      }
      return next;
    });
  };

  // Toggle a single showtime
  const handleShowtimeToggle = (key: ShowtimeKey) => {
    setSelectedShowtimes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Toggle all showtimes for a film
  const handleSelectAllFilm = (film: string) => {
    const filmKeys: ShowtimeKey[] = [];
    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        showings
          .filter((s) => s.film_title === film)
          .forEach((s) => {
            filmKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          });
      });
    });

    const allSelected = filmKeys.every((k) => selectedShowtimes.has(k));
    setSelectedShowtimes((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        filmKeys.forEach((k) => next.delete(k));
      } else {
        filmKeys.forEach((k) => next.add(k));
      }
      return next;
    });
  };

  // Toggle theater expansion
  const handleToggleTheater = (theater: string) => {
    setExpandedTheaters((prev) => {
      const next = new Set(prev);
      if (next.has(theater)) {
        next.delete(theater);
      } else {
        next.add(theater);
      }
      return next;
    });
  };

  // Get all available premium formats across all theaters
  const getAvailableFormats = (): Array<{ format: string; emoji: string; count: number; selectedCount: number }> => {
    const formatCounts = new Map<string, { count: number; selectedCount: number; emoji: string }>();

    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        showings.forEach((s) => {
          const fmt = s.format;
          if (!fmt || fmt.toLowerCase() === 'standard' || fmt === '2D') return;

          const key = makeShowtimeKey(date, theater, s.film_title, s.showtime, fmt);
          const isSelected = selectedShowtimes.has(key);

          if (!formatCounts.has(fmt)) {
            formatCounts.set(fmt, { count: 0, selectedCount: 0, emoji: getFormatEmoji(fmt) });
          }
          const data = formatCounts.get(fmt)!;
          data.count++;
          if (isSelected) data.selectedCount++;
        });
      });
    });

    return Array.from(formatCounts.entries())
      .map(([format, data]) => ({ format, ...data }))
      .sort((a, b) => b.count - a.count);
  };

  // Handle format selection - select/deselect all showtimes of a specific format
  const handleFormatSelect = (targetFormat: string) => {
    const formatKeys: ShowtimeKey[] = [];

    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        const filmsToProcess = selectedFilms.size > 0
          ? showings.filter(s => selectedFilms.has(s.film_title))
          : showings;

        filmsToProcess.forEach((s) => {
          if (s.format === targetFormat) {
            formatKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          }
        });
      });
    });

    // Check if all are selected
    const allSelected = formatKeys.length > 0 && formatKeys.every(k => selectedShowtimes.has(k));

    setSelectedShowtimes(prev => {
      const next = new Set(prev);
      if (allSelected) {
        // Deselect all of this format
        formatKeys.forEach(k => next.delete(k));
      } else {
        // Select all of this format
        formatKeys.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Handle "Select All PLF" - selects all premium large format showtimes
  const handleSelectAllPLF = () => {
    const plfFormats = ['IMAX', 'IMAX 3D', 'IMAX with Laser', 'Dolby Cinema', 'Dolby', 'Dolby Atmos',
                        '4DX', 'D-BOX', 'ScreenX', 'RPX', 'XD', 'BigD', 'UltraScreen', 'GTX', 'PLF'];
    const plfKeys: ShowtimeKey[] = [];

    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        const filmsToProcess = selectedFilms.size > 0
          ? showings.filter(s => selectedFilms.has(s.film_title))
          : showings;

        filmsToProcess.forEach((s) => {
          if (plfFormats.some(p => s.format?.includes(p))) {
            plfKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          }
        });
      });
    });

    const allSelected = plfKeys.length > 0 && plfKeys.every(k => selectedShowtimes.has(k));

    setSelectedShowtimes(prev => {
      const next = new Set(prev);
      if (allSelected) {
        plfKeys.forEach(k => next.delete(k));
      } else {
        plfKeys.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Handle "Select All 3D" - selects all 3D showtimes
  const handleSelectAll3D = () => {
    const keys3d: ShowtimeKey[] = [];

    Object.entries(showtimesData).forEach(([date, dateData]) => {
      Object.entries(dateData).forEach(([theater, showings]) => {
        const filmsToProcess = selectedFilms.size > 0
          ? showings.filter(s => selectedFilms.has(s.film_title))
          : showings;

        filmsToProcess.forEach((s) => {
          if (s.format?.includes('3D')) {
            keys3d.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
          }
        });
      });
    });

    const allSelected = keys3d.length > 0 && keys3d.every(k => selectedShowtimes.has(k));

    setSelectedShowtimes(prev => {
      const next = new Set(prev);
      if (allSelected) {
        keys3d.forEach(k => next.delete(k));
      } else {
        keys3d.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Calculate operating hours for a theater (first - last showtime)
  const getOperatingHours = (theater: string): { first: string; last: string; hours: number } | null => {
    const allShowtimes: string[] = [];
    Object.values(showtimesData).forEach((dateData) => {
      const showings = dateData[theater] || [];
      showings.forEach((s) => allShowtimes.push(s.showtime));
    });

    if (allShowtimes.length === 0) return null;

    const times = allShowtimes.map((t) => ({ time: t, hours: parseTimeToHours(t) }));
    times.sort((a, b) => a.hours - b.hours);

    const first = times[0];
    const last = times[times.length - 1];
    const operatingHours = last.hours - first.hours;

    return { first: first.time, last: last.time, hours: operatingHours };
  };

  // Fetch time estimate when showtime selection changes
  useEffect(() => {
    if (selectedShowtimes.size > 0 && step === 'select-showtimes') {
      estimateTime.mutate(
        { num_showings: selectedShowtimes.size, mode: 'market' },
        {
          onSuccess: (data) => {
            setTimeEstimate({
              seconds: data.estimated_seconds,
              formatted: data.formatted_time,
              hasData: data.has_historical_data,
            });
          },
        }
      );
    } else {
      setTimeEstimate(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShowtimes.size, step]);

  // Countdown timer - update elapsed time every second while scraping
  useEffect(() => {
    if (step !== 'running' || !scrapeStartTime) {
      return;
    }

    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - scrapeStartTime) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [step, scrapeStartTime]);

  // Reset timer when scrape completes
  useEffect(() => {
    if (step === 'results') {
      setScrapeStartTime(null);
    }
  }, [step]);

  // Show confirmation before starting scrape
  const handleRequestScrape = () => {
    if (selectedShowtimes.size === 0) return;
    setShowConfirmDialog(true);
  };

  // Actually start the scrape after confirmation
  const handleConfirmScrape = async () => {
    setShowConfirmDialog(false);
    if (selectedShowtimes.size === 0) return;

    // Get theater objects with URLs from cache
    const theaters = allTheatersInDirector
      .filter((t) => selectedTheaters.includes(t.name) && t.url)
      .map((t) => ({ name: t.name, url: t.url! }));

    try {
      setStep('running');
      setScrapeStartTime(Date.now()); // Start countdown timer
      setElapsedSeconds(0);
      const result = await triggerScrape.mutateAsync({
        mode: 'market',
        market: selectedMarket || selectedDirector,
        theaters,
        dates: selectedDates.map((d) => format(d, 'yyyy-MM-dd')),
        selected_showtimes: Array.from(selectedShowtimes),
        use_cache: useCache,
        cache_max_age_hours: 6,
      });
      setScrapeJobId(result.job_id);
      setIsScraping(true); // Start polling after we have a job ID
    } catch (error) {
      console.error('Failed to start scrape:', error);
      setStep('select-showtimes');
      setIsScraping(false);

      // Handle 409 Conflict - theaters already being scraped
      if (error instanceof AxiosError && error.response?.status === 409) {
        const conflictData = error.response.data as ScrapeConflictError;
        const theaterList = conflictData.conflicting_theaters?.join(', ') || 'some theaters';
        const jobIds = conflictData.conflicting_job_ids?.join(', ') || 'another job';

        toast({
          title: 'Theater Conflict',
          description: `Cannot start scrape: ${theaterList} are already being scraped by job(s) ${jobIds}. Wait for them to complete or cancel them first.`,
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Scrape Failed',
          description: error instanceof Error ? error.message : 'Failed to start scrape',
          variant: 'destructive',
        });
      }
    }
  };

  const handleReset = () => {
    setStep('select-director');
    setSelectedDirector('');
    setSelectedMarket('');
    setSelectedTheaters([]);
    setSelectedDates([addDays(new Date(), 1)]);
    setScrapeJobId(null);
    setShowtimesData({});
    setSelectedShowtimes(new Set());
    setExpandedTheaters(new Set());
    setShowtimeFetchDuration(0);
    setActiveDayparts(new Set());
    setShowtimesFetched(false);
    setSelectedFilms(new Set());
    setTimeEstimate(null);
    setShowConfirmDialog(false);
    setUseCache(false);
    setIsScraping(false);
    // Clear localStorage
    localStorage.removeItem(SCRAPE_JOB_STORAGE_KEY);
    console.log('[MarketMode] Cleared job ID from localStorage (user reset)');
  };

  // Check if scrape completed or failed - stop polling
  useEffect(() => {
    if (scrapeStatus?.status === 'completed' && step === 'running') {
      setStep('results');
      setIsScraping(false);
    } else if (scrapeStatus?.status === 'failed' && step === 'running') {
      setIsScraping(false);
    }
  }, [scrapeStatus?.status, step]);

  // Handle loading and error states
  if (marketsLoading && !scrapeJobId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Loading market data...</p>
      </div>
    );
  }

  if (marketsError && !scrapeJobId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="text-red-500 text-center">
          <h2 className="text-lg font-semibold mb-2">Failed to Load Markets</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Could not connect to the backend API. Please ensure the server is running.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => refetchMarkets()} variant="outline">
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
          <Button onClick={() => {
            const savedJobId = localStorage.getItem(SCRAPE_JOB_STORAGE_KEY);
            if (savedJobId) {
              const jobId = parseInt(savedJobId, 10);
              if (!isNaN(jobId)) {
                setScrapeJobId(jobId);
                setStep('running');
                setIsScraping(true);
                toast({
                  title: 'Reconnecting',
                  description: `Attempting to reconnect to job ${jobId}...`,
                });
              }
            } else {
              toast({
                title: 'No Active Scrape',
                description: 'No saved scrape job found in localStorage.',
                variant: 'destructive',
              });
            }
          }} variant="default">
            <Play className="mr-2 h-4 w-4" />
            Reconnect to Scrape
          </Button>
        </div>
      </div>
    );
  }

  // Calculate selection stats
  const marcusTheatersInDirector = allTheatersInDirector.filter(
    (t) => extractCompany(t.name) === 'Marcus' && isScrapeable(t)
  );
  const allMarcusSelected = marcusTheatersInDirector.length > 0 &&
    marcusTheatersInDirector.every((t) => selectedTheaters.includes(t.name));

  const scrapeableInMarket = getScrapeable(theatersInMarket);
  const allInMarketSelected = scrapeableInMarket.length > 0 &&
    scrapeableInMarket.every((t) => selectedTheaters.includes(t.name));

  const allScrapeable = getScrapeable(allTheatersInDirector);
  const allInDirectorSelected = allScrapeable.length > 0 &&
    allScrapeable.every((t) => selectedTheaters.includes(t.name));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <img src="/PriceScoutLogo.png" alt="" className="h-10 w-auto" />
            PriceScout: Competitive Pricing Tool
          </h1>
          <p className="text-muted-foreground">
            Market Mode - Scrape competitor prices by market
          </p>
        </div>
        <Button variant="outline" onClick={handleReset}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Start Over
        </Button>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-sm">
        Market Mode allows you to scrape prices for all theaters in a specific market. Select a director, then a market, and choose which theaters to include.
      </div>

      {/* Cache Status Warning */}
      {cacheLoading && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 text-sm flex items-center gap-2">
          <RefreshCw className="h-4 w-4 animate-spin text-yellow-500" />
          Loading theater cache data...
        </div>
      )}

      {cacheError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-red-500 font-medium">Theater cache failed to load!</span>
            <span className="text-muted-foreground">Theaters will be missing Fandango URLs.</span>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetchCache()}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Retry
          </Button>
        </div>
      )}

      {!cacheLoading && !cacheError && cacheData && Object.keys(cacheData.markets || {}).length === 0 && (
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-3 text-sm">
          <span className="text-orange-500 font-medium">Theater cache is empty.</span>
          <span className="text-muted-foreground ml-1">Go to Data Management to build the theater cache.</span>
        </div>
      )}

      {/* Director Selection */}
      {(step === 'select-director' || selectedDirector) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Step 1: Select Director
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              {directors.map((director) => (
                <Button
                  key={director}
                  variant={selectedDirector === director ? 'toggleActive' : 'toggle'}
                  size="sm"
                  className="w-full"
                  onClick={() => handleDirectorSelect(director)}
                >
                  {director}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Bulk Selection Buttons */}
      {selectedDirector && step !== 'select-director' && step !== 'select-showtimes' && step !== 'running' && step !== 'results' && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant={allMarcusSelected ? 'toggleActive' : 'toggle'}
            size="sm"
            onClick={handleSelectAllCompanyInDirector}
          >
            {allMarcusSelected ? 'Deselect' : 'Select'} All Marcus Theatres in {selectedDirector}
          </Button>
          <Button
            variant={allInDirectorSelected ? 'toggleActive' : 'toggle'}
            size="sm"
            onClick={handleSelectAllMarketsInDirector}
          >
            {allInDirectorSelected ? 'Deselect' : 'Select'} All Theaters in Region
          </Button>
        </div>
      )}

      {/* Market Selection */}
      {selectedDirector && (step === 'select-market' || step === 'select-theaters' || step === 'select-dates' || step === 'select-showtimes') && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Step 2: Select Market
            </CardTitle>
            <CardDescription>
              Markets in {selectedDirector}'s region
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {marketsInDirector.map((market) => {
                const selectionStatus = getMarketSelectionStatus(market);
                const marketTheaters = getScrapeable(getTheatersInMarket(market));
                const selectedInMarket = marketTheaters.filter(t => selectedTheaters.includes(t.name)).length;

                return (
                  <Button
                    key={market}
                    variant={selectedMarket === market ? 'toggleActive' : selectionStatus === 'all' ? 'toggleActive' : selectionStatus === 'partial' ? 'outline' : 'toggle'}
                    size="sm"
                    className={cn(
                      'w-full justify-start',
                      selectionStatus === 'partial' && 'border-red-500/50 bg-red-500/10'
                    )}
                    onClick={() => handleMarketSelect(market)}
                  >
                    <MapPin className="mr-2 h-4 w-4 flex-shrink-0" />
                    <span className="truncate flex-1 text-left">{market}</span>
                    {selectionStatus !== 'none' && (
                      <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0 h-4">
                        {selectedInMarket}/{marketTheaters.length}
                      </Badge>
                    )}
                  </Button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Continue to Date Selection (when theaters selected via bulk but no market chosen) */}
      {selectedDirector && !selectedMarket && selectedTheaters.length > 0 && step === 'select-market' && (
        <Card className="border-green-500/50 bg-green-500/5">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-green-400">
                  <CheckCircle2 className="h-5 w-5" />
                  {selectedTheaters.length} Theaters Selected
                </CardTitle>
                <CardDescription>
                  Ready to continue to date selection, or select a market to view/modify theater selection
                </CardDescription>
              </div>
              <Button
                variant="default"
                onClick={() => setStep('select-dates')}
              >
                Continue to Date Selection
                <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
        </Card>
      )}

      {/* Theater Selection */}
      {selectedMarket && (step === 'select-theaters' || step === 'select-dates' || step === 'select-showtimes') && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Building2 className="h-5 w-5" />
                  Step 3: Select Theaters in {selectedMarket}
                </CardTitle>
                <CardDescription>
                  {selectedTheaters.length} theaters selected
                </CardDescription>
              </div>
              <Button
                variant={allInMarketSelected ? 'toggleActive' : 'toggle'}
                size="sm"
                onClick={handleSelectAllInMarket}
              >
                {allInMarketSelected ? 'Deselect All' : 'Select All'}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {theatersInMarket.map((theater) => {
                const isSelected = selectedTheaters.includes(theater.name);
                const isClosed = theater.status === 'Permanently Closed';
                const noFandango = theater.not_on_fandango;

                return (
                  <Button
                    key={theater.name}
                    variant={isSelected ? 'toggleActive' : 'toggle'}
                    size="sm"
                    className={cn(
                      'w-full justify-start',
                      isClosed && 'opacity-50 cursor-not-allowed',
                      noFandango && 'opacity-70'
                    )}
                    disabled={isClosed}
                    onClick={() => {
                      if (noFandango && theater.url) {
                        // Open non-Fandango theater URL in new tab for manual use
                        window.open(theater.url, '_blank');
                      } else if (!noFandango) {
                        handleTheaterToggle(theater.name);
                      }
                    }}
                  >
                    <span className="truncate">
                      {theater.name}
                      {isClosed && ' (Closed)'}
                      {noFandango && ' (No Fandango - click to open)'}
                    </span>
                  </Button>
                );
              })}
            </div>

            {selectedTheaters.length > 0 && (
              <div className="mt-4 flex justify-end">
                <Button onClick={() => setStep('select-dates')}>
                  Continue ({selectedTheaters.length} selected)
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Date Selection */}
      {step === 'select-dates' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Step 4: Select Dates
            </CardTitle>
            <CardDescription>
              Choose which dates to scrape prices for
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2 mb-4">
              {[0, 1, 2, 3, 4, 5, 6].map((offset) => {
                const date = addDays(new Date(), offset);
                const isSelected = selectedDates.some(
                  (d) => format(d, 'yyyy-MM-dd') === format(date, 'yyyy-MM-dd')
                );
                return (
                  <Button
                    key={offset}
                    variant={isSelected ? 'toggleActive' : 'toggle'}
                    size="sm"
                    onClick={() => {
                      if (isSelected) {
                        setSelectedDates((prev) =>
                          prev.filter(
                            (d) => format(d, 'yyyy-MM-dd') !== format(date, 'yyyy-MM-dd')
                          )
                        );
                      } else {
                        setSelectedDates((prev) => [...prev, date]);
                      }
                    }}
                  >
                    {offset === 0
                      ? 'Today'
                      : offset === 1
                      ? 'Tomorrow'
                      : format(date, 'EEE, MMM d')}
                  </Button>
                );
              })}
            </div>

            <div className="bg-muted/50 rounded-lg p-4">
              <h4 className="font-medium mb-2">Scrape Summary</h4>
              <div className="grid grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Director</p>
                  <p className="font-medium">{selectedDirector}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Market</p>
                  <p className="font-medium">{selectedMarket}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Theaters</p>
                  <p className="font-medium">{selectedTheaters.length}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Dates</p>
                  <p className="font-medium">{selectedDates.length}</p>
                </div>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep('select-theaters')}>
                Back
              </Button>
              <Button
                onClick={handleFetchShowtimes}
                disabled={selectedDates.length === 0 || fetchShowtimes.isPending}
              >
                {fetchShowtimes.isPending ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    Fetching Showtimes...
                  </>
                ) : (
                  <>
                    <Film className="mr-2 h-4 w-4" />
                    Fetch Showtimes
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Showtime Selection */}
      {step === 'select-showtimes' && (
        <div className="space-y-4">
          {/* Status Banner */}
          {fetchShowtimes.isPending ? (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-sm flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Fetching showtimes from {selectedTheaters.length} theaters...
            </div>
          ) : showtimesFetched ? (
            <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-sm">
              Showtimes fetched successfully in {formatDuration(showtimeFetchDuration)}.
              Found {availableFilms.length} films across {selectedTheaters.length} theaters.
            </div>
          ) : null}

          {/* Showtime Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Step 5: Select Showtimes
              </CardTitle>
              <CardDescription>
                1) Select one or more films below. 2) Then click daypart buttons to add showtimes for those films. Multiple dayparts can be active.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Step 1: Film Selection */}
              <div>
                <h4 className="text-sm font-medium mb-2">Step 1: Select Films <span className="text-xs font-normal text-muted-foreground">(click to select/deselect, dayparts apply to selected films)</span></h4>
                <div className="flex flex-wrap gap-2">
                  {availableFilms.map((film) => {
                    const filmKeys: ShowtimeKey[] = [];
                    Object.entries(showtimesData).forEach(([date, dateData]) => {
                      Object.entries(dateData).forEach(([theater, showings]) => {
                        showings
                          .filter((s) => s.film_title === film)
                          .forEach((s) => {
                            filmKeys.push(makeShowtimeKey(date, theater, s.film_title, s.showtime, s.format));
                          });
                      });
                    });
                    const selectedCount = filmKeys.filter((k) => selectedShowtimes.has(k)).length;
                    const allSelected = filmKeys.length > 0 && selectedCount === filmKeys.length;
                    const someSelected = selectedCount > 0 && selectedCount < filmKeys.length;
                    const isFilmSelected = selectedFilms.has(film);

                    return (
                      <Button
                        key={film}
                        variant={isFilmSelected ? 'default' : allSelected ? 'toggleActive' : someSelected ? 'secondary' : 'toggle'}
                        size="sm"
                        className={isFilmSelected ? 'ring-2 ring-primary ring-offset-2' : someSelected ? 'border-primary/50' : ''}
                        onClick={() => {
                          setSelectedFilms(prev => {
                            const next = new Set(prev);
                            if (next.has(film)) {
                              next.delete(film);
                            } else {
                              next.add(film);
                            }
                            return next;
                          });
                        }}
                        onDoubleClick={() => handleSelectAllFilm(film)}
                      >
                        {film}
                        {someSelected && <span className="ml-1 text-xs opacity-70">({selectedCount})</span>}
                      </Button>
                    );
                  })}
                </div>
                {selectedFilms.size > 0 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Selected: <span className="font-medium text-foreground">{Array.from(selectedFilms).join(', ')}</span>
                    <Button variant="link" size="sm" className="h-auto p-0 ml-2" onClick={() => setSelectedFilms(new Set())}>
                      (clear)
                    </Button>
                  </p>
                )}
              </div>

              {/* Step 2: Daypart Buttons */}
              <div>
                <h4 className="text-sm font-medium mb-2">Step 2: Select Dayparts <span className="text-xs font-normal text-muted-foreground">(applies to {selectedFilms.size === 0 ? 'all films' : 'selected films'})</span></h4>
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(DAYPART_LABELS) as Daypart[]).map((daypart) => (
                    <Button
                      key={daypart}
                      variant={daypart !== 'all' && activeDayparts.has(daypart) ? 'toggleActive' : 'toggle'}
                      size="sm"
                      onClick={() => handleDaypartSelect(daypart)}
                    >
                      {DAYPART_LABELS[daypart]}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Step 3: Format Filter Buttons */}
              {showtimesFetched && (
                <div>
                  <h4 className="text-sm font-medium mb-2">
                    Step 3: Select by Format
                    <span className="text-xs font-normal text-muted-foreground ml-1">
                      (click to select all showtimes of that format{selectedFilms.size > 0 ? ' for selected films' : ''})
                    </span>
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {/* Quick select buttons */}
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-950"
                      onClick={handleSelectAllPLF}
                    >
                      <span className="mr-1">✨</span> All PLF
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950"
                      onClick={handleSelectAll3D}
                    >
                      <span className="mr-1">👓</span> All 3D
                    </Button>
                    <div className="border-l mx-1" />
                    {/* Individual format buttons */}
                    {getAvailableFormats().map(({ format, emoji, count, selectedCount }) => {
                      const allSelected = count > 0 && selectedCount === count;
                      const someSelected = selectedCount > 0 && selectedCount < count;
                      return (
                        <Button
                          key={format}
                          variant={allSelected ? 'toggleActive' : someSelected ? 'secondary' : 'toggle'}
                          size="sm"
                          className={someSelected ? 'border-primary/50' : ''}
                          onClick={() => handleFormatSelect(format)}
                          title={`${count} showtimes, ${selectedCount} selected`}
                        >
                          {emoji && <span className="mr-1">{emoji}</span>}
                          {format}
                          <Badge variant="outline" className="ml-1 text-xs px-1 py-0 h-4">
                            {selectedCount}/{count}
                          </Badge>
                        </Button>
                      );
                    })}
                    {getAvailableFormats().length === 0 && (
                      <span className="text-sm text-muted-foreground">No premium formats available</span>
                    )}
                  </div>
                </div>
              )}

              {/* Theater Expanders with Showtimes - only show when data is loaded */}
              {showtimesFetched && Object.keys(showtimesData).length > 0 && (
              <div className="space-y-2 mt-4">
                {/* Expand/Collapse All Toggle */}
                <div className="flex gap-2 mb-2 flex-wrap items-center">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setExpandedTheaters(new Set(selectedTheaters))}
                  >
                    Expand All
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setExpandedTheaters(new Set())}
                  >
                    Collapse All
                  </Button>
                  <div className="border-l pl-2 ml-2">
                    <Button
                      variant={showCountComparison ? "default" : "outline"}
                      size="sm"
                      disabled={comparisonLoading}
                      onClick={async () => {
                        if (!showCountComparison) {
                          // Fetch comparison data
                          setComparisonLoading(true);
                          try {
                            const playDates = selectedDates.map(d => format(d, 'yyyy-MM-dd'));

                            // Build current counts from fresh scrape data: {theater: {date: count}}
                            const currentCounts: Record<string, Record<string, number>> = {};
                            selectedTheaters.forEach(theaterName => {
                              currentCounts[theaterName] = {};
                              Object.entries(showtimesData).forEach(([dateKey, dateData]) => {
                                const showings = dateData[theaterName] || [];
                                currentCounts[theaterName][dateKey] = showings.length;
                              });
                            });

                            const result = await compareShowtimeCounts.mutateAsync({
                              theaters: selectedTheaters,
                              playDates,
                              currentCounts,
                            });
                            // Index by theater name for quick lookup
                            const indexed: Record<string, TheaterCountComparison> = {};
                            result.comparisons.forEach(c => {
                              indexed[c.theater_name] = c;
                            });
                            setCountComparisons(indexed);
                            setShowCountComparison(true);
                          } catch (err) {
                            console.error('Failed to fetch comparison data:', err);
                          } finally {
                            setComparisonLoading(false);
                          }
                        } else {
                          setShowCountComparison(false);
                        }
                      }}
                    >
                      {comparisonLoading ? (
                        <RefreshCw className="h-4 w-4 animate-spin mr-1" />
                      ) : (
                        <Clock className="h-4 w-4 mr-1" />
                      )}
                      {showCountComparison ? 'Hide Changes' : 'Show Changes vs Last Run'}
                    </Button>
                  </div>
                </div>
                {selectedTheaters.map((theaterName) => {
                  const isExpanded = expandedTheaters.has(theaterName);
                  const opHours = getOperatingHours(theaterName);
                  const comparison = countComparisons[theaterName];

                  // Count showtimes for this theater
                  let theaterShowtimeCount = 0;
                  let selectedInTheater = 0;
                  Object.values(showtimesData).forEach((dateData) => {
                    const showings = dateData[theaterName] || [];
                    theaterShowtimeCount += showings.length;
                    showings.forEach((s) => {
                      Object.keys(showtimesData).forEach((date) => {
                        if (selectedShowtimes.has(makeShowtimeKey(date, theaterName, s.film_title, s.showtime, s.format))) {
                          selectedInTheater++;
                        }
                      });
                    });
                  });

                  // Get premium formats available at this theater (with selection status)
                  const theaterFormats = getTheaterFormats(theaterName, showtimesData, selectedShowtimes, makeShowtimeKey);

                  // Determine status indicator for comparison
                  const getStatusDisplay = (comp: TheaterCountComparison) => {
                    switch (comp.status) {
                      case 'closed':
                        return { emoji: '🔴', label: 'Possible Closure', color: 'text-red-500 bg-red-50 dark:bg-red-950' };
                      case 'reduced':
                        return { emoji: '⚠️', label: 'Reduced', color: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-950' };
                      case 'increased':
                        return { emoji: '📈', label: 'Increased', color: 'text-blue-500 bg-blue-50 dark:bg-blue-950' };
                      case 'normal':
                        return { emoji: '✅', label: 'Normal', color: 'text-green-500 bg-green-50 dark:bg-green-950' };
                      default:
                        return { emoji: '❓', label: 'No Previous Data', color: 'text-gray-400 bg-gray-50 dark:bg-gray-900' };
                    }
                  };

                  return (
                    <div key={theaterName} className="border rounded-lg">
                      <button
                        className="w-full p-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
                        onClick={() => handleToggleTheater(theaterName)}
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                          <span className="font-medium">
                            {selectedInTheater > 0 && <span className="text-green-500 mr-1">✓</span>}
                            {theaterName}
                          </span>
                          <Badge variant="secondary">
                            {theaterShowtimeCount} Showtimes
                          </Badge>
                          {/* Premium Format badges - colored when selected, grayed out when not */}
                          {theaterFormats.length > 0 && (
                            <div className="flex gap-1">
                              {theaterFormats.map(({ format, emoji, hasSelected }) => (
                                <Badge
                                  key={format}
                                  variant="outline"
                                  className={cn(
                                    "text-xs transition-colors",
                                    hasSelected
                                      ? "bg-purple-50 dark:bg-purple-950 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800"
                                      : "bg-gray-50 dark:bg-gray-900 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-700"
                                  )}
                                  title={`${format}${hasSelected ? ' (selected)' : ' (not selected)'}`}
                                >
                                  {emoji} {format}
                                </Badge>
                              ))}
                            </div>
                          )}
                          {/* Show comparison badge when toggle is on */}
                          {showCountComparison && comparison && (
                            <Badge
                              variant="outline"
                              className={cn("text-xs font-mono", getStatusDisplay(comparison).color)}
                            >
                              {getStatusDisplay(comparison).emoji} {comparison.delta >= 0 ? '+' : ''}{comparison.delta} vs last
                              {comparison.status !== 'no_previous' && ` (${comparison.delta_percent > 0 ? '+' : ''}${comparison.delta_percent}%)`}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Show status indicator when comparison is on */}
                          {showCountComparison && comparison && comparison.status !== 'normal' && comparison.status !== 'no_previous' && (
                            <span className={cn("text-xs font-medium px-2 py-0.5 rounded", getStatusDisplay(comparison).color)}>
                              {getStatusDisplay(comparison).label}
                            </span>
                          )}
                          {opHours && (
                            <span className="text-sm text-muted-foreground">
                              {opHours.first} - {opHours.last} ({opHours.hours.toFixed(1)} hrs)
                            </span>
                          )}
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="px-3 pb-3 border-t">
                          {selectedDates.map((date) => {
                            const dateStr = format(date, 'yyyy-MM-dd');
                            const showings = showtimesData[dateStr]?.[theaterName] || [];

                            if (showings.length === 0) return null;

                            // Group by film
                            const filmGroups: Record<string, Showing[]> = {};
                            showings.forEach((s) => {
                              if (!filmGroups[s.film_title]) filmGroups[s.film_title] = [];
                              filmGroups[s.film_title].push(s);
                            });

                            return (
                              <div key={dateStr} className="mt-3">
                                <h5 className="text-sm font-medium text-muted-foreground mb-2">
                                  {format(date, 'EEEE, MMM d')}
                                </h5>
                                {Object.entries(filmGroups).map(([film, filmShowings]) => (
                                  <div key={film} className="mb-3">
                                    <p className="text-sm font-medium mb-1">{film}</p>
                                    <div className="flex flex-wrap gap-1">
                                      {filmShowings.map((s, idx) => {
                                        const key = makeShowtimeKey(dateStr, theaterName, s.film_title, s.showtime, s.format);
                                        const isSelected = selectedShowtimes.has(key);
                                        const emoji = getFormatEmoji(s.format);

                                        return (
                                          <Button
                                            key={`${key}-${idx}`}
                                            variant={isSelected ? 'toggleActive' : 'toggle'}
                                            size="sm"
                                            className="text-xs h-7"
                                            onClick={() => handleShowtimeToggle(key)}
                                          >
                                            {emoji && <span className="mr-1">{emoji}</span>}
                                            {s.showtime}
                                            {s.format !== 'Standard' && (
                                              <span className="ml-1 text-muted-foreground">
                                                ({s.format})
                                              </span>
                                            )}
                                          </Button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              )}

              {/* Summary and Actions */}
              <div className="bg-muted/50 rounded-lg p-4 mt-4">
                <h4 className="font-medium mb-2">Selection Summary</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Showtimes</p>
                    <p className="font-medium text-lg">{selectedShowtimes.size}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Theaters</p>
                    <p className="font-medium text-lg">{selectedTheaters.length}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Dates</p>
                    <p className="font-medium text-lg">{selectedDates.length}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Est. Time</p>
                    <p className="font-medium text-lg">
                      {timeEstimate?.hasData
                        ? timeEstimate.formatted
                        : estimateTime.isPending
                        ? 'Calculating...'
                        : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex justify-between pt-4">
                <Button variant="outline" onClick={() => setStep('select-dates')}>
                  Back
                </Button>
                <Button
                  onClick={handleRequestScrape}
                  disabled={selectedShowtimes.size === 0 || triggerScrape.isPending}
                >
                  {triggerScrape.isPending ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Starting...
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4" />
                      Start Scrape ({selectedShowtimes.size} showtimes)
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle>Confirm Scrape</CardTitle>
              <CardDescription>
                You are about to scrape {selectedShowtimes.size} showtimes
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-muted/50 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Showtimes</p>
                    <p className="font-medium">{selectedShowtimes.size}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Theaters</p>
                    <p className="font-medium">{selectedTheaters.length}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Dates</p>
                    <p className="font-medium">{selectedDates.length}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Estimated Time</p>
                    <p className="font-medium">
                      {timeEstimate?.hasData ? timeEstimate.formatted : 'Unknown'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Scrape Mode Toggle */}
              <div className="space-y-2">
                <p className="text-sm font-medium">Scrape Mode</p>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant={!useCache ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setUseCache(false)}
                    className="w-full"
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Fresh Scrape
                  </Button>
                  <Button
                    variant={useCache ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setUseCache(true)}
                    className="w-full"
                  >
                    <Clock className="mr-2 h-4 w-4" />
                    Quick Check
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {useCache
                    ? 'Uses cached EntTelligence data when fresh (faster, may be up to 6 hours old)'
                    : 'Always scrapes live Fandango data (slower, most accurate)'}
                </p>
              </div>

              {timeEstimate?.hasData && timeEstimate.seconds > 300 && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 text-sm">
                  <p className="text-yellow-400">
                    This scrape may take a while. Make sure you have a stable connection.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowConfirmDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={handleConfirmScrape}>
                  <Play className="mr-2 h-4 w-4" />
                  Start Scrape
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Running State */}
      {step === 'running' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5 animate-spin" />
              Scrape in Progress
              {scrapeStatus?.status && (
                <Badge variant="secondary" className="ml-2 text-xs">
                  {scrapeStatus.status}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Fetching prices from {selectedTheaters.length} theaters...
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={scrapeStatus?.progress ?? 0} className="h-3" />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>
                {scrapeStatus?.showings_completed ?? 0} of{' '}
                {scrapeStatus?.showings_total ?? selectedShowtimes.size} showings
              </span>
              <span>{scrapeStatus?.progress ?? 0}%</span>
            </div>
            {scrapeStatus?.current_theater ? (
              <p className="text-sm">
                Currently scraping: <strong>{scrapeStatus.current_theater}</strong>
                {scrapeStatus.current_showing && (
                  <span className="text-muted-foreground"> (showing {scrapeStatus.current_showing})</span>
                )}
              </p>
            ) : (scrapeStatus?.progress === 0 || !scrapeStatus) ? (
              <p className="text-sm text-muted-foreground">
                Initializing scraper and connecting to Fandango...
              </p>
            ) : null}
            {scrapeStatus?.theaters_completed !== undefined && scrapeStatus?.theaters_total !== undefined && (
              <p className="text-xs text-muted-foreground">
                Theaters: {scrapeStatus.theaters_completed}/{scrapeStatus.theaters_total}
              </p>
            )}

            {/* Countdown Timer with Dynamic Remaining Calculation */}
            <div className="flex items-center justify-between pt-2 border-t text-sm">
              <div className="flex items-center gap-2">
                <Timer className="h-4 w-4 text-muted-foreground" />
                <span>Elapsed: <strong>{formatDuration(elapsedSeconds)}</strong></span>
              </div>
              {(() => {
                const completed = scrapeStatus?.showings_completed ?? 0;
                const total = scrapeStatus?.showings_total ?? selectedShowtimes.size;
                const remaining = total - completed;

                // Calculate dynamic remaining time based on actual progress
                if (completed > 0 && remaining > 0 && elapsedSeconds > 0) {
                  const secondsPerShowing = elapsedSeconds / completed;
                  const remainingSeconds = Math.round(remaining * secondsPerShowing);
                  return (
                    <div className="text-right text-muted-foreground">
                      Remaining: ~{formatDuration(remainingSeconds)}
                      <span className="text-xs ml-2 opacity-70">
                        ({(secondsPerShowing).toFixed(1)}s/showing)
                      </span>
                    </div>
                  );
                } else if (timeEstimate?.hasData && timeEstimate.seconds > 0) {
                  // Fall back to pre-calculated estimate if no progress yet
                  return (
                    <div className="text-right text-muted-foreground">
                      Est: ~{formatDuration(Math.max(0, timeEstimate.seconds - elapsedSeconds))}
                    </div>
                  );
                }
                return null;
              })()}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {step === 'results' && scrapeStatus?.results && (
        <div className="space-y-6">
          {/* Success Message */}
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
            <p className="text-green-400 font-medium flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Report Complete! (Took {formatDuration(scrapeStatus.duration_seconds ?? 0)})
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Data has been successfully saved to the database.
            </p>
          </div>

          {/* Stats */}
          <Card>
            <CardHeader>
              <CardTitle>Scrape Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Building2 className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">{selectedTheaters.length}</p>
                  <p className="text-sm text-muted-foreground">Theaters</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Film className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">
                    {new Set(scrapeStatus.results.map((r: Record<string, unknown>) => r.film_title)).size}
                  </p>
                  <p className="text-sm text-muted-foreground">Films</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Clock className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">{scrapeStatus.results.length}</p>
                  <p className="text-sm text-muted-foreground">Showtimes</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Timer className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">
                    {formatDuration(scrapeStatus.duration_seconds ?? 0)}
                  </p>
                  <p className="text-sm text-muted-foreground">Duration</p>
                </div>
              </div>

              {/* Cache Stats (if cache was used) */}
              {scrapeStatus.use_cache && (scrapeStatus.cache_hits !== undefined || scrapeStatus.cache_misses !== undefined) && (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                  <h4 className="font-medium mb-3 flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Cache Performance (Quick Check Mode)
                  </h4>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-green-400">{scrapeStatus.cache_hits ?? 0}</p>
                      <p className="text-muted-foreground">Cache Hits</p>
                      <p className="text-xs text-muted-foreground">From EntTelligence</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-yellow-400">{scrapeStatus.cache_misses ?? 0}</p>
                      <p className="text-muted-foreground">Cache Misses</p>
                      <p className="text-xs text-muted-foreground">Scraped from Fandango</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-blue-400">
                        {((scrapeStatus.cache_hits ?? 0) + (scrapeStatus.cache_misses ?? 0)) > 0
                          ? Math.round(((scrapeStatus.cache_hits ?? 0) / ((scrapeStatus.cache_hits ?? 0) + (scrapeStatus.cache_misses ?? 0))) * 100)
                          : 0}%
                      </p>
                      <p className="text-muted-foreground">Hit Rate</p>
                      <p className="text-xs text-muted-foreground">Cache efficiency</p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Download Options */}
          <Card>
            <CardHeader>
              <CardTitle>Download Report</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Button variant="outline">
                  <Download className="mr-2 h-4 w-4" />
                  Download as CSV
                </Button>
                <Button variant="outline">
                  <Download className="mr-2 h-4 w-4" />
                  Download as Excel
                </Button>
                <Button variant="default">
                  <Download className="mr-2 h-4 w-4" />
                  Generate Summary PDF
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Results Table */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Analysis Results</CardTitle>
                  <CardDescription>
                    Price and performance data for {selectedMarket}
                  </CardDescription>
                </div>
                {marketEvents && marketEvents.length > 0 && (
                  <div className="flex gap-2">
                    {marketEvents.map(event => (
                      <Badge key={event.id} variant="secondary" className="gap-1">
                        <Calendar className="h-3 w-3" />
                        {event.event_name}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="by-theater">
                <div className="flex items-center justify-between mb-4">
                  <TabsList>
                    <TabsTrigger value="by-theater">By Theater</TabsTrigger>
                    <TabsTrigger value="by-film">By Film</TabsTrigger>
                    <TabsTrigger value="heatmap">Market Map</TabsTrigger>
                    <TabsTrigger value="raw">Raw Data</TabsTrigger>
                  </TabsList>
                  
                  <div className="flex items-center gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={handleSyncMarket}
                      disabled={syncMetadata.isPending}
                    >
                      {syncMetadata.isPending ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                      Sync Market Metadata
                    </Button>
                  </div>
                </div>

                <TabsContent value="heatmap" className="mt-0">
                  <MarketHeatmap
                    marketName={selectedMarket}
                    theaters={theaterMetadata || []}
                    metric="price"
                    data={heatmapData}
                  />
                </TabsContent>

                <TabsContent value="by-theater" className="mt-0">
                  <CollapsibleTheaterResults results={scrapeStatus.results} />
                </TabsContent>
                <TabsContent value="by-film" className="mt-0">
                  <FilmResults results={scrapeStatus.results} />
                </TabsContent>
                <TabsContent value="raw" className="mt-4">
                  <div className="overflow-auto max-h-96">
                    <pre className="text-xs">
                      {JSON.stringify(scrapeStatus.results, null, 2)}
                    </pre>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// COLLAPSIBLE THEATER RESULTS COMPONENT
// =============================================================================

interface ShowingGroup {
  film_title: string;
  showtime: string;
  format: string;
  prices: { ticket_type: string; price: string; priceNum: number }[];
}

interface CollapsibleTheaterResultsProps {
  results: Record<string, unknown>[];
}

function CollapsibleTheaterResults({ results }: CollapsibleTheaterResultsProps) {
  const [expandedTheaters, setExpandedTheaters] = useState<Set<string>>(new Set());

  // Group results by theater, then by showing (film + showtime + format)
  const theaterGroups = useMemo(() => {
    const groups: Record<string, ShowingGroup[]> = {};

    for (const r of results) {
      const theater = r.theater_name as string;
      const film = r.film_title as string;
      const showtime = r.showtime as string;
      const format = (r.format as string) || 'Standard';
      const ticketType = r.ticket_type as string;
      const priceStr = r.price as string;
      const priceMatch = priceStr?.match(/\$?([\d.]+)/);
      const priceNum = priceMatch ? parseFloat(priceMatch[1]) : 0;

      if (!groups[theater]) groups[theater] = [];

      // Find existing showing group or create new one
      const showingKey = `${film}|${showtime}|${format}`;
      let showing = groups[theater].find(
        s => `${s.film_title}|${s.showtime}|${s.format}` === showingKey
      );

      if (!showing) {
        showing = { film_title: film, showtime, format, prices: [] };
        groups[theater].push(showing);
      }

      // Add price to showing (avoid duplicates)
      if (!showing.prices.find(p => p.ticket_type === ticketType)) {
        showing.prices.push({ ticket_type: ticketType, price: priceStr, priceNum });
      }
    }

    // Sort showings by showtime within each theater
    for (const theater of Object.keys(groups)) {
      groups[theater].sort((a, b) => {
        // Parse showtimes for sorting (e.g., "7:00PM" -> numeric)
        const parseTime = (t: string) => {
          const match = t.match(/(\d+):(\d+)\s*(AM|PM)/i);
          if (!match) return 0;
          let hours = parseInt(match[1]);
          const mins = parseInt(match[2]);
          const isPM = match[3].toUpperCase() === 'PM';
          if (isPM && hours !== 12) hours += 12;
          if (!isPM && hours === 12) hours = 0;
          return hours * 60 + mins;
        };
        return parseTime(a.showtime) - parseTime(b.showtime);
      });

      // Sort prices within each showing (Adult first, then alphabetically)
      for (const showing of groups[theater]) {
        showing.prices.sort((a, b) => {
          if (a.ticket_type === 'Adult' || a.ticket_type === 'General Admission') return -1;
          if (b.ticket_type === 'Adult' || b.ticket_type === 'General Admission') return 1;
          return a.ticket_type.localeCompare(b.ticket_type);
        });
      }
    }

    // Sort theaters alphabetically
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [results]);

  const toggleTheater = (theater: string) => {
    setExpandedTheaters(prev => {
      const next = new Set(prev);
      if (next.has(theater)) {
        next.delete(theater);
      } else {
        next.add(theater);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedTheaters(new Set(theaterGroups.map(([theater]) => theater)));
  };

  const collapseAll = () => {
    setExpandedTheaters(new Set());
  };

  // Parse showtime string to minutes since midnight
  const parseTimeToMinutes = (t: string): number => {
    const match = t.match(/(\d+):(\d+)\s*(AM|PM)?/i);
    if (!match) return 0;
    let hours = parseInt(match[1]);
    const mins = parseInt(match[2]);
    const period = match[3]?.toUpperCase();
    if (period === 'PM' && hours !== 12) hours += 12;
    if (period === 'AM' && hours === 12) hours = 0;
    return hours * 60 + mins;
  };

  // Format minutes back to readable time
  const formatMinutesToTime = (mins: number): string => {
    const hours = Math.floor(mins / 60);
    const minutes = mins % 60;
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
    return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
  };

  // Get summary stats for a theater's showings
  const getTheaterSummary = (showings: ShowingGroup[]) => {
    const films = new Set(showings.map(s => s.film_title));
    const allPrices = showings.flatMap(s => s.prices.map(p => p.priceNum)).filter(p => p > 0);
    const minPrice = allPrices.length > 0 ? Math.min(...allPrices) : 0;
    const maxPrice = allPrices.length > 0 ? Math.max(...allPrices) : 0;
    const showingCount = showings.length;

    // Calculate operating hours from showtimes
    const showtimeMinutes = showings.map(s => parseTimeToMinutes(s.showtime)).filter(m => m > 0);
    const firstShowtime = showtimeMinutes.length > 0 ? Math.min(...showtimeMinutes) : 0;
    const lastShowtime = showtimeMinutes.length > 0 ? Math.max(...showtimeMinutes) : 0;
    const opHours = showtimeMinutes.length > 0
      ? `${formatMinutesToTime(firstShowtime)} - ${formatMinutesToTime(lastShowtime)}`
      : null;

    // Count 3D showings
    const count3D = showings.filter(s =>
      s.format?.toLowerCase().includes('3d')
    ).length;

    // Count PLF showings (IMAX, Dolby, Premium Format, ScreenX, 4DX, etc.)
    const plfPatterns = ['imax', 'dolby', 'premium', 'screenx', '4dx', 'rpx', 'superscreen', 'liemax', 'plf'];
    const countPLF = showings.filter(s => {
      const fmt = s.format?.toLowerCase() || '';
      return plfPatterns.some(p => fmt.includes(p));
    }).length;

    return {
      filmCount: films.size,
      showingCount,
      priceRange: allPrices.length > 0 ? `$${minPrice.toFixed(2)} - $${maxPrice.toFixed(2)}` : 'N/A',
      opHours,
      count3D,
      countPLF,
    };
  };

  return (
    <div className="space-y-2">
      {/* Expand/Collapse controls */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted-foreground">
          {theaterGroups.length} theaters
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={expandAll}>
            Expand All
          </Button>
          <Button variant="ghost" size="sm" onClick={collapseAll}>
            Collapse All
          </Button>
        </div>
      </div>

      {/* Theater sections */}
      {theaterGroups.map(([theater, showings]) => {
        const isExpanded = expandedTheaters.has(theater);
        const summary = getTheaterSummary(showings);

        return (
          <div key={theater} className="border rounded-lg overflow-hidden">
            {/* Collapsible header */}
            <button
              onClick={() => toggleTheater(theater)}
              className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="font-medium">{theater}</span>
              </div>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                {summary.opHours && (
                  <span className="text-xs opacity-80">{summary.opHours}</span>
                )}
                <span>{summary.filmCount} films</span>
                <span>{summary.showingCount} showtimes</span>
                {summary.count3D > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {summary.count3D} 3D
                  </Badge>
                )}
                {summary.countPLF > 0 && (
                  <Badge variant="outline" className="text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300">
                    {summary.countPLF} PLF
                  </Badge>
                )}
                <Badge variant="secondary" className="font-mono text-xs">
                  {summary.priceRange}
                </Badge>
              </div>
            </button>

            {/* Expanded content - grouped by showing */}
            {isExpanded && (
              <div className="border-t bg-muted/20">
                <div className="divide-y">
                  {showings.map((showing, i) => {
                    const isStandardFormat = !showing.format || showing.format.toLowerCase() === 'standard';

                    return (
                      <div key={i} className="p-3 hover:bg-muted/30">
                        {/* Film title and showtime row */}
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex-1 min-w-0">
                            <span className="font-medium">{showing.film_title}</span>
                            {!isStandardFormat && (
                              <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                                {getFormatEmoji(showing.format)} {showing.format}
                              </span>
                            )}
                          </div>
                          <span className="text-sm font-mono text-muted-foreground whitespace-nowrap">
                            {showing.showtime}
                          </span>
                        </div>

                        {/* Ticket prices row */}
                        <div className="flex flex-wrap gap-3 text-sm">
                          {showing.prices.map((price, j) => (
                            <div key={j} className="flex items-center gap-1">
                              <span className="text-muted-foreground">{price.ticket_type}:</span>
                              <span className="font-mono font-medium">{price.price}</span>
                            </div>
                          ))}
                        </div>
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
  );
}

// =============================================================================
// BY FILM RESULTS COMPONENT
// =============================================================================

interface FilmResultsProps {
  results: Record<string, unknown>[];
}

function FilmResults({ results }: FilmResultsProps) {
  const [expandedFilms, setExpandedFilms] = useState<Set<string>>(new Set());

  // Group results by film, then by theater
  const filmGroups = useMemo(() => {
    const groups: Record<string, Record<string, ShowingGroup[]>> = {};

    for (const r of results) {
      const film = r.film_title as string;
      const theater = r.theater_name as string;
      const showtime = r.showtime as string;
      const format = (r.format as string) || 'Standard';
      const ticketType = r.ticket_type as string;
      const priceStr = r.price as string;
      const priceMatch = priceStr?.match(/\$?([\d.]+)/);
      const priceNum = priceMatch ? parseFloat(priceMatch[1]) : 0;

      if (!groups[film]) groups[film] = {};
      if (!groups[film][theater]) groups[film][theater] = [];

      // Find existing showing or create new one
      const showingKey = `${showtime}|${format}`;
      let showing = groups[film][theater].find(
        s => `${s.showtime}|${s.format}` === showingKey
      );

      if (!showing) {
        showing = { film_title: film, showtime, format, prices: [] };
        groups[film][theater].push(showing);
      }

      if (!showing.prices.find(p => p.ticket_type === ticketType)) {
        showing.prices.push({ ticket_type: ticketType, price: priceStr, priceNum });
      }
    }

    // Sort showings by time and prices
    for (const film of Object.keys(groups)) {
      for (const theater of Object.keys(groups[film])) {
        groups[film][theater].sort((a, b) => {
          const parseTime = (t: string) => {
            const match = t.match(/(\d+):(\d+)\s*(AM|PM)/i);
            if (!match) return 0;
            let hours = parseInt(match[1]);
            const mins = parseInt(match[2]);
            const isPM = match[3].toUpperCase() === 'PM';
            if (isPM && hours !== 12) hours += 12;
            if (!isPM && hours === 12) hours = 0;
            return hours * 60 + mins;
          };
          return parseTime(a.showtime) - parseTime(b.showtime);
        });

        for (const showing of groups[film][theater]) {
          showing.prices.sort((a, b) => {
            if (a.ticket_type === 'Adult' || a.ticket_type === 'General Admission') return -1;
            if (b.ticket_type === 'Adult' || b.ticket_type === 'General Admission') return 1;
            return a.ticket_type.localeCompare(b.ticket_type);
          });
        }
      }
    }

    // Sort films alphabetically, then theaters
    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([film, theaters]) => ({
        film,
        theaters: Object.entries(theaters).sort(([a], [b]) => a.localeCompare(b)),
      }));
  }, [results]);

  const toggleFilm = (film: string) => {
    setExpandedFilms(prev => {
      const next = new Set(prev);
      if (next.has(film)) {
        next.delete(film);
      } else {
        next.add(film);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedFilms(new Set(filmGroups.map(g => g.film)));
  };

  const collapseAll = () => {
    setExpandedFilms(new Set());
  };

  const getFilmSummary = (theaters: [string, ShowingGroup[]][]) => {
    const theaterCount = theaters.length;
    const allShowings = theaters.flatMap(([, showings]) => showings);
    const showingCount = allShowings.length;
    const allPrices = allShowings
      .flatMap(s => s.prices.map(p => p.priceNum))
      .filter(p => p > 0);
    const minPrice = allPrices.length > 0 ? Math.min(...allPrices) : 0;
    const maxPrice = allPrices.length > 0 ? Math.max(...allPrices) : 0;

    // Count 3D showings
    const count3D = allShowings.filter(s =>
      s.format?.toLowerCase().includes('3d')
    ).length;

    // Count PLF showings
    const plfPatterns = ['imax', 'dolby', 'premium', 'screenx', '4dx', 'rpx', 'superscreen', 'liemax', 'plf'];
    const countPLF = allShowings.filter(s => {
      const fmt = s.format?.toLowerCase() || '';
      return plfPatterns.some(p => fmt.includes(p));
    }).length;

    return {
      theaterCount,
      showingCount,
      priceRange: allPrices.length > 0 ? `$${minPrice.toFixed(2)} - $${maxPrice.toFixed(2)}` : 'N/A',
      count3D,
      countPLF,
    };
  };

  return (
    <div className="space-y-2">
      {/* Expand/Collapse controls */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted-foreground">
          {filmGroups.length} films
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={expandAll}>
            Expand All
          </Button>
          <Button variant="ghost" size="sm" onClick={collapseAll}>
            Collapse All
          </Button>
        </div>
      </div>

      {/* Film sections */}
      {filmGroups.map(({ film, theaters }) => {
        const isExpanded = expandedFilms.has(film);
        const summary = getFilmSummary(theaters);

        return (
          <div key={film} className="border rounded-lg overflow-hidden">
            {/* Collapsible header */}
            <button
              onClick={() => toggleFilm(film)}
              className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="font-medium">{film}</span>
              </div>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <span>{summary.theaterCount} theaters</span>
                <span>{summary.showingCount} showtimes</span>
                {summary.count3D > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {summary.count3D} 3D
                  </Badge>
                )}
                {summary.countPLF > 0 && (
                  <Badge variant="outline" className="text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300">
                    {summary.countPLF} PLF
                  </Badge>
                )}
                <Badge variant="secondary" className="font-mono text-xs">
                  {summary.priceRange}
                </Badge>
              </div>
            </button>

            {/* Expanded content - grouped by theater */}
            {isExpanded && (
              <div className="border-t bg-muted/20">
                {theaters.map(([theater, showings], ti) => (
                  <div key={ti} className="border-b last:border-b-0">
                    <div className="px-3 py-2 bg-muted/30 text-sm font-medium flex items-center gap-2">
                      <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                      {theater}
                    </div>
                    <div className="divide-y">
                      {showings.map((showing, si) => {
                        const isStandardFormat = !showing.format || showing.format.toLowerCase() === 'standard';

                        return (
                          <div key={si} className="px-3 py-2 pl-6 hover:bg-muted/20">
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-sm">{showing.showtime}</span>
                                {!isStandardFormat && (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                                    {getFormatEmoji(showing.format)} {showing.format}
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-3 text-sm">
                              {showing.prices.map((price, pi) => (
                                <div key={pi} className="flex items-center gap-1">
                                  <span className="text-muted-foreground">{price.ticket_type}:</span>
                                  <span className="font-mono font-medium">{price.price}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
