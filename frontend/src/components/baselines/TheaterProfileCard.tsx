/**
 * TheaterProfileCard - Enhanced theater display with profile summaries
 *
 * Shows theater info with company profile data including:
 * - Profile discovery status
 * - Discount days (e.g., "Tue $5")
 * - Premium formats
 * - Coverage gaps count
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  CheckCircle2,
  AlertCircle,
  Tag,
  Film,
  Sparkles,
  Search,
  Loader2,
} from 'lucide-react';
import type { CompanyProfile } from '@/hooks/api/useCompanyProfiles';
import type { TheaterCoverageDetail } from '@/hooks/api/useCoverageGaps';

// Day abbreviations for discount day display
const DAY_ABBREV: Record<number, string> = {
  0: 'Mon',
  1: 'Tue',
  2: 'Wed',
  3: 'Thu',
  4: 'Fri',
  5: 'Sat',
  6: 'Sun',
};

interface TheaterProfileCardProps {
  theaterName: string;
  baselineCount: number;
  ticketTypeCount: number;
  daypartCount: number;
  dayparts: string[]; // Actual daypart values
  dayCount: number;
  profile: CompanyProfile | null;
  coverage: TheaterCoverageDetail | null;
  isYourTheater: boolean;
  onDiscoverProfile?: () => void;
  isDiscovering?: boolean;
}

/**
 * Extract circuit name from theater name using prefix matching
 */
export function getCircuitFromTheaterName(theaterName: string): string {
  const words = theaterName.split(' ');

  // Known multi-word circuit names
  const multiWordCircuits: Record<string, string> = {
    'Movie Tavern': 'Movie Tavern',
    'Studio Movie': 'Studio Movie Grill',
    'B&B Theatres': 'B&B Theatres',
    'LOOK Dine-in': 'LOOK Cinemas',
  };

  if (words.length >= 2) {
    const twoWordKey = `${words[0]} ${words[1]}`;
    if (multiWordCircuits[twoWordKey]) {
      return multiWordCircuits[twoWordKey];
    }
  }

  return words[0] || theaterName;
}

export function TheaterProfileCard({
  theaterName,
  baselineCount,
  ticketTypeCount,
  daypartCount,
  dayparts,
  dayCount,
  profile,
  coverage,
  isYourTheater,
  onDiscoverProfile,
  isDiscovering,
}: TheaterProfileCardProps) {
  const hasProfile = !!profile;
  const hasGaps = (coverage?.gap_count ?? 0) > 0;
  const circuitName = getCircuitFromTheaterName(theaterName);

  // Build tooltip text for profile badge
  const profileTooltip = hasProfile
    ? `Profile discovered with ${profile.sample_count.toLocaleString()} samples`
    : 'No profile discovered for this circuit yet';

  // Build tooltip text for discount days
  const discountDaysTooltip = profile?.discount_days?.length
    ? profile.discount_days.map((dd) => `${dd.day}: $${dd.price.toFixed(2)} (${dd.program})`).join('\n')
    : '';

  // Build tooltip text for premium formats
  const premiumFormatsTooltip = profile?.premium_formats?.length
    ? profile.premium_formats
        .map((fmt) =>
          profile.premium_surcharges[fmt]
            ? `${fmt} (+$${profile.premium_surcharges[fmt].toFixed(2)})`
            : fmt
        )
        .join('\n')
    : '';

  return (
    <div
      className={`p-4 rounded-lg border transition-colors ${
        isYourTheater
          ? 'bg-purple-50/50 border-purple-200 dark:bg-purple-950/20 dark:border-purple-800'
          : 'bg-muted/30 border-border'
      }`}
    >
      {/* Header Row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium truncate" title={theaterName}>
            {theaterName}
          </h4>
          <p className="text-xs text-muted-foreground">{circuitName} Circuit</p>
        </div>

        {/* Profile Status Badge */}
        {hasProfile ? (
          <Badge
            variant="outline"
            className="bg-green-100 text-green-700 border-green-300 cursor-help"
            title={profileTooltip}
          >
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Profile
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="bg-gray-100 text-gray-600 cursor-help"
            title={profileTooltip}
          >
            <AlertCircle className="h-3 w-3 mr-1" />
            No Profile
          </Badge>
        )}
      </div>

      {/* Profile Info Row */}
      {hasProfile && (
        <div className="flex flex-wrap gap-2 mb-3">
          {/* Discount Days */}
          {profile.has_discount_days && profile.discount_days.length > 0 && (
            <Badge
              variant="secondary"
              className="bg-blue-100 text-blue-700 border-blue-300 cursor-help"
              title={discountDaysTooltip}
            >
              <Tag className="h-3 w-3 mr-1" />
              {profile.discount_days.map((dd) => `${DAY_ABBREV[dd.day_of_week]} $${dd.price}`).join(', ')}
            </Badge>
          )}

          {/* Premium Formats */}
          {profile.premium_formats.length > 0 && (
            <Badge
              variant="secondary"
              className="bg-purple-100 text-purple-700 border-purple-300 cursor-help"
              title={premiumFormatsTooltip}
            >
              <Sparkles className="h-3 w-3 mr-1" />
              {profile.premium_formats.length} PLF
            </Badge>
          )}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-2 text-center mb-3">
        <div className="p-1.5 rounded bg-background/50">
          <div className="text-xs text-muted-foreground">Types</div>
          <div className="font-semibold">{ticketTypeCount || '-'}</div>
        </div>
        <div
          className="p-1.5 rounded bg-background/50 cursor-help"
          title={dayparts.length > 0 ? dayparts.join('\n') : 'No dayparts'}
        >
          <div className="text-xs text-muted-foreground">Dayparts</div>
          <div className="font-semibold">{daypartCount || '-'}</div>
        </div>
        <div className="p-1.5 rounded bg-background/50">
          <div className="text-xs text-muted-foreground">Days</div>
          <div className="font-semibold">{dayCount ? `${dayCount}/7` : '-'}</div>
        </div>
        <div className="p-1.5 rounded bg-background/50">
          <div className="text-xs text-muted-foreground">Baselines</div>
          <div className={`font-semibold ${baselineCount > 0 ? 'text-green-600' : 'text-muted-foreground'}`}>
            {baselineCount || 'None'}
          </div>
        </div>
      </div>

      {/* Coverage & Gaps Row */}
      <div className="flex items-center justify-between gap-2">
        {coverage ? (
          <div className="flex items-center gap-2 text-sm">
            {hasGaps ? (
              <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
                <AlertCircle className="h-3 w-3 mr-1" />
                {coverage.gap_count} gap{coverage.gap_count !== 1 ? 's' : ''}
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                Full coverage
              </Badge>
            )}

            {coverage.days_missing.length > 0 && (
              <span className="text-xs text-muted-foreground">
                Missing: {coverage.days_missing.slice(0, 2).join(', ')}
                {coverage.days_missing.length > 2 && ` +${coverage.days_missing.length - 2}`}
              </span>
            )}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">Coverage not analyzed</span>
        )}

        {/* Discover Profile Button (when no profile exists) */}
        {!hasProfile && onDiscoverProfile && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onDiscoverProfile}
            disabled={isDiscovering}
            className="h-7 text-xs"
          >
            {isDiscovering ? (
              <>
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                Discovering...
              </>
            ) : (
              <>
                <Search className="h-3 w-3 mr-1" />
                Discover
              </>
            )}
          </Button>
        )}
      </div>

      {/* Dayparts List */}
      {dayparts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {dayparts.slice(0, 6).map((dp) => (
            <Badge key={dp} variant="outline" className="text-xs px-1.5 py-0 bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950 dark:text-cyan-300 dark:border-cyan-800">
              {dp}
            </Badge>
          ))}
          {dayparts.length > 6 && (
            <Badge variant="outline" className="text-xs px-1.5 py-0">+{dayparts.length - 6}</Badge>
          )}
        </div>
      )}

      {/* Formats List (if available from coverage) */}
      {coverage?.formats && coverage.formats.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {coverage.formats.slice(0, 5).map((fmt) => (
            <Badge key={fmt} variant="outline" className="text-xs px-1.5 py-0">
              <Film className="h-2.5 w-2.5 mr-0.5" />
              {fmt}
            </Badge>
          ))}
          {coverage.formats.length > 5 && (
            <Badge variant="outline" className="text-xs px-1.5 py-0">+{coverage.formats.length - 5}</Badge>
          )}
        </div>
      )}
    </div>
  );
}

export default TheaterProfileCard;
