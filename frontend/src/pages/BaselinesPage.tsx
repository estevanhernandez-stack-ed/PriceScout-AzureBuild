/**
 * Price Baselines Page (Simplified)
 *
 * Tabs:
 * 1. Overview - Coverage stats and data source summary
 * 2. My Markets - Director -> Market -> Theater hierarchy with baseline discovery
 * 3. Company Profiles - Circuit pricing patterns (discount days, ticket types, etc.)
 * 4. Baseline Details - Granular view of all individual baselines
 * 5. Coverage Gaps - Identify missing data for better surge detection
 * 6. Surge Scanner - Detect surge pricing in advance data
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
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
  Target,
  Database,
  Search,
  Building2,
  DollarSign,
  Loader2,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react';
import {
  useBaselines,
  useEntTelligenceAnalyze,
  useFandangoAnalyze,
  useAdvanceSurgeScan,
  useNewFilmMonitor,
  type SurgeDetection,
  type NewFilmSurge,
} from '@/hooks/api';
import { useToast } from '@/hooks/use-toast';
import { CompanyProfilesPanel } from '@/components/baselines/CompanyProfilesPanel';
import { BaselineDetailsPanel } from '@/components/baselines/BaselineDetailsPanel';
import { CoverageGapsPanel } from '@/components/baselines/CoverageGapsPanel';
import { UserCentricOverview } from '@/components/baselines/UserCentricOverview';
import { DataSourceComparisonPanel } from '@/components/baselines/DataSourceComparisonPanel';
import { MyMarketsPanel } from '@/components/baselines/MyMarketsPanel';
import { AlternativeContentPanel } from '@/components/baselines/AlternativeContentPanel';
import { TheaterOnboardingWizard } from '@/components/onboarding';

export function BaselinesPage() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('overview');

  // Surge scanner state
  const [surgeDateFrom, setSurgeDateFrom] = useState<string>('');
  const [surgeDateTo, setSurgeDateTo] = useState<string>('');
  const [surgeCircuit, setSurgeCircuit] = useState<string>('');
  const [surgeTheater, setSurgeTheater] = useState<string>('');
  const [surgeFilm, setSurgeFilm] = useState<string>('');
  const [surgeThreshold, setSurgeThreshold] = useState<number>(20);
  const [minSurgeAmount, setMinSurgeAmount] = useState<number>(1);
  const [runSurgeScan, setRunSurgeScan] = useState(false);

  // New film monitoring state
  const [newFilmLookbackHours, setNewFilmLookbackHours] = useState<number>(24);
  const [runNewFilmScan, setRunNewFilmScan] = useState(false);

  // Saved baselines
  const { data: savedBaselines, isLoading: baselinesLoading } = useBaselines({ activeOnly: true });

  // EntTelligence analysis (always load for overview)
  const { data: entAnalysis, isLoading: entAnalysisLoading } = useEntTelligenceAnalyze({
    lookbackDays: 30,
    enabled: true,
  });

  // Fandango analysis
  const { data: fandangoAnalysis, isLoading: fandangoAnalysisLoading } = useFandangoAnalyze({
    lookbackDays: 30,
    enabled: true,
  });

  // Surge scanner
  const {
    data: surgeScanResults,
    isLoading: surgeScanLoading,
    refetch: refetchSurgeScan,
  } = useAdvanceSurgeScan(
    {
      dateFrom: surgeDateFrom,
      dateTo: surgeDateTo,
      circuit: surgeCircuit || undefined,
      theater: surgeTheater || undefined,
      film: surgeFilm || undefined,
      surgeThreshold,
      minSurgeAmount,
    },
    { enabled: runSurgeScan && !!surgeDateFrom && !!surgeDateTo }
  );

  const handleRunSurgeScan = () => {
    if (!surgeDateFrom || !surgeDateTo) {
      toast({
        title: 'Missing Dates',
        description: 'Please select both start and end dates.',
        variant: 'destructive',
      });
      return;
    }
    setRunSurgeScan(true);
    refetchSurgeScan();
  };

  // New film monitoring
  const {
    data: newFilmResults,
    isLoading: newFilmLoading,
    refetch: refetchNewFilm,
  } = useNewFilmMonitor(
    {
      lookbackHours: newFilmLookbackHours,
      surgeThreshold,
      minSurgeAmount,
    },
    { enabled: runNewFilmScan }
  );

  const handleRunNewFilmScan = () => {
    setRunNewFilmScan(true);
    refetchNewFilm();
  };

  // Stats calculations
  const entStats = entAnalysis?.overall_stats;
  const fandangoStats = fandangoAnalysis?.overall_stats;
  const hasEntData = (entStats?.total_records ?? 0) > 0;
  const hasFandangoData = (fandangoStats?.total_records ?? 0) > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Price Baselines</h1>
        <p className="text-muted-foreground">
          Discover and manage baseline prices for surge detection across your markets.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Baselines</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {baselinesLoading ? '...' : savedBaselines?.length ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">Saved for surge detection</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">EntTelligence Data</CardTitle>
            <Database className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {entAnalysisLoading ? '...' : (entStats?.total_records ?? 0).toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">
              {entStats?.total_theaters?.toLocaleString() ?? 0} theaters, {entStats?.total_circuits ?? 0} circuits
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Fandango Data</CardTitle>
            <Building2 className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {fandangoAnalysisLoading ? '...' : (fandangoStats?.total_records ?? 0).toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">
              {hasFandangoData
                ? `${fandangoStats?.total_theaters?.toLocaleString() ?? 0} theaters, ${fandangoStats?.total_circuits ?? 0} circuits`
                : 'Run scrapes to populate'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Price</CardTitle>
            <DollarSign className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              ${(fandangoStats?.overall_avg_price ?? entStats?.overall_avg_price)?.toFixed(2) ?? '0.00'}
            </div>
            <p className="text-xs text-muted-foreground">
              {hasFandangoData && hasEntData
                ? `Fandango: $${fandangoStats?.overall_avg_price?.toFixed(2)} • Ent: $${entStats?.overall_avg_price?.toFixed(2)}`
                : hasFandangoData
                  ? 'From Fandango scrapes'
                  : 'From EntTelligence data'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="my-markets">My Markets</TabsTrigger>
          <TabsTrigger value="company-profiles">Company Profiles</TabsTrigger>
          <TabsTrigger value="alternative-content">Alternative Content</TabsTrigger>
          <TabsTrigger value="baseline-details">Baseline Details</TabsTrigger>
          <TabsTrigger value="data-comparison">Data Sources</TabsTrigger>
          <TabsTrigger value="coverage-gaps">Coverage Gaps</TabsTrigger>
          <TabsTrigger value="surge">Surge Scanner</TabsTrigger>
          <TabsTrigger value="onboarding">Theater Onboarding</TabsTrigger>
        </TabsList>

        {/* Overview Tab - User-Centric Dashboard */}
        <TabsContent value="overview" className="space-y-4">
          <UserCentricOverview onNavigateToTab={setActiveTab} />
        </TabsContent>

        {/* My Markets Tab */}
        <TabsContent value="my-markets" className="space-y-4">
          <MyMarketsPanel />
        </TabsContent>

        {/* Company Profiles Tab */}
        <TabsContent value="company-profiles" className="space-y-4">
          <CompanyProfilesPanel />
        </TabsContent>

        {/* Alternative Content Tab */}
        <TabsContent value="alternative-content" className="space-y-4">
          <AlternativeContentPanel />
        </TabsContent>

        {/* Baseline Details Tab */}
        <TabsContent value="baseline-details" className="space-y-4">
          <BaselineDetailsPanel />
        </TabsContent>

        {/* Data Source Comparison Tab */}
        <TabsContent value="data-comparison" className="space-y-4">
          <DataSourceComparisonPanel />
        </TabsContent>

        {/* Coverage Gaps Tab */}
        <TabsContent value="coverage-gaps" className="space-y-4">
          <CoverageGapsPanel />
        </TabsContent>

        {/* Surge Scanner Tab */}
        <TabsContent value="surge" className="space-y-4">
          {/* Info Banner */}
          {/* New Film Monitoring Card */}
          <Card className="border-purple-200 bg-purple-50/50 dark:border-purple-900 dark:bg-purple-950/20">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-purple-700 dark:text-purple-300">
                <AlertCircle className="h-5 w-5" />
                New Film Price Monitor
              </CardTitle>
              <CardDescription>
                Detect surge pricing on recently posted films and presale openings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="space-y-1">
                  <Label>Lookback Period</Label>
                  <Select
                    value={String(newFilmLookbackHours)}
                    onValueChange={(v) => setNewFilmLookbackHours(parseInt(v))}
                  >
                    <SelectTrigger className="w-[180px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="6">Last 6 hours</SelectItem>
                      <SelectItem value="12">Last 12 hours</SelectItem>
                      <SelectItem value="24">Last 24 hours</SelectItem>
                      <SelectItem value="48">Last 48 hours</SelectItem>
                      <SelectItem value="72">Last 72 hours</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  onClick={handleRunNewFilmScan}
                  disabled={newFilmLoading}
                  variant="outline"
                  className="mt-5"
                >
                  {newFilmLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Scanning...
                    </>
                  ) : (
                    <>
                      <Search className="mr-2 h-4 w-4" />
                      Check New Films
                    </>
                  )}
                </Button>
              </div>

              {runNewFilmScan && newFilmResults && (
                <div className="mt-4 space-y-3">
                  <div className="flex items-center gap-4 text-sm">
                    <Badge variant={newFilmResults.surges_found > 0 ? 'destructive' : 'secondary'}>
                      {newFilmResults.surges_found} surges found
                    </Badge>
                    <span className="text-muted-foreground">
                      Checked {newFilmResults.total_new_prices.toLocaleString()} new prices •{' '}
                      {newFilmResults.films_checked.length} films
                    </span>
                  </div>

                  {newFilmResults.surges.length > 0 ? (
                    <div className="rounded-md border max-h-[300px] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Film</TableHead>
                            <TableHead>Theater</TableHead>
                            <TableHead>Type</TableHead>
                            <TableHead className="text-right">Price</TableHead>
                            <TableHead className="text-right">Baseline</TableHead>
                            <TableHead className="text-right">Surge</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {newFilmResults.surges.slice(0, 20).map((surge: NewFilmSurge, i: number) => (
                            <TableRow key={i}>
                              <TableCell className="font-medium max-w-[150px] truncate">
                                <div className="flex items-center gap-1">
                                  {surge.film_title}
                                  {surge.is_presale && (
                                    <Badge variant="outline" className="text-xs px-1 py-0">
                                      Presale
                                    </Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="max-w-[150px] truncate text-muted-foreground">
                                {surge.theater_name}
                              </TableCell>
                              <TableCell>
                                {surge.ticket_type}
                                {surge.format && surge.format !== '2D' && (
                                  <Badge variant="outline" className="ml-1 text-xs">
                                    {surge.format}
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="text-right font-medium">
                                ${surge.current_price.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right text-muted-foreground">
                                ${surge.baseline_price.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right">
                                <Badge variant="destructive">+{surge.surge_percent.toFixed(1)}%</Badge>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <div className="text-center py-4 text-muted-foreground">
                      <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
                      No surge pricing detected on new films
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Advance Surge Scanner Info */}
          <Card className="border-orange-200 bg-orange-50/50 dark:border-orange-900 dark:bg-orange-950/20">
            <CardContent className="py-4">
              <div className="flex items-start gap-3">
                <TrendingUp className="h-5 w-5 text-orange-500 mt-0.5 flex-shrink-0" />
                <div className="text-sm">
                  <p className="font-medium text-orange-700 dark:text-orange-300">
                    Advance Surge Price Detection
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Scan EntTelligence cache data for surge pricing on upcoming dates. Compares advance prices
                    against your baselines to detect surge pricing before it becomes current. Perfect for
                    identifying surges on special events, holidays, or high-demand films.
                  </p>
                  <p className="text-muted-foreground mt-2">
                    <strong>Detection:</strong> Flags a surge if price exceeds baseline by{' '}
                    <span className="font-mono">&ge; {surgeThreshold}%</span> <strong>OR</strong>{' '}
                    <span className="font-mono">&ge; ${minSurgeAmount.toFixed(2)}</span>. This catches premium
                    format surges (e.g., $1 on a $22 IMAX ticket is only 4.5%).
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Search className="h-5 w-5" />
                Scan Parameters
              </CardTitle>
              <CardDescription>Select a date range to scan for surge pricing</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-2">
                  <Label>Start Date</Label>
                  <Input type="date" value={surgeDateFrom} onChange={(e) => setSurgeDateFrom(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>End Date</Label>
                  <Input type="date" value={surgeDateTo} onChange={(e) => setSurgeDateTo(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Surge Threshold %</Label>
                  <Input
                    type="number"
                    value={surgeThreshold}
                    onChange={(e) => setSurgeThreshold(parseInt(e.target.value) || 0)}
                    min={0}
                    max={100}
                    placeholder="e.g., 20"
                  />
                  <p className="text-xs text-muted-foreground">0 to disable % check</p>
                </div>
                <div className="space-y-2">
                  <Label>Min Surge Amount $</Label>
                  <Input
                    type="number"
                    step="0.25"
                    value={minSurgeAmount}
                    onChange={(e) => setMinSurgeAmount(parseFloat(e.target.value) || 0)}
                    min={0}
                    max={50}
                    placeholder="e.g., 1.00"
                  />
                  <p className="text-xs text-muted-foreground">0 to disable $ check</p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Circuit Filter</Label>
                  <Input
                    placeholder="e.g., Marcus"
                    value={surgeCircuit}
                    onChange={(e) => setSurgeCircuit(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Theater Filter</Label>
                  <Input
                    placeholder="e.g., IMAX"
                    value={surgeTheater}
                    onChange={(e) => setSurgeTheater(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Film Filter</Label>
                  <Input
                    placeholder="e.g., Wuthering Heights"
                    value={surgeFilm}
                    onChange={(e) => setSurgeFilm(e.target.value)}
                  />
                </div>
              </div>

              <Button onClick={handleRunSurgeScan} disabled={surgeScanLoading || !surgeDateFrom || !surgeDateTo}>
                {surgeScanLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Scanning...
                  </>
                ) : (
                  <>
                    <Search className="mr-2 h-4 w-4" />
                    Scan for Surges
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Scan Results */}
          {runSurgeScan && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-orange-500" />
                  Scan Results
                  {surgeScanResults && (
                    <Badge variant={surgeScanResults.total_surges_found > 0 ? 'destructive' : 'secondary'}>
                      {surgeScanResults.total_surges_found} surges found
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  {surgeScanResults && (
                    <span>
                      Scanned {surgeScanResults.total_prices_scanned.toLocaleString()} prices from{' '}
                      {surgeScanResults.scan_date_from} to {surgeScanResults.scan_date_to}
                      {' '}(thresholds: {surgeScanResults.surge_threshold_percent}%
                      {surgeScanResults.min_surge_amount
                        ? ` or $${surgeScanResults.min_surge_amount.toFixed(2)}`
                        : ''}
                      )
                    </span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {surgeScanLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : surgeScanResults && surgeScanResults.surges.length > 0 ? (
                  <div className="space-y-4">
                    {/* Summary */}
                    <div className="flex flex-wrap gap-4 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">Circuits:</span>
                        <span>{surgeScanResults.circuits_scanned.join(', ')}</span>
                      </div>
                      {surgeScanResults.films_with_surges.length > 0 && (
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Films with surges:</span>
                          <span>{surgeScanResults.films_with_surges.join(', ')}</span>
                        </div>
                      )}
                      {surgeScanResults.discount_day_prices_filtered > 0 && (
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="bg-blue-100 text-blue-700">
                            {surgeScanResults.discount_day_prices_filtered} discount day prices filtered
                          </Badge>
                        </div>
                      )}
                      {surgeScanResults.circuits_with_profiles?.length > 0 && (
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Profile-aware:</span>
                          <span className="text-green-600">{surgeScanResults.circuits_with_profiles.join(', ')}</span>
                        </div>
                      )}
                    </div>

                    {/* Results Table */}
                    <div className="rounded-md border max-h-[500px] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Theater</TableHead>
                            <TableHead>Film</TableHead>
                            <TableHead>Date</TableHead>
                            <TableHead>Type</TableHead>
                            <TableHead>Day/Time</TableHead>
                            <TableHead className="text-right">Price</TableHead>
                            <TableHead className="text-right">Baseline</TableHead>
                            <TableHead className="text-right">Surge</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {surgeScanResults.surges.map((surge: SurgeDetection, i: number) => (
                            <TableRow key={i}>
                              <TableCell className="max-w-[200px] truncate" title={surge.theater_name}>
                                <div className="font-medium">{surge.theater_name}</div>
                                <div className="flex items-center gap-1">
                                  {surge.circuit_name && (
                                    <span className="text-xs text-muted-foreground">{surge.circuit_name}</span>
                                  )}
                                  {surge.is_discount_day && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs px-1 py-0 bg-yellow-100 text-yellow-700"
                                      title={surge.discount_day_price ? `Expected: $${surge.discount_day_price}` : 'Discount day'}
                                    >
                                      Disc Day
                                    </Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="max-w-[150px] truncate" title={surge.film_title}>
                                {surge.film_title}
                              </TableCell>
                              <TableCell>{surge.play_date}</TableCell>
                              <TableCell>
                                {surge.ticket_type}
                                {surge.format && surge.format !== '2D' && (
                                  <Badge variant="outline" className="ml-1 text-xs">
                                    {surge.format}
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col gap-1">
                                  {surge.day_of_week !== null ? (
                                    <Badge
                                      variant={
                                        surge.day_of_week >= 4
                                          ? 'default'
                                          : surge.day_of_week === 1
                                          ? 'destructive'
                                          : 'secondary'
                                      }
                                      className="text-xs w-fit"
                                    >
                                      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][surge.day_of_week]}
                                    </Badge>
                                  ) : (
                                    <Badge
                                      variant={surge.day_type === 'weekend' ? 'default' : 'secondary'}
                                      className="text-xs w-fit"
                                    >
                                      {surge.day_type === 'weekend' ? 'Wknd' : 'Wkdy'}
                                    </Badge>
                                  )}
                                  {surge.daypart && (
                                    <Badge
                                      variant={
                                        surge.daypart === 'matinee'
                                          ? 'secondary'
                                          : surge.daypart === 'evening'
                                          ? 'default'
                                          : 'outline'
                                      }
                                      className="text-xs w-fit"
                                    >
                                      {surge.daypart === 'matinee'
                                        ? 'Mat'
                                        : surge.daypart === 'evening'
                                        ? 'Eve'
                                        : 'Late'}
                                    </Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="text-right font-mono font-bold text-red-600">
                                ${surge.current_price.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right font-mono text-muted-foreground">
                                ${surge.baseline_price.toFixed(2)}
                              </TableCell>
                              <TableCell className="text-right">
                                <span className="text-red-600 font-bold">+{surge.surge_percent.toFixed(0)}%</span>
                                <span className="text-xs text-muted-foreground ml-1">
                                  (+${(surge.current_price - surge.baseline_price).toFixed(2)})
                                </span>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>

                    {surgeScanResults.surges.length >= 200 && (
                      <p className="text-sm text-muted-foreground text-center">
                        Showing first 200 results. Narrow your search to see more.
                      </p>
                    )}
                  </div>
                ) : surgeScanResults ? (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <CheckCircle2 className="h-8 w-8 mb-2 text-green-500" />
                    <p>No surge pricing detected</p>
                    <p className="text-sm">
                      All prices are within thresholds ({surgeThreshold > 0 ? `${surgeThreshold}%` : ''}
                      {surgeThreshold > 0 && minSurgeAmount > 0 ? ' or ' : ''}
                      {minSurgeAmount > 0 ? `$${minSurgeAmount.toFixed(2)}` : ''})
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <AlertCircle className="h-8 w-8 mb-2" />
                    <p>Enter dates and click &quot;Scan for Surges&quot; to begin</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Theater Onboarding Tab */}
        <TabsContent value="onboarding" className="space-y-4">
          <TheaterOnboardingWizard
            onComplete={() => {
              toast({
                title: 'Theater Onboarded',
                description: 'The theater has been successfully onboarded with baselines configured.',
              });
              setActiveTab('my-markets');
            }}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
