/**
 * Company Profiles Panel
 *
 * Displays and manages company/circuit pricing profiles.
 * Shows discovered ticket types, daypart schemes, discount days, and premium formats.
 */

import { useState } from 'react';
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
  Building2,
  RefreshCw,
  Loader2,
  AlertCircle,
  Tag,
  Calendar,
  Film,
  Clock,
  Trash2,
  CheckCircle2,
  XCircle,
  BarChart3,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  useCompanyProfiles,
  useDiscoverProfile,
  useDiscoverAllProfiles,
  useCleanupDuplicateProfiles,
  useDataCoverage,
  formatConfidence,
  getConfidenceLevel,
  getCoverageAssessmentColor,
  type CompanyProfile,
} from '@/hooks/api';
import { useToast } from '@/hooks/use-toast';
import { DiscountProgramsManager } from '@/components/profiles';

export function CompanyProfilesPanel() {
  const { toast } = useToast();
  const [newCircuitName, setNewCircuitName] = useState('');
  const [managingDiscountsFor, setManagingDiscountsFor] = useState<string | null>(null);
  const [showCoverageFor, setShowCoverageFor] = useState<string | null>(null);

  // Fetch profiles
  const { data: profilesData, isLoading, refetch } = useCompanyProfiles();
  const discoverProfile = useDiscoverProfile();
  const discoverAllProfiles = useDiscoverAllProfiles();
  const cleanupDuplicates = useCleanupDuplicateProfiles();

  // Data coverage for the circuit being typed
  const { data: coverageData, isLoading: coverageLoading } = useDataCoverage(
    newCircuitName.trim().length >= 3 ? newCircuitName.trim() : null
  );

  const profiles = profilesData?.profiles ?? [];

  const handleDiscoverProfile = async () => {
    if (!newCircuitName.trim()) {
      toast({
        title: 'Missing Circuit Name',
        description: 'Please enter a circuit name to discover.',
        variant: 'destructive',
      });
      return;
    }

    try {
      const result = await discoverProfile.mutateAsync({
        circuit_name: newCircuitName.trim(),
        lookback_days: 90,
        min_samples: 10,
      });
      toast({
        title: 'Profile Discovered',
        description: result.message,
      });
      setNewCircuitName('');
      refetch();
    } catch (error) {
      toast({
        title: 'Discovery Failed',
        description: error instanceof Error ? error.message : 'Failed to discover profile',
        variant: 'destructive',
      });
    }
  };

  const handleDiscoverAll = async () => {
    try {
      const result = await discoverAllProfiles.mutateAsync({
        lookbackDays: 90,
        minSamples: 10,
      });
      toast({
        title: 'Profiles Discovered',
        description: `Discovered ${result.total} circuit profiles.`,
      });
      refetch();
    } catch (error) {
      toast({
        title: 'Discovery Failed',
        description: error instanceof Error ? error.message : 'Failed to discover profiles',
        variant: 'destructive',
      });
    }
  };

  const handleCleanupDuplicates = async () => {
    try {
      const result = await cleanupDuplicates.mutateAsync();
      console.log('Cleanup result:', result); // Debug logging
      if (result.deleted.length > 0) {
        const keptInfo = result.kept?.join(', ') || 'none';
        toast({
          title: 'Duplicates Cleaned Up',
          description: `Kept: ${keptInfo}. Deleted: ${result.deleted.join(', ')}`,
        });
      } else {
        const existingInfo = result.existing_before
          ?.map(p => `${p.name} (${p.theaters})`)
          .join(', ') || 'none';
        toast({
          title: 'No Duplicates Found',
          description: `Existing profiles: ${existingInfo}`,
        });
      }
      refetch();
    } catch (error) {
      console.error('Cleanup error:', error);
      toast({
        title: 'Cleanup Failed',
        description: error instanceof Error ? error.message : 'Failed to cleanup duplicates',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="space-y-4">
      {/* Discovery Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-blue-500" />
            Discover Circuit Profiles
          </CardTitle>
          <CardDescription>
            Analyze pricing data to discover ticket types, daypart schemes, discount days, and premium formats for each circuit.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <Label htmlFor="circuit-name">Circuit Name</Label>
              <Input
                id="circuit-name"
                placeholder="e.g., Marcus Theatres, AMC, Regal"
                value={newCircuitName}
                onChange={(e) => setNewCircuitName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleDiscoverProfile()}
              />
            </div>
            <Button
              onClick={handleDiscoverProfile}
              disabled={discoverProfile.isPending || !newCircuitName.trim()}
            >
              {discoverProfile.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Discover
            </Button>
            <Button
              variant="outline"
              onClick={handleDiscoverAll}
              disabled={discoverAllProfiles.isPending}
            >
              {discoverAllProfiles.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Discover All Known Circuits
            </Button>
            <Button
              variant="ghost"
              onClick={handleCleanupDuplicates}
              disabled={cleanupDuplicates.isPending}
              className="text-orange-600 hover:text-orange-700 hover:bg-orange-50"
            >
              {cleanupDuplicates.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Cleanup Duplicates
            </Button>
          </div>

          {/* Data Coverage Preview */}
          {newCircuitName.trim().length >= 3 && (
            <DataCoveragePreview
              circuitName={newCircuitName.trim()}
              coverageData={coverageData}
              isLoading={coverageLoading}
            />
          )}
        </CardContent>
      </Card>

      {/* Profiles List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Tag className="h-5 w-5 text-green-500" />
            Discovered Profiles ({profiles.length})
          </CardTitle>
          <CardDescription>
            Pricing characteristics for each theater circuit
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : profiles.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <AlertCircle className="h-12 w-12 mb-4" />
              <p>No profiles discovered yet.</p>
              <p className="text-sm">Click "Discover All Known Circuits" to get started.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {profiles.map((profile) => (
                <ProfileCard
                  key={profile.profile_id}
                  profile={profile}
                  onManageDiscounts={() => setManagingDiscountsFor(profile.circuit_name)}
                  onShowCoverage={() => setShowCoverageFor(
                    showCoverageFor === profile.circuit_name ? null : profile.circuit_name
                  )}
                  showCoverage={showCoverageFor === profile.circuit_name}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Discount Programs Manager */}
      {managingDiscountsFor && (
        <DiscountProgramsManager
          circuitName={managingDiscountsFor}
          className="mt-4"
        />
      )}
    </div>
  );
}

interface ProfileCardProps {
  profile: CompanyProfile;
  onManageDiscounts?: () => void;
  onShowCoverage?: () => void;
  showCoverage?: boolean;
}

function ProfileCard({ profile, onManageDiscounts, onShowCoverage, showCoverage }: ProfileCardProps) {
  const [expanded, setExpanded] = useState(false);

  // Fetch coverage data when requested
  const { data: coverageData, isLoading: coverageLoading } = useDataCoverage(
    showCoverage ? profile.circuit_name : null
  );

  return (
    <div className="border rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Building2 className="h-5 w-5 text-blue-500" />
          <div>
            <h3 className="font-semibold text-lg">{profile.circuit_name}</h3>
            <p className="text-sm text-muted-foreground">
              {profile.theater_count} theaters | {profile.sample_count.toLocaleString()} samples
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {getConfidenceBadge(profile.confidence_score)}
          {getSchemeBadge(profile.daypart_scheme)}
          {onShowCoverage && (
            <Button
              variant="outline"
              size="sm"
              onClick={onShowCoverage}
              className={showCoverage ? 'bg-blue-50 border-blue-300' : ''}
            >
              <BarChart3 className="h-4 w-4 mr-1" />
              Coverage
            </Button>
          )}
          {onManageDiscounts && (
            <Button variant="outline" size="sm" onClick={onManageDiscounts}>
              <Calendar className="h-4 w-4 mr-1" />
              Manage Discounts
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Less' : 'More'}
          </Button>
        </div>
      </div>

      {/* Summary Row */}
      <div className="flex flex-wrap gap-2">
        {profile.has_flat_matinee && (
          <Badge variant="outline" className="text-blue-600">
            <Clock className="h-3 w-3 mr-1" />
            Flat Matinee
          </Badge>
        )}
        {profile.has_discount_days && (
          <Badge variant="outline" className="text-green-600">
            <Calendar className="h-3 w-3 mr-1" />
            Discount Days
          </Badge>
        )}
        {profile.premium_formats.length > 0 && (
          <Badge variant="outline" className="text-purple-600">
            <Film className="h-3 w-3 mr-1" />
            {profile.premium_formats.length} Premium Formats
          </Badge>
        )}
        <Badge variant="outline" className="text-gray-600">
          <Tag className="h-3 w-3 mr-1" />
          {profile.ticket_types.length} Ticket Types
        </Badge>
      </div>

      {/* Discount Days Quick View */}
      {profile.discount_days.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Discount Days:</span>
          {profile.discount_days.map((dd, idx) => (
            <Badge key={idx} variant="secondary" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
              {dd.program}
            </Badge>
          ))}
        </div>
      )}

      {/* Coverage Data */}
      {showCoverage && (
        <DataCoveragePreview
          circuitName={profile.circuit_name}
          coverageData={coverageData}
          isLoading={coverageLoading}
        />
      )}

      {/* Expanded Details */}
      {expanded && (
        <div className="pt-4 border-t space-y-4">
          {/* Ticket Types */}
          <div>
            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
              <Tag className="h-4 w-4" />
              Ticket Types ({profile.ticket_types.length})
            </h4>
            <div className="flex flex-wrap gap-1">
              {profile.ticket_types.map((type) => (
                <Badge key={type} variant="outline" className="text-xs">
                  {type}
                </Badge>
              ))}
            </div>
          </div>

          {/* Discount Days Detail */}
          {profile.discount_days.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Discount Day Programs
              </h4>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Program</TableHead>
                    <TableHead>Day</TableHead>
                    <TableHead>Price</TableHead>
                    <TableHead>Samples</TableHead>
                    <TableHead>Below Avg</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {profile.discount_days.map((dd, idx) => (
                    <TableRow key={idx}>
                      <TableCell className="font-medium">{dd.program}</TableCell>
                      <TableCell>{dd.day}</TableCell>
                      <TableCell>${dd.price.toFixed(2)}</TableCell>
                      <TableCell>{dd.sample_count}</TableCell>
                      <TableCell className="text-green-600">-{dd.below_avg_pct.toFixed(1)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Premium Formats */}
          {profile.premium_formats.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <Film className="h-4 w-4" />
                Premium Formats & Surcharges
              </h4>
              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                {profile.premium_formats.map((format) => (
                  <div key={format} className="flex items-center justify-between border rounded p-2">
                    <span>{format}</span>
                    {profile.premium_surcharges[format] && (
                      <Badge variant="secondary">
                        +${profile.premium_surcharges[format].toFixed(2)}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Daypart Boundaries */}
          {Object.keys(profile.daypart_boundaries).length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <Clock className="h-4 w-4" />
                Daypart Time Ranges
              </h4>
              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                {Object.entries(profile.daypart_boundaries).map(([daypart, range]) => (
                  <div key={daypart} className="flex items-center justify-between border rounded p-2">
                    <span className="font-medium">{daypart}</span>
                    <span className="text-sm text-muted-foreground">{range}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Data Quality */}
          <div className="text-sm text-muted-foreground">
            <p>
              Data range: {profile.date_range_start || 'N/A'} to {profile.date_range_end || 'N/A'}
            </p>
            <p>
              Last updated: {profile.last_updated_at ? new Date(profile.last_updated_at).toLocaleString() : 'N/A'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function getConfidenceBadge(score: number) {
  const level = getConfidenceLevel(score);
  const colors = {
    high: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    low: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  };
  return (
    <Badge className={colors[level]} variant="secondary">
      {formatConfidence(score)}
    </Badge>
  );
}

function getSchemeBadge(scheme: string) {
  const colors: Record<string, string> = {
    'ticket-type-based': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    'time-based': 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    'hybrid': 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    'unknown': 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
  };
  return (
    <Badge className={colors[scheme] || colors['unknown']} variant="secondary">
      {scheme}
    </Badge>
  );
}

// =============================================================================
// DATA COVERAGE PREVIEW COMPONENT
// =============================================================================

interface DataCoveragePreviewProps {
  circuitName: string;
  coverageData: import('@/hooks/api').DataCoverageResponse | undefined;
  isLoading: boolean;
}

function DataCoveragePreview({ circuitName, coverageData, isLoading }: DataCoveragePreviewProps) {
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm text-muted-foreground">Checking data coverage for {circuitName}...</span>
      </div>
    );
  }

  if (!coverageData) {
    return null;
  }

  const assessmentColors = getCoverageAssessmentColor(coverageData.coverage_assessment);

  return (
    <div className={`p-4 rounded-lg border ${assessmentColors}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 className="h-5 w-5" />
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">Data Coverage: {coverageData.coverage_assessment.toUpperCase()}</span>
              {coverageData.can_detect_discount_days ? (
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              ) : (
                <XCircle className="h-4 w-4 text-red-600" />
              )}
            </div>
            <p className="text-sm opacity-80">
              {coverageData.total_samples.toLocaleString()} samples from {coverageData.total_theaters} theaters |{' '}
              {coverageData.weekdays_with_data}/5 weekdays with data
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3">
          {/* Day-by-day coverage */}
          <div className="grid grid-cols-7 gap-2">
            {coverageData.day_coverage.map((day) => (
              <div
                key={day.day_of_week}
                className={`text-center p-2 rounded ${
                  day.has_sufficient_data
                    ? 'bg-green-100 dark:bg-green-900/30'
                    : day.sample_count > 0
                    ? 'bg-yellow-100 dark:bg-yellow-900/30'
                    : 'bg-gray-100 dark:bg-gray-800'
                }`}
              >
                <div className="text-xs font-medium">{day.day_name.slice(0, 3)}</div>
                <div className="text-lg font-bold">{day.sample_count}</div>
                <div className="text-xs opacity-70">{day.theater_count} theaters</div>
                {day.date_range && (
                  <div className="text-xs opacity-50 truncate" title={day.date_range}>
                    {day.date_range}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Recommendation */}
          <div className="p-3 bg-background/50 rounded text-sm">
            {coverageData.recommendation}
          </div>
        </div>
      )}
    </div>
  );
}
