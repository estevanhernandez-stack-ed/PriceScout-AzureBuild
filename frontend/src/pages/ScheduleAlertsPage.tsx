import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import {
  useScheduleAlerts,
  useScheduleAlertSummary,
  useAcknowledgeScheduleAlert,
  useBulkAcknowledgeScheduleAlerts,
  useTriggerScheduleCheck,
  useScheduleMonitorConfig,
  useUpdateScheduleMonitorConfig,
  getAlertTypeInfo,
  type ScheduleAlert,
  type ScheduleMonitorConfig,
} from '@/hooks/api';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import {
  Bell,
  BellOff,
  Film,
  Clock,
  Minus,
  Plus,
  Palette,
  CheckCircle2,
  RefreshCw,
  Play,
  Calendar,
  Star,
  TrendingUp,
  Settings,
  Shield,
  Mail,
  Webhook
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

function AlertTypeIcon({ type }: { type: string }) {
  switch (type) {
    case 'new_film':
      return <Film className="h-4 w-4 text-blue-500" />;
    case 'new_showtime':
      return <Plus className="h-4 w-4 text-green-500" />;
    case 'removed_showtime':
      return <Minus className="h-4 w-4 text-orange-500" />;
    case 'removed_film':
      return <Film className="h-4 w-4 text-red-500" />;
    case 'format_added':
      return <Palette className="h-4 w-4 text-purple-500" />;
    case 'new_schedule':
      return <Calendar className="h-4 w-4 text-cyan-500" />;
    case 'event_added':
      return <Star className="h-4 w-4 text-amber-500" />;
    case 'presale_started':
      return <TrendingUp className="h-4 w-4 text-rose-500" />;
    default:
      return <Clock className="h-4 w-4 text-gray-500" />;
  }
}

function AlertTypeDisplay({ type }: { type: string }) {
  const { label, color } = getAlertTypeInfo(type);
  return (
    <div className="flex items-center gap-2">
      <AlertTypeIcon type={type} />
      <span className={color}>{label}</span>
    </div>
  );
}

export function ScheduleAlertsPage() {
  const [showAcknowledged, setShowAcknowledged] = useState(false);
  const [selectedAlerts, setSelectedAlerts] = useState<Set<number>>(new Set());
  const [acknowledgeDialogOpen, setAcknowledgeDialogOpen] = useState(false);
  const [acknowledgeNotes, setAcknowledgeNotes] = useState('');
  const { toast } = useToast();

  const { data: summary, isLoading: summaryLoading } = useScheduleAlertSummary();
  const { data: alerts, isLoading: alertsLoading, refetch } = useScheduleAlerts({
    acknowledged: showAcknowledged,
    limit: 100,
  });
  const acknowledgeMutation = useAcknowledgeScheduleAlert();
  const bulkAcknowledgeMutation = useBulkAcknowledgeScheduleAlerts();
  const triggerCheckMutation = useTriggerScheduleCheck();

  const { data: config, isLoading: configLoading } = useScheduleMonitorConfig();
  const updateConfigMutation = useUpdateScheduleMonitorConfig();

  const handleSelectAll = (checked: boolean) => {
    if (checked && alerts) {
      setSelectedAlerts(new Set(alerts.map((a) => a.alert_id)));
    } else {
      setSelectedAlerts(new Set());
    }
  };

  const handleSelectAlert = (alertId: number, checked: boolean) => {
    const newSelected = new Set(selectedAlerts);
    if (checked) {
      newSelected.add(alertId);
    } else {
      newSelected.delete(alertId);
    }
    setSelectedAlerts(newSelected);
  };

  const handleAcknowledge = async () => {
    try {
      if (selectedAlerts.size === 1) {
        const alertId = Array.from(selectedAlerts)[0];
        await acknowledgeMutation.mutateAsync({ alertId, notes: acknowledgeNotes || undefined });
      } else {
        await bulkAcknowledgeMutation.mutateAsync({
          alertIds: Array.from(selectedAlerts),
          notes: acknowledgeNotes || undefined,
        });
      }
      toast({
        title: 'Success',
        description: `${selectedAlerts.size} alert(s) acknowledged.`,
      });
      setSelectedAlerts(new Set());
      setAcknowledgeDialogOpen(false);
      setAcknowledgeNotes('');
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to acknowledge alerts.',
        variant: 'destructive',
      });
    }
  };

  const handleTriggerCheck = async () => {
    try {
      const result = await triggerCheckMutation.mutateAsync();
      toast({
        title: 'Schedule Check Complete',
        description: `${result.alerts_created} new alerts created.`,
      });
      refetch();
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to run schedule check.',
        variant: 'destructive',
      });
    }
  };

  const handleUpdateConfig = async (updates: Partial<ScheduleMonitorConfig>) => {
    try {
      await updateConfigMutation.mutateAsync(updates);
      toast({
        title: 'Settings Saved',
        description: 'Schedule monitor configuration updated successfully.',
      });
    } catch {
      toast({
        title: 'Error',
        description: 'Failed to update configuration.',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="space-y-6">
      <Tabs defaultValue="alerts">
        <div className="flex items-center justify-between mb-4">
          <TabsList>
            <TabsTrigger value="alerts">
              <Bell className="h-4 w-4 mr-2" />
              Alerts
            </TabsTrigger>
            <TabsTrigger value="config">
              <Settings className="h-4 w-4 mr-2" />
              Monitor Settings
            </TabsTrigger>
          </TabsList>
          
          <TabsContent value="alerts" className="mt-0">
             <Button
                variant="outline"
                size="sm"
                onClick={handleTriggerCheck}
                disabled={triggerCheckMutation.isPending}
              >
                <Play className={`mr-2 h-4 w-4 ${triggerCheckMutation.isPending ? 'animate-spin' : ''}`} />
                Run Check Now
              </Button>
          </TabsContent>
        </div>

        <TabsContent value="alerts" className="space-y-6 mt-0">
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-5">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Pending</CardTitle>
                <Bell className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summaryLoading ? '...' : summary?.total_pending ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">New Films</CardTitle>
                <Film className="h-4 w-4 text-blue-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summaryLoading ? '...' : summary?.by_type?.new_film ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">New Showtimes</CardTitle>
                <Plus className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summaryLoading ? '...' : summary?.by_type?.new_showtime ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Removed</CardTitle>
                <Minus className="h-4 w-4 text-orange-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summaryLoading
                    ? '...'
                    : (summary?.by_type?.removed_showtime ?? 0) +
                      (summary?.by_type?.removed_film ?? 0)}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Events & Presales</CardTitle>
                <Star className="h-4 w-4 text-amber-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {summaryLoading
                    ? '...'
                    : (summary?.by_type?.event_added ?? 0) +
                      (summary?.by_type?.presale_started ?? 0)}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Alerts Table */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>
                    {showAcknowledged ? 'Acknowledged Alerts' : 'Pending Alerts'}
                  </CardTitle>
                  <CardDescription>
                    {showAcknowledged
                      ? 'Previously reviewed schedule change alerts.'
                      : 'Schedule changes that need your attention.'}
                  </CardDescription>
                </div>
                <div className="flex gap-2">
                  {selectedAlerts.size > 0 && !showAcknowledged && (
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => setAcknowledgeDialogOpen(true)}
                    >
                      <CheckCircle2 className="mr-2 h-4 w-4" />
                      Acknowledge ({selectedAlerts.size})
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => refetch()}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Refresh
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setShowAcknowledged(!showAcknowledged);
                      setSelectedAlerts(new Set());
                    }}
                  >
                    {showAcknowledged ? (
                      <>
                        <Bell className="mr-2 h-4 w-4" />
                        Show Pending
                      </>
                    ) : (
                      <>
                        <BellOff className="mr-2 h-4 w-4" />
                        Show Acknowledged
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {alertsLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : !alerts || alerts.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {showAcknowledged
                    ? 'No acknowledged alerts.'
                    : 'No pending alerts. All caught up!'}
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      {!showAcknowledged && (
                        <TableHead className="w-10">
                          <Checkbox
                            checked={selectedAlerts.size === alerts.length}
                            onCheckedChange={handleSelectAll}
                          />
                        </TableHead>
                      )}
                      <TableHead>Type</TableHead>
                      <TableHead>Theater</TableHead>
                      <TableHead>Film</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Details</TableHead>
                      <TableHead>Triggered</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {alerts.map((alert: ScheduleAlert) => (
                      <TableRow key={alert.alert_id}>
                        {!showAcknowledged && (
                          <TableCell>
                            <Checkbox
                              checked={selectedAlerts.has(alert.alert_id)}
                              onCheckedChange={(checked) =>
                                handleSelectAlert(alert.alert_id, checked as boolean)
                              }
                            />
                          </TableCell>
                        )}
                        <TableCell>
                          <AlertTypeDisplay type={alert.alert_type} />
                        </TableCell>
                        <TableCell className="font-medium max-w-[150px] truncate">
                          {alert.theater_name}
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate">
                          {alert.film_title || '-'}
                        </TableCell>
                        <TableCell>{alert.play_date}</TableCell>
                        <TableCell className="max-w-[250px] truncate text-muted-foreground">
                          {alert.change_details}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {formatDistanceToNow(new Date(alert.triggered_at), { addSuffix: true })}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config">
          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-primary" />
                    <div>
                        <CardTitle>Core Monitor Settings</CardTitle>
                        <CardDescription>Enable/disable the automated schedule worker.</CardDescription>
                    </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                 {configLoading ? (
                   <Skeleton className="h-40 w-full" />
                 ) : (
                   <>
                    <div className="flex items-center justify-between space-x-2">
                        <div className="space-y-0.5">
                            <Label>Enabled</Label>
                            <p className="text-sm text-muted-foreground">Run automated checks in the background.</p>
                        </div>
                        <Switch 
                            checked={config?.is_enabled} 
                            onCheckedChange={(checked) => handleUpdateConfig({ is_enabled: checked })}
                        />
                    </div>
                    
                    <div className="space-y-2 pt-4 border-t">
                        <Label>Check Frequency (Hours)</Label>
                        <div className="flex items-center gap-4">
                            <Input 
                                type="number" 
                                value={config?.check_frequency_hours} 
                                onChange={(e) => handleUpdateConfig({ check_frequency_hours: parseInt(e.target.value) })}
                                className="w-32"
                            />
                            <span className="text-sm text-muted-foreground">Recommended: 6 hours</span>
                        </div>
                    </div>

                    <div className="space-y-2 pt-4 border-t">
                        <Label>Days Ahead</Label>
                        <div className="flex items-center gap-4">
                            <Input 
                                type="number" 
                                value={config?.days_ahead} 
                                onChange={(e) => handleUpdateConfig({ days_ahead: parseInt(e.target.value) })}
                                className="w-32"
                            />
                            <span className="text-sm text-muted-foreground">Monitor schedules up to X days in future.</span>
                        </div>
                    </div>
                   </>
                 )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                    <Bell className="h-5 w-5 text-primary" />
                    <div>
                        <CardTitle>Alert Triggers</CardTitle>
                        <CardDescription>Select which changes should trigger an alert.</CardDescription>
                    </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                 {configLoading ? (
                   <Skeleton className="h-64 w-full" />
                 ) : (
                   <div className="grid gap-4">
                      {[
                        { key: 'alert_on_new_film', label: 'New Film Added' },
                        { key: 'alert_on_new_showtime', label: 'New Showtime Added' },
                        { key: 'alert_on_removed_film', label: 'Film Removed' },
                        { key: 'alert_on_removed_showtime', label: 'Showtime Removed' },
                        { key: 'alert_on_format_added', label: 'New PLF Format' },
                        { key: 'alert_on_time_changed', label: 'Showtime Time Change' },
                        { key: 'alert_on_new_schedule', label: 'Entire New Schedule Released' },
                        { key: 'alert_on_presale', label: 'Presale Started' }
                      ].map((item) => (
                        <div key={item.key} className="flex items-center justify-between">
                            <Label className="font-normal">{item.label}</Label>
                            <Switch 
                                checked={config?.[item.key as keyof ScheduleMonitorConfig] as boolean} 
                                onCheckedChange={(checked) => handleUpdateConfig({ [item.key]: checked })}
                            />
                        </div>
                      ))}
                   </div>
                 )}
              </CardContent>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader>
                <div className="flex items-center gap-2">
                    <Webhook className="h-5 w-5 text-primary" />
                    <div>
                        <CardTitle>Notifications & Integrations</CardTitle>
                        <CardDescription>Configure external notification channels.</CardDescription>
                    </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-6 md:grid-cols-2">
                    <div className="space-y-2">
                        <Label className="flex items-center gap-2">
                            <Mail className="h-4 w-4" />
                            Email Notifications
                        </Label>
                        <Input 
                            placeholder="alerts@company.com" 
                            defaultValue={config?.notification_email}
                            onBlur={(e) => handleUpdateConfig({ notification_email: e.target.value })}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="flex items-center gap-2">
                            <Webhook className="h-4 w-4" />
                            Webhook URL
                        </Label>
                        <Input 
                            placeholder="https://hooks.slack.com/..." 
                            defaultValue={config?.webhook_url}
                            onBlur={(e) => handleUpdateConfig({ webhook_url: e.target.value })}
                        />
                    </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Acknowledge Dialog */}
      <Dialog open={acknowledgeDialogOpen} onOpenChange={setAcknowledgeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Acknowledge Alerts</DialogTitle>
            <DialogDescription>
              Mark {selectedAlerts.size} alert(s) as reviewed. Optionally add notes.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Textarea
              placeholder="Optional notes about these alerts..."
              value={acknowledgeNotes}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAcknowledgeNotes(e.target.value)}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAcknowledgeDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAcknowledge}
              disabled={acknowledgeMutation.isPending || bulkAcknowledgeMutation.isPending}
            >
              {(acknowledgeMutation.isPending || bulkAcknowledgeMutation.isPending)
                ? 'Acknowledging...'
                : 'Acknowledge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
