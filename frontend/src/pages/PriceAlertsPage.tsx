import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PriceAlertsTable } from '@/components/data-tables/PriceAlertsTable';
import { useAlertSummary } from '@/hooks/api';
import { Bell, BellOff, TrendingUp, TrendingDown, Sparkles } from 'lucide-react';

export function PriceAlertsPage() {
  const [showAcknowledged, setShowAcknowledged] = useState(false);
  const { data: summary, isLoading: summaryLoading } = useAlertSummary();

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
      <div className="grid gap-4 md:grid-cols-4">
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
              {summaryLoading ? '...' : summary?.by_type?.PriceIncrease ?? 0}
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
              {summaryLoading ? '...' : summary?.by_type?.PriceDecrease ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Competitors lowered prices
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">New Offerings</CardTitle>
            <Sparkles className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.by_type?.NewOffering ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              New prices detected
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
        </CardHeader>
        <CardContent>
          <PriceAlertsTable acknowledged={showAcknowledged} limit={50} />
        </CardContent>
      </Card>
    </div>
  );
}
