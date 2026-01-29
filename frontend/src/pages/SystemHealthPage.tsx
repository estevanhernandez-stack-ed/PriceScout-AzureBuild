import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { 
  useDetailedSystemHealth, 
  getStatusVariant,
  useResetCircuits,
  useTripCircuit,
  useMaintenanceStatus,
  useRunRetention
} from '@/hooks/api/useSystemHealth';
import {
  Activity,
  Database,
  Bell,
  Clock,
  Shield,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Zap,
  Power,
  RotateCcw,
  Wrench,
  Trash2,
  ListRestart
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { useAuthStore } from '@/stores/authStore';

function StatusIcon({ status }: { status?: string }) {
  switch (status) {
    case 'ok':
    case 'healthy':
    case 'closed':
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case 'degraded':
    case 'half_open':
    case 'stale':
      return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
    case 'error':
    case 'critical':
    case 'unhealthy':
    case 'open':
      return <XCircle className="h-5 w-5 text-red-500" />;
    default:
      return <Activity className="h-5 w-5 text-gray-400" />;
  }
}

function ComponentCard({
  title,
  icon: Icon,
  status,
  children,
  footer,
}: {
  title: string;
  icon: React.ElementType;
  status?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </CardTitle>
        <StatusIcon status={status} />
      </CardHeader>
      <CardContent className="flex-grow">{children}</CardContent>
      {footer && <CardFooter className="pt-2 border-t bg-muted/20">{footer}</CardFooter>}
    </Card>
  );
}

export function SystemHealthPage() {
  const { data: health, isLoading, refetch, isRefetching } = useDetailedSystemHealth();
  const resetMutation = useResetCircuits();
  const tripMutation = useTripCircuit();
  const retentionMutation = useRunRetention();
  const { data: maintenance } = useMaintenanceStatus();
  const { user } = useAuthStore();

  const isAdmin = user?.role === 'admin';
  const isOperator = user?.role === 'admin' || user?.role === 'operator';

  const handleResetAll = () => {
    if (confirm('Are you sure you want to reset all circuit breakers?')) {
      resetMutation.mutate(undefined);
    }
  };

  const handleResetCircuit = (name: string) => {
    resetMutation.mutate(name);
  };

  const handleTripCircuit = (name: string) => {
    if (confirm(`Are you sure you want to manually TRIP the ${name} circuit? This will block all requests until reset.`)) {
      tripMutation.mutate(name);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Dashboard</h1>
          <p className="text-muted-foreground">
            Monitor infrastructure health and manage circuit breakers.
          </p>
        </div>
        <div className="flex gap-2">
          {isOperator && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleResetAll}
              disabled={resetMutation.isPending}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Reset All Circuits
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isRefetching}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${isRefetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Overall Status Banner */}
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <Card
          className={`${
            health?.status === 'healthy'
              ? 'border-green-500 bg-green-50 dark:bg-green-950/20'
              : health?.status === 'degraded'
              ? 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20'
              : 'border-red-500 bg-red-50 dark:bg-red-950/20'
          }`}
        >
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <StatusIcon status={health?.status} />
                <div>
                  <h2 className="text-xl font-semibold capitalize">
                    System {health?.status}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {health?.environment} environment &bull; v{health?.version}
                  </p>
                </div>
              </div>
              <div className="flex gap-4 text-sm">
                {health?.features && (
                  <div className="flex items-center gap-3 pr-6 border-r">
                    {Object.entries(health.features).map(([name, enabled]) => (
                      <div key={name} className="flex items-center gap-1">
                        <div className={`h-2 w-2 rounded-full ${enabled ? 'bg-green-500' : 'bg-gray-300'}`} />
                        <span className="text-xs font-medium uppercase">{name}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="text-right text-muted-foreground">
                  <p>Last checked</p>
                  <p className="font-medium text-foreground">
                     {health?.timestamp ? formatDistanceToNow(new Date(health.timestamp), { addSuffix: true }) : 'Just now'}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Component Status Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Database */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="Database"
            icon={Database}
            status={health?.components?.database?.status}
          >
            <div className="space-y-1">
              <Badge variant={getStatusVariant(health?.components?.database?.status)}>
                {health?.components?.database?.status || 'Unknown'}
              </Badge>
              {health?.components?.database?.message && (
                <p className="text-xs text-muted-foreground mt-2">
                  {health.components.database.message}
                </p>
              )}
            </div>
          </ComponentCard>
        )}

        {/* Fandango Scraper Circuit */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="Fandango Circuit"
            icon={Shield}
            status={health?.circuits?.fandango?.state === 'closed' ? 'ok' : health?.circuits?.fandango?.state}
            footer={
              isOperator && (
                <div className="flex gap-2 w-full">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="flex-1 h-7 text-xs"
                    onClick={() => handleResetCircuit('fandango')}
                    disabled={resetMutation.isPending}
                  >
                    <RotateCcw className="mr-1 h-3 w-3" />
                    Reset
                  </Button>
                  {isAdmin && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="flex-1 h-7 text-xs text-destructive hover:text-destructive"
                      onClick={() => handleTripCircuit('fandango')}
                      disabled={tripMutation.isPending || health?.circuits?.fandango?.state === 'open'}
                    >
                      <Power className="mr-1 h-3 w-3" />
                      Trip
                    </Button>
                  )}
                </div>
              )
            }
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Badge variant={getStatusVariant(health?.circuits?.fandango?.state === 'closed' ? 'ok' : health?.circuits?.fandango?.state)}>
                  {health?.circuits?.fandango?.state || 'Unknown'}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {health?.circuits?.fandango?.failures || 0} / {health?.circuits?.fandango?.failure_threshold || 5} fails
                </span>
              </div>
              <div className="w-full bg-muted h-1 rounded-full overflow-hidden mt-2">
                <div 
                  className={`h-full ${health?.circuits?.fandango?.state === 'open' ? 'bg-red-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, ((health?.circuits?.fandango?.failures || 0) / (health?.circuits?.fandango?.failure_threshold || 5)) * 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground uppercase font-semibold">
                Protects: Scraper Operations
              </p>
            </div>
          </ComponentCard>
        )}

        {/* EntTelligence Circuit */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="EntTelligence Circuit"
            icon={Shield}
            status={health?.circuits?.enttelligence?.state === 'closed' ? 'ok' : health?.circuits?.enttelligence?.state}
            footer={
              isOperator && (
                <div className="flex gap-2 w-full">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="flex-1 h-7 text-xs"
                    onClick={() => handleResetCircuit('enttelligence')}
                    disabled={resetMutation.isPending}
                  >
                    <RotateCcw className="mr-1 h-3 w-3" />
                    Reset
                  </Button>
                  {isAdmin && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="flex-1 h-7 text-xs text-destructive hover:text-destructive"
                      onClick={() => handleTripCircuit('enttelligence')}
                      disabled={tripMutation.isPending || health?.circuits?.enttelligence?.state === 'open'}
                    >
                      <Power className="mr-1 h-3 w-3" />
                      Trip
                    </Button>
                  )}
                </div>
              )
            }
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Badge variant={getStatusVariant(health?.circuits?.enttelligence?.state === 'closed' ? 'ok' : health?.circuits?.enttelligence?.state)}>
                  {health?.circuits?.enttelligence?.state || 'Unknown'}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {health?.circuits?.enttelligence?.failures || 0} / {health?.circuits?.enttelligence?.failure_threshold || 3} fails
                </span>
              </div>
              <div className="w-full bg-muted h-1 rounded-full overflow-hidden mt-2">
                <div 
                  className={`h-full ${health?.circuits?.enttelligence?.state === 'open' ? 'bg-red-500' : 'bg-green-500'}`}
                  style={{ width: `${Math.min(100, ((health?.circuits?.enttelligence?.failures || 0) / (health?.circuits?.enttelligence?.failure_threshold || 3)) * 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground uppercase font-semibold">
                Protects: API Data Sync
              </p>
            </div>
          </ComponentCard>
        )}

        {/* EntTelligence */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="EntTelligence Sync"
            icon={Zap}
            status={health?.components?.enttelligence?.status}
          >
            <div className="space-y-2">
              <Badge variant={getStatusVariant(health?.components?.enttelligence?.status)}>
                {health?.components?.enttelligence?.status || 'Unknown'}
              </Badge>
              {health?.components?.enttelligence?.records_synced !== undefined && (
                <p className="text-sm text-muted-foreground">
                  {health.components.enttelligence.records_synced.toLocaleString()} records synced
                </p>
              )}
              {health?.components?.enttelligence?.last_sync && (
                <p className="text-xs text-muted-foreground">
                  Last: {formatDistanceToNow(new Date(health.components.enttelligence.last_sync), { addSuffix: true })}
                </p>
              )}
              {health?.components?.enttelligence?.message && (
                <p className="text-xs text-muted-foreground">
                  {health.components.enttelligence.message}
                </p>
              )}
            </div>
          </ComponentCard>
        )}

        {/* Pending Alerts */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="Pending Alerts"
            icon={Bell}
            status={health?.components?.alerts?.status}
          >
            <div className="space-y-2">
              <div className="text-2xl font-bold">
                {health?.components?.alerts?.total_pending || 0}
              </div>
              <div className="text-sm text-muted-foreground space-y-1">
                <p>Price: {health?.components?.alerts?.price_pending || 0}</p>
                <p>Schedule: {health?.components?.alerts?.schedule_pending || 0}</p>
              </div>
            </div>
          </ComponentCard>
        )}

        {/* Scheduler */}
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : (
          <ComponentCard
            title="Scheduler"
            icon={Clock}
            status={health?.components?.scheduler?.status}
          >
            <div className="space-y-2">
              <Badge variant={getStatusVariant(health?.components?.scheduler?.status)}>
                {health?.components?.scheduler?.status || 'Unknown'}
              </Badge>
              {health?.components?.scheduler?.age_minutes !== undefined && (
                <p className="text-sm text-muted-foreground">
                  Last activity: {health.components.scheduler.age_minutes.toFixed(0)} min ago
                </p>
              )}
              {health?.components?.scheduler?.last_activity && (
                <p className="text-xs text-muted-foreground">
                  {new Date(health.components.scheduler.last_activity).toLocaleString()}
                </p>
              )}
              {health?.components?.scheduler?.message && (
                <p className="text-xs text-muted-foreground">
                  {health.components.scheduler.message}
                </p>
              )}
            </div>
          </ComponentCard>
        )}

      </div>
      
      {/* Maintenance Tasks */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wrench className="h-5 w-5 text-muted-foreground" />
              Automated Maintenance
            </CardTitle>
            <CardDescription>Scheduled background tasks for system health.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
             <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/10 h-full">
                <div className="flex gap-3">
                    <Trash2 className="h-5 w-5 text-amber-500 mt-1" />
                    <div>
                        <p className="font-semibold text-sm">Data Retention Cleanup</p>
                        <p className="text-xs text-muted-foreground">Deletes records older than retention policy (daily).</p>
                    </div>
                </div>
                <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => retentionMutation.mutate()}
                    disabled={retentionMutation.isPending}
                >
                    {retentionMutation.isPending ? 'Running...' : 'Run Now'}
                </Button>
             </div>
             
             <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/10 h-full">
                <div className="flex gap-3">
                    <ListRestart className="h-5 w-5 text-blue-500 mt-1" />
                    <div>
                        <p className="font-semibold text-sm">Database Vacuum</p>
                        <p className="text-xs text-muted-foreground">Optimizes database storage and reclaims space (weekly).</p>
                    </div>
                </div>
                <Badge variant="outline">Automatic</Badge>
             </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-muted-foreground" />
              Retention Policy
            </CardTitle>
            <CardDescription>Rules for historical data preservation.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
                {maintenance?.retention_policy ? (
                    Object.entries(maintenance.retention_policy).map(([key, days]) => {
                        const labels: Record<string, string> = {
                            showings: 'Scraped Prices',
                            scrape_runs: 'Scrape Records',
                            audit_log: 'Audit Logs',
                            price_alerts: 'Price Alerts',
                            schedule_alerts: 'Schedule Alerts',
                            cache: 'Cache Data',
                            operating_hours: 'Operating Hours',
                        };
                        return (
                            <div key={key} className="flex flex-col p-2 border rounded bg-muted/5">
                                <span className="text-[10px] uppercase font-bold text-muted-foreground">
                                    {labels[key] || key}
                                </span>
                                <span className="text-lg font-semibold">{days as number} Days</span>
                            </div>
                        );
                    })
                ) : (
                    Array.from({ length: 6 }).map((_, i) => (
                        <Skeleton key={i} className="h-12 w-full" />
                    ))
                )}
            </div>
            <p className="text-[10px] text-muted-foreground mt-4 italic">
                Retention periods can be adjusted in system configuration environment variables.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Info Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Health Status Legend</CardTitle>
          <CardDescription>Understanding component status indicators</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <span className="text-sm"><strong>OK / Healthy</strong> - Operating normally</span>
            </div>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-500" />
              <span className="text-sm"><strong>Degraded</strong> - Partial functionality</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="text-sm"><strong>Error / Critical</strong> - Not functioning</span>
            </div>
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-gray-400" />
              <span className="text-sm"><strong>Unknown</strong> - Status unavailable</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
