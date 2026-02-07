import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
  DollarSign,
  Search,
  RefreshCw,
  Download,
  ChevronLeft,
  ChevronRight,
  Building2,
  Film,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { usePriceChecks } from '@/hooks/api';
import { format, subDays } from 'date-fns';

const PAGE_SIZE = 50;

export function PriceChecksPage() {
  const [theaterFilter, setTheaterFilter] = useState('');
  const [filmFilter, setFilmFilter] = useState('');
  const [ticketTypeFilter, setTicketTypeFilter] = useState('');
  const [formatFilter, setFormatFilter] = useState('');
  const [dateFrom, setDateFrom] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [page, setPage] = useState(0);

  const { data, isLoading, refetch, isRefetching } = usePriceChecks({
    theaterName: theaterFilter || undefined,
    filmTitle: filmFilter || undefined,
    ticketType: ticketTypeFilter || undefined,
    format: formatFilter || undefined,
    dateFrom,
    dateTo,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const priceChecks = useMemo(() => data?.price_checks || [], [data]);
  const totalRecords = data?.total_records || 0;
  const totalPages = Math.ceil(totalRecords / PAGE_SIZE);

  // Summary stats
  const summaryStats = useMemo(() => {
    if (!priceChecks.length) return { avg: 0, min: 0, max: 0, count: 0, theaters: 0, films: 0 };

    const prices = priceChecks.map(c => c.price);
    return {
      avg: prices.reduce((a, b) => a + b, 0) / prices.length,
      min: Math.min(...prices),
      max: Math.max(...prices),
      count: totalRecords,
      theaters: new Set(priceChecks.map(c => c.theater_name)).size,
      films: new Set(priceChecks.map(c => c.film_title)).size,
    };
  }, [priceChecks, totalRecords]);

  // CSV export
  const handleExportCsv = () => {
    if (!priceChecks.length) return;

    const headers = ['Date', 'Theater', 'Film', 'Format', 'Ticket Type', 'Showtime', 'Price'];
    const rows = priceChecks.map(c => [
      c.play_date,
      `"${c.theater_name}"`,
      `"${c.film_title}"`,
      c.format || 'Standard',
      c.ticket_type,
      c.showtime,
      c.price.toFixed(2),
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `price-checks-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Price Checks</h1>
          <p className="text-muted-foreground">
            View historical price data and comparisons.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isRefetching}
          >
            <RefreshCw className={`h-4 w-4 ${isRefetching ? 'animate-spin' : ''}`} />
          </Button>
          <Button variant="outline" onClick={handleExportCsv} disabled={!priceChecks.length}>
            <Download className="mr-2 h-4 w-4" />
            CSV
          </Button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-6 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Avg Price</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.avg > 0 ? `$${summaryStats.avg.toFixed(2)}` : '--'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-green-500" />
              <span className="text-xs text-muted-foreground">Min</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.min > 0 ? `$${summaryStats.min.toFixed(2)}` : '--'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-red-500" />
              <span className="text-xs text-muted-foreground">Max</span>
            </div>
            <p className="text-2xl font-bold mt-1">
              {summaryStats.max > 0 ? `$${summaryStats.max.toFixed(2)}` : '--'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Records</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.count.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Theaters</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.theaters}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Film className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Films</span>
            </div>
            <p className="text-2xl font-bold mt-1">{summaryStats.films}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid grid-cols-6 gap-4">
            <div className="space-y-1">
              <Label className="text-xs">Theater</Label>
              <Input
                placeholder="Theater name..."
                value={theaterFilter}
                onChange={(e) => { setTheaterFilter(e.target.value); setPage(0); }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Film</Label>
              <Input
                placeholder="Film title..."
                value={filmFilter}
                onChange={(e) => { setFilmFilter(e.target.value); setPage(0); }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Ticket Type</Label>
              <Input
                placeholder="e.g. Adult..."
                value={ticketTypeFilter}
                onChange={(e) => { setTicketTypeFilter(e.target.value); setPage(0); }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Format</Label>
              <Input
                placeholder="e.g. IMAX..."
                value={formatFilter}
                onChange={(e) => { setFormatFilter(e.target.value); setPage(0); }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">From</Label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">To</Label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Data Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Price History</CardTitle>
              <CardDescription>
                {totalRecords.toLocaleString()} records found
              </CardDescription>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : priceChecks.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <DollarSign className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>No price check records found for the current filters.</p>
              <p className="text-sm mt-1">Try adjusting your date range or clearing filters.</p>
            </div>
          ) : (
            <div className="max-h-[600px] overflow-y-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Theater</TableHead>
                    <TableHead>Film</TableHead>
                    <TableHead>Format</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Showtime</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {priceChecks.map((check, i) => (
                    <TableRow key={`${check.price_id}-${i}`}>
                      <TableCell className="text-muted-foreground">{check.play_date}</TableCell>
                      <TableCell className="font-medium">{check.theater_name}</TableCell>
                      <TableCell>{check.film_title}</TableCell>
                      <TableCell>
                        {check.format ? (
                          <Badge variant="outline">{check.format}</Badge>
                        ) : (
                          <span className="text-muted-foreground">Standard</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{check.ticket_type}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{check.showtime}</TableCell>
                      <TableCell className="text-right font-bold">${check.price.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
