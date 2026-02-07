import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Square,
  RefreshCw,
  Layers,
} from 'lucide-react';
import { useLiveScrapeJobs, useCancelLiveScrapeJob } from '@/hooks/api/useScrapes';
import { useBackgroundJobsStore } from '@/stores/backgroundJobsStore';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'running':
      return (
        <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/30">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Running
        </Badge>
      );
    case 'pending':
      return (
        <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/30">
          <Clock className="h-3 w-3 mr-1" />
          Pending
        </Badge>
      );
    case 'completed':
      return (
        <Badge className="bg-green-500/10 text-green-500 border-green-500/30">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Completed
        </Badge>
      );
    case 'failed':
      return (
        <Badge className="bg-red-500/10 text-red-500 border-red-500/30">
          <XCircle className="h-3 w-3 mr-1" />
          Failed
        </Badge>
      );
    case 'cancelled':
      return (
        <Badge variant="secondary">
          <Square className="h-3 w-3 mr-1" />
          Cancelled
        </Badge>
      );
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export function ScrapesPage() {
  const { data: jobs, isLoading, refetch } = useLiveScrapeJobs();
  const cancelJob = useCancelLiveScrapeJob();
  const { backgroundJobIds } = useBackgroundJobsStore();

  const activeJobs = (jobs ?? []).filter(
    (j) => j.status === 'running' || j.status === 'pending'
  );
  const completedJobs = (jobs ?? []).filter(
    (j) => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled'
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Scrape Jobs</h1>
          <p className="text-muted-foreground">
            View active and recent scrape jobs.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active Jobs</CardDescription>
            <CardTitle className="text-2xl">{activeJobs.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Completed</CardDescription>
            <CardTitle className="text-2xl">{completedJobs.filter((j) => j.status === 'completed').length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Failed / Cancelled</CardDescription>
            <CardTitle className="text-2xl">{completedJobs.filter((j) => j.status === 'failed' || j.status === 'cancelled').length}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              Active Jobs
            </CardTitle>
            <CardDescription>
              Currently running scrape jobs.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeJobs.map((job) => (
              <div key={job.job_id} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={job.status} />
                    <span className="font-medium">Job #{job.job_id}</span>
                    {backgroundJobIds.includes(job.job_id) && (
                      <Badge variant="outline" className="text-xs">
                        <Layers className="h-3 w-3 mr-1" />
                        Background
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => cancelJob.mutate(job.job_id)}
                    disabled={cancelJob.isPending}
                  >
                    <Square className="mr-1 h-3 w-3" />
                    Cancel
                  </Button>
                </div>
                <Progress value={job.progress} className="h-2" />
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>
                    {job.current_theater
                      ? `Scraping: ${job.current_theater}`
                      : 'Initializing...'}
                  </span>
                  <span>
                    {job.theaters_completed}/{job.theaters_total} theaters
                    {' '}({job.progress}%)
                  </span>
                </div>
                {job.duration_seconds !== undefined && (
                  <p className="text-xs text-muted-foreground">
                    Duration: {formatDuration(job.duration_seconds)}
                    {job.use_cache && (
                      <span className="ml-2">
                        Cache: {job.cache_hits ?? 0} hits / {job.cache_misses ?? 0} misses
                      </span>
                    )}
                  </p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* All Jobs Table */}
      <Card>
        <CardHeader>
          <CardTitle>All Jobs</CardTitle>
          <CardDescription>
            Complete list of scrape jobs for this session.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : !jobs || jobs.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No scrape jobs found. Start a scrape from Market Mode.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">Job ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Theaters</TableHead>
                  <TableHead>Showings</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-medium">
                      #{job.job_id}
                      {backgroundJobIds.includes(job.job_id) && (
                        <Layers className="h-3 w-3 inline ml-1 text-muted-foreground" />
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={job.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 min-w-24">
                        <Progress value={job.progress} className="h-1.5 flex-1" />
                        <span className="text-xs text-muted-foreground w-8">
                          {job.progress}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {job.theaters_completed}/{job.theaters_total}
                    </TableCell>
                    <TableCell className="text-sm">
                      {job.showings_completed ?? '-'}/{job.showings_total ?? '-'}
                    </TableCell>
                    <TableCell className="text-sm">
                      {job.duration_seconds !== undefined
                        ? formatDuration(job.duration_seconds)
                        : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      {(job.status === 'running' || job.status === 'pending') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelJob.mutate(job.job_id)}
                          disabled={cancelJob.isPending}
                        >
                          <Square className="h-3 w-3" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
