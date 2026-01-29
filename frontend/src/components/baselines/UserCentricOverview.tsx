/**
 * UserCentricOverview - Personalized dashboard for theater operators
 *
 * Transforms the Overview tab from "system dashboard" to "MY dashboard"
 * Shows only the user's company data with actionable insights.
 */

import { useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  Building2,
  DollarSign,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
  Zap,
  Film,
  MapPin,
  CheckCircle2,
  AlertCircle,
  Tag,
  ArrowRight,
  Loader2,
  Database,
  UserPlus,
  Settings,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import {
  useCoverageHierarchy,
  useAlertSummary,
  useCompanyProfiles,
  useBaselines,
  useCircuitBenchmarks,
  useEntTelligenceAnalyze,
  useFandangoAnalyze,
  usePendingTheaters,
  useACFilms,
  getContentTypeColor,
  type CoverageHierarchy,
  type CompanyProfile,
  type SavedBaseline,
} from '@/hooks/api';

// Helper to extract circuit name from user's company
function getCircuitFromCompany(company: string | null | undefined): string {
  if (!company) return '';
  // Common transformations: "Marcus Theatres" -> "Marcus"
  const words = company.split(' ');
  if (words.length > 1 && words[1].toLowerCase() === 'theatres') {
    return words[0];
  }
  return company;
}

// Get all theaters for a company from coverage hierarchy
function getMyTheaters(
  hierarchy: CoverageHierarchy | undefined,
  company: string | null | undefined,
  locationType?: string | null,
  locationValue?: string | null
): string[] {
  if (!hierarchy || !company) return [];

  const companyData = hierarchy[company];
  if (!companyData) return [];

  const theaters: string[] = [];

  Object.entries(companyData.directors).forEach(([directorName, directorData]) => {
    Object.entries(directorData.markets).forEach(([marketName, marketData]) => {
      // If user is market-scoped, only include their market
      if (locationType === 'market' && locationValue && marketName !== locationValue) {
        return;
      }
      // If user is director-scoped, only include their director's markets
      if (locationType === 'director' && locationValue && directorName !== locationValue) {
        return;
      }

      marketData.theaters.forEach((t) => theaters.push(t.theater_name));
    });
  });

  return theaters;
}

// Calculate my coverage stats from hierarchy
function getMyStats(
  hierarchy: CoverageHierarchy | undefined,
  company: string | null | undefined
): { totalTheaters: number; totalGaps: number; avgCoverage: number } {
  if (!hierarchy || !company) {
    return { totalTheaters: 0, totalGaps: 0, avgCoverage: 0 };
  }

  const companyData = hierarchy[company];
  if (!companyData) {
    return { totalTheaters: 0, totalGaps: 0, avgCoverage: 0 };
  }

  return {
    totalTheaters: companyData.total_theaters,
    totalGaps: companyData.total_gaps,
    avgCoverage: companyData.avg_coverage_score,
  };
}

interface DiscountDayIssue {
  theater: string;
  expectedPrice: number;
  actualPrice: number;
  dayOfWeek: number;
  program: string;
}

// Check discount day compliance
function checkDiscountCompliance(
  profile: CompanyProfile | undefined,
  baselines: SavedBaseline[] | undefined,
  myTheaters: string[]
): DiscountDayIssue[] {
  if (!profile?.has_discount_days || !baselines) return [];

  const issues: DiscountDayIssue[] = [];
  const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  profile.discount_days.forEach((discountDay) => {
    myTheaters.forEach((theater) => {
      // Find baseline for this theater on the discount day
      const baseline = baselines.find(
        (b) =>
          b.theater_name === theater &&
          b.day_of_week === discountDay.day_of_week &&
          (b.ticket_type.toLowerCase().includes('adult') ||
            b.ticket_type.toLowerCase().includes('general'))
      );

      if (baseline && Math.abs(baseline.baseline_price - discountDay.price) > 0.5) {
        issues.push({
          theater,
          expectedPrice: discountDay.price,
          actualPrice: baseline.baseline_price,
          dayOfWeek: discountDay.day_of_week,
          program: discountDay.program || `$${discountDay.price} ${dayNames[discountDay.day_of_week]}s`,
        });
      }
    });
  });

  return issues;
}

interface UserCentricOverviewProps {
  onNavigateToTab: (tab: string) => void;
}

export function UserCentricOverview({ onNavigateToTab }: UserCentricOverviewProps) {
  const user = useAuthStore((state) => state.user);
  const [showSystemView, setShowSystemView] = useState(false);

  // Use same fallback logic as MainLayout - default to 'Marcus Theatres' for admins
  const company = user?.company || user?.default_company || 'Marcus Theatres';
  const circuitName = getCircuitFromCompany(company);

  // Fetch data
  const { data: hierarchy, isLoading: hierarchyLoading } = useCoverageHierarchy({ lookbackDays: 90 });
  const { data: alertSummary, isLoading: alertsLoading } = useAlertSummary();
  const { data: profiles, isLoading: profilesLoading } = useCompanyProfiles();
  const { data: baselines, isLoading: baselinesLoading } = useBaselines({ activeOnly: true });
  const { data: benchmarks } = useCircuitBenchmarks({ limit: 20 });
  const { data: entAnalysis } = useEntTelligenceAnalyze({ lookbackDays: 30, enabled: true });
  const { data: fandangoAnalysis } = useFandangoAnalyze({ lookbackDays: 30, enabled: true });
  const { data: pendingTheaters } = usePendingTheaters();
  const { data: acFilmsData } = useACFilms({ isActive: true, limit: 100 });

  // Derive my theaters
  const myTheaters = useMemo(
    () => getMyTheaters(hierarchy, company, user?.home_location_type, user?.home_location_value),
    [hierarchy, company, user?.home_location_type, user?.home_location_value]
  );

  // Derive my stats
  const myStats = useMemo(() => getMyStats(hierarchy, company), [hierarchy, company]);

  // Get my circuit's profile
  const myProfile = useMemo(() => {
    if (!profiles?.profiles) return undefined;
    return profiles.profiles.find(
      (p) => p.circuit_name.toLowerCase().includes(circuitName.toLowerCase())
    );
  }, [profiles, circuitName]);

  // Filter baselines to my theaters
  const myBaselines = useMemo(() => {
    if (!baselines) return [];
    return baselines.filter((b) => myTheaters.includes(b.theater_name));
  }, [baselines, myTheaters]);

  // Calculate my avg price
  const myAvgPrice = useMemo(() => {
    if (myBaselines.length === 0) return 0;
    const adultBaselines = myBaselines.filter(
      (b) =>
        b.ticket_type.toLowerCase().includes('adult') ||
        b.ticket_type.toLowerCase().includes('general')
    );
    if (adultBaselines.length === 0) return 0;
    return adultBaselines.reduce((sum, b) => sum + b.baseline_price, 0) / adultBaselines.length;
  }, [myBaselines]);

  // Get market average from benchmarks (competitors)
  const marketAvgPrice = useMemo(() => {
    const benchmarkList = benchmarks?.benchmarks;
    if (!benchmarkList?.length) return 0;
    const otherCircuits = benchmarkList.filter(
      (b) => !b.circuit_name.toLowerCase().includes(circuitName.toLowerCase())
    );
    if (otherCircuits.length === 0) return myAvgPrice;
    return (
      otherCircuits.reduce((sum, b) => sum + (b.avg_price_general || 0), 0) / otherCircuits.length
    );
  }, [benchmarks, circuitName, myAvgPrice]);

  // Price position
  const priceDiff = myAvgPrice - marketAvgPrice;
  const priceDiffPercent = marketAvgPrice > 0 ? (priceDiff / marketAvgPrice) * 100 : 0;
  const pricePosition: 'above' | 'at' | 'below' =
    priceDiff > 0.25 ? 'above' : priceDiff < -0.25 ? 'below' : 'at';

  // Count my alerts (filter by my theaters)
  const myAlertCount = useMemo(() => {
    if (!alertSummary?.by_theater) return 0;
    return Object.entries(alertSummary.by_theater)
      .filter(([theater]) => myTheaters.includes(theater))
      .reduce((sum, [, count]) => sum + count, 0);
  }, [alertSummary, myTheaters]);

  // Check discount day compliance
  const discountIssues = useMemo(
    () => checkDiscountCompliance(myProfile, baselines, myTheaters),
    [myProfile, baselines, myTheaters]
  );

  const isLoading = hierarchyLoading || alertsLoading || profilesLoading || baselinesLoading;

  if (!company) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No Company Assigned</h3>
          <p className="text-muted-foreground text-sm">
            Contact your administrator to set up your company profile.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with company context */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Showing data for <span className="font-medium text-foreground">{company}</span>
            {user?.home_location_type === 'market' && user?.home_location_value && (
              <> in <span className="font-medium text-foreground">{user.home_location_value}</span> market</>
            )}
          </p>
        </div>
        {user?.is_admin && (
          <div className="flex items-center gap-2">
            <Switch
              id="system-view"
              checked={showSystemView}
              onCheckedChange={setShowSystemView}
            />
            <Label htmlFor="system-view" className="text-sm text-muted-foreground">
              System view
            </Label>
          </div>
        )}
      </div>

      {/* Main Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* My Theaters Health */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Building2 className="h-4 w-4 text-purple-500" />
              My Theater Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">{myTheaters.length}</span>
                  <span className="text-muted-foreground">theaters</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <Progress value={myStats.avgCoverage} className="h-2 flex-1" />
                  <span className="text-sm font-medium">{myStats.avgCoverage.toFixed(0)}%</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">baseline coverage</p>
              </div>

              {myStats.totalGaps > 0 && (
                <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
                  <AlertCircle className="h-3 w-3 mr-1" />
                  {myStats.totalGaps} coverage gap{myStats.totalGaps !== 1 ? 's' : ''}
                </Badge>
              )}

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between"
                onClick={() => onNavigateToTab('coverage-gaps')}
              >
                View Coverage Details
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Competitive Position */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <DollarSign className="h-4 w-4 text-green-500" />
              Competitive Position
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">${myAvgPrice.toFixed(2)}</span>
                  <span className="text-muted-foreground">avg price</span>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  {pricePosition === 'above' && (
                    <Badge className="bg-red-100 text-red-700 hover:bg-red-100">
                      <TrendingUp className="h-3 w-3 mr-1" />
                      {priceDiffPercent.toFixed(1)}% above market
                    </Badge>
                  )}
                  {pricePosition === 'below' && (
                    <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
                      <TrendingDown className="h-3 w-3 mr-1" />
                      {Math.abs(priceDiffPercent).toFixed(1)}% below market
                    </Badge>
                  )}
                  {pricePosition === 'at' && (
                    <Badge variant="outline">
                      <Minus className="h-3 w-3 mr-1" />
                      At market rate
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Market avg: ${marketAvgPrice.toFixed(2)}
                </p>
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between"
                onClick={() => onNavigateToTab('my-markets')}
              >
                Compare with Competitors
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Needs Attention */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Needs Attention
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between py-1">
                <span className="text-sm">Surge alerts</span>
                <Badge variant={myAlertCount > 0 ? 'destructive' : 'outline'}>
                  {myAlertCount}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-1">
                <span className="text-sm">Coverage gaps</span>
                <Badge variant={myStats.totalGaps > 0 ? 'secondary' : 'outline'}>
                  {myStats.totalGaps}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-1">
                <span className="text-sm">Discount day issues</span>
                <Badge variant={discountIssues.length > 0 ? 'secondary' : 'outline'}>
                  {discountIssues.length}
                </Badge>
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between mt-2"
                onClick={() => onNavigateToTab('surge')}
              >
                Review All Issues
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => onNavigateToTab('surge')}
              className="flex items-center gap-2"
            >
              <Zap className="h-4 w-4 text-yellow-500" />
              Scan for Surges
            </Button>
            <Button
              variant="outline"
              onClick={() => onNavigateToTab('surge')}
              className="flex items-center gap-2"
            >
              <Film className="h-4 w-4 text-blue-500" />
              Check New Films
            </Button>
            <Button
              variant="outline"
              onClick={() => onNavigateToTab('my-markets')}
              className="flex items-center gap-2"
            >
              <MapPin className="h-4 w-4 text-purple-500" />
              View My Markets
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Data Sources & System Status */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Data Freshness */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4 text-blue-500" />
              Data Sources
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {/* EntTelligence */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-blue-500" />
                  <span className="text-sm">EntTelligence</span>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {entAnalysis?.overall_stats?.total_records?.toLocaleString() ?? 0} records
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {entAnalysis?.overall_stats?.total_theaters ?? 0} theaters
                  </div>
                </div>
              </div>

              {/* Fandango */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-orange-500" />
                  <span className="text-sm">Fandango Scrapes</span>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium">
                    {fandangoAnalysis?.overall_stats?.total_records?.toLocaleString() ?? 0} records
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {fandangoAnalysis?.overall_stats?.total_theaters ?? 0} theaters
                  </div>
                </div>
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between mt-2"
                onClick={() => onNavigateToTab('data-comparison')}
              >
                Compare Data Sources
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Profile & Onboarding Status */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Settings className="h-4 w-4 text-purple-500" />
              Configuration Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {/* Profile Status */}
              <div className="flex items-center justify-between">
                <span className="text-sm">Company Profile</span>
                {myProfile ? (
                  <Badge className="bg-green-100 text-green-700 hover:bg-green-100">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Configured
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-yellow-600 border-yellow-300">
                    <AlertCircle className="h-3 w-3 mr-1" />
                    Not Set Up
                  </Badge>
                )}
              </div>

              {/* Discount Days */}
              <div className="flex items-center justify-between">
                <span className="text-sm">Discount Days</span>
                {myProfile?.has_discount_days ? (
                  <Badge variant="secondary">
                    {myProfile.discount_days.length} configured
                  </Badge>
                ) : (
                  <Badge variant="outline">None</Badge>
                )}
              </div>

              {/* Pending Theaters */}
              <div className="flex items-center justify-between">
                <span className="text-sm">Pending Theaters</span>
                {(pendingTheaters?.length ?? 0) > 0 ? (
                  <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                    <UserPlus className="h-3 w-3 mr-1" />
                    {pendingTheaters?.length} new
                  </Badge>
                ) : (
                  <Badge variant="outline">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    All set up
                  </Badge>
                )}
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between mt-2"
                onClick={() => onNavigateToTab('company-profiles')}
              >
                Manage Profile
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Discount Day Compliance */}
      {myProfile?.has_discount_days && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Tag className="h-4 w-4 text-blue-500" />
              Discount Day Status
            </CardTitle>
            <CardDescription>
              {myProfile.discount_days[0]?.program || 'Discount day'} compliance check
            </CardDescription>
          </CardHeader>
          <CardContent>
            {discountIssues.length === 0 ? (
              <div className="flex items-center gap-2 text-green-600 bg-green-50 dark:bg-green-950/20 rounded-md p-3">
                <CheckCircle2 className="h-5 w-5" />
                <span className="text-sm font-medium">
                  All theaters compliant with discount day pricing
                </span>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Alternative Content Notice */}
                {acFilmsData && acFilmsData.total > 0 && (
                  <div className="flex items-start gap-2 text-blue-600 bg-blue-50 dark:bg-blue-950/20 rounded-md p-3">
                    <Film className="h-5 w-5 mt-0.5 flex-shrink-0" />
                    <div className="text-sm">
                      <span className="font-medium">
                        {acFilmsData.total} Alternative Content film{acFilmsData.total !== 1 ? 's' : ''} detected
                      </span>
                      <p className="text-blue-600/80 dark:text-blue-400/80 mt-0.5">
                        Some variances below may be special events (Fathom, Opera, etc.) that are intentionally priced differently.
                      </p>
                    </div>
                  </div>
                )}

                <div className="text-sm text-muted-foreground">
                  {discountIssues.length} theater{discountIssues.length !== 1 ? 's' : ''} with
                  pricing variance
                </div>
                <div className="rounded-md border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left p-2 font-medium">Theater</th>
                        <th className="text-right p-2 font-medium">Expected</th>
                        <th className="text-right p-2 font-medium">Actual</th>
                        <th className="text-center p-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {discountIssues.slice(0, 5).map((issue, idx) => (
                        <tr key={idx} className="border-t">
                          <td className="p-2 truncate max-w-[200px]">{issue.theater}</td>
                          <td className="p-2 text-right font-mono">
                            ${issue.expectedPrice.toFixed(2)}
                          </td>
                          <td className="p-2 text-right font-mono text-orange-600">
                            ${issue.actualPrice.toFixed(2)}
                          </td>
                          <td className="p-2 text-center">
                            <Badge variant="outline" className="bg-yellow-50 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300">
                              +${(issue.actualPrice - issue.expectedPrice).toFixed(2)}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {discountIssues.length > 5 && (
                  <p className="text-xs text-muted-foreground">
                    Showing first 5 of {discountIssues.length} issues
                  </p>
                )}

                {/* Quick AC Films List */}
                {acFilmsData && acFilmsData.films.length > 0 && (
                  <div className="mt-4 pt-4 border-t">
                    <div className="text-sm font-medium mb-2 flex items-center gap-2">
                      <Film className="h-4 w-4 text-purple-500" />
                      Active Alternative Content
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {acFilmsData.films.slice(0, 6).map((film) => (
                        <Badge
                          key={film.id}
                          variant="secondary"
                          className={`text-xs ${getContentTypeColor(film.content_type)}`}
                        >
                          {film.film_title.length > 25
                            ? film.film_title.substring(0, 25) + '...'
                            : film.film_title}
                        </Badge>
                      ))}
                      {acFilmsData.total > 6 && (
                        <Badge variant="outline" className="text-xs">
                          +{acFilmsData.total - 6} more
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* My Baselines Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Building2 className="h-4 w-4 text-purple-500" />
            My Baselines Summary
          </CardTitle>
          <CardDescription>
            {myBaselines.length} active baselines across {myTheaters.length} theaters
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">{myBaselines.length}</div>
              <div className="text-sm text-muted-foreground">Active Baselines</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">
                {new Set(myBaselines.map((b) => b.ticket_type)).size}
              </div>
              <div className="text-sm text-muted-foreground">Ticket Types</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/30">
              <div className="text-2xl font-bold">
                {new Set(myBaselines.map((b) => b.format).filter(Boolean)).size}
              </div>
              <div className="text-sm text-muted-foreground">Formats Tracked</div>
            </div>
          </div>

          <Button
            variant="outline"
            className="w-full mt-4"
            onClick={() => onNavigateToTab('baseline-details')}
          >
            View All Baselines
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default UserCentricOverview;
