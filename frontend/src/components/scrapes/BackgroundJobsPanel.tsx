import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  X,
  ChevronUp,
  ChevronDown,
  Square,
  Layers,
} from 'lucide-react';
import { useLiveScrapeJobs, useCancelLiveScrapeJob } from '@/hooks/api/useScrapes';
import { useBackgroundJobsStore } from '@/stores/backgroundJobsStore';
import { useToast } from '@/hooks/use-toast';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

export function BackgroundJobsPanel() {
  const [expanded, setExpanded] = useState(true);
  const { backgroundJobIds, removeFromBackground } = useBackgroundJobsStore();
  const { data: allJobs } = useLiveScrapeJobs();
  const cancelJob = useCancelLiveScrapeJob();
  const { toast } = useToast();

  // Track which jobs we've already notified about to prevent duplicate toasts
  const notifiedJobsRef = useRef<Set<number>>(new Set());

  // Filter to only background jobs
  const backgroundJobs = (allJobs ?? []).filter((j) =>
    backgroundJobIds.includes(j.job_id)
  );

  // Detect completions and show toast notifications
  useEffect(() => {
    for (const job of backgroundJobs) {
      if (
        (job.status === 'completed' || job.status === 'failed') &&
        !notifiedJobsRef.current.has(job.job_id)
      ) {
        notifiedJobsRef.current.add(job.job_id);
        if (job.status === 'completed') {
          toast({
            title: 'Background Scrape Complete',
            description: `Job #${job.job_id}: ${job.theaters_completed}/${job.theaters_total} theaters scraped in ${formatDuration(job.duration_seconds ?? 0)}.`,
          });
        } else {
          toast({
            title: 'Background Scrape Failed',
            description: `Job #${job.job_id}: ${job.error ?? 'Unknown error'}`,
            variant: 'destructive',
          });
        }
      }
    }
  }, [backgroundJobs, toast]);

  // Nothing to show if no background jobs
  if (backgroundJobIds.length === 0) return null;

  const runningCount = backgroundJobs.filter(
    (j) => j.status === 'running' || j.status === 'pending'
  ).length;
  const finishedCount = backgroundJobs.filter(
    (j) => j.status === 'completed' || j.status === 'failed'
  ).length;

  // Stale IDs: in store but no matching API data (server restarted, etc.)
  // Show them as "unknown" so user can dismiss
  const staleIds = backgroundJobIds.filter(
    (id) => !backgroundJobs.some((j) => j.job_id === id)
  );

  return (
    <div className="fixed bottom-4 right-4 z-40 w-80">
      {!expanded ? (
        // Collapsed pill
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-full shadow-lg hover:bg-primary/90 transition-colors"
        >
          <Layers className="h-4 w-4" />
          <span className="text-sm font-medium">
            {runningCount > 0
              ? `${runningCount} job${runningCount !== 1 ? 's' : ''} running`
              : `${finishedCount} job${finishedCount !== 1 ? 's' : ''} finished`}
          </span>
          <ChevronUp className="h-4 w-4" />
        </button>
      ) : (
        // Expanded card
        <Card className="shadow-xl border-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Layers className="h-4 w-4" />
                Background Jobs
                {runningCount > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    {runningCount} active
                  </Badge>
                )}
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => setExpanded(false)}
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 max-h-80 overflow-y-auto">
            {backgroundJobs.map((job) => (
              <div
                key={job.job_id}
                className="border rounded-lg p-3 space-y-2 bg-muted/30"
              >
                {/* Header row */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    {job.status === 'running' || job.status === 'pending' ? (
                      <Loader2 className="h-4 w-4 animate-spin text-blue-500 shrink-0" />
                    ) : job.status === 'completed' ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                    )}
                    <span className="text-xs font-medium truncate">
                      Job #{job.job_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {(job.status === 'running' || job.status === 'pending') && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs"
                        onClick={() => cancelJob.mutate(job.job_id)}
                      >
                        <Square className="h-3 w-3 mr-1" />
                        Stop
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={() => {
                        removeFromBackground(job.job_id);
                        notifiedJobsRef.current.delete(job.job_id);
                      }}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>

                {/* Progress for active jobs */}
                {(job.status === 'running' || job.status === 'pending') && (
                  <>
                    <Progress value={job.progress} className="h-1.5" />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {job.current_theater
                          ? `Scraping: ${job.current_theater}`
                          : 'Initializing...'}
                      </span>
                      <span>{job.progress}%</span>
                    </div>
                  </>
                )}

                {/* Summary for completed jobs */}
                {job.status === 'completed' && (
                  <p className="text-xs text-muted-foreground">
                    {job.theaters_completed}/{job.theaters_total} theaters
                    {job.duration_seconds
                      ? ` in ${formatDuration(job.duration_seconds)}`
                      : ''}
                  </p>
                )}

                {/* Error for failed jobs */}
                {job.status === 'failed' && (
                  <p className="text-xs text-red-400 truncate">
                    {job.error ?? 'Unknown error'}
                  </p>
                )}
              </div>
            ))}

            {/* Stale jobs (in store but not in API) */}
            {staleIds.map((id) => (
              <div
                key={id}
                className="border rounded-lg p-3 bg-muted/30 flex items-center justify-between"
              >
                <span className="text-xs text-muted-foreground">
                  Job #{id} (no longer tracked)
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => removeFromBackground(id)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}

            {backgroundJobs.length === 0 && staleIds.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-2">
                No background jobs
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
