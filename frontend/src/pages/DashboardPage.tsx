import { useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Bell,
  DollarSign,
  TrendingUp,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight,
  Calendar,
  Loader2,
  Building2
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useNavigate } from 'react-router-dom';
import { usePendingAlerts, useAlertSummary } from '@/hooks/api/usePriceAlerts';
import { useDashboardStats, useScrapeActivity } from '@/hooks/api/useAnalytics';
import { formatDistanceToNow, parseISO, format, subDays } from 'date-fns';

// Helper to format large numbers
const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toLocaleString();
};

// Helper to determine severity color based on alert type
const getSeverityColor = (type: string) => {
  const t = type.toLowerCase();
  if (t.includes('surge') || t.includes('increase')) return 'bg-rose-500';
  if (t.includes('new') || t.includes('offering')) return 'bg-amber-500';
  return 'bg-emerald-500';
};

export function DashboardPage() {
  const navigate = useNavigate();
  const [dateRange, setDateRange] = useState(30);

  // Fetch real data
  const { data: dashboardStats } = useDashboardStats(dateRange);
  const { data: scrapeActivity, isLoading: activityLoading } = useScrapeActivity(dateRange);
  const { data: alertsData, isLoading: alertsLoading } = usePendingAlerts(5);
  const { data: summaryData } = useAlertSummary();
  const recentAlerts = alertsData?.alerts || [];

  // Build chart data from API response
  const chartData = useMemo(() => {
    if (!scrapeActivity) {
      return [
        { name: 'Mon', value: 0 },
        { name: 'Tue', value: 0 },
        { name: 'Wed', value: 0 },
        { name: 'Thu', value: 0 },
        { name: 'Fri', value: 0 },
        { name: 'Sat', value: 0 },
        { name: 'Sun', value: 0 },
      ];
    }
    return scrapeActivity.map(entry => ({
      name: entry.day_name,
      value: entry.records_scraped,
      scrapes: entry.scrape_count
    }));
  }, [scrapeActivity]);

  // Build dynamic stats from API
  const dynamicStats = useMemo(() => {
    const stats = dashboardStats;
    return [
      {
        title: 'Total Price Checks',
        value: stats ? formatNumber(stats.total_price_checks) : '—',
        change: stats ? `${stats.price_checks_change_pct >= 0 ? '+' : ''}${stats.price_checks_change_pct}%` : '—',
        trend: stats && stats.price_checks_change_pct >= 0 ? 'up' : 'down',
        icon: DollarSign,
        color: 'text-emerald-500',
        bg: 'bg-emerald-500/10',
        path: '/price-checks'
      },
      {
        title: 'Active Alerts',
        value: summaryData?.total_pending?.toString() || '0',
        change: summaryData?.total_pending === 0 ? 'All clear' : `+${summaryData?.total_pending} active`,
        trend: summaryData && summaryData.total_pending > 0 ? 'up' : 'down',
        icon: Bell,
        color: 'text-amber-500',
        bg: 'bg-amber-500/10',
        path: '/price-alerts'
      },
      {
        title: 'Theaters Tracked',
        value: stats ? stats.total_theaters.toString() : '—',
        change: `${stats?.total_films || 0} films`,
        trend: 'up',
        icon: Building2,
        color: 'text-cyan-500',
        bg: 'bg-cyan-500/10',
        path: '/admin/system-health'
      },
      {
        title: 'Avg Price Change',
        value: stats ? `${stats.price_change_pct >= 0 ? '+' : ''}${stats.price_change_pct}%` : '—',
        change: 'vs last period',
        trend: stats && stats.price_change_pct >= 0 ? 'up' : 'down',
        icon: TrendingUp,
        color: 'text-rose-500',
        bg: 'bg-rose-500/10',
        path: '/historical-data'
      },
    ];
  }, [dashboardStats, summaryData]);

  // Date range for display
  const dateRangeLabel = useMemo(() => {
    const end = new Date();
    const start = subDays(end, dateRange);
    return `${format(start, 'MMM dd')} - ${format(end, 'MMM dd')}`;
  }, [dateRange]);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight">Intelligence Dashboard</h1>
          <p className="text-muted-foreground text-lg">
            Real-time market insights and competitive pricing metrics.
          </p>
        </div>
        <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setDateRange(dateRange === 30 ? 7 : 30)}>
                <Calendar className="mr-2 h-4 w-4" />
                {dateRangeLabel}
            </Button>
            <Button size="sm" onClick={() => window.location.reload()}>
                <Zap className="mr-2 h-4 w-4" />
                Refresh Data
            </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {dynamicStats.map((stat) => (
          <Card 
            key={stat.title} 
            className="relative overflow-hidden border-none shadow-lg bg-card/50 backdrop-blur-sm cursor-pointer hover:bg-card/80 transition-all hover:scale-[1.02] active:scale-[0.98] group"
            onClick={() => navigate(stat.path)}
          >
            <div className={`absolute top-0 left-0 w-1 h-full ${stat.color.replace('text-', 'bg-')}`} />
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 text-white/90">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider group-hover:text-primary transition-colors">
                {stat.title}
              </CardTitle>
              <div className={`p-2 rounded-lg ${stat.bg}`}>
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stat.value}</div>
              <div className="flex items-center mt-1">
                {stat.trend === 'up' ? (
                  <ArrowUpRight className="h-4 w-4 text-emerald-500 mr-1" />
                ) : (
                  <ArrowDownRight className="h-4 w-4 text-rose-500 mr-1" />
                )}
                <span className={`text-xs font-medium ${stat.trend === 'up' ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {stat.change}
                </span>
                <span className="text-xs text-muted-foreground ml-2 whitespace-nowrap">vs last {dateRange}d</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-7">
        {/* Main Chart */}
        <Card className="md:col-span-4 border-none shadow-xl bg-card/50">
          <CardHeader>
            <CardTitle>Scrape Volume & Activity</CardTitle>
            <CardDescription>Records scraped by day of week (last {dateRange} days)</CardDescription>
          </CardHeader>
          <CardContent className="h-[350px]">
            {activityLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--muted-foreground)/0.1)" />
                <XAxis 
                    dataKey="name" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
                />
                <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
                />
                <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)', backgroundColor: 'hsl(var(--card))' }}
                />
                <Area 
                    type="monotone" 
                    dataKey="value" 
                    stroke="hsl(var(--primary))" 
                    strokeWidth={4} 
                    fillOpacity={1} 
                    fill="url(#colorValue)" 
                />
              </AreaChart>
            </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Live Feed */}
        <Card className="md:col-span-3 border-none shadow-xl bg-card/50">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
                <CardTitle>Security & Live Alerts</CardTitle>
                <CardDescription>Critical changes requiring immediate attention.</CardDescription>
            </div>
            <Badge variant="outline" className="animate-pulse bg-rose-500/10 text-rose-500 border-rose-500/20">
                LIVE
            </Badge>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {alertsLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="h-8 w-8 animate-spin mb-2" />
                  <p className="text-sm">Loading alerts...</p>
                </div>
              ) : recentAlerts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-center">
                  <Bell className="h-8 w-8 mb-2 opacity-20" />
                  <p className="text-sm">No active alerts</p>
                  <p className="text-xs opacity-60">System is stable.</p>
                </div>
              ) : (
                recentAlerts.map((alert) => (
                  <div 
                      key={alert.alert_id} 
                      className="flex items-start gap-4 p-3 rounded-xl hover:bg-muted/50 transition-colors cursor-pointer group"
                      onClick={() => navigate('/price-alerts')}
                  >
                    <div className={`mt-1 h-3 w-3 rounded-full shrink-0 ${getSeverityColor(alert.alert_type)}`} />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                          <p className="text-sm font-semibold">{alert.alert_type}</p>
                          <span className="text-[10px] text-muted-foreground uppercase">
                            {formatDistanceToNow(parseISO(alert.triggered_at), { addSuffix: true })}
                          </span>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-1">
                          {alert.theater_name} {alert.film_title ? `• ${alert.film_title}` : ''}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                ))
              )}
              <Button 
                variant="ghost" 
                className="w-full text-xs text-muted-foreground hover:text-primary"
                onClick={() => navigate('/admin/audit-log')}
              >
                View All Security Logs
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
