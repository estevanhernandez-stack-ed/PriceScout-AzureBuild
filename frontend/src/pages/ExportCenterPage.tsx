import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { 
  FileDown, 
  FileSpreadsheet, 
  Download,
  CheckCircle2,
  Clock,
  History
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

export function ExportCenterPage() {
  const [exportType, setExportType] = useState('prices');
  const [dateRange, setDateRange] = useState('last_7_days');
  const [format, setFormat] = useState('csv');
  const [isExporting, setIsExporting] = useState(false);
  const { toast } = useToast();

  const handleExport = async () => {
    setIsExporting(true);
    try {
      // In production, this would hit /api/v1/exports with filters
      // For now, we simulate a delay and trigger a download if possible
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      const response = await api.get('/scrapes/historical/export', {
        params: { type: exportType, range: dateRange, format },
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `pricescout_export_${exportType}_${new Date().toISOString().split('T')[0]}.${format}`);
      document.body.appendChild(link);
      link.click();
      link.remove();

      toast({
        title: "Export Successful",
        description: `Your ${format.toUpperCase()} export is ready.`,
      });
    } catch (error) {
      console.error('Export failed:', error);
      toast({
        title: "Export Failed",
        description: "There was an error generating your export.",
        variant: "destructive"
      });
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
                    <SelectItem value="prices">Pricing Data</SelectItem>
                    <SelectItem value="showtimes">Schedule & Showtimes</SelectItem>
                    <SelectItem value="historical_trends">Historical Trends</SelectItem>
                    <SelectItem value="market_stats">Market Statistics</SelectItem>
                    <SelectItem value="alerts">Alert History</SelectItem>
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
                    <SelectItem value="custom">Custom Range...</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Market/Theater Filter</Label>
              <Select defaultValue="all">
                <SelectTrigger>
                  <SelectValue placeholder="All Markets" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Markets</SelectItem>
                  <SelectItem value="chicago">Chicago</SelectItem>
                  <SelectItem value="new_york">New York</SelectItem>
                  <SelectItem value="la">Los Angeles</SelectItem>
                </SelectContent>
              </Select>
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
                  variant={format === 'xlsx' ? 'default' : 'outline'} 
                  className="flex-1"
                  onClick={() => setFormat('xlsx')}
                >
                  <FileSpreadsheet className="mr-2 h-4 w-4" />
                  Excel (.xlsx)
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
                  <Clock className="mr-2 h-5 w-5 animate-spin" />
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

        {/* Export History / Quick Info */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Export Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Total Exports (MTD)</span>
                <span className="font-bold">42</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Data Points (MTD)</span>
                <span className="font-bold text-primary">1.2M</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Avg. Generation Time</span>
                <span className="font-bold">4.2s</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <History className="h-4 w-4" />
                Recent Exports
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
               <div className="divide-y">
                  <div className="p-3 flex items-center justify-between hover:bg-muted/50 transition-colors">
                     <div>
                        <p className="text-sm font-medium">Pricing_Data_Q4.xlsx</p>
                        <p className="text-xs text-muted-foreground">2 hours ago • 4.2 MB</p>
                     </div>
                     <CheckCircle2 className="h-4 w-4 text-green-500" />
                  </div>
                  <div className="p-3 flex items-center justify-between hover:bg-muted/50 transition-colors">
                     <div>
                        <p className="text-sm font-medium">Market_Summary.csv</p>
                        <p className="text-xs text-muted-foreground">Yesterday • 150 KB</p>
                     </div>
                     <CheckCircle2 className="h-4 w-4 text-green-500" />
                  </div>
               </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
