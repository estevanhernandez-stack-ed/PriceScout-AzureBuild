import { useState, useMemo, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Ticket,
  Calendar,
  TrendingUp,
  TrendingDown,
  Minus,
  Bell,
  BellRing,
  Plus,
  RefreshCw,
  Search,
  DollarSign,
  Building2,
  Download,
  BarChart3,
  Trophy,
  Activity,
  FileText,
  Target,
  AlertTriangle,
  CheckCircle2,
  Trash2,
  Settings,
  Zap,
  MapPin,
} from 'lucide-react';
import {
  usePresaleFilms,
  usePresaleCircuits,
  usePresaleTrajectory,
  usePresaleVelocity,
  usePresaleComparison,
  usePresaleCompliance,
  usePresaleHeatmapData,
  useSyncPresales,
  useTaskStatus,
  usePresaleWatches,
  useCreatePresaleWatch,
  useUpdatePresaleWatch,
  useDeletePresaleWatch,
  usePresaleWatchNotifications,
  useMarkNotificationRead,
  type MarketScope,
  type PresaleWatch,
  type PresaleFilm,
} from '@/hooks/api';
import { Progress } from '@/components/ui/progress';
import { Loader2 } from 'lucide-react';
import { useMarketEvents } from '@/hooks/api/useMarketContext';
import { format as dateFnsFormat } from 'date-fns';
import { MapContainer, TileLayer, Popup, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import type { PresaleHeatmapTheater } from '@/hooks/api';

// ============================================================================
// Heatmap Sub-Component
// ============================================================================

function PresaleHeatmapMap({
  theaters,
}: {
  theaters: PresaleHeatmapTheater[];
  filmFilter?: string | null;
}) {
  const center = useMemo((): [number, number] => {
    if (theaters.length === 0) return [39.8283, -98.5795]; // US center
    const lat = theaters.reduce((s, t) => s + t.latitude, 0) / theaters.length;
    const lon = theaters.reduce((s, t) => s + t.longitude, 0) / theaters.length;
    return [lat, lon];
  }, [theaters]);

  // Color by showtime density (primary metric for "activity")
  const maxShowtimes = useMemo(
    () => Math.max(1, ...theaters.map((t) => t.total_showtimes)),
    [theaters]
  );

  const getColor = (t: PresaleHeatmapTheater) => {
    if (t.is_marcus) return '#3b82f6'; // Blue for Marcus
    const ratio = t.total_showtimes / maxShowtimes;
    if (ratio > 0.6) return '#ef4444'; // Red - high activity
    if (ratio > 0.3) return '#f97316'; // Orange
    if (ratio > 0.1) return '#eab308'; // Yellow
    return '#22c55e'; // Green - low activity
  };

  const getRadius = (t: PresaleHeatmapTheater) => {
    const ratio = t.total_showtimes / maxShowtimes;
    return Math.max(6, Math.min(18, 6 + ratio * 12));
  };

  return (
    <div className="h-[550px] w-full z-10">
      <MapContainer
        center={center}
        zoom={theaters.length <= 20 ? 7 : 5}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          opacity={0.7}
        />
        {theaters.map((t) => (
          <CircleMarker
            key={t.theater_name}
            center={[t.latitude, t.longitude]}
            radius={getRadius(t)}
            pathOptions={{
              fillColor: getColor(t),
              fillOpacity: 0.8,
              color: t.is_marcus ? '#1d4ed8' : '#fff',
              weight: t.is_marcus ? 3 : 2,
            }}
          >
            <Popup>
              <div className="p-1 space-y-1 min-w-[180px]">
                <h4 className="font-bold text-slate-900 leading-tight text-sm">{t.theater_name}</h4>
                <p className="text-xs text-slate-500">{t.circuit_name || 'Independent'}</p>
                {t.market && <p className="text-xs text-slate-400">{t.market}</p>}
                <div className="pt-2 border-t mt-2 space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-600">Showtimes:</span>
                    <span className="font-semibold">{t.total_showtimes.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-600">Capacity:</span>
                    <span className="font-semibold">{t.total_capacity.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-600">Tickets Sold:</span>
                    <span className="font-semibold">{t.total_tickets_sold.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-600">Fill Rate:</span>
                    <span className="font-semibold">{t.fill_rate_pct.toFixed(1)}%</span>
                  </div>
                  {t.avg_price && (
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-600">Avg Price:</span>
                      <span className="font-semibold">${t.avg_price.toFixed(2)}</span>
                    </div>
                  )}
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-600">Films:</span>
                    <span className="font-semibold">{t.films_count}</span>
                  </div>
                </div>
                {t.is_marcus && (
                  <div className="mt-2 text-center text-xs font-semibold text-blue-600 bg-blue-50 rounded px-2 py-1">
                    Your Theater
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-[1000] bg-white/95 backdrop-blur-sm p-3 rounded-lg border shadow-lg max-w-[180px]">
        <h5 className="text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
          Presale Activity
        </h5>
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#3b82f6] border-2 border-[#1d4ed8]" />
            <span className="text-[10px] text-slate-600">Marcus Theatres</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#ef4444]" />
            <span className="text-[10px] text-slate-600">High Activity</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#f97316]" />
            <span className="text-[10px] text-slate-600">Moderate</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#eab308]" />
            <span className="text-[10px] text-slate-600">Low</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#22c55e]" />
            <span className="text-[10px] text-slate-600">Minimal</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Film Row Sub-Component
// ============================================================================

function FilmRow({
  film,
  isSelected,
  onSelect,
}: {
  film: PresaleFilm;
  isSelected: boolean;
  onSelect: (title: string) => void;
}) {
  return (
    <div
      className={`flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-colors ${
        isSelected ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
      }`}
      onClick={() => onSelect(film.film_title)}
    >
      <div className="flex items-center gap-4 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">{film.film_title}</span>
            <Badge
              className={`shrink-0 text-[10px] px-1.5 ${
                film.days_until_release <= 0
                  ? 'bg-gray-500/10 text-gray-500'
                  : film.days_until_release <= 7
                  ? 'bg-red-500/10 text-red-500'
                  : 'bg-green-500/10 text-green-500'
              }`}
            >
              {film.days_until_release <= 0 ? 'Released' : `${film.days_until_release}d`}
            </Badge>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
            <span>{film.release_date}</span>
            <span>{film.total_circuits} circuit{film.total_circuits !== 1 ? 's' : ''}</span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        <div className="text-right">
          <p className="text-lg font-bold">{film.current_tickets.toLocaleString()}</p>
          <p className="text-[10px] text-muted-foreground">tickets</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold">${film.current_revenue.toLocaleString()}</p>
          <p className="text-[10px] text-muted-foreground">revenue</p>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Circuit Group Sub-Component (collapsible)
// ============================================================================

function CircuitGroup({
  circuitName,
  films,
  selectedFilm,
  onSelectFilm,
  isMarcus,
}: {
  circuitName: string;
  films: PresaleFilm[];
  selectedFilm: string | null;
  onSelectFilm: (title: string) => void;
  isMarcus: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const totalTickets = films.reduce((s, f) => s + f.current_tickets, 0);
  const totalRevenue = films.reduce((s, f) => s + f.current_revenue, 0);

  return (
    <div className={`border rounded-lg overflow-hidden ${isMarcus ? 'border-blue-300 bg-blue-50/30' : ''}`}>
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Building2 className={`h-4 w-4 ${isMarcus ? 'text-blue-500' : 'text-muted-foreground'}`} />
          <span className="font-semibold text-sm">{circuitName}</span>
          <Badge variant="secondary" className="text-[10px]">
            {films.length} film{films.length !== 1 ? 's' : ''}
          </Badge>
          {isMarcus && (
            <Badge className="bg-blue-500/10 text-blue-600 text-[10px]">Your Circuit</Badge>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium">{totalTickets.toLocaleString()} tickets</span>
          <span className="text-sm text-muted-foreground">${totalRevenue.toLocaleString()}</span>
          <span className="text-xs text-muted-foreground">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>
      {expanded && (
        <div className="border-t px-2 py-1 space-y-1">
          {films.map((film) => (
            <FilmRow
              key={film.film_title}
              film={film}
              isSelected={selectedFilm === film.film_title}
              onSelect={onSelectFilm}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Component
// ============================================================================

export function PresaleTrackingPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFilm, setSelectedFilm] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('presales');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(300000); // 5 minutes

  // Market scope: default to Marcus markets only
  const [marketScope, setMarketScope] = useState<MarketScope>('our_markets');

  // Film list sorting & circuit filter
  type SortField = 'release_date' | 'title' | 'tickets';
  const [sortField, setSortField] = useState<SortField>('release_date');
  const [circuitFilter, setCircuitFilter] = useState<string>('__all__');

  // Alerts state (API-backed)
  const { data: watches = [] } = usePresaleWatches();
  const { data: notifications = [] } = usePresaleWatchNotifications();
  const createWatch = useCreatePresaleWatch();
  const updateWatch = useUpdatePresaleWatch();
  const deleteWatch = useDeletePresaleWatch();
  const markRead = useMarkNotificationRead();
  const [showCreateAlertDialog, setShowCreateAlertDialog] = useState(false);
  const [newAlert, setNewAlert] = useState({
    film_title: '',
    alert_type: 'velocity_drop' as PresaleWatch['alert_type'],
    threshold: 10,
  });

  const { data: circuits } = usePresaleCircuits(marketScope);
  const { data: films, isLoading: filmsLoading, refetch } = usePresaleFilms(
    circuitFilter !== '__all__' ? circuitFilter : undefined,
    marketScope
  );

  // Find Marcus circuit name for trajectory filtering (show OUR data in the chart)
  const marcusCircuitName = useMemo(() => {
    if (!circuits) return 'Marcus Theatres'; // Default fallback
    const marcus = circuits.find(c =>
      c.circuit_name.toLowerCase().includes('marcus') ||
      c.circuit_name.toLowerCase().includes('movie tavern')
    );
    return marcus?.circuit_name || 'Marcus Theatres';
  }, [circuits]);

  // Trajectory shows Marcus-only time series (circuit comparison is on separate tab)
  const { data: trajectory, isLoading: trajectoryLoading } = usePresaleTrajectory(selectedFilm || '', marcusCircuitName, marketScope);
  const { data: velocityData } = usePresaleVelocity(selectedFilm || '', marketScope);
  const { data: comparisonData } = usePresaleComparison(selectedFilm || '', undefined, marketScope);
  const { data: complianceData } = usePresaleCompliance(marketScope);
  // Heatmap tied to the selected film
  const { data: heatmapData, isLoading: heatmapLoading } = usePresaleHeatmapData({
    filmTitle: selectedFilm || undefined,
    enabled: !!selectedFilm,
    marketScope,
  });
  const syncMutation = useSyncPresales();
  const [activeSyncTaskId, setActiveSyncTaskId] = useState<string | null>(null);
  const { data: activeTaskStatus } = useTaskStatus(activeSyncTaskId);

  // Market events for context
  const { data: marketEvents } = useMarketEvents(
    useMemo(() => {
      if (!trajectory?.snapshots?.length) return dateFnsFormat(new Date(), 'yyyy-MM-dd');
      return trajectory.snapshots[0].snapshot_date;
    }, [trajectory]),
    useMemo(() => {
      if (!trajectory?.snapshots?.length) return dateFnsFormat(new Date(), 'yyyy-MM-dd');
      return trajectory.snapshots[trajectory.snapshots.length - 1].snapshot_date;
    }, [trajectory])
  );

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      refetch();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, refetch]);

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

  // Check if circuit is Marcus-owned
  const isMarcusCircuit = (name: string) => {
    const lower = name.toLowerCase();
    return lower.includes('marcus') || lower.includes('movie tavern') || lower.includes('spotlight');
  };

  // Get velocity trend badge
  const getVelocityBadge = (trend?: string, showIcon = true) => {
    switch (trend) {
      case 'accelerating':
        return (
          <Badge className="bg-green-500/10 text-green-500">
            {showIcon && <TrendingUp className="h-3 w-3 mr-1" />}
            Accelerating
          </Badge>
        );
      case 'decelerating':
        return (
          <Badge className="bg-red-500/10 text-red-500">
            {showIcon && <TrendingDown className="h-3 w-3 mr-1" />}
            Decelerating
          </Badge>
        );
      case 'steady':
        return (
          <Badge className="bg-yellow-500/10 text-yellow-500">
            {showIcon && <Minus className="h-3 w-3 mr-1" />}
            Steady
          </Badge>
        );
      default:
        return (
          <Badge variant="outline">
            Insufficient Data
          </Badge>
        );
    }
  };

  // Get trend indicator for circuit comparison
  const getTrendIndicator = (value: number, average: number) => {
    const diff = value - average;
    if (diff > 5) return { icon: TrendingUp, color: 'text-green-500', label: `+${diff.toFixed(1)}%` };
    if (diff < -5) return { icon: TrendingDown, color: 'text-red-500', label: `${diff.toFixed(1)}%` };
    return { icon: Minus, color: 'text-muted-foreground', label: '—' };
  };

  // Format colors for stacked bars
  const formatColors = {
    imax: 'bg-blue-500',
    dolby: 'bg-purple-500',
    '3d': 'bg-cyan-500',
    premium: 'bg-orange-500',
    standard: 'bg-gray-400',
  };

  // Sort and filter films
  const filteredFilms = useMemo(() => {
    let result = films?.filter((film) =>
      film.film_title.toLowerCase().includes(searchQuery.toLowerCase())
    ) || [];

    // Sort
    result = [...result].sort((a, b) => {
      switch (sortField) {
        case 'release_date':
          return (a.release_date || '').localeCompare(b.release_date || '');
        case 'title':
          return a.film_title.localeCompare(b.film_title);
        case 'tickets':
          return b.current_tickets - a.current_tickets;
        default:
          return 0;
      }
    });

    return result;
  }, [films, searchQuery, sortField]);

  // Group single-circuit films by circuit for the grouped view
  const groupedByCircuit = useMemo(() => {
    if (circuitFilter !== '__all__') return null; // no grouping when already filtered to a circuit

    const multiCircuit: PresaleFilm[] = [];
    const byCircuit = new Map<string, PresaleFilm[]>();

    for (const film of filteredFilms) {
      if (film.total_circuits === 1 && film.circuit_name) {
        const list = byCircuit.get(film.circuit_name) || [];
        list.push(film);
        byCircuit.set(film.circuit_name, list);
      } else {
        multiCircuit.push(film);
      }
    }

    return { multiCircuit, byCircuit };
  }, [filteredFilms, circuitFilter]);

  // Calculate summary stats
  const summaryStats = useMemo(() => ({
    activePresales: films?.filter((f) => f.days_until_release > 0).length || 0,
    upcomingPresales: films?.filter((f) => f.days_until_release > 14).length || 0,
    totalTickets: films?.reduce((sum, f) => sum + (f.current_tickets || 0), 0) || 0,
    totalRevenue: films?.reduce((sum, f) => sum + (f.current_revenue || 0), 0) || 0,
  }), [films]);

  // Calculate format breakdown from trajectory snapshots
  const formatBreakdown = useMemo(() => {
    if (!trajectory?.snapshots?.length) return null;
    const latest = trajectory.snapshots[trajectory.snapshots.length - 1];
    const total = (latest.tickets_imax || 0) + (latest.tickets_dolby || 0) +
                  (latest.tickets_3d || 0) + (latest.tickets_premium || 0) +
                  (latest.tickets_standard || 0);
    if (total === 0) return null;
    return {
      imax: { count: latest.tickets_imax || 0, pct: ((latest.tickets_imax || 0) / total * 100) },
      dolby: { count: latest.tickets_dolby || 0, pct: ((latest.tickets_dolby || 0) / total * 100) },
      '3d': { count: latest.tickets_3d || 0, pct: ((latest.tickets_3d || 0) / total * 100) },
      premium: { count: latest.tickets_premium || 0, pct: ((latest.tickets_premium || 0) / total * 100) },
      standard: { count: latest.tickets_standard || 0, pct: ((latest.tickets_standard || 0) / total * 100) },
    };
  }, [trajectory]);

  // Marcus-specific stats from comparison
  const marcusStats = useMemo(() => {
    if (!comparisonData?.circuits) return null;
    const marcus = comparisonData.circuits.find(c => isMarcusCircuit(c.circuit_name));
    const avgMarketShare = comparisonData.circuits.reduce((sum, c) => sum + c.market_share_pct, 0) / comparisonData.circuits.length;
    const avgTicketPrice = comparisonData.circuits.reduce((sum, c) => sum + c.avg_ticket_price, 0) / comparisonData.circuits.length;

    if (!marcus) return null;
    return {
      marcus,
      avgMarketShare,
      avgTicketPrice,
      rank: [...comparisonData.circuits].sort((a, b) => b.total_tickets - a.total_tickets)
        .findIndex(c => isMarcusCircuit(c.circuit_name)) + 1,
      totalCircuits: comparisonData.circuits.length,
    };
  }, [comparisonData]);

  // Calculate trajectory projections
  const trajectoryProjections = useMemo(() => {
    if (!trajectory?.snapshots?.length || trajectory.snapshots.length < 3) return null;

    const snapshots = trajectory.snapshots;
    const recent = snapshots.slice(-7); // Last 7 days

    // Calculate average daily growth
    let totalGrowth = 0;
    for (let i = 1; i < recent.length; i++) {
      totalGrowth += recent[i].total_tickets_sold - recent[i - 1].total_tickets_sold;
    }
    const avgDailyGrowth = totalGrowth / (recent.length - 1);

    // Project to release day
    const daysRemaining = trajectory.days_until_release;
    const projectedTotal = trajectory.current_tickets + (avgDailyGrowth * daysRemaining);

    // Calculate confidence based on velocity stability
    const growthRates = [];
    for (let i = 1; i < recent.length; i++) {
      growthRates.push(recent[i].total_tickets_sold - recent[i - 1].total_tickets_sold);
    }
    const avgGrowth = growthRates.reduce((a, b) => a + b, 0) / growthRates.length;
    const variance = growthRates.reduce((sum, rate) => sum + Math.pow(rate - avgGrowth, 2), 0) / growthRates.length;
    const stdDev = Math.sqrt(variance);
    const coeffOfVariation = avgGrowth > 0 ? (stdDev / avgGrowth) * 100 : 100;

    let confidence: 'high' | 'medium' | 'low';
    if (coeffOfVariation < 30) confidence = 'high';
    else if (coeffOfVariation < 60) confidence = 'medium';
    else confidence = 'low';

    return {
      avgDailyGrowth: Math.round(avgDailyGrowth),
      projectedTotal: Math.round(projectedTotal),
      daysRemaining,
      confidence,
      projectedRevenue: projectedTotal * (trajectory.current_revenue / trajectory.current_tickets || 0),
    };
  }, [trajectory]);

  // Alert handlers (API-backed)
  const handleCreateAlert = () => {
    createWatch.mutate({
      film_title: newAlert.film_title || selectedFilm || 'All Films',
      alert_type: newAlert.alert_type,
      threshold: newAlert.threshold,
    });
    setShowCreateAlertDialog(false);
    setNewAlert({ film_title: '', alert_type: 'velocity_drop', threshold: 10 });
  };

  const handleDeleteAlert = (alertId: number) => {
    deleteWatch.mutate(alertId);
  };

  const handleToggleAlert = (alertId: number) => {
    const watch = watches.find(w => w.id === alertId);
    if (watch) {
      updateWatch.mutate({ id: alertId, enabled: !watch.enabled });
    }
  };

  const handleMarkNotificationRead = (notificationId: number) => {
    markRead.mutate(notificationId);
  };

  const unreadNotifications = notifications.filter(n => !n.is_read);

  // Export to CSV
  const handleExportCSV = () => {
    if (!comparisonData?.circuits) return;

    const headers = ['Circuit', 'Tickets', 'Revenue', 'Theaters', 'Avg Price', 'Market Share %'];
    const rows = comparisonData.circuits.map(c => [
      c.circuit_name,
      c.total_tickets,
      c.total_revenue.toFixed(2),
      c.theaters,
      c.avg_ticket_price.toFixed(2),
      c.market_share_pct.toFixed(1),
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `presale_${selectedFilm?.replace(/\s+/g, '_')}_comparison.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export to PDF (generates HTML that can be printed)
  const handleExportPDF = () => {
    if (!trajectory || !comparisonData) return;

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Presale Report - ${selectedFilm}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 20px; }
          h1 { color: #8b0e04; }
          .stat { display: inline-block; margin-right: 40px; }
          .stat-value { font-size: 24px; font-weight: bold; }
          .stat-label { color: #666; font-size: 12px; }
          table { width: 100%; border-collapse: collapse; margin-top: 20px; }
          th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
          th { background: #f5f5f5; }
          .marcus { background: #fef3c7; }
          @media print { body { padding: 0; } }
        </style>
      </head>
      <body>
        <h1>Presale Report: ${selectedFilm}</h1>
        <p>Generated: ${new Date().toLocaleString()}</p>

        <h2>Summary</h2>
        <div class="stat">
          <div class="stat-value">${trajectory.current_tickets.toLocaleString()}</div>
          <div class="stat-label">Total Tickets</div>
        </div>
        <div class="stat">
          <div class="stat-value">$${trajectory.current_revenue.toLocaleString()}</div>
          <div class="stat-label">Total Revenue</div>
        </div>
        <div class="stat">
          <div class="stat-value">${trajectory.days_until_release}</div>
          <div class="stat-label">Days Until Release</div>
        </div>
        <div class="stat">
          <div class="stat-value">${trajectory.velocity_trend}</div>
          <div class="stat-label">Velocity Trend</div>
        </div>

        <h2>Circuit Comparison</h2>
        <table>
          <tr>
            <th>Rank</th>
            <th>Circuit</th>
            <th>Tickets</th>
            <th>Revenue</th>
            <th>Theaters</th>
            <th>Avg Price</th>
            <th>Market Share</th>
          </tr>
          ${[...comparisonData.circuits]
            .sort((a, b) => b.total_tickets - a.total_tickets)
            .map((c, idx) => `
              <tr class="${isMarcusCircuit(c.circuit_name) ? 'marcus' : ''}">
                <td>#${idx + 1}</td>
                <td>${c.circuit_name}</td>
                <td>${c.total_tickets.toLocaleString()}</td>
                <td>$${c.total_revenue.toLocaleString()}</td>
                <td>${c.theaters}</td>
                <td>$${c.avg_ticket_price.toFixed(2)}</td>
                <td>${c.market_share_pct.toFixed(1)}%</td>
              </tr>
            `).join('')}
        </table>

        <p style="margin-top: 40px; color: #666; font-size: 11px;">
          Data source: EntTelligence | PriceScout Presale Tracking
        </p>
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

  // Get alert type display info
  const getAlertTypeInfo = (type: PresaleWatch['alert_type']) => {
    switch (type) {
      case 'velocity_drop':
        return { label: 'Velocity Drop', icon: TrendingDown, color: 'text-red-500' };
      case 'velocity_spike':
        return { label: 'Velocity Spike', icon: TrendingUp, color: 'text-green-500' };
      case 'milestone':
        return { label: 'Ticket Milestone', icon: Target, color: 'text-blue-500' };
      case 'days_out':
        return { label: 'Days Before Release', icon: Calendar, color: 'text-purple-500' };
      case 'market_share':
        return { label: 'Market Share Change', icon: BarChart3, color: 'text-orange-500' };
    }
  };

  if (filmsLoading) {
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
          <h1 className="text-3xl font-bold tracking-tight">Presale Tracking</h1>
          <p className="text-muted-foreground">
            Monitor presale events and sellout velocity (from EntTelligence)
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Market scope toggle */}
          <div className="flex items-center rounded-lg border bg-muted p-0.5 mr-2">
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                marketScope === 'our_markets'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setMarketScope('our_markets')}
            >
              <MapPin className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
              Our Markets
            </button>
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                marketScope === 'full'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setMarketScope('full')}
            >
              National
            </button>
          </div>

          {/* Auto-refresh toggle */}
          <div className="flex items-center gap-2 mr-4">
            <Switch
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
              id="auto-refresh"
            />
            <Label htmlFor="auto-refresh" className="text-sm">
              Auto-refresh
            </Label>
            {autoRefresh && (
              <Select
                value={String(refreshInterval)}
                onValueChange={(v) => setRefreshInterval(Number(v))}
              >
                <SelectTrigger className="w-24 h-8">
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
                Sync Data
              </>
            )}
          </Button>

          {/* Notifications bell */}
          <Button
            variant="outline"
            size="icon"
            className="relative"
            onClick={() => setActiveTab('alerts')}
          >
            {unreadNotifications.length > 0 ? (
              <BellRing className="h-4 w-4 text-yellow-500" />
            ) : (
              <Bell className="h-4 w-4" />
            )}
            {unreadNotifications.length > 0 && (
              <span className="absolute -top-1 -right-1 h-4 w-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                {unreadNotifications.length}
              </span>
            )}
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Ticket className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Active Presales</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.activePresales}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Upcoming</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.upcomingPresales}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Ticket className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Tickets</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.totalTickets.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Revenue</span>
            </div>
            <p className="text-3xl font-bold mt-2">${summaryStats.totalRevenue.toLocaleString()}</p>
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

      {/* Marcus Highlight Card - when film selected */}
      {selectedFilm && marcusStats && (
        <Card className="bg-yellow-500/10 border-yellow-500/30">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Trophy className="h-6 w-6 text-yellow-500" />
                <div>
                  <h3 className="font-semibold">Marcus Theatres Position</h3>
                  <p className="text-sm text-muted-foreground">{selectedFilm}</p>
                </div>
              </div>
              <div className="flex items-center gap-8">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Rank</p>
                  <p className="text-2xl font-bold">#{marcusStats.rank} <span className="text-sm font-normal text-muted-foreground">of {marcusStats.totalCircuits}</span></p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Market Share</p>
                  <div className="flex items-center gap-2">
                    <p className="text-2xl font-bold">{marcusStats.marcus.market_share_pct.toFixed(1)}%</p>
                    {(() => {
                      const trend = getTrendIndicator(marcusStats.marcus.market_share_pct, marcusStats.avgMarketShare);
                      return <span className={`text-sm ${trend.color}`}>{trend.label}</span>;
                    })()}
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Tickets Sold</p>
                  <p className="text-2xl font-bold">{marcusStats.marcus.total_tickets.toLocaleString()}</p>
                </div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">Avg Ticket Price</p>
                  <div className="flex items-center gap-2">
                    <p className="text-2xl font-bold">${marcusStats.marcus.avg_ticket_price.toFixed(2)}</p>
                    {(() => {
                      const trend = getTrendIndicator(marcusStats.marcus.avg_ticket_price, marcusStats.avgTicketPrice);
                      return <span className={`text-sm ${trend.color}`}>{trend.label}</span>;
                    })()}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="presales">
            <Ticket className="h-4 w-4 mr-1" />
            Presale Events
          </TabsTrigger>
          <TabsTrigger value="trajectory">
            <Activity className="h-4 w-4 mr-1" />
            Trajectory
          </TabsTrigger>
          <TabsTrigger value="circuits">
            <Building2 className="h-4 w-4 mr-1" />
            Circuit Comparison
          </TabsTrigger>
          <TabsTrigger value="formats">
            <BarChart3 className="h-4 w-4 mr-1" />
            Format Breakdown
          </TabsTrigger>
          <TabsTrigger value="velocity">
            <TrendingUp className="h-4 w-4 mr-1" />
            Velocity Trends
          </TabsTrigger>
          <TabsTrigger value="compliance">
            <Target className="h-4 w-4 mr-1" />
            Compliance
          </TabsTrigger>
          <TabsTrigger value="alerts" className="relative">
            <Bell className="h-4 w-4 mr-1" />
            Alerts
            {unreadNotifications.length > 0 && (
              <span className="ml-1 h-5 w-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                {unreadNotifications.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Presale Events Tab */}
        <TabsContent value="presales">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Tracked Films</CardTitle>
                  <CardDescription>
                    {circuitFilter !== '__all__'
                      ? `Showing films for ${circuitFilter}`
                      : `${filteredFilms.length} films with presale data`}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  {/* Circuit filter */}
                  <Select value={circuitFilter} onValueChange={(v) => { setCircuitFilter(v); setSelectedFilm(null); }}>
                    <SelectTrigger className="w-[220px] h-9">
                      <Building2 className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
                      <SelectValue placeholder="All Circuits" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">All Circuits</SelectItem>
                      {circuits?.map((c) => (
                        <SelectItem key={c.circuit_name} value={c.circuit_name}>
                          {c.circuit_name} ({c.total_films})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {/* Sort */}
                  <Select value={sortField} onValueChange={(v) => setSortField(v as SortField)}>
                    <SelectTrigger className="w-[160px] h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="release_date">Release Date</SelectItem>
                      <SelectItem value="title">Title A-Z</SelectItem>
                      <SelectItem value="tickets">Tickets Sold</SelectItem>
                    </SelectContent>
                  </Select>

                  {/* Search */}
                  <div className="relative w-48">
                    <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search films..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-8 h-9"
                    />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredFilms.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No presale data available. Sync from EntTelligence to load data.
                </p>
              ) : circuitFilter !== '__all__' || !groupedByCircuit ? (
                /* Flat list when filtering to a specific circuit */
                <div className="space-y-2 max-h-[600px] overflow-y-auto">
                  {filteredFilms.map((film) => (
                    <FilmRow
                      key={film.film_title}
                      film={film}
                      isSelected={selectedFilm === film.film_title}
                      onSelect={setSelectedFilm}
                    />
                  ))}
                </div>
              ) : (
                /* Grouped view: multi-circuit films first, then single-circuit grouped by circuit */
                <div className="space-y-4 max-h-[600px] overflow-y-auto">
                  {/* Multi-circuit films (shown individually) */}
                  {groupedByCircuit.multiCircuit.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider px-1">
                        Multi-Circuit Films ({groupedByCircuit.multiCircuit.length})
                      </h4>
                      {groupedByCircuit.multiCircuit.map((film) => (
                        <FilmRow
                          key={film.film_title}
                          film={film}
                          isSelected={selectedFilm === film.film_title}
                          onSelect={setSelectedFilm}
                        />
                      ))}
                    </div>
                  )}

                  {/* Single-circuit films grouped by circuit */}
                  {Array.from(groupedByCircuit.byCircuit.entries())
                    .sort(([, a], [, b]) => b.reduce((s, f) => s + f.current_tickets, 0) - a.reduce((s, f) => s + f.current_tickets, 0))
                    .map(([circuit, circuitFilms]) => (
                    <CircuitGroup
                      key={circuit}
                      circuitName={circuit}
                      films={circuitFilms}
                      selectedFilm={selectedFilm}
                      onSelectFilm={setSelectedFilm}
                      isMarcus={circuit.toLowerCase().includes('marcus') || circuit.toLowerCase().includes('movie tavern')}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Trajectory Tab */}
        <TabsContent value="trajectory">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Presale Trajectory
                  </CardTitle>
                  <CardDescription>
                    {selectedFilm
                      ? `Ticket sales buildup for ${selectedFilm}`
                      : 'Select a film to view trajectory'}
                  </CardDescription>
                </div>
                {selectedFilm && trajectory && (
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={handleExportCSV}>
                      <Download className="h-4 w-4 mr-2" />
                      CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleExportPDF}>
                      <FileText className="h-4 w-4 mr-2" />
                      PDF
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {!selectedFilm ? (
                <p className="text-center text-muted-foreground py-8">
                  Select a film from the Presale Events tab to view its trajectory
                </p>
              ) : trajectoryLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : !trajectory ? (
                <p className="text-center text-muted-foreground py-8">
                  No trajectory data available for this film
                </p>
              ) : (
                <div className="space-y-6">
                  {/* Film summary header */}
                  <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                    <div>
                      <h3 className="font-medium">{trajectory.film_title}</h3>
                      <p className="text-sm text-muted-foreground">
                        Release: {trajectory.release_date}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">Current Tickets</p>
                        <p className="text-xl font-bold">
                          {trajectory.current_tickets.toLocaleString()}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">Current Revenue</p>
                        <p className="text-xl font-bold">
                          ${trajectory.current_revenue.toLocaleString()}
                        </p>
                      </div>
                      {getVelocityBadge(trajectory.velocity_trend)}
                    </div>
                  </div>

                  {/* Projection Card */}
                  {trajectoryProjections && trajectory.days_until_release > 0 && (
                    <Card className="bg-blue-500/5 border-blue-500/30">
                      <CardContent className="pt-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Zap className="h-5 w-5 text-blue-500" />
                            <div>
                              <h4 className="font-medium">Release Day Projection</h4>
                              <p className="text-sm text-muted-foreground">
                                Based on {trajectoryProjections.avgDailyGrowth.toLocaleString()} avg daily ticket sales
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-6">
                            <div className="text-right">
                              <p className="text-sm text-muted-foreground">Projected Tickets</p>
                              <p className="text-2xl font-bold text-blue-600">
                                {trajectoryProjections.projectedTotal.toLocaleString()}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-sm text-muted-foreground">Projected Revenue</p>
                              <p className="text-2xl font-bold text-blue-600">
                                ${Math.round(trajectoryProjections.projectedRevenue).toLocaleString()}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-sm text-muted-foreground">Confidence</p>
                              <Badge className={
                                trajectoryProjections.confidence === 'high' ? 'bg-green-500/10 text-green-500' :
                                trajectoryProjections.confidence === 'medium' ? 'bg-yellow-500/10 text-yellow-500' :
                                'bg-red-500/10 text-red-500'
                              }>
                                {trajectoryProjections.confidence}
                              </Badge>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {/* Visual trajectory bars - Marcus only */}
                  {trajectory.snapshots.length > 0 && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium">Marcus Ticket Buildup</h4>
                        <Badge variant="outline" className="text-[10px]">
                          {trajectory.snapshots.length} days tracked
                        </Badge>
                      </div>
                      <div className="space-y-2">
                        {trajectory.snapshots.slice(-14).map((snapshot) => {
                          const maxTickets = Math.max(...trajectory.snapshots.map(s => s.total_tickets_sold));
                          const pct = maxTickets > 0 ? (snapshot.total_tickets_sold / maxTickets * 100) : 0;

                          // Find events for this date
                          const eventsOnThisDay = marketEvents?.filter(e =>
                            snapshot.snapshot_date >= e.start_date && snapshot.snapshot_date <= e.end_date
                          );

                          // Format date for display (show date AND days out for context)
                          const dateLabel = snapshot.snapshot_date.slice(5); // MM-DD format

                          return (
                            <div key={snapshot.id} className="group relative">
                              <div className="flex items-center gap-3">
                                <div className="w-24 text-sm text-muted-foreground flex justify-between">
                                  <span>{dateLabel}</span>
                                  <span className="text-xs opacity-60">{snapshot.days_before_release}d</span>
                                </div>
                                <div className="flex-1 h-6 bg-muted rounded overflow-hidden relative">
                                  <div
                                    className="h-full bg-primary transition-all"
                                    style={{ width: `${pct}%` }}
                                  />
                                  {/* Event marker */}
                                  {eventsOnThisDay && eventsOnThisDay.length > 0 && (
                                    <div className="absolute top-0 right-2 h-full flex items-center">
                                      <Badge variant="secondary" className="px-1.5 h-4 text-[9px] bg-yellow-500/20 text-yellow-600 border-yellow-200">
                                        <Calendar className="h-2 w-2 mr-0.5" />
                                        {eventsOnThisDay[0].event_name}
                                      </Badge>
                                    </div>
                                  )}
                                </div>
                                <div className="w-24 text-sm text-right">
                                  {snapshot.total_tickets_sold.toLocaleString()}
                                </div>
                                <div className="w-24 text-sm text-muted-foreground text-right">
                                  ${snapshot.total_revenue.toLocaleString()}
                                </div>
                              </div>
                              {/* Event description tooltip on hover */}
                              {eventsOnThisDay && eventsOnThisDay.length > 0 && (
                                <div className="hidden group-hover:block absolute left-20 bottom-full mb-1 z-50 bg-slate-900 text-white text-[10px] p-2 rounded shadow-lg max-w-xs">
                                  <p className="font-bold">{eventsOnThisDay[0].event_name}</p>
                                  <p className="opacity-80">{eventsOnThisDay[0].description}</p>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Daily snapshots table */}
                  {trajectory.snapshots.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="font-medium">Daily Snapshots</h4>
                      <div className="max-h-64 overflow-y-auto">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Date</TableHead>
                              <TableHead>Days Out</TableHead>
                              <TableHead className="text-right">Tickets</TableHead>
                              <TableHead className="text-right">Revenue</TableHead>
                              <TableHead className="text-right">Theaters</TableHead>
                              <TableHead className="text-right">Avg/Show</TableHead>
                              <TableHead className="text-right">Daily +</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {trajectory.snapshots.slice(-14).reverse().map((snapshot, idx, arr) => {
                              const prevSnapshot = arr[idx + 1];
                              const dailyIncrease = prevSnapshot
                                ? snapshot.total_tickets_sold - prevSnapshot.total_tickets_sold
                                : 0;
                              return (
                                <TableRow key={snapshot.id}>
                                  <TableCell>{snapshot.snapshot_date}</TableCell>
                                  <TableCell>{snapshot.days_before_release}d</TableCell>
                                  <TableCell className="text-right font-medium">
                                    {snapshot.total_tickets_sold.toLocaleString()}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    ${snapshot.total_revenue.toLocaleString()}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {snapshot.total_theaters}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {snapshot.avg_tickets_per_show.toFixed(1)}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {dailyIncrease > 0 && (
                                      <span className="text-green-500">+{dailyIncrease.toLocaleString()}</span>
                                    )}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Theater Heatmap for selected film */}
              {selectedFilm && (
                <div className="mt-6 space-y-4">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-5 w-5 text-blue-500" />
                    <h4 className="font-medium">Theater Map</h4>
                    <span className="text-sm text-muted-foreground">
                      Presale activity for {selectedFilm}
                    </span>
                  </div>

                  {heatmapLoading ? (
                    <div className="h-[400px] flex items-center justify-center border rounded-lg">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : !heatmapData || heatmapData.theaters.length === 0 ? (
                    <div className="h-[200px] flex flex-col items-center justify-center text-center border rounded-lg">
                      <MapPin className="h-8 w-8 text-slate-300 mb-2" />
                      <p className="text-sm text-muted-foreground">No geographic data for this film</p>
                    </div>
                  ) : (
                    <>
                      {/* Summary */}
                      <div className="grid grid-cols-4 gap-3">
                        <div className="p-3 border rounded-lg">
                          <div className="text-xs text-muted-foreground">Theaters</div>
                          <div className="text-xl font-bold">{heatmapData.theaters_with_data}</div>
                        </div>
                        <div className="p-3 border rounded-lg">
                          <div className="text-xs text-muted-foreground">Showtimes</div>
                          <div className="text-xl font-bold">
                            {heatmapData.theaters.reduce((s, t) => s + t.total_showtimes, 0).toLocaleString()}
                          </div>
                        </div>
                        <div className="p-3 border rounded-lg">
                          <div className="text-xs text-muted-foreground">Tickets Sold</div>
                          <div className="text-xl font-bold">
                            {heatmapData.theaters.reduce((s, t) => s + t.total_tickets_sold, 0).toLocaleString()}
                          </div>
                        </div>
                        <div className="p-3 border rounded-lg">
                          <div className="text-xs text-muted-foreground">Avg Fill Rate</div>
                          <div className="text-xl font-bold">
                            {(heatmapData.theaters.reduce((s, t) => s + t.fill_rate_pct, 0) / (heatmapData.theaters.length || 1)).toFixed(1)}%
                          </div>
                        </div>
                      </div>

                      {/* Map */}
                      <Card className="overflow-hidden">
                        <CardContent className="p-0 relative">
                          <PresaleHeatmapMap theaters={heatmapData.theaters} />
                        </CardContent>
                      </Card>

                      {/* Top theaters table */}
                      <div className="max-h-[300px] overflow-y-auto border rounded-lg">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Theater</TableHead>
                              <TableHead>Circuit</TableHead>
                              <TableHead className="text-right">Sold</TableHead>
                              <TableHead className="text-right">Fill Rate</TableHead>
                              <TableHead className="text-right">Avg Price</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {[...heatmapData.theaters]
                              .sort((a, b) => b.total_tickets_sold - a.total_tickets_sold)
                              .slice(0, 30)
                              .map((t) => (
                              <TableRow key={t.theater_name}>
                                <TableCell className="font-medium text-sm">
                                  {t.theater_name}
                                  {t.is_marcus && <Badge variant="secondary" className="ml-1 text-[9px]">Marcus</Badge>}
                                </TableCell>
                                <TableCell className="text-xs">{t.circuit_name || '-'}</TableCell>
                                <TableCell className="text-right text-sm">{t.total_tickets_sold.toLocaleString()}</TableCell>
                                <TableCell className="text-right text-sm">
                                  <span className={
                                    t.fill_rate_pct > 70 ? 'text-red-600 font-medium' :
                                    t.fill_rate_pct > 40 ? 'text-orange-600' : ''
                                  }>{t.fill_rate_pct.toFixed(1)}%</span>
                                </TableCell>
                                <TableCell className="text-right text-sm">
                                  {t.avg_price ? `$${t.avg_price.toFixed(2)}` : '-'}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Circuit Comparison Tab */}
        <TabsContent value="circuits">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Building2 className="h-5 w-5" />
                    Circuit Comparison
                  </CardTitle>
                  <CardDescription>
                    {selectedFilm
                      ? `Compare presale performance across circuits for ${selectedFilm}`
                      : 'Select a film to view circuit comparison'}
                  </CardDescription>
                </div>
                {selectedFilm && comparisonData && (
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={handleExportCSV}>
                      <Download className="h-4 w-4 mr-2" />
                      CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleExportPDF}>
                      <FileText className="h-4 w-4 mr-2" />
                      PDF
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {!selectedFilm ? (
                <p className="text-center text-muted-foreground py-8">
                  Select a film from the Presale Events tab to view circuit comparison
                </p>
              ) : !comparisonData?.circuits?.length ? (
                <p className="text-center text-muted-foreground py-8">
                  No circuit comparison data available for this film
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="text-sm text-muted-foreground">
                    Total: {comparisonData.total_tickets.toLocaleString()} tickets across {comparisonData.total_circuits} circuits
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Rank</TableHead>
                        <TableHead>Circuit</TableHead>
                        <TableHead className="text-right">Tickets</TableHead>
                        <TableHead className="text-right">Revenue</TableHead>
                        <TableHead className="text-right">Theaters</TableHead>
                        <TableHead className="text-right">Avg Price</TableHead>
                        <TableHead className="text-right">Market Share</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {[...comparisonData.circuits]
                        .sort((a, b) => b.total_tickets - a.total_tickets)
                        .map((circuit, idx) => {
                          const isMarcus = isMarcusCircuit(circuit.circuit_name);
                          return (
                            <TableRow
                              key={circuit.circuit_name}
                              className={isMarcus ? 'bg-yellow-500/10' : ''}
                            >
                              <TableCell>
                                {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `#${idx + 1}`}
                              </TableCell>
                              <TableCell className="font-medium">
                                {circuit.circuit_name}
                                {isMarcus && (
                                  <Badge className="ml-2 bg-yellow-500/20 text-yellow-600">
                                    Marcus
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="text-right font-medium">
                                {circuit.total_tickets.toLocaleString()}
                              </TableCell>
                              <TableCell className="text-right">
                                ${circuit.total_revenue.toLocaleString()}
                              </TableCell>
                              <TableCell className="text-right">
                                {circuit.theaters}
                              </TableCell>
                              <TableCell className="text-right">
                                ${circuit.avg_ticket_price.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <div className="w-20 h-2 bg-muted rounded overflow-hidden">
                                    <div
                                      className={`h-full ${isMarcus ? 'bg-yellow-500' : 'bg-primary'}`}
                                      style={{ width: `${circuit.market_share_pct}%` }}
                                    />
                                  </div>
                                  <span className="w-12 text-right">{circuit.market_share_pct.toFixed(1)}%</span>
                                </div>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Format Breakdown Tab */}
        <TabsContent value="formats">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Format Breakdown
              </CardTitle>
              <CardDescription>
                {selectedFilm
                  ? `Ticket sales by format for ${selectedFilm}`
                  : 'Select a film to view format breakdown'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!selectedFilm ? (
                <p className="text-center text-muted-foreground py-8">
                  Select a film from the Presale Events tab to view format breakdown
                </p>
              ) : !formatBreakdown ? (
                <p className="text-center text-muted-foreground py-8">
                  No format breakdown data available for this film
                </p>
              ) : (
                <div className="space-y-6">
                  {/* Stacked bar visualization */}
                  <div className="space-y-2">
                    <h4 className="font-medium">Format Distribution</h4>
                    <div className="h-10 flex rounded overflow-hidden">
                      {formatBreakdown.imax.pct > 0 && (
                        <div
                          className={`${formatColors.imax} flex items-center justify-center text-white text-xs font-medium`}
                          style={{ width: `${formatBreakdown.imax.pct}%` }}
                          title={`IMAX: ${formatBreakdown.imax.pct.toFixed(1)}%`}
                        >
                          {formatBreakdown.imax.pct > 5 && '📽️'}
                        </div>
                      )}
                      {formatBreakdown.dolby.pct > 0 && (
                        <div
                          className={`${formatColors.dolby} flex items-center justify-center text-white text-xs font-medium`}
                          style={{ width: `${formatBreakdown.dolby.pct}%` }}
                          title={`Dolby: ${formatBreakdown.dolby.pct.toFixed(1)}%`}
                        >
                          {formatBreakdown.dolby.pct > 5 && '🔊'}
                        </div>
                      )}
                      {formatBreakdown['3d'].pct > 0 && (
                        <div
                          className={`${formatColors['3d']} flex items-center justify-center text-white text-xs font-medium`}
                          style={{ width: `${formatBreakdown['3d'].pct}%` }}
                          title={`3D: ${formatBreakdown['3d'].pct.toFixed(1)}%`}
                        >
                          {formatBreakdown['3d'].pct > 5 && '👓'}
                        </div>
                      )}
                      {formatBreakdown.premium.pct > 0 && (
                        <div
                          className={`${formatColors.premium} flex items-center justify-center text-white text-xs font-medium`}
                          style={{ width: `${formatBreakdown.premium.pct}%` }}
                          title={`Premium: ${formatBreakdown.premium.pct.toFixed(1)}%`}
                        >
                          {formatBreakdown.premium.pct > 5 && '✨'}
                        </div>
                      )}
                      {formatBreakdown.standard.pct > 0 && (
                        <div
                          className={`${formatColors.standard} flex items-center justify-center text-white text-xs font-medium`}
                          style={{ width: `${formatBreakdown.standard.pct}%` }}
                          title={`Standard: ${formatBreakdown.standard.pct.toFixed(1)}%`}
                        >
                          {formatBreakdown.standard.pct > 10 && 'STD'}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Format detail cards */}
                  <div className="grid grid-cols-5 gap-4">
                    <Card>
                      <CardContent className="pt-4 text-center">
                        <div className="text-2xl mb-1">📽️</div>
                        <p className="font-medium">IMAX</p>
                        <p className="text-2xl font-bold">{formatBreakdown.imax.count.toLocaleString()}</p>
                        <p className="text-sm text-muted-foreground">{formatBreakdown.imax.pct.toFixed(1)}%</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 text-center">
                        <div className="text-2xl mb-1">🔊</div>
                        <p className="font-medium">Dolby</p>
                        <p className="text-2xl font-bold">{formatBreakdown.dolby.count.toLocaleString()}</p>
                        <p className="text-sm text-muted-foreground">{formatBreakdown.dolby.pct.toFixed(1)}%</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 text-center">
                        <div className="text-2xl mb-1">👓</div>
                        <p className="font-medium">3D</p>
                        <p className="text-2xl font-bold">{formatBreakdown['3d'].count.toLocaleString()}</p>
                        <p className="text-sm text-muted-foreground">{formatBreakdown['3d'].pct.toFixed(1)}%</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 text-center">
                        <div className="text-2xl mb-1">✨</div>
                        <p className="font-medium">Premium</p>
                        <p className="text-2xl font-bold">{formatBreakdown.premium.count.toLocaleString()}</p>
                        <p className="text-sm text-muted-foreground">{formatBreakdown.premium.pct.toFixed(1)}%</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 text-center">
                        <div className="text-2xl mb-1">🎬</div>
                        <p className="font-medium">Standard</p>
                        <p className="text-2xl font-bold">{formatBreakdown.standard.count.toLocaleString()}</p>
                        <p className="text-sm text-muted-foreground">{formatBreakdown.standard.pct.toFixed(1)}%</p>
                      </CardContent>
                    </Card>
                  </div>

                  {/* PLF Percentage */}
                  <div className="p-4 bg-muted/50 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">Premium Large Format (PLF) Penetration</p>
                        <p className="text-sm text-muted-foreground">IMAX + Dolby + Other Premium formats</p>
                      </div>
                      <p className="text-3xl font-bold">
                        {(formatBreakdown.imax.pct + formatBreakdown.dolby.pct + formatBreakdown.premium.pct).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Velocity Trends Tab */}
        <TabsContent value="velocity">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Velocity Trends
              </CardTitle>
              <CardDescription>
                {selectedFilm
                  ? `Daily ticket velocity for ${selectedFilm}`
                  : 'Select a film to view velocity trends'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!selectedFilm ? (
                <p className="text-center text-muted-foreground py-8">
                  Select a film from the Presale Events tab to view velocity trends
                </p>
              ) : !velocityData?.length ? (
                <p className="text-center text-muted-foreground py-8">
                  No velocity data available for this film
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="text-sm text-muted-foreground">
                    Velocity measures daily ticket sales rate. Accelerating (&gt;+10%), Steady (±10%), Decelerating (&lt;-10%)
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Circuit</TableHead>
                        <TableHead className="text-right">Daily Tickets</TableHead>
                        <TableHead className="text-right">Daily Revenue</TableHead>
                        <TableHead className="text-right">Change</TableHead>
                        <TableHead>Trend</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {velocityData.map((v) => {
                        const isMarcus = isMarcusCircuit(v.circuit_name);
                        return (
                          <TableRow
                            key={`${v.circuit_name}-${v.snapshot_date}`}
                            className={isMarcus ? 'bg-yellow-500/10' : ''}
                          >
                            <TableCell>{v.snapshot_date}</TableCell>
                            <TableCell className="font-medium">
                              {v.circuit_name}
                              {isMarcus && (
                                <Badge className="ml-2 bg-yellow-500/20 text-yellow-600">
                                  Marcus
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-right font-medium">
                              {v.daily_tickets.toLocaleString()}
                            </TableCell>
                            <TableCell className="text-right">
                              ${v.daily_revenue.toLocaleString()}
                            </TableCell>
                            <TableCell className="text-right">
                              <span className={v.velocity_change > 0 ? 'text-green-500' : v.velocity_change < 0 ? 'text-red-500' : ''}>
                                {v.velocity_change > 0 ? '+' : ''}{v.velocity_change.toFixed(1)}%
                              </span>
                            </TableCell>
                            <TableCell>
                              {getVelocityBadge(v.trend, false)}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Compliance Tab */}
        <TabsContent value="compliance">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-5 w-5 text-blue-500" />
                  Presale Posting Compliance
                </CardTitle>
                <CardDescription>
                  How far in advance is Marcus posting showtimes vs. competitors?
                  A higher "days ahead" means tickets are available for purchase earlier.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {complianceData?.films?.length ? (
                  <div className="space-y-6">
                    {/* Upcoming films where Marcus is behind */}
                    {(() => {
                      const upcoming = complianceData.films.filter(
                        (f) => f.days_until_release > 0
                      );
                      const behind = upcoming.filter(
                        (f) => f.marcus_delta !== null && f.marcus_delta < 0
                      );
                      const notPosting = upcoming.filter(
                        (f) => f.marcus_rank === null && f.total_circuits >= 3
                      );

                      return (
                        <>
                          {/* Summary Cards */}
                          <div className="grid gap-4 md:grid-cols-4">
                            <Card>
                              <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Upcoming Films</CardTitle>
                              </CardHeader>
                              <CardContent>
                                <div className="text-2xl font-bold">{upcoming.length}</div>
                                <p className="text-xs text-muted-foreground">with presale data</p>
                              </CardContent>
                            </Card>
                            <Card>
                              <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Marcus Behind</CardTitle>
                              </CardHeader>
                              <CardContent>
                                <div className="text-2xl font-bold text-red-500">{behind.length}</div>
                                <p className="text-xs text-muted-foreground">posting later than average</p>
                              </CardContent>
                            </Card>
                            <Card>
                              <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Not Posting</CardTitle>
                              </CardHeader>
                              <CardContent>
                                <div className="text-2xl font-bold text-amber-500">{notPosting.length}</div>
                                <p className="text-xs text-muted-foreground">films others are showing</p>
                              </CardContent>
                            </Card>
                            <Card>
                              <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">All Films Tracked</CardTitle>
                              </CardHeader>
                              <CardContent>
                                <div className="text-2xl font-bold">{complianceData.total_films}</div>
                                <p className="text-xs text-muted-foreground">including released</p>
                              </CardContent>
                            </Card>
                          </div>

                          {/* Films Table */}
                          <div className="rounded-md border max-h-[600px] overflow-auto">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Film</TableHead>
                                  <TableHead className="text-right">Release</TableHead>
                                  <TableHead className="text-right">Days Out</TableHead>
                                  <TableHead className="text-right">Circuits</TableHead>
                                  <TableHead className="text-right">Marcus Rank</TableHead>
                                  <TableHead className="text-right">Marcus Days Ahead</TableHead>
                                  <TableHead className="text-right">Avg Days Ahead</TableHead>
                                  <TableHead className="text-right">Delta</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {complianceData.films
                                  .filter((f) => f.days_until_release >= -7)
                                  .sort((a, b) => a.days_until_release - b.days_until_release)
                                  .map((film) => {
                                    const deltaColor =
                                      film.marcus_delta === null
                                        ? 'text-amber-500'
                                        : film.marcus_delta >= 0
                                        ? 'text-green-600'
                                        : film.marcus_delta < -3
                                        ? 'text-red-600 font-medium'
                                        : 'text-red-500';

                                    return (
                                      <TableRow key={film.film_title}>
                                        <TableCell className="font-medium max-w-[200px] truncate">
                                          {film.film_title}
                                        </TableCell>
                                        <TableCell className="text-right text-sm">
                                          {film.release_date}
                                        </TableCell>
                                        <TableCell className="text-right">
                                          <Badge
                                            variant={film.days_until_release > 0 ? 'default' : 'secondary'}
                                            className={
                                              film.days_until_release > 14
                                                ? 'bg-blue-100 text-blue-800'
                                                : film.days_until_release > 0
                                                ? 'bg-amber-100 text-amber-800'
                                                : ''
                                            }
                                          >
                                            {film.days_until_release > 0
                                              ? `${film.days_until_release}d`
                                              : 'Released'}
                                          </Badge>
                                        </TableCell>
                                        <TableCell className="text-right">{film.total_circuits}</TableCell>
                                        <TableCell className="text-right">
                                          {film.marcus_rank !== null ? (
                                            <span className={film.marcus_rank <= 3 ? 'text-green-600 font-medium' : ''}>
                                              #{film.marcus_rank}/{film.total_circuits}
                                            </span>
                                          ) : (
                                            <Badge variant="outline" className="text-amber-600 border-amber-300">
                                              Not Posting
                                            </Badge>
                                          )}
                                        </TableCell>
                                        <TableCell className="text-right font-mono">
                                          {film.marcus_days_ahead !== null ? `${film.marcus_days_ahead}d` : '—'}
                                        </TableCell>
                                        <TableCell className="text-right font-mono text-muted-foreground">
                                          {film.avg_days_ahead}d
                                        </TableCell>
                                        <TableCell className={`text-right font-mono ${deltaColor}`}>
                                          {film.marcus_delta !== null
                                            ? `${film.marcus_delta > 0 ? '+' : ''}${film.marcus_delta}d`
                                            : '—'}
                                        </TableCell>
                                      </TableRow>
                                    );
                                  })}
                              </TableBody>
                            </Table>
                          </div>

                          {/* Top Circuits Leaderboard */}
                          {upcoming.length > 0 && (
                            <Card>
                              <CardHeader>
                                <CardTitle className="text-sm font-medium">
                                  Top Circuits by Presale Posting (Next Film)
                                </CardTitle>
                              </CardHeader>
                              <CardContent>
                                {(() => {
                                  const nextFilm = upcoming[0];
                                  return (
                                    <div className="space-y-2">
                                      <p className="text-sm text-muted-foreground mb-3">
                                        <span className="font-medium">{nextFilm.film_title}</span>
                                        {' '}&mdash; releasing {nextFilm.release_date}
                                      </p>
                                      {nextFilm.circuit_ranking.slice(0, 10).map(([circuit, days], i) => {
                                        const isM = circuit.toLowerCase().includes('marcus') ||
                                                    circuit.toLowerCase().includes('movie tavern');
                                        return (
                                          <div
                                            key={circuit}
                                            className={`flex items-center justify-between text-sm py-1 px-2 rounded ${
                                              isM ? 'bg-blue-50 dark:bg-blue-950/30 font-medium' : ''
                                            }`}
                                          >
                                            <span>
                                              <span className="text-muted-foreground mr-2">#{i + 1}</span>
                                              {circuit}
                                              {isM && (
                                                <Badge variant="outline" className="ml-2 text-xs">Marcus</Badge>
                                              )}
                                            </span>
                                            <span className="font-mono">{days}d ahead</span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  );
                                })()}
                              </CardContent>
                            </Card>
                          )}
                        </>
                      );
                    })()}
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    <Target className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="font-medium">No Compliance Data Yet</p>
                    <p className="text-sm">
                      Run an EntTelligence sync to populate presale posting data.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts">
          <div className="grid grid-cols-2 gap-6">
            {/* Alert Configuration */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Settings className="h-5 w-5" />
                      Alert Configuration
                    </CardTitle>
                    <CardDescription>
                      Set up notifications for presale events
                    </CardDescription>
                  </div>
                  <Button onClick={() => setShowCreateAlertDialog(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    New Alert
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {watches.length === 0 ? (
                  <div className="text-center py-8">
                    <Bell className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-muted-foreground mb-4">
                      No alerts configured. Create an alert to get notified about presale events.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {watches.map((watch) => {
                      const typeInfo = getAlertTypeInfo(watch.alert_type);
                      return (
                        <div
                          key={watch.id}
                          className={`flex items-center justify-between p-3 border rounded-lg ${
                            watch.enabled ? '' : 'opacity-50'
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <typeInfo.icon className={`h-5 w-5 ${typeInfo.color}`} />
                            <div>
                              <p className="font-medium">{watch.film_title}</p>
                              <p className="text-sm text-muted-foreground">
                                {typeInfo.label}: {watch.threshold}
                                {watch.alert_type === 'velocity_drop' || watch.alert_type === 'velocity_spike' || watch.alert_type === 'market_share' ? '%' : ''}
                                {watch.alert_type === 'milestone' ? ' tickets' : ''}
                                {watch.alert_type === 'days_out' ? ' days' : ''}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {watch.trigger_count > 0 && (
                              <Badge variant="outline">{watch.trigger_count} triggers</Badge>
                            )}
                            <Switch
                              checked={watch.enabled}
                              onCheckedChange={() => handleToggleAlert(watch.id)}
                            />
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteAlert(watch.id)}
                            >
                              <Trash2 className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Notifications */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <BellRing className="h-5 w-5" />
                      Notifications
                    </CardTitle>
                    <CardDescription>
                      Recent alert triggers
                    </CardDescription>
                  </div>
                  {unreadNotifications.length > 0 && (
                    <Badge variant="secondary">{unreadNotifications.length} unread</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {notifications.length === 0 ? (
                  <div className="text-center py-8">
                    <CheckCircle2 className="h-12 w-12 mx-auto text-green-500 mb-4" />
                    <p className="text-muted-foreground">
                      No notifications. Alerts will appear here when triggered.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {notifications.map((notification) => (
                      <div
                        key={notification.id}
                        className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                          notification.is_read ? 'opacity-60' : 'bg-primary/5 border-primary/30'
                        }`}
                        onClick={() => handleMarkNotificationRead(notification.id)}
                      >
                        <div className="flex items-start gap-3">
                          {notification.severity === 'critical' ? (
                            <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5" />
                          ) : notification.severity === 'warning' ? (
                            <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
                          ) : (
                            <Bell className="h-5 w-5 text-blue-500 mt-0.5" />
                          )}
                          <div className="flex-1">
                            <p className="font-medium">{notification.film_title}</p>
                            <p className="text-sm text-muted-foreground">{notification.message}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              {new Date(notification.triggered_at).toLocaleString()}
                            </p>
                          </div>
                          {!notification.is_read && (
                            <div className="h-2 w-2 bg-primary rounded-full" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Create Alert Dialog */}
      <Dialog open={showCreateAlertDialog} onOpenChange={setShowCreateAlertDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Alert</DialogTitle>
            <DialogDescription>
              Configure a new presale alert notification
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="alert-film">Film</Label>
              <Select
                value={newAlert.film_title}
                onValueChange={(v) => setNewAlert({ ...newAlert, film_title: v })}
              >
                <SelectTrigger id="alert-film" className="mt-1">
                  <SelectValue placeholder="Select film or All Films" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="All Films">All Films</SelectItem>
                  {films?.map((film) => (
                    <SelectItem key={film.film_title} value={film.film_title}>
                      {film.film_title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="alert-type">Alert Type</Label>
              <Select
                value={newAlert.alert_type}
                onValueChange={(v) => setNewAlert({ ...newAlert, alert_type: v as PresaleWatch['alert_type'] })}
              >
                <SelectTrigger id="alert-type" className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="velocity_drop">Velocity Drop</SelectItem>
                  <SelectItem value="velocity_spike">Velocity Spike</SelectItem>
                  <SelectItem value="milestone">Ticket Milestone</SelectItem>
                  <SelectItem value="days_out">Days Before Release</SelectItem>
                  <SelectItem value="market_share">Market Share Change</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="alert-threshold">
                Threshold
                {newAlert.alert_type === 'velocity_drop' && ' (% decrease)'}
                {newAlert.alert_type === 'velocity_spike' && ' (% increase)'}
                {newAlert.alert_type === 'milestone' && ' (ticket count)'}
                {newAlert.alert_type === 'days_out' && ' (days)'}
                {newAlert.alert_type === 'market_share' && ' (% change)'}
              </Label>
              <Input
                id="alert-threshold"
                type="number"
                value={newAlert.threshold}
                onChange={(e) => setNewAlert({ ...newAlert, threshold: Number(e.target.value) })}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {newAlert.alert_type === 'velocity_drop' && 'Alert when velocity drops by this percentage'}
                {newAlert.alert_type === 'velocity_spike' && 'Alert when velocity increases by this percentage'}
                {newAlert.alert_type === 'milestone' && 'Alert when ticket count reaches this number'}
                {newAlert.alert_type === 'days_out' && 'Alert when film is this many days from release'}
                {newAlert.alert_type === 'market_share' && 'Alert when Marcus market share changes by this percentage'}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateAlertDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateAlert}>
              Create Alert
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
