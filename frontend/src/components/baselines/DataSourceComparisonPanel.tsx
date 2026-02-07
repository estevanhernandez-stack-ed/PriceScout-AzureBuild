/**
 * Data Source Comparison Panel
 *
 * Compares EntTelligence prices against Fandango baselines to understand:
 * - Are EntTelligence prices tax-inclusive or exclusive?
 * - How accurate is EntTelligence pricing vs actual Fandango prices?
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Scale,
  Search,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  TrendingUp,
  Info,
  Receipt,
} from 'lucide-react';
import { useCompareDataSources, useTaxConfig, type PriceComparisonItem } from '@/hooks/api';

export function DataSourceComparisonPanel() {
  const [theaterFilter, setTheaterFilter] = useState('');
  const [runComparison, setRunComparison] = useState(false);
  const [applyTax, setApplyTax] = useState(true);

  const { data: taxConfig } = useTaxConfig();
  const taxConfigured = taxConfig?.enabled ?? false;

  const { data: comparison, isLoading } = useCompareDataSources({
    theaterFilter: theaterFilter || undefined,
    minSamples: 3,
    limit: 200,
    applyTax,
    enabled: runComparison,
  });

  const handleCompare = () => {
    setRunComparison(true);
  };

  const getTaxBadge = () => {
    if (!comparison) return null;
    const likelihood = comparison.summary.tax_inclusive_likelihood;

    if (likelihood === 'likely_tax_exclusive') {
      return (
        <Badge variant="destructive" className="text-sm">
          <TrendingDown className="h-3 w-3 mr-1" />
          Likely TAX-EXCLUSIVE
        </Badge>
      );
    }
    if (likelihood === 'likely_tax_inclusive') {
      return (
        <Badge variant="default" className="bg-green-600 text-sm">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Likely TAX-INCLUSIVE
        </Badge>
      );
    }
    if (likelihood === 'likely_tax_inclusive_but_different') {
      return (
        <Badge variant="secondary" className="text-sm">
          <AlertTriangle className="h-3 w-3 mr-1" />
          Prices Higher Than Expected
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-sm">
        Unknown
      </Badge>
    );
  };

  return (
    <div className="space-y-4">
      {/* Info Card */}
      <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="py-4">
          <div className="flex items-start gap-3">
            <Info className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
            <div className="text-sm">
              <p className="font-medium text-blue-700 dark:text-blue-300">
                Understanding EntTelligence vs Fandango Prices
              </p>
              <p className="text-muted-foreground mt-1">
                <strong>Fandango</strong> shows customer-facing prices (definitely tax-inclusive).
                <strong> EntTelligence</strong> pricing standards are unknown. This comparison helps
                determine if EntTelligence prices are tax-inclusive or tax-exclusive.
              </p>
              <p className="text-muted-foreground mt-2">
                <strong>Tax detection:</strong> If EntTelligence is consistently 7-10% lower,
                prices are likely tax-exclusive. US sales tax typically ranges 6-10%.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Comparison Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-5 w-5 text-purple-500" />
            Compare Data Sources
          </CardTitle>
          <CardDescription>
            Compare EntTelligence prices against your verified Fandango baselines
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4 items-end">
            <div className="flex-1 space-y-2">
              <Label>Theater Filter (optional)</Label>
              <Input
                placeholder="e.g., AMC, Marcus..."
                value={theaterFilter}
                onChange={(e) => setTheaterFilter(e.target.value)}
              />
            </div>
            <Button onClick={handleCompare} disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Comparing...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4 mr-2" />
                  Run Comparison
                </>
              )}
            </Button>
          </div>

          {/* Tax Toggle */}
          <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
            <div className="flex items-center gap-2">
              <Receipt className="h-4 w-4 text-green-600" />
              <div>
                <Label className="text-sm font-medium">Apply Estimated Tax</Label>
                <p className="text-xs text-muted-foreground">
                  {taxConfigured
                    ? `Adjust EntTelligence prices with estimated tax (default: ${((taxConfig?.default_rate ?? 0) * 100).toFixed(1)}%)`
                    : 'Configure tax rates in the Tax Configuration panel below to enable'}
                </p>
              </div>
            </div>
            <Switch
              checked={applyTax}
              onCheckedChange={setApplyTax}
              disabled={!taxConfigured}
            />
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {comparison && (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Tax Status</CardTitle>
              </CardHeader>
              <CardContent>
                {getTaxBadge()}
                <p className="text-xs text-muted-foreground mt-2">
                  {comparison.summary.interpretation}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Avg Difference</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold flex items-center gap-2">
                  {comparison.avg_difference_percent > 0 ? (
                    <TrendingUp className="h-5 w-5 text-red-500" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-blue-500" />
                  )}
                  {comparison.avg_difference_percent > 0 ? '+' : ''}
                  {comparison.avg_difference_percent.toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground">
                  ${comparison.avg_difference.toFixed(2)} per ticket
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Comparisons</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{comparison.total_comparisons}</div>
                <p className="text-xs text-muted-foreground">
                  theater/ticket/format matches
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Price Direction</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex gap-2 text-sm">
                  <Badge variant="outline" className="bg-blue-100 text-blue-800">
                    Ent Lower: {comparison.fandango_higher_count}
                  </Badge>
                  <Badge variant="outline" className="bg-red-100 text-red-800">
                    Ent Higher: {comparison.ent_higher_count}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Exact matches: {comparison.exact_match_count}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Comparison Table */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Price Comparison Details
                <Badge variant="secondary">{comparison.comparisons.length}</Badge>
              </CardTitle>
              <CardDescription>
                Side-by-side comparison of EntTelligence vs Fandango prices
              </CardDescription>
            </CardHeader>
            <CardContent>
              {comparison.comparisons.length > 0 ? (
                <div className="rounded-md border max-h-[500px] overflow-auto">
                  {comparison.tax_adjustment_applied && (
                    <div className="px-3 py-2 bg-green-50 dark:bg-green-950/20 border-b text-xs text-green-700 dark:text-green-300 flex items-center gap-1">
                      <Receipt className="h-3 w-3" />
                      Tax adjustment applied (default rate: {((comparison.default_tax_rate ?? 0) * 100).toFixed(1)}%)
                    </div>
                  )}
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Theater</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Format</TableHead>
                        <TableHead className="text-right">EntTelligence</TableHead>
                        {comparison.tax_adjustment_applied && (
                          <TableHead className="text-right">+ Tax</TableHead>
                        )}
                        <TableHead className="text-right">Fandango</TableHead>
                        <TableHead className="text-right">Difference</TableHead>
                        {comparison.tax_adjustment_applied && (
                          <TableHead className="text-right">Tax Rate</TableHead>
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparison.comparisons.map((item: PriceComparisonItem, i: number) => {
                        // Use adjusted difference if tax applied, otherwise raw
                        const displayDiffPct = comparison.tax_adjustment_applied && item.adjusted_difference_percent != null
                          ? item.adjusted_difference_percent
                          : item.difference_percent;

                        return (
                          <TableRow key={i}>
                            <TableCell className="font-medium max-w-[200px] truncate">
                              {item.theater_name}
                            </TableCell>
                            <TableCell>{item.ticket_type}</TableCell>
                            <TableCell>{item.format || '2D'}</TableCell>
                            <TableCell className="text-right font-mono">
                              ${item.enttelligence_price.toFixed(2)}
                              <span className="text-xs text-muted-foreground ml-1">
                                ({item.ent_sample_count})
                              </span>
                            </TableCell>
                            {comparison.tax_adjustment_applied && (
                              <TableCell className="text-right font-mono text-green-700 dark:text-green-400">
                                {item.ent_price_tax_adjusted != null
                                  ? `$${item.ent_price_tax_adjusted.toFixed(2)}`
                                  : '—'}
                              </TableCell>
                            )}
                            <TableCell className="text-right font-mono font-bold">
                              ${item.fandango_baseline.toFixed(2)}
                            </TableCell>
                            <TableCell className="text-right">
                              <span
                                className={
                                  displayDiffPct < -5
                                    ? 'text-blue-600 font-medium'
                                    : displayDiffPct > 5
                                    ? 'text-red-600 font-medium'
                                    : 'text-muted-foreground'
                                }
                              >
                                {displayDiffPct > 0 ? '+' : ''}
                                {displayDiffPct.toFixed(1)}%
                              </span>
                            </TableCell>
                            {comparison.tax_adjustment_applied && (
                              <TableCell className="text-right text-xs text-muted-foreground font-mono">
                                {item.tax_rate_applied != null
                                  ? `${(item.tax_rate_applied * 100).toFixed(1)}%`
                                  : '—'}
                              </TableCell>
                            )}
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                  <p>No matching theaters found between EntTelligence and Fandango</p>
                  <p className="text-sm">
                    Make sure you have both EntTelligence data and Fandango baselines for the same theaters
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Empty State */}
      {!comparison && !isLoading && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <Scale className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">Ready to Compare</p>
              <p className="text-sm">
                Click "Run Comparison" to compare EntTelligence prices against your Fandango baselines
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
