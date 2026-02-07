/**
 * System Diagnostics Panel
 *
 * Read-only system diagnostics: data source health, table row counts,
 * baseline status, and configuration summary.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Activity, Database, Target, Settings, Loader2, AlertCircle } from 'lucide-react';
import { useSystemDiagnostics } from '@/hooks/api';

function formatNumber(n: number | null): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString();
}

export function SystemDiagnosticsPanel() {
  const { data, isLoading, error } = useSystemDiagnostics();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          <AlertCircle className="h-8 w-8 mx-auto mb-2" />
          <p>Failed to load system diagnostics.</p>
        </CardContent>
      </Card>
    );
  }

  const ent = data.data_sources.enttelligence;
  const fan = data.data_sources.fandango;

  return (
    <div className="space-y-4">
      {/* Data Sources */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Activity className="h-5 w-5 text-blue-600" />
              EntTelligence
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {ent?.status === 'unavailable' ? (
              <p className="text-muted-foreground">Data source unavailable</p>
            ) : ent ? (
              <>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Date Range</span>
                  <span className="font-mono">{ent.date_range || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Fetch</span>
                  <span className="font-mono">{ent.last_fetch || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Theaters</span>
                  <span>{formatNumber(ent.theaters ?? null)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Circuits</span>
                  <span>{formatNumber(ent.circuits ?? null)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total Rows</span>
                  <span>{formatNumber(ent.total_rows ?? null)}</span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">No data available</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Activity className="h-5 w-5 text-orange-600" />
              Fandango
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {fan?.status === 'unavailable' ? (
              <p className="text-muted-foreground">Data source unavailable</p>
            ) : fan ? (
              <>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Date Range</span>
                  <span className="font-mono">{fan.date_range || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Scrape</span>
                  <span className="font-mono">{fan.last_scrape || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Theaters</span>
                  <span>{formatNumber(fan.theaters ?? null)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total Showings</span>
                  <span>{formatNumber(fan.total_showings ?? null)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total Prices</span>
                  <span>{formatNumber(fan.total_prices ?? null)}</span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">No data available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Table Row Counts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Database className="h-5 w-5" />
            Table Row Counts
          </CardTitle>
          <CardDescription>
            Row counts for key database tables
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Table</TableHead>
                  <TableHead className="text-right">Rows</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(data.table_counts).map(([table, count]) => (
                  <TableRow key={table}>
                    <TableCell className="font-mono text-sm">{table}</TableCell>
                    <TableCell className="text-right font-mono">
                      {count === null ? (
                        <Badge variant="outline" className="text-xs">missing</Badge>
                      ) : (
                        formatNumber(count)
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Baseline Summary */}
      {Object.keys(data.baseline_summary).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Target className="h-5 w-5" />
              Active Baselines by Source
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-right">Active Count</TableHead>
                    <TableHead>Earliest</TableHead>
                    <TableHead>Latest Discovery</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(data.baseline_summary).map(([source, info]) => (
                    <TableRow key={source}>
                      <TableCell className="font-medium">{source}</TableCell>
                      <TableCell className="text-right font-mono">{formatNumber(info.active_count)}</TableCell>
                      <TableCell className="font-mono text-sm">{info.earliest || '—'}</TableCell>
                      <TableCell className="font-mono text-sm">{info.latest_discovery || '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Config Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Settings className="h-5 w-5" />
            Configuration Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <Badge variant={data.config_summary.tax_enabled ? 'default' : 'outline'}>
                {data.config_summary.tax_enabled ? 'Enabled' : 'Disabled'}
              </Badge>
              <p className="text-sm text-muted-foreground mt-1">Tax Estimation</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-mono font-bold">
                {(data.config_summary.tax_default_rate * 100).toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground">Default Tax Rate</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-mono font-bold">
                {data.config_summary.tax_state_overrides}
              </p>
              <p className="text-sm text-muted-foreground">State Overrides</p>
            </div>
            <div className="text-center">
              <Badge variant={data.config_summary.enttelligence_enabled ? 'default' : 'outline'}>
                {data.config_summary.enttelligence_enabled ? 'Enabled' : 'Disabled'}
              </Badge>
              <p className="text-sm text-muted-foreground mt-1">EntTelligence</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {data.error && (
        <Card className="border-destructive">
          <CardContent className="py-4 text-destructive text-sm">
            Diagnostics error: {data.error}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
