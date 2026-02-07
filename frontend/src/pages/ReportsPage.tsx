import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileText, Download, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { api } from '@/lib/api';
import { format as fmtDate } from 'date-fns';

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportsPage() {
  // Daily Lineup params
  const [dailyTheater, setDailyTheater] = useState('');
  const [dailyDate, setDailyDate] = useState(fmtDate(new Date(), 'yyyy-MM-dd'));

  // Operating Hours params
  const [ohTheater, setOhTheater] = useState('');
  const [ohDate, setOhDate] = useState('');

  // PLF Formats params
  const [plfDate, setPlfDate] = useState('');

  // Price Comparison params
  const [pcMarket, setPcMarket] = useState('');
  const [pcDays, setPcDays] = useState('7');

  const [downloading, setDownloading] = useState<string | null>(null);
  const { toast } = useToast();

  const handleDownload = async (reportKey: string, formatType: string) => {
    const key = `${reportKey}-${formatType}`;
    setDownloading(key);
    try {
      switch (reportKey) {
        case 'daily-lineup': {
          if (!dailyTheater) {
            toast({ title: 'Theater Required', description: 'Enter a theater name for the Daily Lineup report.', variant: 'destructive' });
            return;
          }
          if (formatType === 'csv') {
            const response = await api.get('/reports/daily-lineup', {
              params: { theater: dailyTheater, date: dailyDate, format: 'csv' },
              responseType: 'blob',
            });
            triggerDownload(
              new Blob([response.data]),
              `daily_lineup_${dailyTheater.replace(/\s+/g, '_')}_${dailyDate}.csv`
            );
          } else if (formatType === 'pdf') {
            // Fetch JSON data first, then generate PDF via showtime-view endpoint
            const lineupResp = await api.get('/reports/daily-lineup', {
              params: { theater: dailyTheater, date: dailyDate, format: 'json' },
            });
            const lineup = lineupResp.data;
            const showtimes = lineup.showtimes || [];
            const pdfResp = await api.post(
              '/reports/showtime-view/pdf',
              {
                all_showings: showtimes,
                selected_films: [...new Set(showtimes.map((s: Record<string, unknown>) => s.film_title))],
                theaters: [dailyTheater],
                date_start: dailyDate,
                date_end: dailyDate,
                context_title: `Daily Lineup — ${dailyTheater} — ${dailyDate}`,
              },
              { responseType: 'blob' }
            );
            triggerDownload(
              new Blob([pdfResp.data], { type: 'application/pdf' }),
              `daily_lineup_${dailyTheater.replace(/\s+/g, '_')}_${dailyDate}.pdf`
            );
          }
          break;
        }

        case 'price-comparison': {
          const params: Record<string, string> = {};
          if (pcMarket) params.market = pcMarket;
          if (pcDays) params.days = pcDays;

          const response = await api.get('/price-comparison', { params });
          const data: Array<{
            theater_name: string;
            ticket_type: string;
            avg_price: number;
            price_count: number;
            vs_market_avg: number | null;
          }> = response.data;

          if (!data.length) {
            toast({ title: 'No Data', description: 'No price comparison data found for current filters.', variant: 'destructive' });
            return;
          }

          if (formatType === 'csv') {
            const headers = ['Theater', 'Ticket Type', 'Avg Price', 'Price Count', 'vs Market Avg %'];
            const rows = data.map((r) => [
              `"${r.theater_name}"`,
              r.ticket_type,
              r.avg_price?.toFixed(2) ?? '',
              String(r.price_count),
              r.vs_market_avg != null ? `${r.vs_market_avg.toFixed(1)}%` : 'N/A',
            ]);
            const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
            triggerDownload(new Blob([csv], { type: 'text/csv' }), 'price_comparison.csv');
          } else {
            triggerDownload(
              new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
              'price_comparison.json'
            );
          }
          break;
        }

        case 'operating-hours': {
          const params: Record<string, string> = { format: formatType };
          if (ohTheater) params.theater = ohTheater;
          if (ohDate) params.date = ohDate;

          if (formatType === 'csv') {
            const response = await api.get('/reports/operating-hours', { params, responseType: 'blob' });
            triggerDownload(new Blob([response.data]), 'operating_hours.csv');
          } else {
            const response = await api.get('/reports/operating-hours', { params });
            triggerDownload(
              new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }),
              'operating_hours.json'
            );
          }
          break;
        }

        case 'plf-formats': {
          const params: Record<string, string> = { format: formatType };
          if (plfDate) params.date = plfDate;

          if (formatType === 'csv') {
            const response = await api.get('/reports/plf-formats', { params, responseType: 'blob' });
            triggerDownload(new Blob([response.data]), 'plf_formats.csv');
          } else {
            const response = await api.get('/reports/plf-formats', { params });
            triggerDownload(
              new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }),
              'plf_formats.json'
            );
          }
          break;
        }
      }
      toast({ title: 'Download Started', description: `Your ${formatType.toUpperCase()} report is downloading.` });
    } catch (error: unknown) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to generate report. Check that data exists for the selected parameters.';
      toast({ title: 'Download Failed', description: detail, variant: 'destructive' });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Reports</h1>
        <p className="text-muted-foreground">
          Generate and download market analysis reports.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Daily Lineup */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-lg">Daily Lineup</CardTitle>
            </div>
            <CardDescription>
              Complete showtime and pricing lineup for a specific theater and date.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Theater Name</Label>
                <Input
                  placeholder="e.g. Marcus Elgin Cinema"
                  value={dailyTheater}
                  onChange={(e) => setDailyTheater(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Date</Label>
                <Input
                  type="date"
                  value={dailyDate}
                  onChange={(e) => setDailyDate(e.target.value)}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('daily-lineup', 'pdf')}
                disabled={downloading === 'daily-lineup-pdf' || !dailyTheater}
              >
                {downloading === 'daily-lineup-pdf' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                PDF
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('daily-lineup', 'csv')}
                disabled={downloading === 'daily-lineup-csv' || !dailyTheater}
              >
                {downloading === 'daily-lineup-csv' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                CSV
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Price Comparison */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-lg">Price Comparison</CardTitle>
            </div>
            <CardDescription>
              Side-by-side price comparison across competitors.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Market (optional)</Label>
                <Input
                  placeholder="e.g. Chicago"
                  value={pcMarket}
                  onChange={(e) => setPcMarket(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Lookback Days</Label>
                <Input
                  type="number"
                  min="1"
                  max="90"
                  value={pcDays}
                  onChange={(e) => setPcDays(e.target.value)}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('price-comparison', 'csv')}
                disabled={downloading === 'price-comparison-csv'}
              >
                {downloading === 'price-comparison-csv' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('price-comparison', 'json')}
                disabled={downloading === 'price-comparison-json'}
              >
                {downloading === 'price-comparison-json' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                JSON
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Operating Hours */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-lg">Operating Hours</CardTitle>
            </div>
            <CardDescription>
              Theater operating hours and showtime distribution.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Theater (optional)</Label>
                <Input
                  placeholder="All theaters"
                  value={ohTheater}
                  onChange={(e) => setOhTheater(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Date (optional)</Label>
                <Input
                  type="date"
                  value={ohDate}
                  onChange={(e) => setOhDate(e.target.value)}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('operating-hours', 'csv')}
                disabled={downloading === 'operating-hours-csv'}
              >
                {downloading === 'operating-hours-csv' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('operating-hours', 'json')}
                disabled={downloading === 'operating-hours-json'}
              >
                {downloading === 'operating-hours-json' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                JSON
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* PLF Formats */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-lg">PLF Formats</CardTitle>
            </div>
            <CardDescription>
              Premium Large Format availability and pricing across theaters.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Date (optional)</Label>
              <Input
                type="date"
                value={plfDate}
                onChange={(e) => setPlfDate(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('plf-formats', 'csv')}
                disabled={downloading === 'plf-formats-csv'}
              >
                {downloading === 'plf-formats-csv' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDownload('plf-formats', 'json')}
                disabled={downloading === 'plf-formats-json'}
              >
                {downloading === 'plf-formats-json' ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                JSON
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
