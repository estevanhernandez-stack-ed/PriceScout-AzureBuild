import { useState, useMemo } from 'react';
import { useMarketsHierarchy, usePriceChecks, usePriceComparison, usePLFDistribution, useAnalyticsPriceTrends } from '@/hooks/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  History,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Building2,
  Film,
  Download,
  RefreshCw,
  Search,
  BarChart3,
  LineChart,
  AlertTriangle,
  Trophy,
  Eye,
  Filter,
  PieChart,
} from 'lucide-react';
import { 
  LineChart as ReLineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as ReTooltip, 
  ResponsiveContainer, 
  Legend,
  BarChart as ReBarChart,
  Bar
} from 'recharts';
import { format, subDays } from 'date-fns';

type AnalysisType = 'prices' | 'films' | 'glance' | 'plf';
type DateRange = '7d' | '30d' | '90d' | '1y';
type DaypartFilter = 'all' | 'matinee' | 'evening';
type FormatFilter = 'all' | 'standard' | 'imax' | 'dolby' | '3d' | 'plf';

const DATE_RANGE_DAYS: Record<DateRange, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
  '1y': 365,
};

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

// Detect if price is PLF
const isPLF = (formatStr?: string | null) => {
  if (!formatStr) return false;
  const lower = formatStr.toLowerCase();
  return lower.includes('imax') || lower.includes('dolby') ||
         lower.includes('atmos') || lower.includes('4dx') ||
         lower.includes('d-box') || lower.includes('premium');
};

// Determine daypart from showtime
const getDaypart = (showtime: string): 'matinee' | 'evening' => {
  try {
    const timePart = showtime.split(' ').pop() || showtime;
    const [hours] = timePart.split(':').map(Number);
    const isPM = showtime.toLowerCase().includes('pm');
    const hour24 = isPM && hours !== 12 ? hours + 12 : hours;
    return hour24 < 17 ? 'matinee' : 'evening';
  } catch {
    return 'evening';
  }
};

export function HistoricalDataPage() {
  // Analysis type selection
  const [analysisType, setAnalysisType] = useState<AnalysisType>('prices');

  // Hierarchy selection
  const [selectedCompany, setSelectedCompany] = useState<string>('');
  const [selectedDirector, setSelectedDirector] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedTheaters, setSelectedTheaters] = useState<string[]>([]);

  // Filters
  const [dateRange, setDateRange] = useState<DateRange>('30d');
  const [searchQuery, setSearchQuery] = useState('');
  const [daypartFilter, setDaypartFilter] = useState<DaypartFilter>('all');
  const [formatFilter, setFormatFilter] = useState<FormatFilter>('all');
  const [ticketTypeFilter, setTicketTypeFilter] = useState<string>('all');

  const { data: hierarchyData, isLoading: hierarchyLoading } = useMarketsHierarchy();

  const dateFrom = format(subDays(new Date(), DATE_RANGE_DAYS[dateRange]), 'yyyy-MM-dd');
  const dateTo = format(new Date(), 'yyyy-MM-dd'); // Fetch data
  const {
    data: priceChecksData,
    isLoading: priceChecksLoading,
  } = usePriceChecks({
    theaterName: selectedTheaters.length === 1 ? selectedTheaters[0] : undefined,
    dateFrom,
    dateTo,
    limit: 500,
  });

  // Get price comparison
  const {
    data: comparisonData,
    isLoading: comparisonLoading,
  } = usePriceComparison({
    market: selectedMarket || undefined,
    days: DATE_RANGE_DAYS[dateRange],
  });

  // Get specialized analytics data
  const {
    data: plfDistributionData,
    isLoading: plfDistributionLoading,
  } = usePLFDistribution({
    market: selectedMarket || undefined,
    days: DATE_RANGE_DAYS[dateRange],
  });

  const {
    data: analyticsTrendData,
    isLoading: analyticsTrendLoading,
  } = useAnalyticsPriceTrends(
    selectedTheaters.length === 1 ? selectedTheaters[0] : '',
    DATE_RANGE_DAYS[dateRange]
  );

  // Get price history for selected theater (DEPRECATED - using analyticsTrendData)

  // Build hierarchy dropdowns
  const companies = useMemo(() => {
    if (!hierarchyData) return [];
    return Object.keys(hierarchyData).sort();
  }, [hierarchyData]);

  const directors = useMemo(() => {
    if (!hierarchyData || !selectedCompany) return [];
    return Object.keys(hierarchyData[selectedCompany] || {}).sort();
  }, [hierarchyData, selectedCompany]);

  const markets = useMemo(() => {
    if (!hierarchyData || !selectedCompany || !selectedDirector) return [];
    return Object.keys(hierarchyData[selectedCompany]?.[selectedDirector] || {}).sort();
  }, [hierarchyData, selectedCompany, selectedDirector]);

  const theatersInMarket = useMemo(() => {
    if (!hierarchyData || !selectedCompany || !selectedDirector || !selectedMarket) return [];
    return hierarchyData[selectedCompany]?.[selectedDirector]?.[selectedMarket]?.theaters || [];
  }, [hierarchyData, selectedCompany, selectedDirector, selectedMarket]);

  // Get unique ticket types from data
  const ticketTypes = useMemo(() => {
    const checks = priceChecksData?.price_checks || [];
    return ['all', ...new Set(checks.map(c => c.ticket_type))].sort();
  }, [priceChecksData]);

  // Filter and process price data
  const filteredPrices = useMemo(() => {
    let checks = priceChecksData?.price_checks || [];

    // Search filter
    if (searchQuery) {
      checks = checks.filter(
        (entry) =>
          entry.theater_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          entry.film_title.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Format filter
    if (formatFilter !== 'all') {
      checks = checks.filter(entry => {
        const fmt = (entry.format || '').toLowerCase();
        switch (formatFilter) {
          case 'imax': return fmt.includes('imax');
          case 'dolby': return fmt.includes('dolby') || fmt.includes('atmos');
          case '3d': return fmt.includes('3d');
          case 'plf': return isPLF(entry.format);
          case 'standard': return !isPLF(entry.format);
          default: return true;
        }
      });
    }

    // Ticket type filter
    if (ticketTypeFilter !== 'all') {
      checks = checks.filter(entry => entry.ticket_type === ticketTypeFilter);
    }

    // Daypart filter
    if (daypartFilter !== 'all') {
      checks = checks.filter(entry => getDaypart(entry.showtime) === daypartFilter);
    }

    return checks;
  }, [priceChecksData, searchQuery, formatFilter, ticketTypeFilter, daypartFilter]);

  // Calculate summary stats
  const summaryStats = useMemo(() => {
    const checks = filteredPrices;

    if (checks.length === 0) {
      return {
        avgPrice: 0,
        minPrice: 0,
        maxPrice: 0,
        priceCount: 0,
        theatersTracked: 0,
        filmsTracked: 0,
        plfPct: 0,
      };
    }

    const prices = checks.map(c => c.price);
    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const uniqueTheaters = new Set(checks.map(c => c.theater_name)).size;
    const uniqueFilms = new Set(checks.map(c => c.film_title)).size;
    const plfCount = checks.filter(c => isPLF(c.format)).length;

    return {
      avgPrice,
      minPrice,
      maxPrice,
      priceCount: checks.length,
      theatersTracked: uniqueTheaters,
      filmsTracked: uniqueFilms,
      plfPct: (plfCount / checks.length) * 100,
    };
  }, [filteredPrices]);

  // Film analysis data
  const filmAnalysis = useMemo(() => {
    const checks = filteredPrices;
    if (checks.length === 0) return null;

    // Group by film
    const byFilm: Record<string, { showings: number; totalPrice: number; theaters: Set<string>; formats: Set<string> }> = {};
    checks.forEach(c => {
      if (!byFilm[c.film_title]) {
        byFilm[c.film_title] = { showings: 0, totalPrice: 0, theaters: new Set(), formats: new Set() };
      }
      byFilm[c.film_title].showings++;
      byFilm[c.film_title].totalPrice += c.price;
      byFilm[c.film_title].theaters.add(c.theater_name);
      if (c.format) byFilm[c.film_title].formats.add(c.format);
    });

    const films = Object.entries(byFilm)
      .map(([title, data]) => ({
        title,
        showings: data.showings,
        avgPrice: data.totalPrice / data.showings,
        theaterCount: data.theaters.size,
        formats: Array.from(data.formats),
        hasPLF: Array.from(data.formats).some(f => isPLF(f)),
      }))
      .sort((a, b) => b.showings - a.showings);

    // Calculate top stats
    const topFilm = films[0];
    const avgShowingsPerFilm = films.reduce((sum, f) => sum + f.showings, 0) / films.length;

    return {
      films: films.slice(0, 20),
      topFilm,
      totalFilms: films.length,
      avgShowingsPerFilm,
    };
  }, [filteredPrices]);

  // "At a Glance" market pricing
  const atAGlanceData = useMemo(() => {
    const checks = filteredPrices;
    if (checks.length === 0) return null;

    // Group by theater → ticket type → daypart
    const byTheater: Record<string, {
      matinee: Record<string, { prices: number[]; formats: string[] }>;
      evening: Record<string, { prices: number[]; formats: string[] }>;
      company?: string;
    }> = {};

    checks.forEach(c => {
      if (!byTheater[c.theater_name]) {
        byTheater[c.theater_name] = { matinee: {}, evening: {} };
      }

      const daypart = getDaypart(c.showtime);
      const ticketKey = isPLF(c.format) ? `${c.ticket_type} (PLF)` : c.ticket_type;

      if (!byTheater[c.theater_name][daypart][ticketKey]) {
        byTheater[c.theater_name][daypart][ticketKey] = { prices: [], formats: [] };
      }
      byTheater[c.theater_name][daypart][ticketKey].prices.push(c.price);
      if (c.format) byTheater[c.theater_name][daypart][ticketKey].formats.push(c.format);
    });

    // Build report rows
    const rows = Object.entries(byTheater).map(([theater, data]) => {
      const getDisplayPrice = (daypart: 'matinee' | 'evening', ticketType: string) => {
        const entry = data[daypart][ticketType];
        if (!entry) return null;
        const uniquePrices = [...new Set(entry.prices)].sort((a, b) => a - b);
        const hasSurcharge = uniquePrices.length > 1;
        return {
          prices: uniquePrices,
          hasSurcharge,
          avgPrice: entry.prices.reduce((a, b) => a + b, 0) / entry.prices.length,
        };
      };

      // Find all ticket types for this theater
      const allTicketTypes = new Set([
        ...Object.keys(data.matinee),
        ...Object.keys(data.evening),
      ]);

      return {
        theater,
        ticketTypes: Array.from(allTicketTypes),
        matinee: data.matinee,
        evening: data.evening,
        getDisplayPrice,
      };
    });

    return { rows };
  }, [filteredPrices]);



  // Export handlers
  const handleExportCsv = () => {
    if (filteredPrices.length === 0) return;

    const headers = ['Date', 'Theater', 'Film', 'Format', 'Ticket Type', 'Showtime', 'Daypart', 'Price', 'PLF'];
    const rows = filteredPrices.map(c => [
      c.play_date,
      c.theater_name,
      c.film_title,
      c.format || 'Standard',
      c.ticket_type,
      c.showtime,
      getDaypart(c.showtime),
      c.price.toFixed(2),
      isPLF(c.format) ? 'Yes' : 'No',
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.map(cell => `"${cell}"`).join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `historical-data-${analysisType}-${dateRange}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (hierarchyLoading) {
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
          <h1 className="text-3xl font-bold tracking-tight">Historical Data & Analysis</h1>
          <p className="text-muted-foreground">
            Analyze pricing trends, film performance, and market comparisons
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleExportCsv} disabled={filteredPrices.length === 0}>
            <Download className="mr-2 h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Analysis Type Selection */}
      <div className="flex gap-2">
        <Button
          variant={analysisType === 'prices' ? 'default' : 'outline'}
          onClick={() => setAnalysisType('prices')}
        >
          <DollarSign className="mr-2 h-4 w-4" />
          Price Analysis
        </Button>
        <Button
          variant={analysisType === 'films' ? 'default' : 'outline'}
          onClick={() => setAnalysisType('films')}
        >
          <Film className="mr-2 h-4 w-4" />
          Film Analysis
        </Button>
        <Button
          variant={analysisType === 'glance' ? 'default' : 'outline'}
          onClick={() => setAnalysisType('glance')}
        >
          <Eye className="mr-2 h-4 w-4" />
          At a Glance
        </Button>
        <Button
          variant={analysisType === 'plf' ? 'default' : 'outline'}
          onClick={() => setAnalysisType('plf')}
        >
          <PieChart className="mr-2 h-4 w-4" />
          PLF Distribution
        </Button>
      </div>

      {/* Scope Selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Define Scope
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-4">
            {/* Company */}
            <div>
              <Label htmlFor="company">Company</Label>
              <select
                id="company"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={selectedCompany}
                onChange={(e) => {
                  setSelectedCompany(e.target.value);
                  setSelectedDirector('');
                  setSelectedMarket('');
                  setSelectedTheaters([]);
                }}
              >
                <option value="">All Companies</option>
                {companies.map((company) => (
                  <option key={company} value={company}>
                    {company} {isMarcusCompany(company) ? '⭐' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Director */}
            <div>
              <Label htmlFor="director">Director</Label>
              <select
                id="director"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={selectedDirector}
                onChange={(e) => {
                  setSelectedDirector(e.target.value);
                  setSelectedMarket('');
                  setSelectedTheaters([]);
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

            {/* Market */}
            <div>
              <Label htmlFor="market">Market</Label>
              <select
                id="market"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={selectedMarket}
                onChange={(e) => {
                  setSelectedMarket(e.target.value);
                  setSelectedTheaters([]);
                }}
                disabled={!selectedDirector}
              >
                <option value="">Select Market</option>
                {markets.map((market) => (
                  <option key={market} value={market}>
                    {market}
                  </option>
                ))}
              </select>
            </div>

            {/* Theater */}
            <div>
              <Label htmlFor="theater">Theater</Label>
              <select
                id="theater"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={selectedTheaters[0] || ''}
                onChange={(e) => setSelectedTheaters(e.target.value ? [e.target.value] : [])}
                disabled={!selectedMarket}
              >
                <option value="">All Theaters</option>
                {theatersInMarket.map((theater) => (
                  <option key={theater.name} value={theater.name}>
                    {theater.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Date Range */}
            <div>
              <Label>Date Range</Label>
              <div className="flex gap-1 mt-1">
                {(['7d', '30d', '90d', '1y'] as const).map((range) => (
                  <Button
                    key={range}
                    variant={dateRange === range ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setDateRange(range)}
                    className="flex-1"
                  >
                    {range === '7d' ? '7D' : range === '30d' ? '30D' : range === '90d' ? '90D' : '1Y'}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          {/* Post-Report Filters */}
          <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t">
            <div>
              <Label htmlFor="search">Search</Label>
              <div className="relative mt-1">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="search"
                  placeholder="Theater or film..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="daypart">Daypart</Label>
              <select
                id="daypart"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={daypartFilter}
                onChange={(e) => setDaypartFilter(e.target.value as DaypartFilter)}
              >
                <option value="all">All Dayparts</option>
                <option value="matinee">Matinee (before 5PM)</option>
                <option value="evening">Evening (5PM+)</option>
              </select>
            </div>
            <div>
              <Label htmlFor="format">Format</Label>
              <select
                id="format"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={formatFilter}
                onChange={(e) => setFormatFilter(e.target.value as FormatFilter)}
              >
                <option value="all">All Formats</option>
                <option value="standard">Standard Only</option>
                <option value="imax">IMAX</option>
                <option value="dolby">Dolby Cinema</option>
                <option value="3d">3D</option>
                <option value="plf">All PLF</option>
              </select>
            </div>
            <div>
              <Label htmlFor="ticketType">Ticket Type</Label>
              <select
                id="ticketType"
                className="w-full mt-1 p-2 border rounded-md bg-background"
                value={ticketTypeFilter}
                onChange={(e) => setTicketTypeFilter(e.target.value)}
              >
                {ticketTypes.map((type) => (
                  <option key={type} value={type}>
                    {type === 'all' ? 'All Types' : type}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary Stats */}
      <div className="grid grid-cols-6 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Avg Price</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.avgPrice > 0 ? `$${summaryStats.avgPrice.toFixed(2)}` : 'N/A'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-green-500" />
              <span className="text-xs text-muted-foreground">Min Price</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.minPrice > 0 ? `$${summaryStats.minPrice.toFixed(2)}` : 'N/A'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-red-500" />
              <span className="text-xs text-muted-foreground">Max Price</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.maxPrice > 0 ? `$${summaryStats.maxPrice.toFixed(2)}` : 'N/A'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Records</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.priceCount.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Theaters</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.theatersTracked}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Film className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">PLF %</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.plfPct.toFixed(1)}%</p>
          </CardContent>
        </Card>
      </div>

      {/* Content based on analysis type */}
      {analysisType === 'prices' && (
        <Tabs defaultValue="history" className="space-y-4">
          <TabsList>
            <TabsTrigger value="history">
              <History className="h-4 w-4 mr-1" />
              Price Records
            </TabsTrigger>
            <TabsTrigger value="trends">
              <LineChart className="h-4 w-4 mr-1" />
              Trends
            </TabsTrigger>
            <TabsTrigger value="comparison">
              <BarChart3 className="h-4 w-4 mr-1" />
              Market Comparison
            </TabsTrigger>
          </TabsList>

          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>Recent Price Data</CardTitle>
                <CardDescription>
                  {filteredPrices.length} records in selected period
                </CardDescription>
              </CardHeader>
              <CardContent>
                {priceChecksLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredPrices.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    No price data found. Run some price scrapes or adjust your filters.
                  </p>
                ) : (
                  <div className="max-h-[500px] overflow-y-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Date</TableHead>
                          <TableHead>Theater</TableHead>
                          <TableHead>Film</TableHead>
                          <TableHead>Format</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Daypart</TableHead>
                          <TableHead className="text-right">Price</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredPrices.slice(0, 100).map((entry, i) => (
                          <TableRow key={`${entry.theater_name}-${entry.film_title}-${entry.showtime}-${i}`}>
                            <TableCell className="text-muted-foreground">{entry.play_date}</TableCell>
                            <TableCell className="font-medium">{entry.theater_name}</TableCell>
                            <TableCell>{entry.film_title}</TableCell>
                            <TableCell>
                              <span className="mr-1">{getFormatEmoji(entry.format || 'Standard')}</span>
                              {entry.format || 'Standard'}
                              {isPLF(entry.format) && (
                                <Badge className="ml-1 bg-purple-500/10 text-purple-500" variant="outline">PLF</Badge>
                              )}
                            </TableCell>
                            <TableCell>
                              <Badge variant="secondary">{entry.ticket_type}</Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">
                                {getDaypart(entry.showtime) === 'matinee' ? '🌅 Matinee' : '🌙 Evening'}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right font-bold">${entry.price.toFixed(2)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    {filteredPrices.length > 100 && (
                      <p className="text-center text-muted-foreground py-2 text-sm">
                        Showing first 100 of {filteredPrices.length} records
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="trends">
            <Card>
              <CardHeader>
                <CardTitle>Price Trends</CardTitle>
                <CardDescription>
                  {selectedTheaters.length === 1
                    ? `Daily averages for ${selectedTheaters[0]}`
                    : 'Select a specific theater to view detailed trends'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {selectedTheaters.length !== 1 ? (
                  <p className="text-center text-muted-foreground py-8">
                    Select a specific theater to view price trends.
                  </p>
                ) : analyticsTrendLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : !analyticsTrendData || analyticsTrendData.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    No trend data available for this theater.
                  </p>
                ) : (
                  <div className="h-[400px] w-full mt-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <ReLineChart data={analyticsTrendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#333" />
                        <XAxis 
                          dataKey="date" 
                          stroke="#888" 
                          fontSize={12}
                          tickFormatter={(val) => format(new Date(val), 'MMM d')}
                        />
                        <YAxis 
                          stroke="#888" 
                          fontSize={12} 
                          tickFormatter={(val) => `$${val}`}
                          domain={['auto', 'auto']}
                        />
                        <ReTooltip 
                          contentStyle={{ backgroundColor: '#1f1f1f', border: '1px solid #333' }}
                          labelStyle={{ color: '#888' }}
                          formatter={(value: number) => [`$${value.toFixed(2)}`, '']}
                        />
                        <Legend />
                        <Line 
                          type="monotone" 
                          dataKey="standard_avg" 
                          name="Standard 2D" 
                          stroke="#8884d8" 
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          activeDot={{ r: 6 }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="plf_avg" 
                          name="All PLF" 
                          stroke="#ffc658" 
                          strokeWidth={2}
                          dot={{ r: 4 }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="imax_avg" 
                          name="IMAX" 
                          stroke="#82ca9d" 
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          connectNulls
                        />
                        <Line 
                          type="monotone" 
                          dataKey="dolby_avg" 
                          name="Dolby" 
                          stroke="#ff7300" 
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          connectNulls
                        />
                      </ReLineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="comparison">
            <Card>
              <CardHeader>
                <CardTitle>Market Comparison</CardTitle>
                <CardDescription>Compare pricing across theaters</CardDescription>
              </CardHeader>
              <CardContent>
                {comparisonLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : !comparisonData || comparisonData.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    No comparison data available.
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Theater</TableHead>
                        <TableHead>Ticket Type</TableHead>
                        <TableHead className="text-right">Avg Price</TableHead>
                        <TableHead className="text-right">Records</TableHead>
                        <TableHead className="text-right">vs Market</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparisonData.map((comp, i) => (
                        <TableRow key={`${comp.theater_name}-${comp.ticket_type}-${i}`}>
                          <TableCell className="font-medium">{comp.theater_name}</TableCell>
                          <TableCell>
                            <Badge variant="secondary">{comp.ticket_type}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-bold">${comp.avg_price.toFixed(2)}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{comp.price_count}</TableCell>
                          <TableCell className="text-right">
                            {comp.vs_market_avg !== null && comp.vs_market_avg !== undefined && (
                              <Badge
                                className={
                                  comp.vs_market_avg >= 0
                                    ? 'bg-red-500/10 text-red-500'
                                    : 'bg-green-500/10 text-green-500'
                                }
                              >
                                {comp.vs_market_avg >= 0 ? '+' : ''}{comp.vs_market_avg.toFixed(1)}%
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {analysisType === 'films' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Film className="h-5 w-5" />
              Film Performance Analysis
            </CardTitle>
            <CardDescription>
              Analyze film distribution, pricing, and format mix
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!filmAnalysis ? (
              <p className="text-center text-muted-foreground py-8">
                No film data available for the selected criteria.
              </p>
            ) : (
              <div className="space-y-6">
                {/* Top film highlight */}
                {filmAnalysis.topFilm && (
                  <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Trophy className="h-6 w-6 text-yellow-500" />
                      <div>
                        <p className="font-semibold">Top Film: {filmAnalysis.topFilm.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {filmAnalysis.topFilm.showings} showings • ${filmAnalysis.topFilm.avgPrice.toFixed(2)} avg • {filmAnalysis.topFilm.theaterCount} theaters
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Summary stats */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-4 bg-muted/50 rounded-lg text-center">
                    <p className="text-3xl font-bold">{filmAnalysis.totalFilms}</p>
                    <p className="text-sm text-muted-foreground">Total Films</p>
                  </div>
                  <div className="p-4 bg-muted/50 rounded-lg text-center">
                    <p className="text-3xl font-bold">{filmAnalysis.avgShowingsPerFilm.toFixed(1)}</p>
                    <p className="text-sm text-muted-foreground">Avg Showings/Film</p>
                  </div>
                  <div className="p-4 bg-muted/50 rounded-lg text-center">
                    <p className="text-3xl font-bold">
                      {filmAnalysis.films.filter(f => f.hasPLF).length}
                    </p>
                    <p className="text-sm text-muted-foreground">Films with PLF</p>
                  </div>
                </div>

                {/* Film table */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rank</TableHead>
                      <TableHead>Film</TableHead>
                      <TableHead className="text-right">Showings</TableHead>
                      <TableHead className="text-right">Avg Price</TableHead>
                      <TableHead className="text-right">Theaters</TableHead>
                      <TableHead>Formats</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filmAnalysis.films.map((film, idx) => (
                      <TableRow key={film.title}>
                        <TableCell>
                          {idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `#${idx + 1}`}
                        </TableCell>
                        <TableCell className="font-medium">{film.title}</TableCell>
                        <TableCell className="text-right font-bold">{film.showings}</TableCell>
                        <TableCell className="text-right">${film.avgPrice.toFixed(2)}</TableCell>
                        <TableCell className="text-right">{film.theaterCount}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {film.formats.slice(0, 3).map(fmt => (
                              <span key={fmt} title={fmt}>{getFormatEmoji(fmt)}</span>
                            ))}
                            {film.formats.length > 3 && (
                              <span className="text-muted-foreground">+{film.formats.length - 3}</span>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {analysisType === 'glance' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5" />
              Market At a Glance
            </CardTitle>
            <CardDescription>
              Quick view of pricing by theater, ticket type, and daypart
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!atAGlanceData || atAGlanceData.rows.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">
                No data available. Select a market or run some scrapes.
              </p>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <AlertTriangle className="h-4 w-4 text-yellow-500" />
                  Yellow highlighting indicates potential surcharge pricing (multiple prices for same daypart/type)
                </div>

                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Theater</TableHead>
                        <TableHead>Ticket Type</TableHead>
                        <TableHead className="text-center">🌅 Matinee</TableHead>
                        <TableHead className="text-center">🌙 Evening</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {atAGlanceData.rows.flatMap(row =>
                        row.ticketTypes.map((ticketType, idx) => {
                          const matinee = row.getDisplayPrice('matinee', ticketType);
                          const evening = row.getDisplayPrice('evening', ticketType);

                          return (
                            <TableRow key={`${row.theater}-${ticketType}`}>
                              {idx === 0 && (
                                <TableCell
                                  rowSpan={row.ticketTypes.length}
                                  className="font-medium align-top"
                                >
                                  {row.theater}
                                </TableCell>
                              )}
                              <TableCell>
                                <Badge variant="secondary">{ticketType}</Badge>
                              </TableCell>
                              <TableCell className={`text-center ${matinee?.hasSurcharge ? 'bg-yellow-500/10' : ''}`}>
                                {matinee ? (
                                  <div>
                                    <span className="font-bold">
                                      {matinee.prices.length === 1
                                        ? `$${matinee.prices[0].toFixed(2)}`
                                        : `$${matinee.prices[0].toFixed(2)} - $${matinee.prices[matinee.prices.length - 1].toFixed(2)}`}
                                    </span>
                                    {matinee.hasSurcharge && (
                                      <AlertTriangle className="h-3 w-3 inline ml-1 text-yellow-500" />
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className={`text-center ${evening?.hasSurcharge ? 'bg-yellow-500/10' : ''}`}>
                                {evening ? (
                                  <div>
                                    <span className="font-bold">
                                      {evening.prices.length === 1
                                        ? `$${evening.prices[0].toFixed(2)}`
                                        : `$${evening.prices[0].toFixed(2)} - $${evening.prices[evening.prices.length - 1].toFixed(2)}`}
                                    </span>
                                    {evening.hasSurcharge && (
                                      <AlertTriangle className="h-3 w-3 inline ml-1 text-yellow-500" />
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* PLF Distribution Analysis */}
      {analysisType === 'plf' && (
        <div className="space-y-6">
          <Card className="border-border/40 bg-card/50 backdrop-blur-xl">
            <CardHeader>
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <PieChart className="h-5 w-5 text-primary" />
                PLF vs Standard Distribution
              </CardTitle>
              <CardDescription>
                Breakdown of premium format inventory and pricing across theaters
              </CardDescription>
            </CardHeader>
            <CardContent>
              {plfDistributionLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !plfDistributionData || plfDistributionData.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  No distribution data found for the current selection.
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* Summary Chart */}
                  <div className="h-[400px]">
                    <h4 className="text-sm font-medium mb-4 text-center">Specific Format Mix (%)</h4>
                    <ResponsiveContainer width="100%" height="100%">
                      <ReBarChart
                        data={plfDistributionData.reduce((acc: any[], curr: any) => {
                          const existing = acc.find(a => a.theater === curr.theater_name);
                          if (existing) {
                            existing[curr.specific_format] = curr.pct_of_total;
                          } else {
                            acc.push({ theater: curr.theater_name, [curr.specific_format]: curr.pct_of_total });
                          }
                          return acc;
                        }, [])}
                        layout="vertical"
                      >
                        <CartesianGrid strokeDasharray="3 3" horizontal stroke="#333" />
                        <XAxis type="number" stroke="#888" fontSize={12} unit="%" />
                        <YAxis 
                          dataKey="theater" 
                          type="category" 
                          stroke="#888" 
                          fontSize={10} 
                          width={150}
                        />
                        <ReTooltip 
                          contentStyle={{ backgroundColor: '#1f1f1f', border: '1px solid #333' }}
                          labelStyle={{ color: '#888' }}
                        />
                        <Legend />
                        <Bar dataKey="Standard" stackId="a" fill="#8884d8" name="Standard" />
                        <Bar dataKey="IMAX" stackId="a" fill="#82ca9d" name="IMAX" />
                        <Bar dataKey="Dolby" stackId="a" fill="#ffc658" name="Dolby" />
                        <Bar dataKey="3D" stackId="a" fill="#ff7300" name="3D" />
                        <Bar dataKey="Other PLF" stackId="a" fill="#00C49F" name="Other PLF" />
                      </ReBarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Pricing Comparison */}
                  <div className="h-[400px]">
                    <h4 className="text-sm font-medium mb-4 text-center">Average Price by Format ($)</h4>
                    <ResponsiveContainer width="100%" height="100%">
                      <ReBarChart
                        data={plfDistributionData.reduce((acc: any[], curr: any) => {
                          const existing = acc.find(a => a.theater === curr.theater_name);
                          if (existing) {
                            existing[curr.specific_format] = curr.avg_price;
                          } else {
                            acc.push({ theater: curr.theater_name, [curr.specific_format]: curr.avg_price });
                          }
                          return acc;
                        }, [])}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#333" />
                        <XAxis dataKey="theater" stroke="#888" fontSize={10} tick={false} />
                        <YAxis stroke="#888" fontSize={12} tickFormatter={val => `$${val}`} />
                        <ReTooltip 
                          contentStyle={{ backgroundColor: '#1f1f1f', border: '1px solid #333' }}
                          formatter={(val: number) => [`$${val.toFixed(2)}`, '']}
                        />
                        <Legend />
                        <Bar dataKey="Standard" fill="#8884d8" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="IMAX" fill="#82ca9d" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="Dolby" fill="#ffc658" radius={[4, 4, 0, 0]} />
                      </ReBarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/40 bg-card/50 backdrop-blur-xl">
            <CardHeader>
              <CardTitle className="text-base font-semibold">Detailed Distribution Table</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border border-border/40 overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/50">
                    <TableRow>
                      <TableHead>Theater</TableHead>
                      <TableHead>Format</TableHead>
                      <TableHead className="text-right">Avg Price</TableHead>
                      <TableHead className="text-right">Showings</TableHead>
                      <TableHead className="text-right">% of Mix</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {plfDistributionData?.map((entry, idx) => (
                      <TableRow key={`${entry.theater_name}-${entry.specific_format}-${idx}`}>
                        <TableCell className="font-medium text-xs">{entry.theater_name}</TableCell>
                        <TableCell>
                          <Badge variant={entry.format_group === 'PLF' ? 'default' : 'secondary'} className="text-[10px] uppercase">
                            {entry.specific_format}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">${entry.avg_price.toFixed(2)}</TableCell>
                        <TableCell className="text-right text-xs">{entry.showing_count}</TableCell>
                        <TableCell className="text-right text-xs">
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-mono">{entry.pct_of_total}%</span>
                            <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden">
                              <div 
                                className={`h-full ${entry.format_group === 'PLF' ? 'bg-primary' : 'bg-muted-foreground/30'}`}
                                style={{ width: `${entry.pct_of_total}%` }}
                              />
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
