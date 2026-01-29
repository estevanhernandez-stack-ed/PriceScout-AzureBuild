import { useState, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Database,
  HardDrive,
  RefreshCw,
  Trash2,
  Download,
  Upload,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileJson,
  FileSpreadsheet,
  Settings,
  Building2,
  FileDown,
  RotateCcw,
  Activity,
  Ban,
  ChevronDown,
  ChevronUp,
  Link,
  ExternalLink,
  Zap,
  Loader2,
} from 'lucide-react';
import {
  useCacheStatus,
  useCacheMarkets,
  useCacheBackups,
  useRefreshCache,
  useMatchTheater,
  useTheaterCache,
} from '@/hooks/api/useCache';
import { useLiveScrapeJobs, useCancelLiveScrapeJob } from '@/hooks/api/useScrapes';
import { useEntTelligenceStatus, useSyncPrices, useSyncMarkets, useTaskStatus } from '@/hooks/api';
import { api } from '@/lib/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';

// Hook for deleting cache
function useDeleteCache() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.delete('/cache');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cache'] });
      queryClient.invalidateQueries({ queryKey: ['theaterCache'] });
    },
  });
}

export function DataManagementPage() {
  const [refreshProgress, setRefreshProgress] = useState(0);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: cacheStatus, isLoading: statusLoading, refetch: refetchStatus } = useCacheStatus();
  const { data: marketsData, isLoading: marketsLoading } = useCacheMarkets();
  const { data: fullCacheData } = useTheaterCache();
  const { data: backupsData } = useCacheBackups();
  const { data: liveJobs, isLoading: jobsLoading } = useLiveScrapeJobs();
  
  const refreshMutation = useRefreshCache();
  const deleteMutation = useDeleteCache();
  const cancelJobMutation = useCancelLiveScrapeJob();
  const matchMutation = useMatchTheater();

  const { data: entStatus } = useEntTelligenceStatus();
  const syncPricesMutation = useSyncPrices();
  const syncMarketsMutation = useSyncMarkets();

  const [syncStartDate, setSyncStartDate] = useState(new Date().toISOString().split('T')[0]);
  const [syncEndDate, setSyncEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [activeSyncTaskId, setActiveSyncTaskId] = useState<string | null>(null);
  const { data: activeTaskStatus } = useTaskStatus(activeSyncTaskId);

  const [expandedMarket, setExpandedMarket] = useState<string | null>(null);
  const [editingTheater, setEditingTheater] = useState<{
    market: string;
    theater_name: string;
    url: string;
  } | null>(null);
  const [newUrl, setNewUrl] = useState('');

  const isLoading = statusLoading || marketsLoading;

  const handleRefreshCache = async (forceFullRefresh: boolean = false) => {
    setRefreshProgress(0);
    const interval = setInterval(() => {
      setRefreshProgress((prev) => Math.min(prev + 10, 90));
    }, 200);

    try {
      await refreshMutation.mutateAsync({
        force_full_refresh: forceFullRefresh,
        rebuild_broken_urls: true,
      });
      setRefreshProgress(100);
    } finally {
      clearInterval(interval);
      setTimeout(() => setRefreshProgress(0), 1000);
    }
  };

  const handleDeleteCache = async () => {
    try {
      await deleteMutation.mutateAsync();
      setShowDeleteDialog(false);
    } catch (error) {
      console.error('Failed to delete cache:', error);
    }
  };

  const handleExport = async (exportType: string) => {
    setIsExporting(exportType);
    try {
      let response;
      let filename: string;

      switch (exportType) {
        case 'price-csv':
          response = await api.get('/exports/prices', {
            responseType: 'blob',
            params: { format: 'csv' },
          });
          filename = `price_history_${new Date().toISOString().split('T')[0]}.csv`;
          break;
        case 'price-excel':
          response = await api.get('/exports/prices', {
            responseType: 'blob',
            params: { format: 'xlsx' },
          });
          filename = `price_history_${new Date().toISOString().split('T')[0]}.xlsx`;
          break;
        case 'theater-json':
          response = await api.get('/cache/theaters', { responseType: 'blob' });
          filename = `theater_cache_${new Date().toISOString().split('T')[0]}.json`;
          break;
        case 'backup-json':
          response = await api.get('/cache/backup/download', { responseType: 'blob' });
          filename = `full_backup_${new Date().toISOString().split('T')[0]}.json`;
          break;
        default:
          return;
      }

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(null);
    }
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      await api.post('/cache/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      refetchStatus();
    } catch (error) {
      console.error('Import failed:', error);
    }

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpdateTheaterUrl = async () => {
    if (!editingTheater) return;
    try {
      await matchMutation.mutateAsync({
        market: editingTheater.market,
        theater_name: editingTheater.theater_name,
        fandango_url: newUrl,
      });
      setEditingTheater(null);
    } catch (error) {
      console.error('Failed to update URL:', error);
    }
  };

  const formatBytes = (kb: number) => {
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  };

  const getStatusIcon = (status: 'fresh' | 'stale' | 'missing') => {
    switch (status) {
      case 'fresh':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case 'stale':
        return <Clock className="h-4 w-4 text-yellow-500" />;
      case 'missing':
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Calculate summary stats from actual data
  const totalCacheSize = cacheStatus?.file_size_kb || 0;
  const marketCount = cacheStatus?.market_count || 0;
  const theaterCount = cacheStatus?.theater_count || 0;
  const lastUpdated = cacheStatus?.last_updated;

  // Determine cache freshness
  const getCacheFreshness = (): 'fresh' | 'stale' | 'missing' => {
    if (!cacheStatus?.cache_file_exists) return 'missing';
    if (!lastUpdated) return 'missing';
    const lastUpdate = new Date(lastUpdated);
    const hoursSince = (Date.now() - lastUpdate.getTime()) / (1000 * 60 * 60);
    if (hoursSince < 24) return 'fresh';
    return 'stale';
  };

  const cacheFreshness = getCacheFreshness();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Data Management</h1>
          <p className="text-muted-foreground">
            Manage caches, databases, and data exports
          </p>
        </div>
        <Badge variant="outline" className="text-sm py-1 px-3">
          <Settings className="mr-1 h-3 w-3" />
          Admin Only
        </Badge>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Cache Size</span>
            </div>
            <p className="text-3xl font-bold mt-2">{formatBytes(totalCacheSize)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Markets</span>
            </div>
            <p className="text-3xl font-bold mt-2">{marketCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Theaters</span>
            </div>
            <p className="text-3xl font-bold mt-2">{theaterCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Status</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              {getStatusIcon(cacheFreshness)}
              <span className="text-lg font-medium capitalize">{cacheFreshness}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="cache" className="space-y-4">
        <TabsList>
          <TabsTrigger value="cache">Cache Management</TabsTrigger>
          <TabsTrigger value="markets">Markets</TabsTrigger>
          <TabsTrigger value="jobs">
            Live Jobs
            {liveJobs?.some(j => j.status === 'running') && (
              <Badge variant="default" className="ml-2 h-4 w-4 p-0 flex items-center justify-center animate-pulse">
                !
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="export">Import/Export</TabsTrigger>
          <TabsTrigger value="backups">Backups</TabsTrigger>
          <TabsTrigger value="sync">Data Sync</TabsTrigger>
        </TabsList>

        <TabsContent value="cache">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-5 w-5" />
                Cache Status
              </CardTitle>
              <CardDescription>
                Manage application caches and refresh data
              </CardDescription>
            </CardHeader>
            <CardContent>
              {(refreshMutation.isPending || refreshProgress > 0) && (
                <div className="mb-4 p-4 bg-muted/50 rounded-lg">
                  <p className="text-sm mb-2">Refreshing cache...</p>
                  <Progress value={refreshProgress} className="h-2" />
                </div>
              )}

              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 border rounded-lg">
                  <div className="flex items-center gap-4">
                    {getStatusIcon(cacheFreshness)}
                    <div>
                      <p className="font-medium">Theater Cache</p>
                      <p className="text-sm text-muted-foreground">
                        {formatBytes(totalCacheSize)} | {theaterCount} theaters in {marketCount} markets
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Last updated: {lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Never'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        cacheFreshness === 'fresh'
                          ? 'default'
                          : cacheFreshness === 'stale'
                          ? 'secondary'
                          : 'destructive'
                      }
                    >
                      {cacheFreshness}
                    </Badge>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRefreshCache(false)}
                      disabled={refreshMutation.isPending}
                    >
                      <RefreshCw className="h-3 w-3 mr-1" />
                      Refresh
                    </Button>
                  </div>
                </div>

                {cacheStatus?.metadata && (
                  <div className="p-4 border rounded-lg bg-muted/30">
                    <h4 className="font-medium mb-2">Cache Metadata</h4>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Last Refresh Type:</span>{' '}
                        <span className="font-medium">{cacheStatus.metadata.last_refresh_type || 'Unknown'}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Cache File Exists:</span>{' '}
                        <span className="font-medium">{cacheStatus.cache_file_exists ? 'Yes' : 'No'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 mt-6">
                <Button
                  variant="outline"
                  onClick={() => refetchStatus()}
                >
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Check Status
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleRefreshCache(true)}
                  disabled={refreshMutation.isPending}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Full Rebuild
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => setShowDeleteDialog(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Clear Cache
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="markets">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                Market Statistics
              </CardTitle>
              <CardDescription>
                View market data and theater counts
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!marketsData || marketsData.markets.length === 0 ? (
                <div className="text-center py-12">
                  <Database className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-muted-foreground mb-4">
                    No market data available. Please build the theater cache first.
                  </p>
                  <Button onClick={() => handleRefreshCache(true)}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Build Cache
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-5 gap-4 p-3 bg-muted/50 rounded-lg font-medium text-sm">
                    <div className="col-span-1">Market Name</div>
                    <div className="text-right">Total</div>
                    <div className="text-right">Active</div>
                    <div className="text-right">Not on Fan.</div>
                    <div className="text-right">Actions</div>
                  </div>
                  <div className="max-h-[600px] overflow-y-auto space-y-1">
                    {marketsData.markets.map((market) => (
                      <div key={market.market_name} className="space-y-1">
                        <div
                          className={`grid grid-cols-5 gap-4 p-3 border rounded-lg text-sm transition-colors ${
                            expandedMarket === market.market_name ? 'bg-primary/5 border-primary/50' : 'hover:bg-muted/30'
                          }`}
                        >
                          <div className="font-medium flex items-center gap-2">
                             <Building2 className="h-4 w-4 text-muted-foreground" />
                             {market.market_name}
                          </div>
                          <div className="text-right">{market.total_theaters}</div>
                          <div className="text-right text-green-600">{market.active_theaters}</div>
                          <div className="text-right text-muted-foreground">
                            {market.not_on_fandango}
                          </div>
                          <div className="text-right">
                             <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 w-7 p-0"
                                onClick={() => setExpandedMarket(expandedMarket === market.market_name ? null : market.market_name)}
                             >
                                {expandedMarket === market.market_name ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                             </Button>
                          </div>
                        </div>

                        {expandedMarket === market.market_name && fullCacheData?.markets?.[market.market_name] && (
                           <div className="pl-6 space-y-1 pb-2">
                              {fullCacheData.markets[market.market_name].theaters.map((t: any) => (
                                 <div key={t.name} className="flex items-center justify-between p-2 text-xs border rounded-md bg-background shadow-sm">
                                    <div className="flex-1 min-w-0">
                                       <p className="font-medium truncate">{t.name}</p>
                                       <p className="text-muted-foreground truncate opacity-70 flex items-center gap-1">
                                          <Link className="h-3 w-3" />
                                          {t.url || 'No URL matched'}
                                       </p>
                                    </div>
                                    <div className="flex items-center gap-1 ml-4">
                                       {t.url && (
                                          <a href={t.url} target="_blank" rel="noreferrer" className="p-1 hover:text-primary">
                                             <ExternalLink className="h-4 w-4" />
                                          </a>
                                       )}
                                       <Button 
                                          variant="ghost" 
                                          size="sm" 
                                          className="h-7 text-[10px]"
                                          onClick={() => {
                                            setEditingTheater({
                                                market: market.market_name,
                                                theater_name: t.name,
                                                url: t.url || ''
                                            });
                                            setNewUrl(t.url || '');
                                          }}
                                       >
                                          Edit URL
                                       </Button>
                                    </div>
                                 </div>
                              ))}
                           </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="pt-4 border-t mt-4">
                    <p className="text-sm text-muted-foreground">
                      Total: {marketsData.total_count} markets
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="export">
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Download className="h-5 w-5" />
                  Export Data
                </CardTitle>
                <CardDescription>
                  Download data in various formats
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleExport('price-csv')}
                  disabled={isExporting === 'price-csv'}
                >
                  {isExporting === 'price-csv' ? (
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                  )}
                  Export Price History (CSV)
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleExport('price-excel')}
                  disabled={isExporting === 'price-excel'}
                >
                  {isExporting === 'price-excel' ? (
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                  )}
                  Export Price History (Excel)
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleExport('theater-json')}
                  disabled={isExporting === 'theater-json'}
                >
                  {isExporting === 'theater-json' ? (
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileJson className="mr-2 h-4 w-4" />
                  )}
                  Export Theater Cache (JSON)
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleExport('backup-json')}
                  disabled={isExporting === 'backup-json'}
                >
                  {isExporting === 'backup-json' ? (
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileDown className="mr-2 h-4 w-4" />
                  )}
                  Download Full Backup (JSON)
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Upload className="h-5 w-5" />
                  Import Data
                </CardTitle>
                <CardDescription>
                  Upload data files to restore or migrate
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.csv"
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <div
                  className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const file = e.dataTransfer.files[0];
                    if (file && fileInputRef.current) {
                      const dataTransfer = new DataTransfer();
                      dataTransfer.items.add(file);
                      fileInputRef.current.files = dataTransfer.files;
                      fileInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                  }}
                >
                  <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Drag and drop files here, or click to browse
                  </p>
                  <Button variant="outline" className="mt-4">
                    Select File
                  </Button>
                </div>
                <div className="text-sm text-muted-foreground">
                  <p className="font-medium mb-1">Supported formats:</p>
                  <ul className="list-disc list-inside space-y-1">
                    <li>JSON backup files</li>
                    <li>CSV price history</li>
                    <li>Theater cache JSON</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="backups">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileDown className="h-5 w-5" />
                Backup History
              </CardTitle>
              <CardDescription>
                View and restore from previous backups
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!backupsData || backupsData.backups.length === 0 ? (
                <div className="text-center py-12">
                  <FileDown className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    No backup files found. Backups are created automatically when the cache is refreshed.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-4 gap-4 p-3 bg-muted/50 rounded-lg font-medium text-sm">
                    <div>Filename</div>
                    <div className="text-right">Size</div>
                    <div className="text-right">Modified</div>
                    <div className="text-right">Actions</div>
                  </div>
                  {backupsData.backups.map((backup) => (
                    <div
                      key={backup.filename}
                      className="grid grid-cols-4 gap-4 p-3 border rounded-lg text-sm items-center"
                    >
                      <div className="font-medium truncate" title={backup.filename}>
                        {backup.filename}
                      </div>
                      <div className="text-right">{formatBytes(backup.size_kb)}</div>
                      <div className="text-right text-muted-foreground">
                        {new Date(backup.modified_at).toLocaleString()}
                      </div>
                      <div className="text-right">
                        <Button variant="ghost" size="sm">
                          <Download className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  <div className="pt-4 border-t mt-4">
                    <p className="text-sm text-muted-foreground">
                      {backupsData.backup_count} backup files
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sync">
          <div className="grid grid-cols-2 gap-6">
            <Card className="shadow-lg border-primary/10">
              <CardHeader className="bg-primary/[0.02]">
                <CardTitle className="flex items-center gap-2">
                  <Zap className="h-5 w-5 text-primary" />
                  EntTelligence Price Sync
                </CardTitle>
                <CardDescription>
                  Sync pricing data for hybrid scrape optimization.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6 pt-6">
                <div className="p-4 border rounded-lg bg-gradient-to-br from-muted/20 to-muted/10">
                    <div className="flex justify-between items-center mb-4">
                        <span className="text-sm font-medium">Cache Freshness</span>
                        <Badge variant={entStatus?.is_fresh ? 'default' : 'destructive'} className="shadow-sm">
                            {entStatus?.is_fresh ? 'Fresh' : 'Stale/Missing'}
                        </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1">
                            <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Entries</p>
                            <p className="font-bold text-xl tabular-nums">{entStatus?.fresh_entries?.toLocaleString()} / {entStatus?.total_entries?.toLocaleString()}</p>
                        </div>
                        <div className="space-y-1 text-right">
                            <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Until Stale</p>
                            <p className="font-bold text-xl tabular-nums">{entStatus?.hours_until_stale}h</p>
                        </div>
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-2">
                            <Label className="text-xs">Start Date</Label>
                            <Input 
                                type="date" 
                                value={syncStartDate}
                                onChange={(e) => setSyncStartDate(e.target.value)}
                                className="h-9"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">End Date</Label>
                            <Input 
                                type="date" 
                                value={syncEndDate}
                                onChange={(e) => setSyncEndDate(e.target.value)}
                                className="h-9"
                            />
                        </div>
                    </div>
                    
                    <Button 
                        disabled={syncPricesMutation.isPending || activeTaskStatus?.status === 'PENDING'}
                        className="w-full relative overflow-hidden"
                        onClick={async () => {
                            const res = await syncPricesMutation.mutateAsync({ 
                                start_date: syncStartDate,
                                end_date: syncEndDate
                            });
                            if (res.task_id) setActiveSyncTaskId(res.task_id);
                        }}
                    >
                        {syncPricesMutation.isPending ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Triggering...
                            </>
                        ) : 'Run Price Sync'}
                    </Button>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-6">
              <Card className="shadow-lg border-primary/10">
                <CardHeader className="bg-primary/[0.02]">
                  <CardTitle className="flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-primary" />
                    Theater & Market Sync
                  </CardTitle>
                  <CardDescription>
                    Refresh theater metadata from master database.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6 pt-6">
                  <div className="p-4 border rounded-lg bg-blue-50/50 dark:bg-blue-900/10 text-sm border-blue-200/50 dark:border-blue-800/50">
                      <div className="flex items-center gap-2 font-medium text-blue-800 dark:text-blue-300">
                          <Activity className="h-4 w-4" />
                          Background Sync Enabled
                      </div>
                      <p className="text-blue-600 dark:text-blue-400 mt-1 text-xs">
                          Scanning for new theaters and matching Fandango URLs runs as a background worker.
                      </p>
                  </div>

                  <div className="space-y-3">
                      <Button 
                          variant="outline" 
                          className="w-full border-primary/20 hover:border-primary/40"
                          onClick={async () => {
                              const res = await syncMarketsMutation.mutateAsync();
                              if (res.task_id) setActiveSyncTaskId(res.task_id);
                          }}
                          disabled={syncMarketsMutation.isPending || activeTaskStatus?.status === 'PENDING'}
                      >
                          {syncMarketsMutation.isPending ? (
                              <>
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                  Starting Sync...
                              </>
                          ) : (
                              <>
                                  <RefreshCw className="mr-2 h-4 w-4" />
                                  Manual Theater Sync
                              </>
                          )}
                      </Button>
                      <p className="text-[10px] text-center text-muted-foreground uppercase">
                          Source: EntTelligence Master Theater List
                      </p>
                  </div>
                </CardContent>
              </Card>

              {activeSyncTaskId && activeTaskStatus && (
                <Card className="border-primary/20 shadow-md animate-in fade-in slide-in-from-top-2">
                  <CardHeader className="py-3 px-4 flex-row items-center justify-between space-y-0 bg-muted/30">
                    <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-tight">
                      <Activity className="h-3.5 w-3.5" />
                      Current Task
                    </div>
                    <Badge variant={activeTaskStatus.ready ? 'default' : 'secondary'} className="text-[10px]">
                      {activeTaskStatus.status}
                    </Badge>
                  </CardHeader>
                  <CardContent className="p-4 pt-2">
                    <div className="space-y-3">
                        <div className="flex flex-col gap-1">
                            <span className="text-[10px] text-muted-foreground font-mono truncate">ID: {activeSyncTaskId}</span>
                            {!activeTaskStatus.ready && (
                                <div className="flex items-center gap-2 mt-2">
                                    <div className="h-1 flex-1 bg-muted rounded-full overflow-hidden">
                                        <div className="h-full bg-primary animate-progress-indeterminate" />
                                    </div>
                                    <span className="text-[10px] text-muted-foreground animate-pulse">Running</span>
                                </div>
                            )}
                        </div>
                        
                        {activeTaskStatus.ready && activeTaskStatus.result && (
                            <div className="p-2 rounded bg-green-500/10 border border-green-500/20 text-xs text-green-600 dark:text-green-400">
                                <p className="font-bold flex items-center gap-1">
                                    <CheckCircle2 className="h-3 w-3" />
                                    Success
                                </p>
                                <p className="mt-1">
                                    {activeTaskStatus.result.message || `Processed ${activeTaskStatus.result.records_cached || 0} records.`}
                                </p>
                            </div>
                        )}

                        {activeTaskStatus.ready && activeTaskStatus.error && (
                            <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-xs text-red-600">
                                <p className="font-bold flex items-center gap-1">
                                    <AlertTriangle className="h-3 w-3" />
                                    Error
                                </p>
                                <p className="mt-1 truncate">{activeTaskStatus.error}</p>
                            </div>
                        )}

                        {activeTaskStatus.ready && (
                            <Button variant="ghost" size="sm" className="w-full text-[10px] h-7" onClick={() => setActiveSyncTaskId(null)}>
                                Dismiss
                            </Button>
                        )}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>
        {/* Jobs Content */}
        <TabsContent value="jobs">
           <Card>
              <CardHeader>
                 <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Live Scrape Jobs
                 </CardTitle>
                 <CardDescription>
                    Monitor active and recent background scrape jobs
                 </CardDescription>
              </CardHeader>
              <CardContent>
                 {jobsLoading ? (
                    <div className="flex justify-center py-12">
                       <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                 ) : !liveJobs || liveJobs.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                       <p>No active or recent jobs found in memory.</p>
                    </div>
                 ) : (
                    <div className="space-y-4">
                       {liveJobs.map((job) => (
                          <div key={job.job_id} className="p-4 border rounded-lg space-y-3">
                             <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                   <div className={`p-2 rounded-full ${
                                      job.status === 'running' ? 'bg-blue-100 text-blue-600 animate-pulse' :
                                      job.status === 'completed' ? 'bg-green-100 text-green-600' :
                                      job.status === 'failed' ? 'bg-red-100 text-red-600' :
                                      'bg-muted text-muted-foreground'
                                   }`}>
                                      <Activity className="h-4 w-4" />
                                   </div>
                                   <div>
                                      <p className="font-bold flex items-center gap-2">
                                         Job #{job.job_id} 
                                         <Badge variant={
                                            job.status === 'completed' ? 'default' :
                                            job.status === 'running' ? 'secondary' :
                                            'outline'
                                         }>
                                            {job.status}
                                         </Badge>
                                      </p>
                                      <p className="text-xs text-muted-foreground">
                                         {job.current_theater ? `Currently: ${job.current_theater}` : 'No activity details'}
                                      </p>
                                   </div>
                                </div>
                                <div className="flex items-center gap-2">
                                   {job.status === 'running' && (
                                      <Button 
                                         variant="destructive" 
                                         size="sm"
                                         className="h-8"
                                         onClick={() => cancelJobMutation.mutate(job.job_id)}
                                         disabled={cancelJobMutation.isPending}
                                      >
                                         <Ban className="h-3 w-3 mr-1" />
                                         Cancel
                                      </Button>
                                   )}
                                   <span className="text-xs font-mono text-muted-foreground">
                                      {job.duration_seconds?.toFixed(1)}s
                                   </span>
                                </div>
                             </div>
                             
                             <div className="space-y-1">
                                <div className="flex justify-between text-[10px] text-muted-foreground uppercase font-bold">
                                   <span>Progress</span>
                                   <span>{job.progress}%</span>
                                </div>
                                <Progress value={job.progress} className="h-1.5" />
                             </div>
  
                             <div className="flex items-center gap-4 text-xs">
                                <div className="flex items-center gap-1">
                                   <span className="text-muted-foreground">Theaters:</span>
                                   <span className="font-medium">{job.theaters_completed}/{job.theaters_total}</span>
                                </div>
                                {job.showings_completed !== undefined && (
                                   <div className="flex items-center gap-1">
                                      <span className="text-muted-foreground">Showings:</span>
                                      <span className="font-medium">{job.showings_completed}</span>
                                   </div>
                                )}
                                {job.error && (
                                   <div className="text-red-500 truncate flex-1 flex items-center gap-1">
                                      <AlertTriangle className="h-3 w-3" />
                                      {job.error}
                                   </div>
                                )}
                             </div>
                          </div>
                       ))}
                    </div>
                 )}
              </CardContent>
           </Card>
        </TabsContent>
      </Tabs>

      {/* Delete Cache Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-500">
              <AlertTriangle className="h-5 w-5" />
              Clear Cache
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to clear the theater cache? This will remove all cached
              theater data and you will need to rebuild the cache before running scrapes.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground">
              Current cache contains:
            </p>
            <ul className="text-sm mt-2 space-y-1">
              <li><strong>{marketCount}</strong> markets</li>
              <li><strong>{theaterCount}</strong> theaters</li>
              <li><strong>{formatBytes(totalCacheSize)}</strong> of data</li>
            </ul>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteCache}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Clearing...' : 'Clear Cache'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Theater URL Dialog */}
      <Dialog open={!!editingTheater} onOpenChange={(open) => !open && setEditingTheater(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Theater URL</DialogTitle>
            <DialogDescription>
              Directly update the Fandango URL for this theater in the cache.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-4">
             <div>
                <Label className="text-xs font-bold text-muted-foreground uppercase">Theater</Label>
                <p className="font-medium">{editingTheater?.theater_name}</p>
                <p className="text-xs text-muted-foreground">{editingTheater?.market}</p>
             </div>
             <div className="space-y-2">
                <Label htmlFor="edit-url">Fandango URL</Label>
                <Input 
                   id="edit-url"
                   value={newUrl}
                   onChange={(e) => setNewUrl(e.target.value)}
                   placeholder="https://www.fandango.com/..."
                />
             </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingTheater(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdateTheaterUrl}
              disabled={matchMutation.isPending}
            >
              Update Cache
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}
