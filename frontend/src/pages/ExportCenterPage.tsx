import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  FileDown,
  Download,
  Loader2,
  Info,
} from 'lucide-react';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { api } from '@/lib/api';
import { format as fmtDate, subDays, subMonths } from 'date-fns';

interface ExportTypeInfo {
  label: string;
  description: string;
  endpoint: string;
  /** Does the backend support a `format` query param for this endpoint? */
  supportsFormatParam: boolean;
  /** Does this endpoint require specific params beyond date range? */
  needsDateRange: boolean;
}

const EXPORT_TYPES: Record<string, ExportTypeInfo> = {
  prices: {
    label: 'Pricing Data',
    description: 'Price check records including theater, film, ticket type, format, and price. Up to 1,000 records per export.',
    endpoint: '/price-checks',
    supportsFormatParam: false,
    needsDateRange: true,
  },
  operating_hours: {
    label: 'Operating Hours',
    description: 'Theater opening/closing times derived from first and last showtimes per day.',
    endpoint: '/reports/operating-hours',
    supportsFormatParam: true,
    needsDateRange: false,
  },
  plf_formats: {
    label: 'PLF Formats',
    description: 'Premium Large Format (IMAX, Dolby, ScreenX, etc.) availability and showtime counts by theater.',
    endpoint: '/reports/plf-formats',
    supportsFormatParam: true,
    needsDateRange: false,
  },
  price_comparison: {
    label: 'Price Comparison',
    description: 'Average price comparison across theaters with market average differential. Aggregated by ticket type.',
    endpoint: '/price-comparison',
    supportsFormatParam: false,
    needsDateRange: false,
  },
  alerts: {
    label: 'Alert History',
    description: 'Price alert records including threshold, detected value, severity, and resolution status.',
    endpoint: '/price-alerts',
    supportsFormatParam: false,
    needsDateRange: false,
  },
};

function computeDateRange(rangeKey: string): { from: string; to: string } {
  const today = new Date();
  const to = fmtDate(today, 'yyyy-MM-dd');
  switch (rangeKey) {
    case 'today':
      return { from: to, to };
    case 'yesterday': {
      const d = fmtDate(subDays(today, 1), 'yyyy-MM-dd');
      return { from: d, to: d };
    }
    case 'last_7_days':
      return { from: fmtDate(subDays(today, 7), 'yyyy-MM-dd'), to };
    case 'last_30_days':
      return { from: fmtDate(subDays(today, 30), 'yyyy-MM-dd'), to };
    case 'last_quarter':
      return { from: fmtDate(subMonths(today, 3), 'yyyy-MM-dd'), to };
    default:
      return { from: fmtDate(subDays(today, 7), 'yyyy-MM-dd'), to };
  }
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Convert an array of objects to CSV string */
function jsonToCsv(data: Record<string, unknown>[]): string {
  if (!data.length) return '';
  const headers = Object.keys(data[0]);
  const rows = data.map((row) =>
    headers.map((h) => {
      const val = row[h];
      if (val == null) return '';
      const str = String(val);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"`
        : str;
    }).join(',')
  );
  return [headers.join(','), ...rows].join('\n');
}

export function ExportCenterPage() {
  const [exportType, setExportType] = useState('prices');
  const [dateRange, setDateRange] = useState('last_7_days');
  const [format, setFormat] = useState<'csv' | 'json'>('csv');
  const [isExporting, setIsExporting] = useState(false);
  const { toast } = useToast();

  const selectedInfo = EXPORT_TYPES[exportType];
  const dateRangeValues = useMemo(() => computeDateRange(dateRange), [dateRange]);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const info = EXPORT_TYPES[exportType];
      const dateSuffix = `${dateRangeValues.from}_to_${dateRangeValues.to}`;
      const filename = `pricescout_${exportType}_${dateSuffix}.${format}`;

      switch (exportType) {
        case 'prices': {
          // /price-checks returns JSON; convert client-side for CSV
          const response = await api.get(info.endpoint, {
            params: {
              date_from: dateRangeValues.from,
              date_to: dateRangeValues.to,
              limit: 1000,
              offset: 0,
            },
          });
          const records = response.data?.price_checks || [];
          if (!records.length) {
            toast({ title: 'No Data', description: 'No pricing records found for the selected date range.', variant: 'destructive' });
            return;
          }
          if (format === 'csv') {
            const csv = jsonToCsv(records);
            triggerDownload(new Blob([csv], { type: 'text/csv' }), filename);
          } else {
            triggerDownload(
              new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' }),
              filename
            );
          }
          break;
        }

        case 'operating_hours': {
          // Backend supports format param
          const params: Record<string, string> = { format, limit: '500' };
          if (format === 'csv') {
            const response = await api.get(info.endpoint, { params, responseType: 'blob' });
            triggerDownload(new Blob([response.data]), filename);
          } else {
            const response = await api.get(info.endpoint, { params });
            triggerDownload(
              new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }),
              filename
            );
          }
          break;
        }

        case 'plf_formats': {
          // Backend supports format param
          const params: Record<string, string> = { format };
          if (dateRangeValues.to === dateRangeValues.from) {
            params.date = dateRangeValues.to;
          }
          if (format === 'csv') {
            const response = await api.get(info.endpoint, { params, responseType: 'blob' });
            triggerDownload(new Blob([response.data]), filename);
          } else {
            const response = await api.get(info.endpoint, { params });
            triggerDownload(
              new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }),
              filename
            );
          }
          break;
        }

        case 'price_comparison': {
          // Returns JSON array; convert client-side for CSV
          const days = dateRange === 'today' ? 1
            : dateRange === 'yesterday' ? 1
            : dateRange === 'last_7_days' ? 7
            : dateRange === 'last_30_days' ? 30
            : 90;

          const response = await api.get(info.endpoint, { params: { days } });
          const data = response.data;
          if (!Array.isArray(data) || !data.length) {
            toast({ title: 'No Data', description: 'No price comparison data available.', variant: 'destructive' });
            return;
          }
          if (format === 'csv') {
            const csv = jsonToCsv(data);
            triggerDownload(new Blob([csv], { type: 'text/csv' }), filename);
          } else {
            triggerDownload(
              new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
              filename
            );
          }
          break;
        }

        case 'alerts': {
          // Returns JSON with .alerts array; convert client-side for CSV
          const response = await api.get(info.endpoint, { params: { limit: 500 } });
          const alerts = response.data?.alerts || response.data || [];
          const records = Array.isArray(alerts) ? alerts : [];
          if (!records.length) {
            toast({ title: 'No Data', description: 'No alert records found.', variant: 'destructive' });
            return;
          }
          if (format === 'csv') {
            const csv = jsonToCsv(records);
            triggerDownload(new Blob([csv], { type: 'text/csv' }), filename);
          } else {
            triggerDownload(
              new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' }),
              filename
            );
          }
          break;
        }
      }

      toast({ title: 'Export Complete', description: `Your ${format.toUpperCase()} export has been downloaded.` });
    } catch (error: unknown) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Export failed. Please check your parameters and try again.';
      toast({ title: 'Export Failed', description: detail, variant: 'destructive' });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Export Center</h1>
        <p className="text-muted-foreground">
          Centralized hub for exporting pricing, schedule, and historical data.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Export Configuration */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Generate New Export</CardTitle>
            <CardDescription>
              Configure your data export parameters and download format.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Data Category</Label>
                <Select value={exportType} onValueChange={setExportType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(EXPORT_TYPES).map(([key, info]) => (
                      <SelectItem key={key} value={key}>{info.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Date Range</Label>
                <Select value={dateRange} onValueChange={setDateRange}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="today">Today</SelectItem>
                    <SelectItem value="yesterday">Yesterday</SelectItem>
                    <SelectItem value="last_7_days">Last 7 Days</SelectItem>
                    <SelectItem value="last_30_days">Last 30 Days</SelectItem>
                    <SelectItem value="last_quarter">Last Quarter</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>File Format</Label>
              <div className="flex gap-4">
                <Button
                  variant={format === 'csv' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => setFormat('csv')}
                >
                  <FileDown className="mr-2 h-4 w-4" />
                  CSV
                </Button>
                <Button
                  variant={format === 'json' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => setFormat('json')}
                >
                  <Download className="mr-2 h-4 w-4" />
                  JSON
                </Button>
              </div>
            </div>

            <Button
              className="w-full h-12 text-lg font-bold"
              onClick={handleExport}
              disabled={isExporting}
            >
              {isExporting ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Generating Export...
                </>
              ) : (
                <>
                  <Download className="mr-2 h-5 w-5" />
                  Download Export
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Export Info Panel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Info className="h-4 w-4" />
              About This Export
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm font-medium">{selectedInfo.label}</p>
              <p className="text-sm text-muted-foreground mt-1">
                {selectedInfo.description}
              </p>
            </div>
            <div className="border-t pt-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Date Range</span>
                <span className="text-xs font-mono">
                  {dateRangeValues.from} &rarr; {dateRangeValues.to}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Format</span>
                <span className="text-xs font-mono uppercase">{format}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">API Endpoint</span>
                <span className="text-xs font-mono text-muted-foreground">{selectedInfo.endpoint}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
