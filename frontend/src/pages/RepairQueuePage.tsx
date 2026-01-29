import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { useToast } from '@/hooks/use-toast';
import {
  useRepairQueueStatus,
  useRepairQueueJobs,
  useRepairQueueFailed,
  useResetRepairJob,
  useClearFailedJobs,
  useProcessRepairQueue,
  useMaintenanceHistory,
  useRunMaintenance,
  getTimeUntilRetry,
  getBackoffDisplay,
  type RepairJob,
  type MaintenanceHistoryEntry,
} from '@/hooks/api';
import {
  Wrench,
  Clock,
  AlertTriangle,
  RefreshCw,
  Play,
  Trash2,
  RotateCcw,
  History,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

function RepairJobRow({
  job,
  onReset,
  isResetting,
}: {
  job: RepairJob;
  onReset: () => void;
  isResetting: boolean;
}) {
  const isMaxAttempts = job.attempts >= 5;

  return (
    <TableRow className={isMaxAttempts ? 'bg-red-50 dark:bg-red-950/10' : ''}>
      <TableCell className="font-medium">{job.theater_name}</TableCell>
      <TableCell>{job.market_name}</TableCell>
      <TableCell>{job.zip_code || '-'}</TableCell>
      <TableCell>
        <Badge variant={isMaxAttempts ? 'destructive' : 'secondary'}>
          {job.attempts} / 5
        </Badge>
      </TableCell>
      <TableCell>
        {isMaxAttempts ? (
          <span className="text-red-500 font-medium">Max reached</span>
        ) : (
          <span className="text-muted-foreground">
            {getTimeUntilRetry(job.next_attempt_at)}
          </span>
        )}
      </TableCell>
      <TableCell>
        <span className="text-muted-foreground text-sm">
          {getBackoffDisplay(job.attempts)}
        </span>
      </TableCell>
      <TableCell className="max-w-[200px] truncate text-muted-foreground text-sm">
        {job.error_message || '-'}
      </TableCell>
      <TableCell>
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          disabled={isResetting}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function MaintenanceHistoryCard({ entry }: { entry: MaintenanceHistoryEntry }) {
  const isAlert = entry.overall_status === 'alert';
  const isError = entry.overall_status === 'error';
  const failureRate = entry.checked > 0 ? (entry.failed / entry.checked) * 100 : 0;

  return (
    <Card className={isAlert ? 'border-yellow-500' : isError ? 'border-red-500' : ''}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            {new Date(entry.timestamp).toLocaleString()}
          </CardTitle>
          <Badge
            variant={
              entry.overall_status === 'ok'
                ? 'default'
                : entry.overall_status === 'alert'
                ? 'secondary'
                : 'destructive'
            }
          >
            {entry.overall_status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="text-sm">
            <span className="text-muted-foreground">Checked:</span>{' '}
            <span className="font-medium">{entry.checked}</span> theaters
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">Failed:</span>{' '}
            <span className={entry.failed > 0 ? 'font-medium text-red-500' : 'font-medium'}>
              {entry.failed}
            </span>
            {entry.checked > 0 && (
              <span className="text-muted-foreground"> ({failureRate.toFixed(1)}%)</span>
            )}
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">Repaired:</span>{' '}
            <span className={entry.repaired > 0 ? 'font-medium text-green-600' : 'font-medium'}>
              {entry.repaired}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function RepairQueuePage() {
  const [confirmClear, setConfirmClear] = useState(false);
  const [resettingJob, setResettingJob] = useState<string | null>(null);
  const { toast } = useToast();

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useRepairQueueStatus();
  const { data: jobs, isLoading: jobsLoading, refetch: refetchJobs } = useRepairQueueJobs();
  const { data: failedJobs, refetch: refetchFailed } = useRepairQueueFailed();
  const { data: history, isLoading: historyLoading } = useMaintenanceHistory(5);

  const resetMutation = useResetRepairJob();
  const clearMutation = useClearFailedJobs();
  const processMutation = useProcessRepairQueue();
  const maintenanceMutation = useRunMaintenance();

  const refetchAll = () => {
    refetchStatus();
    refetchJobs();
    refetchFailed();
  };

  const handleReset = async (job: RepairJob) => {
    const key = `${job.theater_name}|${job.market_name}`;
    setResettingJob(key);
    try {
      await resetMutation.mutateAsync({
        theaterName: job.theater_name,
        marketName: job.market_name,
      });
      toast({
        title: 'Job Reset',
        description: `${job.theater_name} reset for immediate retry.`,
      });
      refetchAll();
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to reset repair job.',
        variant: 'destructive',
      });
    } finally {
      setResettingJob(null);
    }
  };

  const handleClearFailed = async () => {
    try {
      const result = await clearMutation.mutateAsync();
      toast({
        title: 'Cleared',
        description: `${result.cleared} permanently failed entries removed.`,
      });
      setConfirmClear(false);
      refetchAll();
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to clear failed entries.',
        variant: 'destructive',
      });
    }
  };

  const handleProcessQueue = async () => {
    try {
      const result = await processMutation.mutateAsync();
      toast({
        title: 'Queue Processed',
        description: `${result.processed} processed: ${result.success} success, ${result.failed} failed.`,
      });
      refetchAll();
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to process repair queue.',
        variant: 'destructive',
      });
    }
  };

  const handleRunMaintenance = async () => {
    try {
      const result = await maintenanceMutation.mutateAsync();
      toast({
        title: 'Maintenance Complete',
        description: `Checked ${result.health_check.checked} theaters, repaired ${result.repairs.repaired}.`,
      });
      refetchAll();
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to run maintenance.',
        variant: 'destructive',
      });
    }
  };

  const pendingJobs = jobs?.filter((j) => j.attempts < 5) || [];
  const maxAttemptsJobs = failedJobs || [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Repair Queue</h1>
          <p className="text-muted-foreground">
            Manage failed theater URL repairs with exponential backoff retry.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunMaintenance}
            disabled={maintenanceMutation.isPending}
          >
            <Wrench className={`mr-2 h-4 w-4 ${maintenanceMutation.isPending ? 'animate-spin' : ''}`} />
            Run Maintenance
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleProcessQueue}
            disabled={processMutation.isPending || (status?.due_now ?? 0) === 0}
          >
            <Play className={`mr-2 h-4 w-4 ${processMutation.isPending ? 'animate-spin' : ''}`} />
            Process Queue
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Queued</CardTitle>
            <Wrench className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statusLoading ? '...' : status?.total_queued ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Due Now</CardTitle>
            <Clock className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {statusLoading ? '...' : status?.due_now ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Max Attempts</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {statusLoading ? '...' : status?.max_attempts_reached ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">Needs manual review</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Max Retries</CardTitle>
            <RefreshCw className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statusLoading ? '...' : status?.max_attempts_limit ?? 5}
            </div>
            <p className="text-xs text-muted-foreground">per theater</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs for Queue and History */}
      <Tabs defaultValue="queue">
        <TabsList>
          <TabsTrigger value="queue">
            Repair Queue ({pendingJobs.length})
          </TabsTrigger>
          <TabsTrigger value="failed" className="text-red-600">
            Failed ({maxAttemptsJobs.length})
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="h-4 w-4 mr-1" />
            History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="queue">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Queued Repairs</CardTitle>
                  <CardDescription>
                    Theaters waiting for URL repair with exponential backoff retry.
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={refetchAll}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {jobsLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : pendingJobs.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No repairs in queue. All theaters healthy!
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Theater</TableHead>
                      <TableHead>Market</TableHead>
                      <TableHead>ZIP</TableHead>
                      <TableHead>Attempts</TableHead>
                      <TableHead>Next Retry</TableHead>
                      <TableHead>Backoff</TableHead>
                      <TableHead>Last Error</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pendingJobs.map((job) => (
                      <RepairJobRow
                        key={`${job.theater_name}|${job.market_name}`}
                        job={job}
                        onReset={() => handleReset(job)}
                        isResetting={resettingJob === `${job.theater_name}|${job.market_name}`}
                      />
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="failed">
          <Card className="border-red-200">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-red-600">Permanently Failed</CardTitle>
                  <CardDescription>
                    Theaters that exceeded maximum retry attempts. Manual intervention required.
                  </CardDescription>
                </div>
                {maxAttemptsJobs.length > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setConfirmClear(true)}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Clear All
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {maxAttemptsJobs.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No permanently failed theaters.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Theater</TableHead>
                      <TableHead>Market</TableHead>
                      <TableHead>ZIP</TableHead>
                      <TableHead>Attempts</TableHead>
                      <TableHead>First Failure</TableHead>
                      <TableHead>Last Error</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {maxAttemptsJobs.map((job) => (
                      <TableRow key={`${job.theater_name}|${job.market_name}`}>
                        <TableCell className="font-medium">{job.theater_name}</TableCell>
                        <TableCell>{job.market_name}</TableCell>
                        <TableCell>{job.zip_code || '-'}</TableCell>
                        <TableCell>
                          <Badge variant="destructive">{job.attempts}</Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {job.first_failure_at
                            ? formatDistanceToNow(new Date(job.first_failure_at), { addSuffix: true })
                            : '-'}
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-muted-foreground text-sm">
                          {job.error_message || '-'}
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleReset(job)}
                            disabled={resettingJob === `${job.theater_name}|${job.market_name}`}
                          >
                            <RotateCcw className="mr-1 h-4 w-4" />
                            Reset
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Maintenance History</CardTitle>
              <CardDescription>
                Recent cache maintenance runs and their results.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {historyLoading ? (
                <div className="space-y-4">
                  <Skeleton className="h-32 w-full" />
                  <Skeleton className="h-32 w-full" />
                </div>
              ) : !history || history.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No maintenance history available.
                </div>
              ) : (
                <div className="space-y-4">
                  {history.map((entry, idx) => (
                    <MaintenanceHistoryCard key={idx} entry={entry} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Confirm Clear Dialog */}
      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear Failed Entries</DialogTitle>
            <DialogDescription>
              This will remove all theaters that have reached maximum retry attempts from the queue.
              They will need to be manually repaired or re-added.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleClearFailed}
              disabled={clearMutation.isPending}
            >
              {clearMutation.isPending ? 'Clearing...' : 'Clear All'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
