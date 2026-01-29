import * as React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Film,
  Ticket,
  Clock,
  BarChart3,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useCoverageIndicators, type CoverageIndicators as CoverageData } from '@/hooks/api/useOnboarding';

// =============================================================================
// TYPES
// =============================================================================

interface CoverageIndicatorsProps {
  theaterName: string;
  compact?: boolean;
  showGaps?: boolean;
  className?: string;
}

interface CoverageBarProps {
  label: string;
  discovered: string[];
  expected: string[];
  coverage: number;
  icon: React.ReactNode;
  compact?: boolean;
}

// =============================================================================
// COVERAGE BAR COMPONENT
// =============================================================================

function CoverageBar({
  label,
  discovered,
  expected,
  coverage,
  icon,
  compact = false,
}: CoverageBarProps) {
  const percent = Math.round(coverage * 100);
  const missing = expected.filter((e) => !discovered.includes(e));

  const getColorClass = (pct: number) => {
    if (pct >= 100) return 'text-green-500';
    if (pct >= 60) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getProgressClass = (pct: number) => {
    if (pct >= 100) return '[&>div]:bg-green-500';
    if (pct >= 60) return '[&>div]:bg-yellow-500';
    return '[&>div]:bg-red-500';
  };

  if (compact) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            {icon}
            {label}
          </span>
          <span className={cn('font-medium', getColorClass(percent))}>
            {discovered.length}/{expected.length} ({percent}%)
          </span>
        </div>
        <Progress value={percent} className={cn('h-1.5', getProgressClass(percent))} />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 font-medium">
          {icon}
          {label}
        </span>
        <span className={cn('text-sm font-semibold', getColorClass(percent))}>
          {discovered.length} of {expected.length} ({percent}%)
        </span>
      </div>
      <Progress value={percent} className={cn('h-2', getProgressClass(percent))} />
      <div className="flex flex-wrap gap-1.5">
        {discovered.map((item) => (
          <Badge key={item} variant="success" className="text-xs">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            {item}
          </Badge>
        ))}
        {missing.map((item) => (
          <Badge key={item} variant="outline" className="text-xs text-muted-foreground">
            <XCircle className="mr-1 h-3 w-3" />
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// OVERALL SCORE COMPONENT
// =============================================================================

interface OverallScoreProps {
  score: number;
  baselineCount: number;
  compact?: boolean;
}

function OverallScore({ score, baselineCount, compact = false }: OverallScoreProps) {
  const percent = Math.round(score * 100);

  const getScoreIcon = () => {
    if (percent >= 80) return <CheckCircle2 className="h-8 w-8 text-green-500" />;
    if (percent >= 50) return <AlertTriangle className="h-8 w-8 text-yellow-500" />;
    return <XCircle className="h-8 w-8 text-red-500" />;
  };

  const getScoreLabel = () => {
    if (percent >= 80) return 'Excellent';
    if (percent >= 60) return 'Good';
    if (percent >= 40) return 'Fair';
    return 'Needs Data';
  };

  const getScoreColor = () => {
    if (percent >= 80) return 'text-green-500';
    if (percent >= 60) return 'text-yellow-500';
    if (percent >= 40) return 'text-orange-500';
    return 'text-red-500';
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between py-2 px-3 bg-muted/50 rounded-lg">
        <span className="text-sm text-muted-foreground flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Overall Coverage
        </span>
        <span className={cn('text-lg font-bold', getScoreColor())}>
          {percent}%
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
      {getScoreIcon()}
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <span className="font-semibold">Overall Coverage Score</span>
          <span className={cn('text-2xl font-bold', getScoreColor())}>
            {percent}%
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
          <span>{getScoreLabel()}</span>
          <span>•</span>
          <span>{baselineCount} baselines discovered</span>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// GAPS LIST COMPONENT
// =============================================================================

interface GapsListProps {
  gaps: CoverageData['gaps'];
}

function GapsList({ gaps }: GapsListProps) {
  const hasGaps =
    gaps.formats.length > 0 ||
    gaps.ticket_types.length > 0 ||
    gaps.dayparts.length > 0;

  if (!hasGaps) {
    return (
      <div className="flex items-center gap-2 text-green-500 p-3 bg-green-500/10 rounded-lg">
        <CheckCircle2 className="h-5 w-5" />
        <span className="font-medium">No coverage gaps detected!</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="font-medium flex items-center gap-2 text-yellow-500">
        <AlertTriangle className="h-4 w-4" />
        Coverage Gaps
      </h4>
      <div className="grid gap-2">
        {gaps.formats.length > 0 && (
          <div className="flex items-start gap-2 text-sm">
            <Film className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <span className="text-muted-foreground">Missing formats: </span>
              <span className="font-medium">{gaps.formats.join(', ')}</span>
            </div>
          </div>
        )}
        {gaps.ticket_types.length > 0 && (
          <div className="flex items-start gap-2 text-sm">
            <Ticket className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <span className="text-muted-foreground">Missing ticket types: </span>
              <span className="font-medium">{gaps.ticket_types.join(', ')}</span>
            </div>
          </div>
        )}
        {gaps.dayparts.length > 0 && (
          <div className="flex items-start gap-2 text-sm">
            <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <span className="text-muted-foreground">Missing dayparts: </span>
              <span className="font-medium">{gaps.dayparts.join(', ')}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function CoverageIndicators({
  theaterName,
  compact = false,
  showGaps = true,
  className,
}: CoverageIndicatorsProps) {
  const { data, isLoading, error } = useCoverageIndicators(theaterName);

  if (isLoading) {
    return (
      <div className={cn('flex items-center justify-center p-8', className)}>
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={cn('text-center text-muted-foreground p-4', className)}>
        Unable to load coverage data
      </div>
    );
  }

  if (compact) {
    return (
      <div className={cn('space-y-3', className)}>
        <OverallScore
          score={data.overall_score}
          baselineCount={data.baseline_count}
          compact
        />
        <div className="space-y-2">
          <CoverageBar
            label="Formats"
            discovered={data.formats_discovered}
            expected={data.formats_expected}
            coverage={data.format_coverage}
            icon={<Film className="h-3.5 w-3.5" />}
            compact
          />
          <CoverageBar
            label="Ticket Types"
            discovered={data.ticket_types_discovered}
            expected={data.ticket_types_expected}
            coverage={data.ticket_type_coverage}
            icon={<Ticket className="h-3.5 w-3.5" />}
            compact
          />
          <CoverageBar
            label="Dayparts"
            discovered={data.dayparts_discovered}
            expected={data.dayparts_expected}
            coverage={data.daypart_coverage}
            icon={<Clock className="h-3.5 w-3.5" />}
            compact
          />
        </div>
      </div>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-lg">Coverage Indicators</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <OverallScore
          score={data.overall_score}
          baselineCount={data.baseline_count}
        />

        <div className="space-y-4">
          <CoverageBar
            label="Formats"
            discovered={data.formats_discovered}
            expected={data.formats_expected}
            coverage={data.format_coverage}
            icon={<Film className="h-4 w-4" />}
          />
          <CoverageBar
            label="Ticket Types"
            discovered={data.ticket_types_discovered}
            expected={data.ticket_types_expected}
            coverage={data.ticket_type_coverage}
            icon={<Ticket className="h-4 w-4" />}
          />
          <CoverageBar
            label="Dayparts"
            discovered={data.dayparts_discovered}
            expected={data.dayparts_expected}
            coverage={data.daypart_coverage}
            icon={<Clock className="h-4 w-4" />}
          />
        </div>

        {showGaps && <GapsList gaps={data.gaps} />}
      </CardContent>
    </Card>
  );
}

export default CoverageIndicators;
