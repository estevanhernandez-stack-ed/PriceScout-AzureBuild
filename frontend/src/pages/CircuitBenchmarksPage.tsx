import { useState, useMemo, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
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
  BarChart3,
  Building2,
  RefreshCw,
  Download,
  Calendar,
  Clock,
  Film,
  Percent,
  TrendingUp,
  TrendingDown,
  Minus,
  Trophy,
  Sun,
  Moon,
  Sunset,
  FileText,
  Play,
  Pause,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import {
  useCircuitBenchmarks,
  useCircuitBenchmarkWeeks,
  useSyncCircuitBenchmarks,
  useTaskStatus,
} from '@/hooks/api';
import { format, parseISO, subDays } from 'date-fns';
import { cn } from '@/lib/utils';

interface CircuitBenchmark {
  benchmark_id: number;
  circuit_name: string;
  week_ending_date: string;
  period_start_date?: string;
  total_showtimes: number;
  total_capacity: number;
  total_theaters: number;
  total_films: number;
  avg_screens_per_film: number;
  avg_showtimes_per_theater: number;
  format_standard_pct: number;
  format_imax_pct: number;
  format_dolby_pct: number;
  format_3d_pct: number;
  format_other_premium_pct: number;
  plf_total_pct: number;
  daypart_matinee_pct: number;
  daypart_evening_pct: number;
  daypart_late_pct: number;
  avg_price_general?: number;
  avg_price_child?: number;
  avg_price_senior?: number;
}

// Check if circuit is Marcus or Marcus brand
const isMarcusCircuit = (name: string) => {
  const lower = name.toLowerCase();
  return lower.includes('marcus') || lower.includes('movie tavern') || lower.includes('spotlight');
};

// Format week date range
const formatWeekRange = (weekEndingDate: string, periodStartDate?: string) => {
  try {
    const endDate = parseISO(weekEndingDate);
    const startDate = periodStartDate ? parseISO(periodStartDate) : subDays(endDate, 6);
    return `${format(startDate, 'M/d')} - ${format(endDate, 'M/d')}`;
  } catch {
    return weekEndingDate;
  }
};

// Get trend indicator
const getTrendIndicator = (value: number, average: number) => {
  const diff = value - average;
  if (diff > 1) return { icon: TrendingUp, color: 'text-green-500', label: `+${diff.toFixed(1)}%` };
  if (diff < -1) return { icon: TrendingDown, color: 'text-red-500', label: `${diff.toFixed(1)}%` };
  return { icon: Minus, color: 'text-muted-foreground', label: '—' };
};

export function CircuitBenchmarksPage() {
  const [selectedWeek, setSelectedWeek] = useState<string>('');
  const [activeTab, setActiveTab] = useState('circuits');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(300000); // 5 minutes
  const [lastRefreshTime, setLastRefreshTime] = useState<Date | null>(null);
  const [activeSyncTaskId, setActiveSyncTaskId] = useState<string | null>(null);

  const { data: weeksData, isLoading: weeksLoading } = useCircuitBenchmarkWeeks();
  const {
    data: benchmarksData,
    isLoading: benchmarksLoading,
    refetch,
  } = useCircuitBenchmarks({
    week_ending_date: selectedWeek || undefined,
    limit: 100,
  });
  const syncMutation = useSyncCircuitBenchmarks();
  const { data: activeTaskStatus } = useTaskStatus(activeSyncTaskId);

  // Set initial week when weeks are loaded
  useEffect(() => {
    if (weeksData && weeksData.length > 0 && !selectedWeek) {
      setSelectedWeek(weeksData[0].week_ending_date);
    }
  }, [weeksData, selectedWeek]);

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      refetch();
      setLastRefreshTime(new Date());
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, refetch]);

  // Manual refresh handler
  const handleManualRefresh = useCallback(() => {
    refetch();
    setLastRefreshTime(new Date());
  }, [refetch]);

  const isLoading = weeksLoading || benchmarksLoading;
  const benchmarks: CircuitBenchmark[] = benchmarksData?.benchmarks || [];

  // Sort benchmarks by total showtimes (largest first)
  const sortedBenchmarks = useMemo(() => {
    return [...benchmarks].sort((a, b) => b.total_showtimes - a.total_showtimes);
  }, [benchmarks]);

  // Sort by PLF for ranking
  const plfRankedBenchmarks = useMemo(() => {
    return [...benchmarks].sort((a, b) => b.plf_total_pct - a.plf_total_pct);
  }, [benchmarks]);

  // Calculate summary statistics
  const summaryStats = useMemo(() => {
    if (!benchmarks.length) {
      return {
        totalCircuits: 0,
        totalTheaters: 0,
        totalShowtimes: 0,
        avgPlfPercent: 0,
        avgShowtimesPerTheater: 0,
      };
    }

    const totalTheaters = benchmarks.reduce((sum, b) => sum + b.total_theaters, 0);
    const totalShowtimes = benchmarks.reduce((sum, b) => sum + b.total_showtimes, 0);
    const avgPlf = benchmarks.reduce((sum, b) => sum + b.plf_total_pct, 0) / benchmarks.length;
    const avgShowtimes = benchmarks.reduce((sum, b) => sum + b.avg_showtimes_per_theater, 0) / benchmarks.length;

    return {
      totalCircuits: benchmarks.length,
      totalTheaters,
      totalShowtimes,
      avgPlfPercent: avgPlf,
      avgShowtimesPerTheater: avgShowtimes,
    };
  }, [benchmarks]);

  // Find Marcus benchmark for comparison
  const marcusBenchmark = useMemo(() => {
    return benchmarks.find(b => b.circuit_name.toLowerCase().includes('marcus') && !b.circuit_name.toLowerCase().includes('movie tavern'));
  }, [benchmarks]);

  // Calculate industry averages (excluding Marcus brands for fairer comparison)
  const industryAverages = useMemo(() => {
    const nonMarcus = benchmarks.filter(b => !isMarcusCircuit(b.circuit_name));
    if (!nonMarcus.length) return null;

    return {
      plf_total_pct: nonMarcus.reduce((sum, b) => sum + b.plf_total_pct, 0) / nonMarcus.length,
      format_imax_pct: nonMarcus.reduce((sum, b) => sum + b.format_imax_pct, 0) / nonMarcus.length,
      format_dolby_pct: nonMarcus.reduce((sum, b) => sum + b.format_dolby_pct, 0) / nonMarcus.length,
      avg_showtimes_per_theater: nonMarcus.reduce((sum, b) => sum + b.avg_showtimes_per_theater, 0) / nonMarcus.length,
      daypart_matinee_pct: nonMarcus.reduce((sum, b) => sum + b.daypart_matinee_pct, 0) / nonMarcus.length,
      daypart_evening_pct: nonMarcus.reduce((sum, b) => sum + b.daypart_evening_pct, 0) / nonMarcus.length,
      daypart_late_pct: nonMarcus.reduce((sum, b) => sum + b.daypart_late_pct, 0) / nonMarcus.length,
    };
  }, [benchmarks]);

  const handleSync = async () => {
    try {
      const response = await syncMutation.mutateAsync();
      if (response.task_id) {
        setActiveSyncTaskId(response.task_id);
      }
      refetch();
    } catch (error) {
      console.error('Sync failed:', error);
    }
  };

  const handleExport = () => {
    if (!benchmarks.length) return;

    const headers = ['Circuit', 'Theaters', 'Showtimes', 'Films', 'PLF %', 'IMAX %', 'Dolby %', '3D %', 'Other PLF %', 'Shows/Theater', 'Matinee %', 'Evening %', 'Late %'];
    const rows = sortedBenchmarks.map((b) => [
      b.circuit_name,
      b.total_theaters,
      b.total_showtimes,
      b.total_films,
      b.plf_total_pct.toFixed(1),
      b.format_imax_pct.toFixed(1),
      b.format_dolby_pct.toFixed(1),
      b.format_3d_pct.toFixed(1),
      b.format_other_premium_pct.toFixed(1),
      b.avg_showtimes_per_theater.toFixed(1),
      b.daypart_matinee_pct.toFixed(1),
      b.daypart_evening_pct.toFixed(1),
      b.daypart_late_pct.toFixed(1),
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `circuit-benchmarks-${selectedWeek || 'all'}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  // PDF Export via print-ready HTML
  const handleExportPDF = () => {
    if (!benchmarks.length) return;

    // Get period_start_date from first benchmark if available
    const firstBenchmark = benchmarks[0];
    const weekLabel = selectedWeek
      ? formatWeekRange(selectedWeek, firstBenchmark?.period_start_date)
      : 'All Time';

    const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <title>Circuit Benchmarks Report - ${weekLabel}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; color: #333; }
    h1 { color: #8b0e04; border-bottom: 2px solid #8b0e04; padding-bottom: 10px; }
    h2 { color: #666; margin-top: 30px; }
    .summary { display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 30px; }
    .summary-card { background: #f5f5f5; padding: 15px; border-radius: 8px; text-align: center; }
    .summary-card .label { font-size: 12px; color: #666; }
    .summary-card .value { font-size: 24px; font-weight: bold; color: #8b0e04; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
    th { background: #8b0e04; color: white; }
    tr:nth-child(even) { background: #f9f9f9; }
    .marcus { background: #fef3c7 !important; }
    .marcus td:first-child { color: #854d0e; font-weight: bold; }
    .bar-container { display: flex; height: 20px; border-radius: 4px; overflow: hidden; }
    .bar-segment { display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; }
    .timestamp { color: #999; font-size: 12px; margin-top: 30px; text-align: center; }
    @media print { body { margin: 0; } }
  </style>
</head>
<body>
  <h1>Circuit Benchmarks Report</h1>
  <p>Week: ${weekLabel} | Generated: ${new Date().toLocaleString()}</p>

  <div class="summary">
    <div class="summary-card">
      <div class="label">Circuits</div>
      <div class="value">${summaryStats.totalCircuits}</div>
    </div>
    <div class="summary-card">
      <div class="label">Total Theaters</div>
      <div class="value">${summaryStats.totalTheaters.toLocaleString()}</div>
    </div>
    <div class="summary-card">
      <div class="label">Total Showtimes</div>
      <div class="value">${summaryStats.totalShowtimes.toLocaleString()}</div>
    </div>
    <div class="summary-card">
      <div class="label">Avg PLF %</div>
      <div class="value">${summaryStats.avgPlfPercent.toFixed(1)}%</div>
    </div>
    <div class="summary-card">
      <div class="label">Shows/Theater</div>
      <div class="value">${summaryStats.avgShowtimesPerTheater.toFixed(1)}</div>
    </div>
  </div>

  <h2>Circuit Performance</h2>
  <table>
    <thead>
      <tr>
        <th>Rank</th>
        <th>Circuit</th>
        <th>Theaters</th>
        <th>Showtimes</th>
        <th>Films</th>
        <th>PLF %</th>
        <th>Shows/Theater</th>
      </tr>
    </thead>
    <tbody>
      ${sortedBenchmarks.map((b, idx) => `
        <tr class="${isMarcusCircuit(b.circuit_name) ? 'marcus' : ''}">
          <td>${idx + 1}</td>
          <td>${b.circuit_name}</td>
          <td>${b.total_theaters}</td>
          <td>${b.total_showtimes.toLocaleString()}</td>
          <td>${b.total_films}</td>
          <td>${b.plf_total_pct.toFixed(1)}%</td>
          <td>${b.avg_showtimes_per_theater.toFixed(1)}</td>
        </tr>
      `).join('')}
    </tbody>
  </table>

  <h2>Format Distribution</h2>
  <table>
    <thead>
      <tr>
        <th>Circuit</th>
        <th>Standard</th>
        <th>IMAX</th>
        <th>Dolby</th>
        <th>3D</th>
        <th>Other PLF</th>
        <th>Total PLF</th>
      </tr>
    </thead>
    <tbody>
      ${sortedBenchmarks.map(b => `
        <tr class="${isMarcusCircuit(b.circuit_name) ? 'marcus' : ''}">
          <td>${b.circuit_name}</td>
          <td>${b.format_standard_pct.toFixed(1)}%</td>
          <td>${b.format_imax_pct.toFixed(1)}%</td>
          <td>${b.format_dolby_pct.toFixed(1)}%</td>
          <td>${b.format_3d_pct.toFixed(1)}%</td>
          <td>${b.format_other_premium_pct.toFixed(1)}%</td>
          <td><strong>${b.plf_total_pct.toFixed(1)}%</strong></td>
        </tr>
      `).join('')}
    </tbody>
  </table>

  <h2>Daypart Strategy</h2>
  <table>
    <thead>
      <tr>
        <th>Circuit</th>
        <th>Matinee (&lt;5 PM)</th>
        <th>Evening (5-9 PM)</th>
        <th>Late (&gt;9 PM)</th>
      </tr>
    </thead>
    <tbody>
      ${sortedBenchmarks.map(b => `
        <tr class="${isMarcusCircuit(b.circuit_name) ? 'marcus' : ''}">
          <td>${b.circuit_name}</td>
          <td>${b.daypart_matinee_pct.toFixed(1)}%</td>
          <td>${b.daypart_evening_pct.toFixed(1)}%</td>
          <td>${b.daypart_late_pct.toFixed(1)}%</td>
        </tr>
      `).join('')}
    </tbody>
  </table>

  <div class="timestamp">
    Report generated by PriceScout | ${new Date().toISOString()}
  </div>
</body>
</html>
    `;

    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(htmlContent);
      printWindow.document.close();
      printWindow.print();
    }
  };

  if (isLoading && !benchmarks.length) {
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
          <h1 className="text-3xl font-bold tracking-tight">Circuit Benchmarks</h1>
          <p className="text-muted-foreground">
            Compare performance across major theater circuits (from EntTelligence)
            {lastRefreshTime && (
              <span className="ml-2 text-xs">
                Last updated: {lastRefreshTime.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Auto-refresh controls */}
          <div className="flex items-center gap-2 border rounded-lg px-3 py-2 bg-muted/30">
            <Switch
              id="auto-refresh"
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
            <Label htmlFor="auto-refresh" className="text-sm cursor-pointer">
              {autoRefresh ? <Play className="h-3 w-3 inline mr-1" /> : <Pause className="h-3 w-3 inline mr-1" />}
              Auto
            </Label>
            {autoRefresh && (
              <Select
                value={String(refreshInterval)}
                onValueChange={(v) => setRefreshInterval(Number(v))}
              >
                <SelectTrigger className="w-20 h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="60000">1 min</SelectItem>
                  <SelectItem value="300000">5 min</SelectItem>
                  <SelectItem value="600000">10 min</SelectItem>
                  <SelectItem value="1800000">30 min</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>
          <Select value={selectedWeek} onValueChange={setSelectedWeek}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Select week" />
            </SelectTrigger>
            <SelectContent>
              {weeksData?.map((week) => (
                <SelectItem key={week.week_ending_date} value={week.week_ending_date}>
                  {formatWeekRange(week.week_ending_date, week.period_start_date)} ({week.circuit_count} circuits)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={handleSync}
            disabled={syncMutation.isPending || !!activeSyncTaskId}
          >
            {syncMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Triggering...
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-4 w-4" />
                Sync
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={handleManualRefresh}
            size="icon"
            title="Refresh data"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button variant="outline" onClick={handleExport} disabled={!benchmarks.length}>
            <Download className="mr-2 h-4 w-4" />
            CSV
          </Button>
          <Button variant="outline" onClick={handleExportPDF} disabled={!benchmarks.length}>
            <FileText className="mr-2 h-4 w-4" />
            PDF
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Circuits</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.totalCircuits}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Theaters</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.totalTheaters.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Showtimes</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.totalShowtimes.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Percent className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Avg PLF %</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.avgPlfPercent.toFixed(1)}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Film className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Shows/Theater</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.avgShowtimesPerTheater.toFixed(1)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Task Monitoring Card */}
      {activeSyncTaskId && activeTaskStatus && (
        <Card className="border-primary/20 shadow-md animate-in fade-in slide-in-from-top-2 overflow-hidden">
          <div className="bg-primary/[0.03] px-4 py-2 border-b border-primary/10 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
              <Activity className="h-3.5 w-3.5" />
              Sync Task Monitoring
            </div>
            <Badge variant={activeTaskStatus.ready ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0 h-4">
              {activeTaskStatus.status}
            </Badge>
          </div>
          <CardContent className="p-4 pt-3">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-[10px] text-muted-foreground font-mono truncate">ID: {activeSyncTaskId}</span>
                  {!activeTaskStatus.ready && (
                    <span className="text-xs font-medium animate-pulse text-primary mt-1">Background sync in progress...</span>
                  )}
                </div>
                {activeTaskStatus.ready && (
                  <Button variant="ghost" size="sm" className="h-7 text-[10px] font-bold uppercase" onClick={() => setActiveSyncTaskId(null)}>
                    Dismiss
                  </Button>
                )}
              </div>

              {!activeTaskStatus.ready && (
                <Progress value={undefined} className="h-1.5" />
              )}

              {activeTaskStatus.ready && activeTaskStatus.result && (
                <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/10 text-xs text-green-700 dark:text-green-400 flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-bold">Sync Completed</p>
                    <p className="mt-0.5 opacity-90">{activeTaskStatus.result.message || 'Data successfully updated from EntTelligence.'}</p>
                  </div>
                </div>
              )}

              {activeTaskStatus.ready && activeTaskStatus.error && (
                <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/10 text-xs text-red-700 dark:text-red-400 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-bold">Sync Failed</p>
                    <p className="mt-0.5 opacity-90">{activeTaskStatus.error}</p>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Marcus vs Industry Comparison */}
      {marcusBenchmark && industryAverages && (
        <Card className="border-yellow-500/30 bg-yellow-500/5">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Trophy className="h-5 w-5 text-yellow-500" />
              Marcus vs Industry Average
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-6">
              <div>
                <p className="text-sm text-muted-foreground">PLF Mix</p>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{marcusBenchmark.plf_total_pct.toFixed(1)}%</span>
                  {(() => {
                    const trend = getTrendIndicator(marcusBenchmark.plf_total_pct, industryAverages.plf_total_pct);
                    return (
                      <span className={cn('text-sm flex items-center gap-1', trend.color)}>
                        <trend.icon className="h-4 w-4" />
                        {trend.label}
                      </span>
                    );
                  })()}
                </div>
                <p className="text-xs text-muted-foreground">vs {industryAverages.plf_total_pct.toFixed(1)}% avg</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">IMAX</p>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{marcusBenchmark.format_imax_pct.toFixed(1)}%</span>
                  {(() => {
                    const trend = getTrendIndicator(marcusBenchmark.format_imax_pct, industryAverages.format_imax_pct);
                    return (
                      <span className={cn('text-sm flex items-center gap-1', trend.color)}>
                        <trend.icon className="h-4 w-4" />
                        {trend.label}
                      </span>
                    );
                  })()}
                </div>
                <p className="text-xs text-muted-foreground">vs {industryAverages.format_imax_pct.toFixed(1)}% avg</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Dolby</p>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{marcusBenchmark.format_dolby_pct.toFixed(1)}%</span>
                  {(() => {
                    const trend = getTrendIndicator(marcusBenchmark.format_dolby_pct, industryAverages.format_dolby_pct);
                    return (
                      <span className={cn('text-sm flex items-center gap-1', trend.color)}>
                        <trend.icon className="h-4 w-4" />
                        {trend.label}
                      </span>
                    );
                  })()}
                </div>
                <p className="text-xs text-muted-foreground">vs {industryAverages.format_dolby_pct.toFixed(1)}% avg</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Shows/Theater</p>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{marcusBenchmark.avg_showtimes_per_theater.toFixed(1)}</span>
                  {(() => {
                    const trend = getTrendIndicator(marcusBenchmark.avg_showtimes_per_theater, industryAverages.avg_showtimes_per_theater);
                    return (
                      <span className={cn('text-sm flex items-center gap-1', trend.color)}>
                        <trend.icon className="h-4 w-4" />
                        {trend.label}
                      </span>
                    );
                  })()}
                </div>
                <p className="text-xs text-muted-foreground">vs {industryAverages.avg_showtimes_per_theater.toFixed(1)} avg</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="circuits">By Circuit</TabsTrigger>
          <TabsTrigger value="formats">Format Mix</TabsTrigger>
          <TabsTrigger value="dayparts">Daypart Strategy</TabsTrigger>
          <TabsTrigger value="plf">PLF Ranking</TabsTrigger>
          <TabsTrigger value="weeks">Week History</TabsTrigger>
        </TabsList>

        {/* By Circuit Tab */}
        <TabsContent value="circuits">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Circuit Comparison
              </CardTitle>
              <CardDescription>
                Performance metrics by theater circuit (sorted by volume)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sortedBenchmarks.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No benchmark data available. Try syncing from EntTelligence.
                </p>
              ) : (
                <div className="space-y-3">
                  {sortedBenchmarks.map((benchmark, idx) => {
                    const isMarcus = isMarcusCircuit(benchmark.circuit_name);
                    return (
                      <div
                        key={benchmark.benchmark_id}
                        className={cn(
                          'flex items-center justify-between p-4 border rounded-lg transition-colors',
                          isMarcus
                            ? 'border-yellow-500/50 bg-yellow-500/10 hover:bg-yellow-500/20'
                            : 'hover:bg-muted/50'
                        )}
                      >
                        <div className="flex items-center gap-4">
                          <span className="text-muted-foreground w-6 text-right">{idx + 1}</span>
                          <div className="w-48">
                            <span className={cn('font-medium', isMarcus && 'text-yellow-600')}>
                              {benchmark.circuit_name}
                            </span>
                          </div>
                          <Badge variant="secondary">{benchmark.total_theaters} theaters</Badge>
                          <Badge variant="outline">{benchmark.total_films} films</Badge>
                        </div>
                        <div className="flex items-center gap-8">
                          <div className="text-right">
                            <p className="text-sm text-muted-foreground">Showtimes</p>
                            <p className="font-medium">{benchmark.total_showtimes.toLocaleString()}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm text-muted-foreground">PLF Mix</p>
                            <p className="font-medium">{benchmark.plf_total_pct.toFixed(1)}%</p>
                          </div>
                          <div className="text-right w-28">
                            <p className="text-sm text-muted-foreground">Shows/Theater</p>
                            <p className="text-xl font-bold">{benchmark.avg_showtimes_per_theater.toFixed(1)}</p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Format Mix Tab */}
        <TabsContent value="formats">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Film className="h-5 w-5" />
                Format Distribution
              </CardTitle>
              <CardDescription>
                Premium format breakdown by circuit (visual bars)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sortedBenchmarks.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No benchmark data available.
                </p>
              ) : (
                <div className="space-y-4">
                  {sortedBenchmarks.map((benchmark) => {
                    const isMarcus = isMarcusCircuit(benchmark.circuit_name);
                    return (
                      <div
                        key={benchmark.benchmark_id}
                        className={cn(
                          'p-4 border rounded-lg',
                          isMarcus && 'border-yellow-500/50 bg-yellow-500/5'
                        )}
                      >
                        <div className="flex items-center justify-between mb-3">
                          <h4 className={cn('font-medium', isMarcus && 'text-yellow-600')}>
                            {benchmark.circuit_name}
                          </h4>
                          <Badge variant="outline">
                            PLF: {benchmark.plf_total_pct.toFixed(1)}%
                          </Badge>
                        </div>

                        {/* Stacked bar visualization */}
                        <div className="h-8 rounded-lg overflow-hidden flex">
                          <div
                            className="bg-gray-400 flex items-center justify-center text-xs text-white"
                            style={{ width: `${benchmark.format_standard_pct}%` }}
                            title={`Standard: ${benchmark.format_standard_pct.toFixed(1)}%`}
                          >
                            {benchmark.format_standard_pct > 10 && `${benchmark.format_standard_pct.toFixed(0)}%`}
                          </div>
                          <div
                            className="bg-blue-500 flex items-center justify-center text-xs text-white"
                            style={{ width: `${benchmark.format_imax_pct}%` }}
                            title={`IMAX: ${benchmark.format_imax_pct.toFixed(1)}%`}
                          >
                            {benchmark.format_imax_pct > 3 && 'IMAX'}
                          </div>
                          <div
                            className="bg-purple-500 flex items-center justify-center text-xs text-white"
                            style={{ width: `${benchmark.format_dolby_pct}%` }}
                            title={`Dolby: ${benchmark.format_dolby_pct.toFixed(1)}%`}
                          >
                            {benchmark.format_dolby_pct > 3 && 'Dolby'}
                          </div>
                          <div
                            className="bg-green-500 flex items-center justify-center text-xs text-white"
                            style={{ width: `${benchmark.format_3d_pct}%` }}
                            title={`3D: ${benchmark.format_3d_pct.toFixed(1)}%`}
                          >
                            {benchmark.format_3d_pct > 3 && '3D'}
                          </div>
                          <div
                            className="bg-orange-500 flex items-center justify-center text-xs text-white"
                            style={{ width: `${benchmark.format_other_premium_pct}%` }}
                            title={`Other PLF: ${benchmark.format_other_premium_pct.toFixed(1)}%`}
                          >
                            {benchmark.format_other_premium_pct > 3 && 'PLF'}
                          </div>
                        </div>

                        {/* Legend row */}
                        <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-gray-400" />
                            Standard {benchmark.format_standard_pct.toFixed(1)}%
                          </span>
                          <span className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-blue-500" />
                            IMAX {benchmark.format_imax_pct.toFixed(1)}%
                          </span>
                          <span className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-purple-500" />
                            Dolby {benchmark.format_dolby_pct.toFixed(1)}%
                          </span>
                          <span className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-green-500" />
                            3D {benchmark.format_3d_pct.toFixed(1)}%
                          </span>
                          <span className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-orange-500" />
                            Other PLF {benchmark.format_other_premium_pct.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Daypart Strategy Tab */}
        <TabsContent value="dayparts">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Daypart Strategy
              </CardTitle>
              <CardDescription>
                Time-of-day showtime distribution (Matinee / Evening / Late)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sortedBenchmarks.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No benchmark data available.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Circuit</TableHead>
                      <TableHead className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Sun className="h-4 w-4" />
                          Matinee
                        </div>
                        <span className="text-xs font-normal">&lt; 5 PM</span>
                      </TableHead>
                      <TableHead className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Sunset className="h-4 w-4" />
                          Evening
                        </div>
                        <span className="text-xs font-normal">5 - 9 PM</span>
                      </TableHead>
                      <TableHead className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Moon className="h-4 w-4" />
                          Late
                        </div>
                        <span className="text-xs font-normal">&gt; 9 PM</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedBenchmarks.map((benchmark) => {
                      const isMarcus = isMarcusCircuit(benchmark.circuit_name);
                      return (
                        <TableRow
                          key={benchmark.benchmark_id}
                          className={cn(isMarcus && 'bg-yellow-500/10')}
                        >
                          <TableCell className={cn('font-medium', isMarcus && 'text-yellow-600')}>
                            {benchmark.circuit_name}
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="flex flex-col items-center">
                              <span className="font-medium">{benchmark.daypart_matinee_pct.toFixed(1)}%</span>
                              <Progress value={benchmark.daypart_matinee_pct} className="h-2 w-20 mt-1" />
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="flex flex-col items-center">
                              <span className="font-medium">{benchmark.daypart_evening_pct.toFixed(1)}%</span>
                              <Progress value={benchmark.daypart_evening_pct} className="h-2 w-20 mt-1" />
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="flex flex-col items-center">
                              <span className="font-medium">{benchmark.daypart_late_pct.toFixed(1)}%</span>
                              <Progress value={benchmark.daypart_late_pct} className="h-2 w-20 mt-1" />
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* PLF Ranking Tab */}
        <TabsContent value="plf">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Trophy className="h-5 w-5" />
                PLF Penetration Ranking
              </CardTitle>
              <CardDescription>
                Circuits ranked by total premium large format percentage
              </CardDescription>
            </CardHeader>
            <CardContent>
              {plfRankedBenchmarks.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No benchmark data available.
                </p>
              ) : (
                <div className="space-y-2">
                  {plfRankedBenchmarks.map((benchmark, idx) => {
                    const isMarcus = isMarcusCircuit(benchmark.circuit_name);
                    const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '';
                    return (
                      <div
                        key={benchmark.benchmark_id}
                        className={cn(
                          'flex items-center gap-4 p-3 border rounded-lg',
                          isMarcus && 'border-yellow-500/50 bg-yellow-500/10'
                        )}
                      >
                        <span className="w-8 text-center text-lg">{medal || idx + 1}</span>
                        <div className="flex-1">
                          <span className={cn('font-medium', isMarcus && 'text-yellow-600')}>
                            {benchmark.circuit_name}
                          </span>
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <Progress value={benchmark.plf_total_pct} className="h-3 flex-1" />
                            <span className="font-bold w-16 text-right">
                              {benchmark.plf_total_pct.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        <div className="flex gap-4 text-sm text-muted-foreground">
                          <span className="text-blue-500">IMAX {benchmark.format_imax_pct.toFixed(1)}%</span>
                          <span className="text-purple-500">Dolby {benchmark.format_dolby_pct.toFixed(1)}%</span>
                          <span className="text-orange-500">Other {benchmark.format_other_premium_pct.toFixed(1)}%</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Week History Tab */}
        <TabsContent value="weeks">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                Available Weeks
              </CardTitle>
              <CardDescription>
                Historical data availability - click to load
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!weeksData || weeksData.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No historical data available. Sync from EntTelligence to load data.
                </p>
              ) : (
                <div className="space-y-2">
                  {weeksData.map((week) => (
                    <div
                      key={week.week_ending_date}
                      className={cn(
                        'flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-colors',
                        selectedWeek === week.week_ending_date
                          ? 'border-primary bg-primary/5'
                          : 'hover:bg-muted/50'
                      )}
                      onClick={() => setSelectedWeek(week.week_ending_date)}
                    >
                      <div className="flex items-center gap-3">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="font-medium">
                            {formatWeekRange(week.week_ending_date, week.period_start_date)}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            Week ending {week.week_ending_date}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant="secondary">{week.circuit_count} circuits</Badge>
                        <span className="text-sm text-muted-foreground">
                          {week.total_showtimes.toLocaleString()} showtimes
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {week.data_freshness}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
