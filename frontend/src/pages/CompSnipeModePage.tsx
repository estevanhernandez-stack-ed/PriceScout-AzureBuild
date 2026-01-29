import { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Crosshair,
  Plus,
  Trash2,
  Play,
  RefreshCw,
  CheckCircle2,
  DollarSign,
  Film,
  Clock,
  ExternalLink,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  LayoutGrid,
  List as ListIcon,
  Eye,
  EyeOff,
  Search,
  MapPin,
  History as HistoryIcon,
  Loader2,
} from 'lucide-react';
import {
  useTriggerScrape,
  useScrapeStatus,
  useFetchShowtimes,
  useEstimateScrapeTime,
  useSearchTheatersFandango,
  useSearchTheatersCache,
  useMarketTheaters,
  useLiveScrapeJobs,
  type Showing,
  type TheaterSearchResult,
} from '@/hooks/api';
import { useAuthStore } from '@/stores/authStore';
import { useToast } from '@/hooks/use-toast';
import { format, isToday, addDays } from 'date-fns';
import { cn } from '@/lib/utils';

// LocalStorage key for persisting scrape job ID
const COMPSNIPE_JOB_STORAGE_KEY = 'pricescout_compsnipe_scrape_job';

interface TheaterEntry {
  id: string;
  name: string;
  url: string;
}

interface ScrapeResult {
  theater_name: string;
  film_title: string;
  showtime: string;
  price: number;
  format: string;
  is_plf?: boolean;
}

type WorkflowStep = 'input' | 'film-selection' | 'running' | 'results';
type FilmScope = 'all' | 'common' | 'manual';

// Format emoji mapping
const getFormatEmoji = (format: string, isPLF: boolean) => {
  const formatLower = format.toLowerCase();
  if (formatLower.includes('imax')) return '📽️';
  if (formatLower.includes('dolby') || formatLower.includes('atmos')) return '🔊';
  if (formatLower.includes('4dx')) return '💨';
  if (formatLower.includes('3d')) return '👓';
  if (formatLower.includes('d-box') || formatLower.includes('dbox')) return '💺';
  if (isPLF) return '✨';
  return '';
};

export function CompSnipeModePage() {
  // Theater input state
  const [theaters, setTheaters] = useState<TheaterEntry[]>([
    { id: '1', name: '', url: '' },
  ]);

  // Date selection state
  const [selectedDate, setSelectedDate] = useState<string>(format(new Date(), 'yyyy-MM-dd'));

  // Workflow state
  const [step, setStep] = useState<WorkflowStep>('input');

  // Film selection state
  const [filmScope, setFilmScope] = useState<FilmScope>('all');
  const [availableShowtimes, setAvailableShowtimes] = useState<Record<string, Record<string, Showing[]>>>({});
  const [selectedFilms, setSelectedFilms] = useState<Set<string>>(new Set());
  const [expandedTheaters, setExpandedTheaters] = useState<Set<string>>(new Set());

  // Scrape state
  const [jobId, setJobId] = useState<number | null>(null);
  const [results, setResults] = useState<ScrapeResult[]>([]);
  const [viewMode, setViewMode] = useState<'list' | 'matrix'>('matrix');
  const [visibleTheaters, setVisibleTheaters] = useState<Set<string>>(new Set());

  // Search state
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState<'name' | 'zip' | 'cache'>('name');
  const [searchResults, setSearchResults] = useState<TheaterSearchResult[]>([]);

  // Confirmation dialog
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [estimatedTime, setEstimatedTime] = useState<string>('');

  // Mutations and queries
  const triggerMutation = useTriggerScrape();
  const fetchShowtimesMutation = useFetchShowtimes();
  const estimateTimeMutation = useEstimateScrapeTime();
  const searchFandangoMutation = useSearchTheatersFandango();
  const searchCacheMutation = useSearchTheatersCache();

  const { user } = useAuthStore();
  const { toast } = useToast();
  const { data: marketTheaters } = useMarketTheaters(user?.home_location_type === 'market' ? user.home_location_value || '' : '');

  // Check for running scrapes (used to restore state on page load)
  const { data: liveScrapeJobs } = useLiveScrapeJobs();

  // Restore scrape state from localStorage or API on mount
  useEffect(() => {
    // Check localStorage first
    const savedJobId = localStorage.getItem(COMPSNIPE_JOB_STORAGE_KEY);
    if (savedJobId) {
      const parsedJobId = parseInt(savedJobId, 10);
      if (!isNaN(parsedJobId)) {
        console.log('[CompSnipe] Restoring job ID from localStorage:', parsedJobId);
        setJobId(parsedJobId);
        setStep('running');
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
        console.log('[CompSnipe] Found active job from API:', activeJob.job_id);
        setJobId(activeJob.job_id);
        setStep('running');
        localStorage.setItem(COMPSNIPE_JOB_STORAGE_KEY, String(activeJob.job_id));
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
    if (jobId) {
      localStorage.setItem(COMPSNIPE_JOB_STORAGE_KEY, String(jobId));
      console.log('[CompSnipe] Saved job ID to localStorage:', jobId);
    }
  }, [jobId]);

  // Poll for status when we have an active job
  const { data: jobStatus, error: jobStatusError } = useScrapeStatus(jobId || 0, {
    enabled: !!jobId && (step === 'running' || step === 'results'),
    refetchInterval: step === 'running' ? 2000 : false,
  });

  // Clear localStorage when scrape completes
  useEffect(() => {
    if (jobStatus?.status === 'completed' || jobStatus?.status === 'failed') {
      const timeout = setTimeout(() => {
        localStorage.removeItem(COMPSNIPE_JOB_STORAGE_KEY);
        console.log('[CompSnipe] Cleared job ID from localStorage (job completed)');
      }, 5 * 60 * 1000);
      return () => clearTimeout(timeout);
    }
  }, [jobStatus?.status]);

  // Auto-set visible theaters after results
  useEffect(() => {
    if (results.length > 0 && visibleTheaters.size === 0) {
      const allTheaters = new Set(results.map(r => r.theater_name));
      setVisibleTheaters(allTheaters);
    }
  }, [results, visibleTheaters.size]);

  // Auto-populate home theaters on first load
  useEffect(() => {
    if (!user) return;
    
    // Only run if the theaters list is empty or just has the initial empty entry
    const isEmpty = theaters.length === 0 || (theaters.length === 1 && !theaters[0].name && !theaters[0].url);
    if (!isEmpty) return;

    if (user.home_location_type === 'theater' && user.home_location_value) {
      // Search cache for this specific theater to get its URL
      searchCacheMutation.mutate(user.home_location_value, {
        onSuccess: (data) => {
          if (data && data.length > 0) {
            // Find an exact match if possible, or just take the first result
            const match = data.find(t => t.name.toLowerCase() === user.home_location_value?.toLowerCase()) || data[0];
            setTheaters([{ id: '1', name: match.name, url: match.url }]);
          }
        }
      });
    } else if (user.home_location_type === 'market' && marketTheaters && marketTheaters.length > 0) {
      const homeTheaters = marketTheaters.map((t, idx) => ({
        id: (idx + 1).toString(),
        name: t.theater_name,
        url: t.url || ''
      }));
      setTheaters(homeTheaters);
    }
  }, [user, marketTheaters, theaters.length]);

  // Handle stale job IDs (e.g., server restarted and job no longer exists)
  useEffect(() => {
    if (jobStatusError && jobId) {
      const isNotFound = (jobStatusError as any)?.response?.status === 404;
      if (isNotFound) {
        console.log('[CompSnipe] Job not found (server may have restarted), clearing stale job ID:', jobId);
        localStorage.removeItem(COMPSNIPE_JOB_STORAGE_KEY);
        setJobId(null);
        setStep('input');
        toast({
          title: 'Session Expired',
          description: 'The previous scrape session is no longer available. Please start a new scrape.',
          variant: 'destructive',
        });
      }
    }
  }, [jobStatusError, jobId, toast]);

  // Check if it's after 4 PM for same-day warning
  const isAfter4PM = useMemo(() => {
    return new Date().getHours() >= 16;
  }, []);

  const isSameDay = useMemo(() => {
    return isToday(new Date(selectedDate + 'T00:00:00'));
  }, [selectedDate]);

  // Calculate available films based on scope
  const filteredFilms = useMemo(() => {
    if (!availableShowtimes || Object.keys(availableShowtimes).length === 0) return [];

    const allFilms = new Set<string>();
    const filmsByTheater: Record<string, Set<string>> = {};

    // Get films by theater
    Object.values(availableShowtimes).forEach(theaterShowtimes => {
      Object.entries(theaterShowtimes).forEach(([theaterName, showings]) => {
        if (!filmsByTheater[theaterName]) {
          filmsByTheater[theaterName] = new Set();
        }
        showings.forEach(s => {
          allFilms.add(s.film_title);
          filmsByTheater[theaterName].add(s.film_title);
        });
      });
    });

    if (filmScope === 'all') {
      return Array.from(allFilms).sort();
    } else if (filmScope === 'common') {
      // Only films available in ALL theaters
      const theaterFilmSets = Object.values(filmsByTheater);
      if (theaterFilmSets.length === 0) return [];

      let commonFilms = new Set(theaterFilmSets[0]);
      for (let i = 1; i < theaterFilmSets.length; i++) {
        commonFilms = new Set([...commonFilms].filter(f => theaterFilmSets[i].has(f)));
      }
      return Array.from(commonFilms).sort();
    }

    return Array.from(allFilms).sort();
  }, [availableShowtimes, filmScope]);

  // Watch for job completion
  useEffect(() => {
    if (jobStatus?.status === 'completed' && jobStatus.results) {
      const transformedResults: ScrapeResult[] = jobStatus.results.map((r: Record<string, unknown>) => ({
        theater_name: String(r.theater_name || 'Unknown'),
        film_title: String(r.film_title || 'Unknown'),
        showtime: String(r.showtime || ''),
        price: Number(r.price) || 0,
        format: String(r.format || 'Standard'),
        is_plf: Boolean(r.is_plf),
      }));
      setResults(transformedResults);
      
      // Auto-set visible theaters
      const uniqueTheaters = Array.from(new Set(transformedResults.map(r => r.theater_name)));
      setVisibleTheaters(new Set(uniqueTheaters));
      
      setStep('results');
      setJobId(null);
    } else if (jobStatus?.status === 'failed') {
      setJobId(null);
      setStep('input');
    }
  }, [jobStatus]);

  const addTheater = () => {
    setTheaters([...theaters, { id: Date.now().toString(), name: '', url: '' }]);
  };

  const removeTheater = (id: string) => {
    if (theaters.length > 1) {
      setTheaters(theaters.filter((t) => t.id !== id));
    }
  };

  const updateTheater = (id: string, field: 'name' | 'url', value: string) => {
    setTheaters(
      theaters.map((t) => (t.id === id ? { ...t, [field]: value } : t))
    );
  };

  const handleFetchShowtimes = async () => {
    const validTheaters = theaters.filter((t) => t.url.trim());
    if (validTheaters.length === 0) return;

    try {
      const response = await fetchShowtimesMutation.mutateAsync({
        theaters: validTheaters.map((t, idx) => ({
          name: t.name || `Theater ${idx + 1}`,
          url: t.url,
        })),
        dates: [selectedDate],
      });

      setAvailableShowtimes(response.showtimes);

      // Auto-select all films initially
      const allFilms = new Set<string>();
      Object.values(response.showtimes).forEach(theaterShowtimes => {
        Object.values(theaterShowtimes).forEach(showings => {
          showings.forEach(s => allFilms.add(s.film_title));
        });
      });
      setSelectedFilms(allFilms);
      setStep('film-selection');
    } catch (error) {
      console.error('Failed to fetch showtimes:', error);
    }
  };

  const handleFilmToggle = (film: string) => {
    const newSelected = new Set(selectedFilms);
    if (newSelected.has(film)) {
      newSelected.delete(film);
    } else {
      newSelected.add(film);
    }
    setSelectedFilms(newSelected);
  };

  const handleProceedToScrape = async () => {
    // Count total showtimes for estimation
    let totalShowtimes = 0;
    Object.values(availableShowtimes).forEach(theaterShowtimes => {
      Object.values(theaterShowtimes).forEach(showings => {
        totalShowtimes += showings.filter(s => selectedFilms.has(s.film_title)).length;
      });
    });

    // Get time estimate
    try {
      const estimate = await estimateTimeMutation.mutateAsync({
        num_showings: totalShowtimes,
        mode: 'compsnipe',
      });
      setEstimatedTime(estimate.formatted_time);
    } catch {
      setEstimatedTime('Unknown');
    }

    setShowConfirmDialog(true);
  };

  const handleStartScrape = async () => {
    setShowConfirmDialog(false);
    setStep('running');

    const validTheaters = theaters.filter((t) => t.url.trim());

    try {
      const response = await triggerMutation.mutateAsync({
        mode: 'compsnipe',
        theaters: validTheaters.map((t, idx) => ({
          name: t.name || `Theater ${idx + 1}`,
          url: t.url,
        })),
        dates: [selectedDate],
      });
      setJobId(response.job_id);
    } catch (error) {
      console.error('Failed to trigger scrape:', error);
      setStep('film-selection');
    }
  };

  const handleReset = () => {
    setTheaters([{ id: '1', name: '', url: '' }]);
    setSelectedDate(format(new Date(), 'yyyy-MM-dd'));
    setStep('input');
    setFilmScope('all');
    setAvailableShowtimes({});
    setSelectedFilms(new Set());
    setExpandedTheaters(new Set());
    setResults([]);
    setJobId(null);
    // Clear localStorage
    localStorage.removeItem(COMPSNIPE_JOB_STORAGE_KEY);
    console.log('[CompSnipe] Cleared job ID from localStorage (user reset)');
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    try {
      if (searchType === 'cache') {
        const results = await searchCacheMutation.mutateAsync(searchQuery);
        setSearchResults(results);
      } else {
        const results = await searchFandangoMutation.mutateAsync({
          query: searchQuery,
          searchType: searchType as 'name' | 'zip',
          date: selectedDate,
        });
        setSearchResults(results);
      }
    } catch (error) {
      console.error('Search failed:', error);
    }
  };

  const addSearchedTheater = (result: TheaterSearchResult) => {
    // Check if URL already exists
    if (theaters.some(t => t.url === result.url)) return;

    const newTheater = {
      id: Date.now().toString(),
      name: result.name,
      url: result.url,
    };

    // Replace first empty theater if exists, otherwise append
    if (theaters.length === 1 && !theaters[0].url.trim() && !theaters[0].name.trim()) {
      setTheaters([newTheater]);
    } else {
      setTheaters([...theaters, newTheater]);
    }
    setIsSearchOpen(false);
  };

  const handleExportCSV = () => {
    if (results.length === 0) return;

    const headers = ['Theater', 'Film', 'Showtime', 'Price', 'Format'];
    const rows = results.map(r => [
      r.theater_name,
      r.film_title,
      r.showtime,
      `$${r.price.toFixed(2)}`,
      r.format,
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `compsnipe_${selectedDate}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const toggleTheaterExpand = (theaterName: string) => {
    const newExpanded = new Set(expandedTheaters);
    if (newExpanded.has(theaterName)) {
      newExpanded.delete(theaterName);
    } else {
      newExpanded.add(theaterName);
    }
    setExpandedTheaters(newExpanded);
  };

  const validTheaterCount = theaters.filter((t) => t.url.trim()).length;
  const isRunning = step === 'running' || fetchShowtimesMutation.isPending;
  const progress = jobStatus?.progress || 0;

  // Group results by theater for display
  const resultsByTheater = useMemo(() => {
    const grouped: Record<string, ScrapeResult[]> = {};
    results.forEach(r => {
      if (!grouped[r.theater_name]) {
        grouped[r.theater_name] = [];
      }
      grouped[r.theater_name].push(r);
    });
    return grouped;
  }, [results]);
  
  // Pivot data for matrix view
  const matrixData = useMemo(() => {
    if (results.length === 0) return { films: [], theaters: [], data: {} as Record<string, Record<string, ScrapeResult[]>> };
    
    const uniqueTheaters = Array.from(new Set(results.map(r => r.theater_name))).sort();
    const uniqueFilms = Array.from(new Set(results.map(r => r.film_title))).sort();
    
    const data: Record<string, Record<string, ScrapeResult[]>> = {};
    
    uniqueFilms.forEach(film => {
      data[film] = {};
      uniqueTheaters.forEach(theater => {
        data[film][theater] = results.filter(r => r.film_title === film && r.theater_name === theater);
      });
    });
    
    return {
      films: uniqueFilms,
      theaters: uniqueTheaters,
      data
    };
  }, [results]);

  const toggleTheaterVisibility = (name: string) => {
    const next = new Set(visibleTheaters);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    setVisibleTheaters(next);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">CompSnipe Mode</h1>
          <p className="text-muted-foreground">
            Quick competitor price check by direct URL entry
          </p>
        </div>
        <Button variant="outline" onClick={handleReset}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Reset
        </Button>
      </div>

      {/* Step 1: Theater URL Input */}
      {step === 'input' && (
        <Card className="border-border/40 bg-card/50 backdrop-blur-xl">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Theater Selection</CardTitle>
                <CardDescription>Enter Fandango URLs or search for theaters</CardDescription>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                className="bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary"
                onClick={() => setIsSearchOpen(true)}
              >
                <Search className="mr-2 h-4 w-4" />
                Find Theaters
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-4">
              <Label>Date Strategy</Label>
              <div className="flex flex-wrap gap-2">
                <Input
                  type="date"
                  className="w-40"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedDate(format(new Date(), 'yyyy-MM-dd'))}
                >
                  Today
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedDate(format(addDays(new Date(), 1), 'yyyy-MM-dd'))}
                >
                  Tomorrow
                </Button>
              </div>

              {/* Same-day 4 PM warning */}
              {isSameDay && isAfter4PM && (
                <div className="flex items-center gap-2 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-yellow-600">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="text-sm">
                    It's after 4 PM. Same-day showtimes may be limited or sold out.
                  </span>
                </div>
              )}
            </div>

            {/* Theater entries */}
            <div className="space-y-4">
              {theaters.map((theater, index) => (
                <div key={theater.id} className="group relative bg-muted/20 hover:bg-muted/40 p-4 rounded-xl transition-all border border-transparent hover:border-border/60">
                  <div className="flex gap-4 items-start">
                    <div className="flex-1 space-y-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-muted-foreground bg-muted w-6 h-6 flex items-center justify-center rounded-full">
                          {index + 1}
                        </span>
                        <Input
                          placeholder="Theater Name (e.g. AMC NorthPark 15)"
                          value={theater.name}
                          onChange={(e) => updateTheater(theater.id, 'name', e.target.value)}
                          className="bg-background/50 border-border/40 focus:border-primary/40"
                          disabled={isRunning}
                        />
                      </div>
                      <Input
                        placeholder="Fandango URL (Full link from browser)"
                        value={theater.url}
                        onChange={(e) => updateTheater(theater.id, 'url', e.target.value)}
                        className="bg-background/50 border-border/40 focus:border-primary/40 font-mono text-xs"
                        disabled={isRunning}
                      />
                    </div>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      onClick={() => removeTheater(theater.id)} 
                      disabled={theaters.length === 1 || isRunning}
                      className="mt-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={addTheater} disabled={isRunning}>
                <Plus className="mr-2 h-4 w-4" />
                Add Theater
              </Button>
              <Button
                onClick={handleFetchShowtimes}
                disabled={validTheaterCount === 0 || fetchShowtimesMutation.isPending}
              >
                {fetchShowtimesMutation.isPending ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    Fetching Films...
                  </>
                ) : (
                  <>
                    <Film className="mr-2 h-4 w-4" />
                    Find Available Films ({validTheaterCount} theater{validTheaterCount !== 1 ? 's' : ''})
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Film Selection */}
      {step === 'film-selection' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Film className="h-5 w-5" />
              Select Films to Scrape
            </CardTitle>
            <CardDescription>
              Found {filteredFilms.length} films across {Object.keys(resultsByTheater).length || validTheaterCount} theaters
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Film scope selection */}
            <div className="space-y-2">
              <Label>Film Scope</Label>
              <Tabs value={filmScope} onValueChange={(v) => setFilmScope(v as FilmScope)}>
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="all">All Films</TabsTrigger>
                  <TabsTrigger value="common">Common Films Only</TabsTrigger>
                  <TabsTrigger value="manual">Manual Selection</TabsTrigger>
                </TabsList>
              </Tabs>
              <p className="text-xs text-muted-foreground">
                {filmScope === 'all' && 'Scrape all films available at any theater'}
                {filmScope === 'common' && 'Only scrape films showing at ALL selected theaters'}
                {filmScope === 'manual' && 'Manually select which films to scrape'}
              </p>
            </div>

            {/* Film grid */}
            {filmScope === 'manual' && (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">
                    {selectedFilms.size} of {filteredFilms.length} films selected
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedFilms(new Set(filteredFilms))}
                    >
                      Select All
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedFilms(new Set())}
                    >
                      Clear All
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {filteredFilms.map(film => (
                    <Button
                      key={film}
                      variant={selectedFilms.has(film) ? 'default' : 'outline'}
                      className={cn(
                        'justify-start h-auto py-2 px-3 text-left',
                        selectedFilms.has(film) && 'bg-primary text-primary-foreground'
                      )}
                      onClick={() => handleFilmToggle(film)}
                    >
                      <span className="truncate">{film}</span>
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {/* Preview of showtimes by theater */}
            <div className="space-y-2">
              <Label>Showtime Preview by Theater</Label>
              <div className="space-y-2">
                {Object.entries(availableShowtimes[selectedDate] || {}).map(([theaterName, showings]) => {
                  const filteredShowings = showings.filter(s =>
                    filmScope !== 'manual' || selectedFilms.has(s.film_title)
                  );
                  const isExpanded = expandedTheaters.has(theaterName);

                  return (
                    <div key={theaterName} className="border rounded-lg">
                      <button
                        onClick={() => toggleTheaterExpand(theaterName)}
                        className="w-full flex items-center justify-between p-3 hover:bg-muted/50"
                      >
                        <div className="flex items-center gap-2">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                          <span className="font-medium">{theaterName}</span>
                          <Badge variant="secondary">{filteredShowings.length} showtimes</Badge>
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="px-3 pb-3">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                            {filteredShowings.slice(0, 12).map((showing, idx) => (
                              <div key={idx} className="bg-muted/50 rounded p-2 text-sm">
                                <p className="font-medium truncate">{showing.film_title}</p>
                                <div className="flex items-center gap-2 text-muted-foreground">
                                  <span>{showing.showtime}</span>
                                  <span>
                                    {getFormatEmoji(showing.format || 'Standard', showing.is_plf || false)}
                                    {showing.format}
                                  </span>
                                </div>
                              </div>
                            ))}
                            {filteredShowings.length > 12 && (
                              <div className="col-span-full text-sm text-muted-foreground text-center">
                                ... and {filteredShowings.length - 12} more
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep('input')}>
                Back
              </Button>
              <Button
                onClick={handleProceedToScrape}
                disabled={filmScope === 'manual' && selectedFilms.size === 0}
              >
                <Play className="mr-2 h-4 w-4" />
                Proceed to Scrape
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Running */}
      {step === 'running' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5 animate-spin" />
              Scraping in Progress
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={progress} className="h-3" />
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{progress}% complete</span>
              {jobStatus?.current_theater && (
                <span>Scraping: {jobStatus.current_theater}</span>
              )}
            </div>
            {jobStatus?.theaters_completed !== undefined && (
              <p className="text-sm text-muted-foreground text-center">
                {jobStatus.theaters_completed} of {jobStatus.theaters_total} theaters completed
              </p>
            )}
            {jobStatus?.duration_seconds && (
              <p className="text-sm text-muted-foreground text-center">
                Elapsed: {Math.round(jobStatus.duration_seconds)}s
              </p>
            )}

            {jobStatus?.status === 'failed' && (
              <div className="flex items-center gap-2 text-destructive">
                <XCircle className="h-5 w-5" />
                <span>Scrape failed: {jobStatus.error || 'Unknown error'}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 4: Results */}
      {step === 'results' && (
        <div className="space-y-6">
          <Card className="border-border/40 bg-card/50 backdrop-blur-xl">
            <CardHeader>
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    Scrape Complete
                  </CardTitle>
                  <CardDescription>
                    Comparing {results.length} showtimes across {Object.keys(resultsByTheater).length} theaters
                  </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <div className="flex border rounded-md p-1 bg-muted/30">
                    <Button
                      variant={viewMode === 'matrix' ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => setViewMode('matrix')}
                      className="h-8 px-3"
                    >
                      <LayoutGrid className="mr-2 h-4 w-4" />
                      Matrix
                    </Button>
                    <Button
                      variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                      size="sm"
                      onClick={() => setViewMode('list')}
                      className="h-8 px-3"
                    >
                      <ListIcon className="mr-2 h-4 w-4" />
                      List
                    </Button>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleExportCSV}>
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                    Export CSV
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Crosshair className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-xl font-bold">{Object.keys(resultsByTheater).length}</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Theaters</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Film className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-xl font-bold">
                    {new Set(results.map((r) => r.film_title)).size}
                  </p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Films</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Clock className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-xl font-bold">{results.length}</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Showtimes</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <DollarSign className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-xl font-bold">
                    {results.length > 0
                      ? `$${(results.reduce((sum, r) => sum + r.price, 0) / results.length).toFixed(2)}`
                      : 'N/A'}
                  </p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Avg Price</p>
                </div>
              </div>

              {/* Theater Visibility Toggles */}
              {viewMode === 'matrix' && matrixData.theaters.length > 1 && (
                <div className="mt-8 space-y-3">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Eye className="h-4 w-4" />
                    Column Visibility
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {matrixData.theaters.map(t => (
                      <Badge
                        key={t}
                        variant={visibleTheaters.has(t) ? 'default' : 'outline'}
                        className="cursor-pointer hover:opacity-80 transition-opacity"
                        onClick={() => toggleTheaterVisibility(t)}
                      >
                        {visibleTheaters.has(t) ? <Eye className="h-3 w-3 mr-1" /> : <EyeOff className="h-3 w-3 mr-1" />}
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {results.length === 0 ? (
            <Card>
              <CardContent className="py-8">
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                  <AlertTriangle className="h-12 w-12" />
                  <p>No showtimes found for the provided URLs.</p>
                  <p className="text-sm">Try different theater URLs or check if they are valid Fandango pages.</p>
                </div>
              </CardContent>
            </Card>
          ) : viewMode === 'matrix' ? (
            <Card className="border-border/40 bg-card/50 backdrop-blur-xl overflow-hidden">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/50">
                    <TableRow>
                      <TableHead className="w-[250px] sticky left-0 bg-background/80 backdrop-blur-md z-10">Film Title</TableHead>
                      {matrixData.theaters.filter(t => visibleTheaters.has(t)).map(t => (
                        <TableHead key={t} className="min-w-[180px] text-center">{t}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {matrixData.films.map(film => {
                      // Find lowest price for this film for color coding
                      const allPrices = results
                        .filter(r => r.film_title === film && visibleTheaters.has(r.theater_name))
                        .map(r => r.price);
                      const minPrice = allPrices.length > 0 ? Math.min(...allPrices) : null;

                      return (
                        <TableRow key={film}>
                          <TableCell className="font-semibold sticky left-0 bg-background/80 backdrop-blur-md z-10 border-r">
                            {film}
                          </TableCell>
                          {matrixData.theaters.filter(t => visibleTheaters.has(t)).map(t => {
                            const theaterResults = matrixData.data[film][t];
                            if (!theaterResults || theaterResults.length === 0) {
                              return (
                                <TableCell key={t} className="text-center text-muted-foreground italic">
                                  No showings
                                </TableCell>
                              );
                            }

                            return (
                              <TableCell key={t} className="p-0">
                                <div className="p-2 space-y-1">
                                  {theaterResults.map((r, i) => (
                                    <div 
                                      key={i} 
                                      className={cn(
                                        "flex justify-between items-center px-2 py-1 rounded text-xs",
                                        r.price === minPrice ? "bg-green-500/10 text-green-600 font-bold" : "bg-muted/20"
                                      )}
                                    >
                                      <span className="flex items-center gap-1">
                                        <span className="text-[10px] op-60">{r.showtime}</span>
                                        {getFormatEmoji(r.format, r.is_plf || false)}
                                      </span>
                                      <span>${r.price.toFixed(2)}</span>
                                    </div>
                                  ))}
                                </div>
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </Card>
          ) : (
            <div className="space-y-4">
              {Object.entries(resultsByTheater).map(([theaterName, theaterResults]) => {
                const theater = theaters.find(t =>
                  t.name === theaterName ||
                  theaterName.includes(t.name) ||
                  (t.name && t.name.length > 3 && theaterName.toLowerCase().includes(t.name.toLowerCase()))
                );
                const isExpanded = expandedTheaters.has(theaterName);

                // Calculate operating hours
                const times = theaterResults.map(r => r.showtime).sort();
                const firstShowtime = times[0];
                const lastShowtime = times[times.length - 1];

                return (
                  <Card key={theaterName} className="border-border/40 bg-card/50 backdrop-blur-xl">
                    <button
                      onClick={() => toggleTheaterExpand(theaterName)}
                      className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        <div className="text-left">
                          <span className="font-semibold">{theaterName}</span>
                          <div className="flex items-center gap-4 text-xs text-muted-foreground uppercase tracking-wide mt-1">
                            <span>{theaterResults.length} showtimes</span>
                            <span>{firstShowtime} - {lastShowtime}</span>
                          </div>
                        </div>
                      </div>
                      {theater?.url && (
                        <a
                          href={theater.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline flex items-center gap-1 bg-primary/10 px-2 py-1 rounded-full"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Fandango
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </button>

                    {isExpanded && (
                      <CardContent className="px-4 pb-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
                          {theaterResults.map((result, i) => (
                            <div key={i} className="bg-muted/30 border border-border/20 rounded-lg p-2 text-sm">
                              <p className="font-medium truncate text-xs">{result.film_title}</p>
                              <div className="flex justify-between items-center mt-1">
                                <span className="text-xs text-muted-foreground">{result.showtime}</span>
                                <span className="font-bold text-primary">${result.price.toFixed(2)}</span>
                              </div>
                              <div className="flex flex-wrap gap-1 mt-1">
                                <Badge variant="outline" className="text-[9px] h-4 px-1 leading-none">
                                  {getFormatEmoji(result.format, result.is_plf || false)} {result.format}
                                </Badge>
                              </div>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Theater Search Dialog */}
      <Dialog open={isSearchOpen} onOpenChange={setIsSearchOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Find Theater</DialogTitle>
            <DialogDescription>
              Search Fandango or your saved markets to quickly find theater URLs
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex gap-2 py-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={searchType === 'zip' ? "Enter ZIP code..." : "Search theater name or market..."}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="pl-10"
              />
            </div>
            <Tabs 
              value={searchType} 
              onValueChange={(v) => setSearchType(v as 'name' | 'zip' | 'cache')}
              className="w-auto"
            >
              <TabsList>
                <TabsTrigger value="name">Name</TabsTrigger>
                <TabsTrigger value="zip">ZIP</TabsTrigger>
                <TabsTrigger value="cache">Market</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button onClick={handleSearch} disabled={searchFandangoMutation.isPending || searchCacheMutation.isPending}>
              {(searchFandangoMutation.isPending || searchCacheMutation.isPending) ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Search'
              )}
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto min-h-[300px] border rounded-lg bg-muted/30">
            {!searchResults.length && !searchFandangoMutation.isPending && !searchCacheMutation.isPending ? (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground p-8 text-center">
                <MapPin className="h-12 w-12 mb-4 opacity-20" />
                <p>Search for theaters by name, ZIP, or browse by market.</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {searchResults.map((result, idx) => (
                  <div key={idx} className="p-4 hover:bg-muted/50 flex items-center justify-between group">
                    <div className="space-y-1 overflow-hidden mr-4">
                      <div className="font-medium truncate">{result.name}</div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="truncate max-w-[300px] font-mono">{result.url}</span>
                        {result.market && (
                          <Badge variant="outline" className="text-[10px] py-0 h-4">
                            {result.market}
                          </Badge>
                        )}
                      </div>
                    </div>
                    <Button 
                      size="sm" 
                      onClick={() => addSearchedTheater(result)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Plus className="mr-2 h-3 w-3" />
                      Add
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter className="pt-4">
            <div className="flex-1 flex items-center gap-2 text-xs text-muted-foreground">
              <HistoryIcon className="h-3 w-3" />
              Recent searches are not saved
            </div>
            <Button variant="ghost" onClick={() => setIsSearchOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Scrape</DialogTitle>
            <DialogDescription>
              You are about to scrape prices for {filmScope === 'manual' ? selectedFilms.size : filteredFilms.length} films
              across {validTheaterCount} theaters.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <span className="text-muted-foreground">Estimated Time:</span>
              <span className="font-medium">{estimatedTime || 'Calculating...'}</span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirmDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleStartScrape}>
              <Play className="mr-2 h-4 w-4" />
              Start Scrape
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
