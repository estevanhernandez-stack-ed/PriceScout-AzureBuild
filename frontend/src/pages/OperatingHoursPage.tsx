import { useState, useMemo, useEffect } from 'react';
import { useMarketsHierarchy, useTheaterCache } from '@/hooks/api/useMarkets';
import {
  useFetchOperatingHours,
  type OperatingHoursScrapeRecord,
  type WeekComparisonRecord,
} from '@/hooks/api/useReports';
import { useTheaterOperatingHours, useUpdateTheaterOperatingHours, type DailyOperatingHours } from '@/hooks/api/useOperatingHoursConfig';
import { useEstimateScrapeTime } from '@/hooks/api/useScrapes';
import { useMarkTheaterStatus } from '@/hooks/api/useZeroShowtimes';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  MapPin,
  Building2,
  Clock,
  RefreshCw,
  Download,
  CheckCircle2,
  Play,
  Calendar,
  Users,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  ArrowRight,
  Settings,
  Save,
  Timer,
  Printer,
  Minimize2,
  Maximize2,
} from 'lucide-react';
import { format, addDays, nextThursday, startOfDay } from 'date-fns';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/authStore';
import { useToast } from '@/hooks/use-toast';

type WorkflowStep = 'select-director' | 'select-market' | 'select-theaters' | 'select-dates' | 'running' | 'results';

interface TheaterEntry {
  name: string;
  zip?: string;
  status?: string;
  url?: string;
  company?: string;
  not_on_fandango?: boolean;
}

// Format duration in seconds to human-readable string
function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  }

  return `${minutes}m ${secs}s`;
}

export function OperatingHoursPage() {
  const { user } = useAuthStore();
  const selectedCompany = user?.company || 'Marcus Theatres';

  // Workflow state
  const [step, setStep] = useState<WorkflowStep>('select-director');
  const [topTab, setTopTab] = useState<'analyze' | 'configure'>('analyze');
  const [configTheater, setConfigTheater] = useState<string | null>(null);
  const [configHours, setConfigHours] = useState<DailyOperatingHours[]>([]);
  const [selectedDirector, setSelectedDirector] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedTheaters, setSelectedTheaters] = useState<string[]>([]);
  const [startDate, setStartDate] = useState<Date>(addDays(new Date(), 1));
  const [endDate, setEndDate] = useState<Date>(addDays(new Date(), 7));

  // Results state
  const [operatingHours, setOperatingHours] = useState<OperatingHoursScrapeRecord[]>([]);
  const [comparison, setComparison] = useState<WeekComparisonRecord[] | null>(null);
  const [summary, setSummary] = useState<{ changed: number; no_change: number; new: number }>({
    changed: 0,
    no_change: 0,
    new: 0,
  });
  const [scrapeDuration, setScrapeDuration] = useState<number>(0);

  // Mark theater dialog state
  const [markDialogOpen, setMarkDialogOpen] = useState(false);
  const [markDialogTheater, setMarkDialogTheater] = useState<string>('');
  const [markDialogAction, setMarkDialogAction] = useState<'not_on_fandango' | 'closed'>('not_on_fandango');
  const [markDialogUrl, setMarkDialogUrl] = useState<string>('');

  // Time estimation state
  const [timeEstimate, setTimeEstimate] = useState<{ seconds: number; formatted: string; hasData: boolean } | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Elapsed time tracking for running state
  const [scrapeStartTime, setScrapeStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Track elapsed time while running
  useEffect(() => {
    if (step === 'running' && scrapeStartTime) {
      const interval = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - scrapeStartTime) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    } else if (step !== 'running') {
      // Reset when not running
      setElapsedSeconds(0);
    }
  }, [step, scrapeStartTime]);

  // Expanded theaters in results
  const [expandedTheaters, setExpandedTheaters] = useState<Set<string>>(new Set());

  // API hooks
  const { data: marketsData, isLoading: marketsLoading } = useMarketsHierarchy();
  const { data: cacheData } = useTheaterCache();
  const fetchOperatingHours = useFetchOperatingHours();
  const estimateTime = useEstimateScrapeTime();
  const markTheaterStatus = useMarkTheaterStatus();
  const { toast } = useToast();

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

    return marketData.theaters.map((t) => {
      const cacheTheater = cacheData?.markets?.[selectedMarket]?.theaters?.find(
        (ct) => ct.name === t.name
      );
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

  // NEW: Group all theaters by market for Configuration mode
  const groupedTheatersByMarket = useMemo(() => {
    if (!companyData) return {};
    const grouped: Record<string, TheaterEntry[]> = {};
    Object.keys(companyData).forEach((director) => {
      Object.keys(companyData[director]).forEach((market) => {
        if (!grouped[market]) grouped[market] = [];
        grouped[market].push(...companyData[director][market].theaters);
      });
    });
    return grouped;
  }, [companyData]);

  // Check if a theater is scrapeable (moved here so it can be used in selectedMarketsInfo)
  const isScrapeable = (theater: TheaterEntry): boolean => {
    if (theater.status === 'Permanently Closed') return false;
    if (theater.not_on_fandango) return false;
    return true;
  };

  const getScrapeable = (theaters: TheaterEntry[]): TheaterEntry[] => {
    return theaters.filter(isScrapeable);
  };

  // Calculate which markets are covered by the current theater selection
  const selectedMarketsInfo = useMemo(() => {
    if (!companyData || !selectedDirector || selectedTheaters.length === 0) {
      return { markets: [], marketCount: 0, isBulkSelection: false };
    }

    const directorData = companyData[selectedDirector];
    if (!directorData) return { markets: [], marketCount: 0, isBulkSelection: false };

    const marketsWithSelected: string[] = [];
    let totalTheatersInDirector = 0;

    Object.entries(directorData).forEach(([marketName, marketData]) => {
      const marketTheaterNames = marketData.theaters
        .filter((t) => isScrapeable(t))
        .map((t) => t.name);
      totalTheatersInDirector += marketTheaterNames.length;

      const selectedInMarket = marketTheaterNames.filter((name) =>
        selectedTheaters.includes(name)
      );
      if (selectedInMarket.length > 0) {
        marketsWithSelected.push(marketName);
      }
    });

    // Check if this looks like a bulk selection (all or most theaters selected)
    const isBulkSelection = selectedTheaters.length >= totalTheatersInDirector * 0.8;

    return {
      markets: marketsWithSelected,
      marketCount: marketsWithSelected.length,
      totalMarkets: Object.keys(directorData).length,
      isBulkSelection,
    };
  }, [companyData, selectedDirector, selectedTheaters]);

  const { data: existingConfig } = useTheaterOperatingHours(configTheater);
  const updateConfigMutation = useUpdateTheaterOperatingHours();

  useEffect(() => {
    if (existingConfig && existingConfig.length > 0) {
      // Ensure we have all 7 days
      const fullHours = Array.from({ length: 7 }, (_, i) => {
        const existing = existingConfig.find((h) => h.day_of_week === i);
        return (
          existing || {
            day_of_week: i,
            open_time: '',
            close_time: '',
            first_showtime: '',
            last_showtime: '',
          }
        );
      });
      setConfigHours(fullHours);
    } else if (configTheater) {
      // Initialize empty days for new configuration
      setConfigHours(
        Array.from({ length: 7 }, (_, i) => ({
          day_of_week: i,
          open_time: '',
          close_time: '',
          first_showtime: '',
          last_showtime: '',
        }))
      );
    }
  }, [existingConfig, configTheater]);

  const handleConfigChange = (dayIndex: number, field: keyof DailyOperatingHours, value: string) => {
    const newHours = [...configHours];
    newHours[dayIndex] = { ...newHours[dayIndex], [field]: value };
    setConfigHours(newHours);
  };

  const handleSaveConfig = async () => {
    if (!configTheater) return;
    try {
      await updateConfigMutation.mutateAsync({
        theater_name: configTheater,
        hours: configHours,
      });
      alert('Operating hours configuration saved successfully!');
    } catch (error) {
      console.error('Failed to save configuration:', error);
      alert('Failed to save configuration. Please try again.');
    }
  };

  const daysOfWeek = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];

  // Calculate number of days selected
  const numDays = useMemo(() => {
    const diffTime = Math.abs(endDate.getTime() - startDate.getTime());
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
  }, [startDate, endDate]);

  // Estimate showtime count (rough estimate: 30 showtimes per theater per day)
  const estimatedShowtimes = selectedTheaters.length * numDays * 30;

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
      // Skip to date selection when using bulk selection
      setStep('select-dates');
    }
  };

  // Bulk selection: Select all Marcus + Movie Tavern theaters in director
  const handleSelectAllMarcusAndMovieTavern = () => {
    const ownedTheaters = allTheatersInDirector
      .filter((t) => {
        const company = extractCompany(t.name);
        return (company === 'Marcus' || company === 'Movie Tavern') && isScrapeable(t);
      })
      .map((t) => t.name);

    const allSelected = ownedTheaters.every((t) => selectedTheaters.includes(t));

    if (allSelected) {
      setSelectedTheaters((prev) => prev.filter((t) => !ownedTheaters.includes(t)));
    } else {
      setSelectedTheaters((prev) => [...new Set([...prev, ...ownedTheaters])]);
      setStep('select-dates');
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
      // Skip to date selection when using bulk selection
      setStep('select-dates');
    }
  };

  // Set Thu-Thu date range (next Thursday to following Wednesday = 7 days)
  const handleSetThuThu = () => {
    const today = startOfDay(new Date());
    const nextThurs = nextThursday(today);
    const followingWed = addDays(nextThurs, 6);
    setStartDate(nextThurs);
    setEndDate(followingWed);
  };

  // Set this week range
  const handleSetThisWeek = () => {
    const today = startOfDay(new Date());
    setStartDate(today);
    setEndDate(addDays(today, 6));
  };

  // Fetch time estimate when selection changes
  useEffect(() => {
    if (selectedTheaters.length > 0 && step === 'select-dates') {
      estimateTime.mutate(
        { num_showings: estimatedShowtimes, mode: 'showtimes' },  // Use 'showtimes' mode for faster estimate (no price scraping)
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
  }, [selectedTheaters.length, numDays, step]);

  // Group operating hours by theater - MUST be before any early returns (Rules of Hooks)
  const hoursByTheater = useMemo(() => {
    const grouped: Record<string, OperatingHoursScrapeRecord[]> = {};
    operatingHours.forEach((oh) => {
      if (!grouped[oh.theater_name]) grouped[oh.theater_name] = [];
      grouped[oh.theater_name].push(oh);
    });
    // Sort each theater's hours by date
    Object.values(grouped).forEach((arr) => arr.sort((a, b) => a.date.localeCompare(b.date)));
    return grouped;
  }, [operatingHours]);

  // Detect theaters with 0 showtimes across ALL scraped dates
  const zeroShowtimeTheaters = useMemo(() => {
    if (operatingHours.length === 0) return [];
    const theaters: string[] = [];
    Object.entries(hoursByTheater).forEach(([theater, hours]) => {
      const allZero = hours.every(h => h.showtime_count === 0);
      if (allZero && hours.length > 0) {
        theaters.push(theater);
      }
    });
    return theaters;
  }, [hoursByTheater, operatingHours.length]);

  // Open mark-theater dialog
  const openMarkDialog = (theaterName: string) => {
    setMarkDialogTheater(theaterName);
    setMarkDialogAction('not_on_fandango');
    setMarkDialogUrl('');
    setMarkDialogOpen(true);
  };

  // Submit mark-theater action
  const handleSubmitMarkTheater = () => {
    markTheaterStatus.mutate(
      {
        theater_name: markDialogTheater,
        market: selectedMarket,
        status: markDialogAction,
        external_url: markDialogAction === 'not_on_fandango' && markDialogUrl ? markDialogUrl : undefined,
        reason: 'zero_showtimes',
      },
      {
        onSuccess: () => {
          const label = markDialogAction === 'closed' ? 'Permanently Closed' : 'Not on Fandango';
          toast({
            title: 'Theater marked',
            description: `${markDialogTheater} has been marked as ${label}. It will be excluded from future scrapes.`,
          });
          setMarkDialogOpen(false);
        },
        onError: (error) => {
          toast({
            title: 'Error',
            description: `Failed to mark theater: ${error.message}`,
            variant: 'destructive',
          });
        },
      }
    );
  };

  // Show confirmation before starting
  const handleRequestScrape = () => {
    if (selectedTheaters.length === 0) return;
    setShowConfirmDialog(true);
  };

  // Actually start the scrape
  const handleConfirmScrape = async () => {
    setShowConfirmDialog(false);
    if (selectedTheaters.length === 0) return;

    const theaters = allTheatersInDirector
      .filter((t) => selectedTheaters.includes(t.name) && t.url)
      .map((t) => ({ name: t.name, url: t.url ?? '' }));

    console.log('[OperatingHours] Starting scrape:', {
      theaterCount: theaters.length,
      dateRange: `${format(startDate, 'yyyy-MM-dd')} to ${format(endDate, 'yyyy-MM-dd')}`,
      numDays,
    });

    try {
      setScrapeStartTime(Date.now());
      setStep('running');
      console.log('[OperatingHours] API request sent, waiting for response...');

      const result = await fetchOperatingHours.mutateAsync({
        theaters,
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd'),
      });

      console.log('[OperatingHours] Scrape completed:', {
        operatingHoursCount: result.operating_hours?.length,
        duration: result.duration_seconds,
        summary: result.summary,
      });

      setOperatingHours(result.operating_hours);
      setComparison(result.comparison || null);
      setSummary(result.summary);
      setScrapeDuration(result.duration_seconds);
      setExpandedTheaters(new Set(selectedTheaters));
      setStep('results');
    } catch (error) {
      console.error('[OperatingHours] Scrape failed:', error);
      setStep('select-dates');
    }
  };

  const handleReset = () => {
    setStep('select-director');
    setSelectedDirector('');
    setSelectedMarket('');
    setSelectedTheaters([]);
    setStartDate(addDays(new Date(), 1));
    setEndDate(addDays(new Date(), 7));
    setOperatingHours([]);
    setComparison(null);
    setSummary({ changed: 0, no_change: 0, new: 0 });
    setScrapeDuration(0);
    setTimeEstimate(null);
    setShowConfirmDialog(false);
    setExpandedTheaters(new Set());
    setScrapeStartTime(null);
  };

  const handleToggleTheaterExpand = (theater: string) => {
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

  // Expand all theaters in results
  const handleExpandAll = () => {
    setExpandedTheaters(new Set(Object.keys(hoursByTheater)));
  };

  // Collapse all theaters in results
  const handleCollapseAll = () => {
    setExpandedTheaters(new Set());
  };

  // Print operating hours report
  const handlePrint = () => {
    // Create a print-friendly version
    const printContent = document.getElementById('operating-hours-results');
    if (!printContent) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    const theaterCount = Object.keys(hoursByTheater).length;
    const dateEntryCount = operatingHours.length;

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Operating Hours Report - ${selectedDirector}</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
            font-size: 12px;
          }
          h1 { font-size: 18px; margin-bottom: 5px; }
          h2 { font-size: 14px; margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
          .header { margin-bottom: 20px; }
          .meta { color: #666; font-size: 11px; }
          .summary { display: flex; gap: 20px; margin-bottom: 20px; }
          .summary-item { padding: 10px 15px; background: #f5f5f5; border-radius: 4px; }
          .summary-item strong { display: block; font-size: 16px; }
          table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
          th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
          th { background: #f0f0f0; font-weight: 600; }
          tr:nth-child(even) { background: #fafafa; }
          .theater-header { background: #e8e8e8; font-weight: 600; }
          @media print {
            body { padding: 0; }
            .no-print { display: none; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>Operating Hours Report</h1>
          <p class="meta">Director: ${selectedDirector} | Generated: ${format(new Date(), 'PPP p')}</p>
          <p class="meta">Date Range: ${format(startDate, 'PP')} - ${format(endDate, 'PP')}</p>
        </div>
        <div class="summary">
          <div class="summary-item"><strong>${theaterCount}</strong> Theaters</div>
          <div class="summary-item"><strong>${dateEntryCount}</strong> Date Entries</div>
          ${comparison ? `
            <div class="summary-item"><strong>${summary.changed}</strong> Changed</div>
            <div class="summary-item"><strong>${summary.no_change}</strong> No Change</div>
            <div class="summary-item"><strong>${summary.new}</strong> New</div>
          ` : ''}
        </div>
        ${Object.entries(hoursByTheater).map(([theater, hours]) => `
          <h2>${theater}</h2>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Day</th>
                <th>Facility Open</th>
                <th>Facility Close</th>
                <th>First Start</th>
                <th>Last Start</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              ${hours.map((h) => `
                <tr>
                  <td>${h.date}</td>
                  <td>${format(new Date(h.date), 'EEE')}</td>
                  <td>${h.open_time}</td>
                  <td>${h.close_time}</td>
                  <td>${h.first_showtime || '-'}</td>
                  <td>${h.last_showtime || '-'}</td>
                  <td>${h.duration_hours} hrs</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `).join('')}
        <script>
          window.onload = function() { window.print(); }
        </script>
      </body>
      </html>
    `);
    printWindow.document.close();
  };

  // Print summary only (without individual theater details)
  const handlePrintSummary = () => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    const theaterCount = Object.keys(hoursByTheater).length;
    const dateEntryCount = operatingHours.length;

    // Calculate aggregate stats per theater
    const theaterStats = Object.entries(hoursByTheater).map(([theater, hours]) => {
      const avgDuration = hours.reduce((sum, h) => sum + h.duration_hours, 0) / hours.length;
      const minDuration = Math.min(...hours.map(h => h.duration_hours));
      const maxDuration = Math.max(...hours.map(h => h.duration_hours));
      return { theater, avgDuration, minDuration, maxDuration, days: hours.length };
    });

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Operating Hours Summary - ${selectedDirector}</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            max-width: 900px;
            margin: 0 auto;
            font-size: 12px;
          }
          h1 { font-size: 18px; margin-bottom: 5px; }
          .header { margin-bottom: 20px; }
          .meta { color: #666; font-size: 11px; }
          .summary { display: flex; gap: 20px; margin-bottom: 20px; }
          .summary-item { padding: 10px 15px; background: #f5f5f5; border-radius: 4px; }
          .summary-item strong { display: block; font-size: 16px; }
          table { width: 100%; border-collapse: collapse; }
          th, td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; }
          th { background: #f0f0f0; font-weight: 600; }
          tr:nth-child(even) { background: #fafafa; }
          @media print {
            body { padding: 0; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>Operating Hours Summary</h1>
          <p class="meta">Director: ${selectedDirector} | Generated: ${format(new Date(), 'PPP p')}</p>
          <p class="meta">Date Range: ${format(startDate, 'PP')} - ${format(endDate, 'PP')}</p>
        </div>
        <div class="summary">
          <div class="summary-item"><strong>${theaterCount}</strong> Theaters</div>
          <div class="summary-item"><strong>${dateEntryCount}</strong> Date Entries</div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Theater</th>
              <th>Days</th>
              <th>Avg Duration</th>
              <th>Min Duration</th>
              <th>Max Duration</th>
            </tr>
          </thead>
          <tbody>
            ${theaterStats.map((s) => `
              <tr>
                <td>${s.theater}</td>
                <td>${s.days}</td>
                <td>${s.avgDuration.toFixed(1)} hrs</td>
                <td>${s.minDuration} hrs</td>
                <td>${s.maxDuration} hrs</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        <script>
          window.onload = function() { window.print(); }
        </script>
      </body>
      </html>
    `);
    printWindow.document.close();
  };

  // Export to CSV
  const handleExportCsv = () => {
    const headers = ['Theater', 'Date', 'Day', 'Facility Open', 'Facility Close', 'First Start', 'Last Start', 'Duration (hrs)', 'Showtimes'];
    const rows = operatingHours.map((oh) => [
      oh.theater_name,
      oh.date,
      format(new Date(oh.date), 'EEEE'),
      oh.open_time,
      oh.close_time,
      oh.first_showtime || '-',
      oh.last_showtime || '-',
      oh.duration_hours,
      oh.showtime_count,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `operating-hours-${format(startDate, 'yyyy-MM-dd')}-to-${format(endDate, 'yyyy-MM-dd')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (marketsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Calculate selection stats
  const marcusTheatersInDirector = allTheatersInDirector.filter(
    (t) => extractCompany(t.name) === 'Marcus' && isScrapeable(t)
  );
  const allMarcusSelected = marcusTheatersInDirector.length > 0 &&
    marcusTheatersInDirector.every((t) => selectedTheaters.includes(t.name));

  const marcusAndMovieTavernInDirector = allTheatersInDirector.filter(
    (t) => {
      const company = extractCompany(t.name);
      return (company === 'Marcus' || company === 'Movie Tavern') && isScrapeable(t);
    }
  );
  const allMarcusAndMovieTavernSelected = marcusAndMovieTavernInDirector.length > 0 &&
    marcusAndMovieTavernInDirector.every((t) => selectedTheaters.includes(t.name));
  const hasMovieTaverns = allTheatersInDirector.some(
    (t) => extractCompany(t.name) === 'Movie Tavern' && isScrapeable(t)
  );

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
            <Clock className="h-8 w-8" />
            Operating Hours Mode
          </h1>
          <p className="text-muted-foreground">
            Manage and track theater operating hours configurations
          </p>
        </div>
        <div className="flex gap-2">
          <Tabs value={topTab} onValueChange={(v) => setTopTab(v as 'analyze' | 'configure')} className="w-[400px]">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="analyze" className="flex items-center gap-2">
                <RefreshCw className="h-4 w-4" />
                Analyze
              </TabsTrigger>
              <TabsTrigger value="configure" className="flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Configure
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <Button variant="outline" onClick={handleReset}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Start Over
          </Button>
        </div>
      </div>

      {topTab === 'configure' ? (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                Select Theater to Configure
              </CardTitle>
              <CardDescription>
                Choose a theater to manage its daily operating hour settings
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {/* Simplified theater selection for config mode */}
                {Object.keys(groupedTheatersByMarket).map((market) => (
                  <div key={market} className="w-full">
                    <h3 className="text-sm font-semibold mb-2 text-muted-foreground">{market}</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mb-4">
                      {groupedTheatersByMarket[market].map((t) => (
                        <Button
                          key={t.name}
                          variant={configTheater === t.name ? 'toggleActive' : 'toggle'}
                          size="sm"
                          onClick={() => setConfigTheater(t.name)}
                          className="justify-start truncate"
                        >
                          {t.name}
                        </Button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {configTheater && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Clock className="h-5 w-5" />
                      Operating Hours: {configTheater}
                    </CardTitle>
                    <CardDescription>
                      Define standard operating hours and showtime ranges for each day
                    </CardDescription>
                  </div>
                  <Button
                    onClick={handleSaveConfig}
                    disabled={updateConfigMutation.isPending}
                    className="flex items-center gap-2"
                  >
                    {updateConfigMutation.isPending ? (
                      <RefreshCw className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Save Configuration
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="bg-secondary/50">
                        <th className="p-2 text-left border">Day</th>
                        <th className="p-2 text-left border">Facility Open</th>
                        <th className="p-2 text-left border">Facility Close</th>
                        <th className="p-2 text-left border">First Start Time</th>
                        <th className="p-2 text-left border">Last Start Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {daysOfWeek.map((day, index) => {
                        const hours = configHours.find((h) => h.day_of_week === index);
                        return (
                          <tr key={day} className="hover:bg-secondary/20">
                            <td className="p-2 border font-medium">{day}</td>
                            <td className="p-2 border">
                              <input
                                type="text"
                                placeholder="10:00 AM"
                                className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary rounded px-2 py-1"
                                value={hours?.open_time || ''}
                                onChange={(e) =>
                                  handleConfigChange(index, 'open_time', e.target.value)
                                }
                              />
                            </td>
                            <td className="p-2 border">
                              <input
                                type="text"
                                placeholder="11:30 PM"
                                className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary rounded px-2 py-1"
                                value={hours?.close_time || ''}
                                onChange={(e) =>
                                  handleConfigChange(index, 'close_time', e.target.value)
                                }
                              />
                            </td>
                            <td className="p-2 border">
                              <input
                                type="text"
                                placeholder="10:30 AM"
                                className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary rounded px-2 py-1"
                                value={hours?.first_showtime || ''}
                                onChange={(e) =>
                                  handleConfigChange(index, 'first_showtime', e.target.value)
                                }
                              />
                            </td>
                            <td className="p-2 border">
                              <input
                                type="text"
                                placeholder="10:45 PM"
                                className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary rounded px-2 py-1"
                                value={hours?.last_showtime || ''}
                                onChange={(e) =>
                                  handleConfigChange(index, 'last_showtime', e.target.value)
                                }
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        <>

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-sm">
        Operating Hours Mode scrapes all showtimes and calculates when each theater opens and closes.
        Use the Thu-Thu button for weekly reports that compare against the previous week.
      </div>

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
      {selectedDirector && step !== 'select-director' && step !== 'running' && step !== 'results' && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant={allMarcusSelected ? 'toggleActive' : 'toggle'}
            size="sm"
            onClick={handleSelectAllCompanyInDirector}
          >
            {allMarcusSelected ? 'Deselect' : 'Select'} All Marcus in {selectedDirector}
          </Button>
          {hasMovieTaverns && (
            <Button
              variant={allMarcusAndMovieTavernSelected ? 'toggleActive' : 'toggle'}
              size="sm"
              onClick={handleSelectAllMarcusAndMovieTavern}
            >
              {allMarcusAndMovieTavernSelected ? 'Deselect' : 'Select'} All Marcus & Movie Tavern
            </Button>
          )}
          <Button
            variant={allInDirectorSelected ? 'toggleActive' : 'toggle'}
            size="sm"
            onClick={handleSelectAllMarketsInDirector}
          >
            {allInDirectorSelected ? 'Deselect' : 'Select'} All Markets in {selectedDirector}
          </Button>
        </div>
      )}

      {/* Market Selection */}
      {selectedDirector && (step === 'select-market' || step === 'select-theaters' || step === 'select-dates') && (
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
              {marketsInDirector.map((market) => (
                <Button
                  key={market}
                  variant={selectedMarket === market ? 'toggleActive' : 'toggle'}
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => handleMarketSelect(market)}
                >
                  <MapPin className="mr-2 h-4 w-4 flex-shrink-0" />
                  <span className="truncate">{market}</span>
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Theater Selection */}
      {selectedMarket && (step === 'select-theaters' || step === 'select-dates') && (
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
                      isClosed && 'opacity-50 cursor-not-allowed'
                    )}
                    disabled={isClosed || noFandango}
                    onClick={() => handleTheaterToggle(theater.name)}
                  >
                    <span className="truncate">
                      {theater.name}
                      {isClosed && ' (Closed)'}
                      {noFandango && ' (No Fandango)'}
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
              Step 4: Select Date Range
            </CardTitle>
            <CardDescription>
              Choose which dates to fetch operating hours for
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Bulk Selection Notification */}
            {selectedMarketsInfo.isBulkSelection && (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-400 flex-shrink-0" />
                <p className="text-sm text-green-400">
                  <span className="font-medium">{selectedTheaters.length} theaters</span> selected across{' '}
                  <span className="font-medium">
                    {selectedMarketsInfo.marketCount === selectedMarketsInfo.totalMarkets
                      ? `all ${selectedMarketsInfo.marketCount} markets`
                      : `${selectedMarketsInfo.marketCount} markets`}
                  </span>{' '}
                  in {selectedDirector}'s region
                </p>
              </div>
            )}

            {/* Quick Date Range Buttons */}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={handleSetThisWeek}>
                This Week (7 days)
              </Button>
              <Button variant="outline" size="sm" onClick={handleSetThuThu}>
                Next Thu-Thu (Weekly Report)
              </Button>
            </div>

            {/* Date Range Display */}
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <label className="text-sm text-muted-foreground">Start Date</label>
                <input
                  type="date"
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border bg-secondary text-foreground"
                  value={format(startDate, 'yyyy-MM-dd')}
                  onChange={(e) => setStartDate(new Date(e.target.value))}
                />
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground mt-6" />
              <div className="flex-1">
                <label className="text-sm text-muted-foreground">End Date</label>
                <input
                  type="date"
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border bg-secondary text-foreground"
                  value={format(endDate, 'yyyy-MM-dd')}
                  onChange={(e) => setEndDate(new Date(e.target.value))}
                />
              </div>
            </div>

            {/* Summary */}
            <div className="bg-muted/50 rounded-lg p-4">
              <h4 className="font-medium mb-2">Scrape Summary</h4>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Director</p>
                  <p className="font-medium">{selectedDirector}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Markets</p>
                  <p className="font-medium">
                    {selectedMarketsInfo.marketCount === selectedMarketsInfo.totalMarkets
                      ? `All ${selectedMarketsInfo.marketCount} markets`
                      : `${selectedMarketsInfo.marketCount} of ${selectedMarketsInfo.totalMarkets}`}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Theaters</p>
                  <p className="font-medium">{selectedTheaters.length}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Days</p>
                  <p className="font-medium">{numDays}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Est. Time</p>
                  <p className="font-medium">
                    {timeEstimate?.hasData
                      ? timeEstimate.formatted
                      : estimateTime.isPending
                      ? 'Calculating...'
                      : 'N/A'}
                  </p>
                </div>
              </div>
              {/* Show selected markets */}
              {selectedMarketsInfo.marketCount > 0 && selectedMarketsInfo.marketCount <= 6 && (
                <div className="mt-3 pt-3 border-t border-border/50">
                  <p className="text-xs text-muted-foreground mb-1">Markets included:</p>
                  <div className="flex flex-wrap gap-1">
                    {selectedMarketsInfo.markets.map((market) => (
                      <Badge key={market} variant="secondary" className="text-xs">
                        {market}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep('select-theaters')}>
                Back
              </Button>
              <Button
                onClick={handleRequestScrape}
                disabled={selectedTheaters.length === 0 || fetchOperatingHours.isPending}
              >
                <Play className="mr-2 h-4 w-4" />
                Fetch Operating Hours
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Running State */}
      {step === 'running' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5 animate-spin" />
              Fetching Operating Hours
            </CardTitle>
            <CardDescription>
              Scraping showtimes from {selectedTheaters.length} theaters across{' '}
              {selectedMarketsInfo.marketCount} market{selectedMarketsInfo.marketCount !== 1 ? 's' : ''} for {numDays} days...
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Indeterminate progress bar */}
            <div className="h-3 bg-muted rounded-full overflow-hidden">
              <div className="h-full w-1/3 bg-primary rounded-full animate-progress-indeterminate" />
            </div>

            {/* Progress details */}
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-blue-400">{selectedTheaters.length}</p>
                <p className="text-muted-foreground">Theaters</p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-blue-400">{selectedMarketsInfo.marketCount}</p>
                <p className="text-muted-foreground">Markets</p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-blue-400">{numDays}</p>
                <p className="text-muted-foreground">Days</p>
              </div>
            </div>

            <p className="text-sm text-muted-foreground">
              Collecting showtimes and calculating operating hours. This includes amenity discovery for screen counts and PLF detection.
            </p>

            {/* Elapsed time display */}
            <div className="flex items-center justify-between pt-2 border-t text-sm">
              <div className="flex items-center gap-2">
                <Timer className="h-4 w-4 text-muted-foreground" />
                <span>Elapsed: <strong>{formatDuration(elapsedSeconds)}</strong></span>
              </div>
              {timeEstimate?.hasData && timeEstimate.seconds > 0 && elapsedSeconds < timeEstimate.seconds && (
                <div className="text-right text-muted-foreground">
                  Est. remaining: ~{formatDuration(Math.max(0, timeEstimate.seconds - elapsedSeconds))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {step === 'results' && (
        <div className="space-y-6">
          {/* Success Message */}
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
            <p className="text-green-400 font-medium flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Operating Hours Retrieved! (Took {scrapeDuration.toFixed(2)} seconds)
            </p>
          </div>

          {/* Summary Stats */}
          <Card>
            <CardHeader>
              <CardTitle>Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Building2 className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">{Object.keys(hoursByTheater).length}</p>
                  <p className="text-sm text-muted-foreground">Theaters</p>
                </div>
                <div className="bg-muted/50 rounded-lg p-4 text-center">
                  <Calendar className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-2xl font-bold">{operatingHours.length}</p>
                  <p className="text-sm text-muted-foreground">Date Entries</p>
                </div>
                {comparison && (
                  <>
                    <div className="bg-blue-500/10 rounded-lg p-4 text-center">
                      <AlertCircle className="h-6 w-6 mx-auto mb-2 text-blue-400" />
                      <p className="text-2xl font-bold text-blue-400">{summary.changed}</p>
                      <p className="text-sm text-muted-foreground">Changed</p>
                    </div>
                    <div className="bg-green-500/10 rounded-lg p-4 text-center">
                      <CheckCircle2 className="h-6 w-6 mx-auto mb-2 text-green-400" />
                      <p className="text-2xl font-bold text-green-400">{summary.no_change}</p>
                      <p className="text-sm text-muted-foreground">No Change</p>
                    </div>
                    <div className="bg-yellow-500/10 rounded-lg p-4 text-center">
                      <Clock className="h-6 w-6 mx-auto mb-2 text-yellow-400" />
                      <p className="text-2xl font-bold text-yellow-400">{summary.new}</p>
                      <p className="text-sm text-muted-foreground">New</p>
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Zero Showtime Warning */}
          {zeroShowtimeTheaters.length > 0 && (
            <Card className="border-orange-300 bg-orange-50 dark:bg-orange-950/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-orange-500" />
                  Theaters with 0 Showtimes ({zeroShowtimeTheaters.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {zeroShowtimeTheaters.map(theater => (
                    <div key={theater} className="flex items-center justify-between text-sm">
                      <span>{theater}</span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openMarkDialog(theater)}
                      >
                        Update Status
                      </Button>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-3">
                  These theaters returned 0 showtimes for all scraped dates. They may have moved to their own ticketing sites
                  or permanently closed. Click "Update Status" to mark them.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Export & Print Actions */}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={handleExportCsv}>
              <Download className="mr-2 h-4 w-4" />
              Export CSV
            </Button>
            <Button variant="outline" onClick={handlePrint}>
              <Printer className="mr-2 h-4 w-4" />
              Print Full Report
            </Button>
            <Button variant="outline" onClick={handlePrintSummary}>
              <Printer className="mr-2 h-4 w-4" />
              Print Summary
            </Button>
          </div>

          {/* Results Tabs */}
          <Card id="operating-hours-results">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle>Operating Hours Details</CardTitle>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleExpandAll}>
                  <Maximize2 className="mr-1 h-3 w-3" />
                  Expand All
                </Button>
                <Button variant="outline" size="sm" onClick={handleCollapseAll}>
                  <Minimize2 className="mr-1 h-3 w-3" />
                  Collapse All
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="by-theater">
                <TabsList>
                  <TabsTrigger value="by-theater">By Theater</TabsTrigger>
                  {comparison && <TabsTrigger value="comparison">Week Comparison</TabsTrigger>}
                </TabsList>

                <TabsContent value="by-theater" className="mt-4">
                  <div className="space-y-2">
                    {Object.entries(hoursByTheater).map(([theater, hours]) => {
                      const isExpanded = expandedTheaters.has(theater);
                      const avgDuration = hours.reduce((sum, h) => sum + h.duration_hours, 0) / hours.length;

                      return (
                        <div key={theater} className="border rounded-lg">
                          <button
                            className="w-full p-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
                            onClick={() => handleToggleTheaterExpand(theater)}
                          >
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronRight className="h-4 w-4" />
                              )}
                              <span className="font-medium">{theater}</span>
                              <Badge variant="secondary">{hours.length} days</Badge>
                            </div>
                            <span className="text-sm text-muted-foreground">
                              Avg: {avgDuration.toFixed(1)} hrs/day
                            </span>
                          </button>

                          {isExpanded && (
                            <div className="px-4 pb-3 border-t">
                              <div className="grid grid-cols-7 gap-2 text-sm font-medium text-muted-foreground py-2 border-b">
                                <div>Date</div>
                                <div>Day</div>
                                <div>Facility Open</div>
                                <div>Facility Close</div>
                                <div>First Start</div>
                                <div>Last Start</div>
                                <div className="text-right">Duration</div>
                              </div>
                              {hours.map((h) => (
                                <div
                                  key={`${h.theater_name}-${h.date}`}
                                  className="grid grid-cols-7 gap-2 text-sm py-2 border-b last:border-b-0"
                                >
                                  <div>{h.date}</div>
                                  <div>{format(new Date(h.date), 'EEE')}</div>
                                  <div>{h.open_time}</div>
                                  <div>{h.close_time}</div>
                                  <div>{h.first_showtime || '-'}</div>
                                  <div>{h.last_showtime || '-'}</div>
                                  <div className="text-right">{h.duration_hours} hrs</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </TabsContent>

                {comparison && (
                  <TabsContent value="comparison" className="mt-4">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-2">Theater</th>
                            <th className="text-left py-2 px-2">Day</th>
                            <th className="text-left py-2 px-2">Prev Week</th>
                            <th className="text-left py-2 px-2">Current Week</th>
                            <th className="text-left py-2 px-2">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparison.map((c, i) => (
                            <tr
                              key={i}
                              className={cn(
                                'border-b',
                                c.status === 'changed' && 'bg-blue-500/10',
                                c.status === 'new' && 'bg-yellow-500/10',
                                c.status === 'no_change' && 'bg-green-500/5'
                              )}
                            >
                              <td className="py-2 px-2 font-medium">{c.theater_name}</td>
                              <td className="py-2 px-2">{c.day_of_week}</td>
                              <td className="py-2 px-2">
                                {c.prev_open ? (
                                  <span>{c.prev_open} - {c.prev_close}</span>
                                ) : (
                                  <span className="text-muted-foreground">N/A</span>
                                )}
                              </td>
                              <td className="py-2 px-2">
                                {c.curr_open} - {c.curr_close}
                              </td>
                              <td className="py-2 px-2">
                                <Badge
                                  variant={
                                    c.status === 'changed'
                                      ? 'default'
                                      : c.status === 'new'
                                      ? 'secondary'
                                      : 'outline'
                                  }
                                  className={cn(
                                    c.status === 'changed' && 'bg-blue-500',
                                    c.status === 'new' && 'bg-yellow-500 text-black'
                                  )}
                                >
                                  {c.status === 'changed' && 'Changed'}
                                  {c.status === 'new' && 'New'}
                                  {c.status === 'no_change' && 'No Change'}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </TabsContent>
                )}
              </Tabs>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle>Confirm Operating Hours Fetch</CardTitle>
              <CardDescription>
                You are about to fetch operating hours for {selectedTheaters.length} theaters across{' '}
                {selectedMarketsInfo.marketCount} market{selectedMarketsInfo.marketCount !== 1 ? 's' : ''}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-muted/50 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Director</p>
                    <p className="font-medium">{selectedDirector}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Markets</p>
                    <p className="font-medium">
                      {selectedMarketsInfo.marketCount === selectedMarketsInfo.totalMarkets
                        ? `All ${selectedMarketsInfo.marketCount}`
                        : `${selectedMarketsInfo.marketCount} of ${selectedMarketsInfo.totalMarkets}`}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Theaters</p>
                    <p className="font-medium">{selectedTheaters.length}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Days</p>
                    <p className="font-medium">{numDays}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Date Range</p>
                    <p className="font-medium">
                      {format(startDate, 'MMM d')} - {format(endDate, 'MMM d')}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Est. Time</p>
                    <p className="font-medium">
                      {timeEstimate?.hasData ? timeEstimate.formatted : 'Unknown'}
                    </p>
                  </div>
                </div>
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
                  Start Fetch
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
        </>
      )}

      {/* Mark Theater Status Dialog */}
      <Dialog open={markDialogOpen} onOpenChange={setMarkDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Update Theater Status</DialogTitle>
            <DialogDescription>
              {markDialogTheater} returned 0 showtimes. Choose how to mark it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {/* Action selection */}
            <div className="space-y-2">
              <Button
                variant={markDialogAction === 'not_on_fandango' ? 'default' : 'outline'}
                className="w-full justify-start"
                onClick={() => setMarkDialogAction('not_on_fandango')}
              >
                Not on Fandango — Theater uses its own ticketing site
              </Button>
              <Button
                variant={markDialogAction === 'closed' ? 'default' : 'outline'}
                className="w-full justify-start"
                onClick={() => setMarkDialogAction('closed')}
              >
                Permanently Closed — Theater is no longer operating
              </Button>
            </div>

            {/* URL input for not_on_fandango */}
            {markDialogAction === 'not_on_fandango' && (
              <div className="space-y-1">
                <label className="text-sm font-medium">Theater's own website (optional)</label>
                <Input
                  placeholder="https://www.example.com/showtimes"
                  value={markDialogUrl}
                  onChange={(e) => setMarkDialogUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  If you know the theater's direct ticketing URL, paste it here. The theater button in Market Mode will open this URL.
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMarkDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmitMarkTheater}
              disabled={markTheaterStatus.isPending}
            >
              {markTheaterStatus.isPending ? 'Saving...' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
