/**
 * Market Scope Panel
 *
 * Read-only diagnostics showing how markets.json theaters are resolved
 * against theater_metadata and EntTelligence price cache.
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
import { MapPin, Building2, Users, Loader2, AlertCircle } from 'lucide-react';
import { useMarketScope } from '@/hooks/api';

export function MarketScopePanel() {
  const { data, isLoading, error } = useMarketScope();

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
          <p>Failed to load market scope data.</p>
        </CardContent>
      </Card>
    );
  }

  const matchRate = data.total_in_market_theaters > 0
    ? Math.round((data.enttelligence_matched / data.total_in_market_theaters) * 100)
    : 0;

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <Building2 className="h-4 w-4" />
              Total Theaters
            </div>
            <p className="text-2xl font-bold">{data.total_in_market_theaters}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {data.marcus_count} Marcus + {data.competitor_count} competitors
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <MapPin className="h-4 w-4" />
              Markets
            </div>
            <p className="text-2xl font-bold">{data.total_markets}</p>
            <p className="text-xs text-muted-foreground mt-1">
              across {data.total_directors} directors
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              EntTelligence Match
            </div>
            <p className="text-2xl font-bold">
              {data.enttelligence_matched}
              <span className="text-base font-normal text-muted-foreground">
                /{data.total_in_market_theaters}
              </span>
            </p>
            <Badge variant={matchRate >= 90 ? 'default' : 'secondary'} className="mt-1">
              {matchRate}% resolved
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <AlertCircle className="h-4 w-4" />
              Unmatched
            </div>
            <p className="text-2xl font-bold">{data.enttelligence_unmatched}</p>
            <p className="text-xs text-muted-foreground mt-1">
              no EntTelligence data
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Director Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Users className="h-5 w-5" />
            Per-Director Breakdown
          </CardTitle>
          <CardDescription>
            Theater distribution by director from markets.json
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Director</TableHead>
                  <TableHead className="text-right">Markets</TableHead>
                  <TableHead className="text-right">Theaters</TableHead>
                  <TableHead className="text-right">Marcus</TableHead>
                  <TableHead className="text-right">Competitors</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.directors.map((d) => (
                  <TableRow key={d.director}>
                    <TableCell className="font-medium">{d.director}</TableCell>
                    <TableCell className="text-right">{d.market_count}</TableCell>
                    <TableCell className="text-right">{d.theater_count}</TableCell>
                    <TableCell className="text-right">{d.marcus_count}</TableCell>
                    <TableCell className="text-right">{d.competitor_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Unmatched Theaters */}
      {data.match_diagnostics.unmatched.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              Unmatched Theaters ({data.match_diagnostics.unmatched.length})
            </CardTitle>
            <CardDescription>
              These theaters from markets.json have no corresponding entry in theater_metadata
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {data.match_diagnostics.unmatched.map((name) => (
                <div key={name} className="text-sm py-1 px-2 rounded bg-muted/50">
                  {name}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
