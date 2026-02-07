import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PriceAlertsTable } from '@/components/data-tables/PriceAlertsTable';
import { useAlertSummary, useAcknowledgeAll } from '@/hooks/api';
import { Bell, BellOff, TrendingUp, TrendingDown, Zap, AlertTriangle, CheckCheck } from 'lucide-react';

export function PriceAlertsPage() {
  const [showAcknowledged, setShowAcknowledged] = useState(false);
  const { data: summary, isLoading: summaryLoading } = useAlertSummary();
  const acknowledgeAll = useAcknowledgeAll();

  const handleAcknowledgeAll = async () => {
    if (!summary?.total_pending || summary.total_pending === 0) return;
    const confirmed = window.confirm(
      `Acknowledge all ${summary.total_pending} pending alerts? This cannot be undone.`
    );
    if (!confirmed) return;
    await acknowledgeAll.mutateAsync({ notes: 'Bulk cleared all pending alerts' });
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold">Price Alerts</h1>
        <p className="text-muted-foreground">
          Monitor price changes and manage alerts from your tracked competitors.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Alerts</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.total_pending ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Require attention
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Price Increases</CardTitle>
            <TrendingUp className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.by_type?.price_increase ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Competitors raised prices
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Price Decreases</CardTitle>
            <TrendingDown className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.by_type?.price_decrease ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Competitors lowered prices
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Surges Detected</CardTitle>
            <Zap className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.by_type?.surge_detected ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Above baseline threshold
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Discount Violations</CardTitle>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.by_type?.discount_day_overcharge ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Above expected discount price
            </p>
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
                  ? 'Previously reviewed price change alerts.'
                  : 'Price change alerts that need your attention.'}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {!showAcknowledged && (summary?.total_pending ?? 0) > 0 && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleAcknowledgeAll}
                  disabled={acknowledgeAll.isPending}
                >
                  <CheckCheck className="mr-2 h-4 w-4" />
                  {acknowledgeAll.isPending
                    ? 'Clearing...'
                    : `Acknowledge All (${summary?.total_pending ?? 0})`}
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAcknowledged(!showAcknowledged)}
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
          <PriceAlertsTable acknowledged={showAcknowledged} limit={50} />
        </CardContent>
      </Card>
    </div>
  );
}
