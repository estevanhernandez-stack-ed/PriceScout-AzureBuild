import { useState } from 'react';
import { usePriceAlerts, useAcknowledgeAlert, useBulkAcknowledge } from '@/hooks/api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, RefreshCw, TrendingUp, TrendingDown, Sparkles } from 'lucide-react';

interface PriceAlertsTableProps {
  acknowledged?: boolean;
  limit?: number;
}

export function PriceAlertsTable({
  acknowledged = false,
  limit = 25,
}: PriceAlertsTableProps) {
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const { data, isLoading, error, refetch, isFetching } = usePriceAlerts({
    acknowledged,
    limit,
  });

  const acknowledgeAlert = useAcknowledgeAlert();
  const bulkAcknowledge = useBulkAcknowledge();

  const handleAcknowledge = async (alertId: number) => {
    await acknowledgeAlert.mutateAsync({ alertId });
    setSelectedIds((ids) => ids.filter((id) => id !== alertId));
  };

  const handleBulkAcknowledge = async () => {
    if (selectedIds.length === 0) return;
    await bulkAcknowledge.mutateAsync({ alertIds: selectedIds });
    setSelectedIds([]);
  };

  const toggleSelection = (alertId: number) => {
    setSelectedIds((ids) =>
      ids.includes(alertId)
        ? ids.filter((id) => id !== alertId)
        : [...ids, alertId]
    );
  };

  const toggleAll = () => {
    if (!data?.alerts) return;
    if (selectedIds.length === data.alerts.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(data.alerts.map((a) => a.alert_id));
    }
  };

  const getAlertIcon = (alertType: string) => {
    switch (alertType) {
      case 'PriceIncrease':
        return <TrendingUp className="h-4 w-4 text-red-500" />;
      case 'PriceDecrease':
        return <TrendingDown className="h-4 w-4 text-green-500" />;
      case 'NewOffering':
        return <Sparkles className="h-4 w-4 text-blue-500" />;
      default:
        return null;
    }
  };

  const getAlertBadge = (alertType: string) => {
    switch (alertType) {
      case 'PriceIncrease':
        return <Badge variant="destructive">Increase</Badge>;
      case 'PriceDecrease':
        return <Badge variant="success">Decrease</Badge>;
      case 'NewOffering':
        return <Badge variant="info">New</Badge>;
      default:
        return <Badge variant="secondary">{alertType}</Badge>;
    }
  };

  const formatPrice = (price?: number | null) => {
    if (price == null) return '-';
    return `$${price.toFixed(2)}`;
  };

  const formatChange = (oldPrice?: number | null, newPrice?: number | null) => {
    if (oldPrice == null || newPrice == null) return null;
    const change = ((newPrice - oldPrice) / oldPrice) * 100;
    const sign = change > 0 ? '+' : '';
    return `${sign}${change.toFixed(1)}%`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatPlayDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatDaypart = (daypart?: string | null) => {
    if (!daypart) return null;
    // Capitalize first letter and handle underscores
    return daypart.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const formatShortDate = (dateStr?: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
        <p className="text-sm text-destructive">
          Error loading alerts: {error.message}
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="mt-2">
          Try Again
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {data?.total ?? 0} alerts total
            {selectedIds.length > 0 && ` (${selectedIds.length} selected)`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && !acknowledged && (
            <Button
              size="sm"
              onClick={handleBulkAcknowledge}
              disabled={bulkAcknowledge.isPending}
            >
              <Check className="mr-2 h-4 w-4" />
              Acknowledge ({selectedIds.length})
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${isFetching ? 'animate-spin' : ''}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {!acknowledged && (
                <TableHead className="w-12">
                  <input
                    type="checkbox"
                    checked={Boolean(
                      data?.alerts &&
                      data.alerts.length > 0 &&
                      selectedIds.length === data.alerts.length
                    )}
                    onChange={toggleAll}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                </TableHead>
              )}
              <TableHead>Theater</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>For Date</TableHead>
              <TableHead>Old Price</TableHead>
              <TableHead>New Price</TableHead>
              <TableHead>Change</TableHead>
              <TableHead>Triggered</TableHead>
              {!acknowledged && <TableHead className="w-24">Action</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell
                  colSpan={acknowledged ? 7 : 9}
                  className="h-24 text-center"
                >
                  <div className="flex items-center justify-center">
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    Loading alerts...
                  </div>
                </TableCell>
              </TableRow>
            ) : data?.alerts && data.alerts.length > 0 ? (
              data.alerts.map((alert) => (
                <TableRow key={alert.alert_id}>
                  {!acknowledged && (
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(alert.alert_id)}
                        onChange={() => toggleSelection(alert.alert_id)}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                    </TableCell>
                  )}
                  <TableCell className="font-medium">
                    <div>
                      <p>{alert.theater_name}</p>
                      {alert.film_title && (
                        <p className="text-xs text-muted-foreground">
                          {alert.film_title}
                        </p>
                      )}
                      {(alert.format || alert.ticket_type) && (
                        <p className="text-xs text-muted-foreground">
                          {[alert.ticket_type, alert.format].filter(Boolean).join(' • ')}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {getAlertIcon(alert.alert_type)}
                      {getAlertBadge(alert.alert_type)}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div>
                      <p className="font-medium">{formatPlayDate(alert.play_date)}</p>
                      {(alert.showtime || alert.daypart) && (
                        <p className="text-xs text-muted-foreground">
                          {alert.showtime && alert.daypart
                            ? `${alert.showtime} (${formatDaypart(alert.daypart)})`
                            : alert.showtime || formatDaypart(alert.daypart)}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div>
                      <p>{formatPrice(alert.old_price)}</p>
                      {alert.old_price_captured_at && (
                        <p className="text-xs text-muted-foreground">
                          from {formatShortDate(alert.old_price_captured_at)}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{formatPrice(alert.new_price)}</TableCell>
                  <TableCell>
                    {formatChange(alert.old_price, alert.new_price) && (
                      <span
                        className={
                          (alert.new_price ?? 0) > (alert.old_price ?? 0)
                            ? 'text-red-500'
                            : 'text-green-500'
                        }
                      >
                        {formatChange(alert.old_price, alert.new_price)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(alert.triggered_at)}
                  </TableCell>
                  {!acknowledged && (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleAcknowledge(alert.alert_id)}
                        disabled={acknowledgeAlert.isPending}
                      >
                        <Check className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={acknowledged ? 7 : 9}
                  className="h-24 text-center text-muted-foreground"
                >
                  No {acknowledged ? 'acknowledged' : 'pending'} alerts found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
