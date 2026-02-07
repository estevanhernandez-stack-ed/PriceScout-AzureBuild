/**
 * Name Mapping Panel
 *
 * Shows theater name mapping status: known aliases, match log, and unmatched theaters.
 * Helps admins understand how market theater names resolve to EntTelligence names.
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
import { Link2, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { useNameMapping } from '@/hooks/api';

function getMethodBadge(method: string) {
  switch (method) {
    case 'exact':
      return <Badge variant="default">exact</Badge>;
    case 'normalized':
      return <Badge variant="secondary">normalized</Badge>;
    case 'deep_normalized':
      return <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">deep</Badge>;
    case 'substring':
      return <Badge className="bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">substring</Badge>;
    case 'word_set':
      return <Badge className="bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300">word-set</Badge>;
    case 'deep_word_set':
      return <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">deep word-set</Badge>;
    case 'alias':
      return <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">alias</Badge>;
    default:
      return <Badge variant="outline">{method}</Badge>;
  }
}

export function NameMappingPanel() {
  const { data, isLoading, error } = useNameMapping();

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
          <p>Failed to load name mapping data.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Theater Name Resolution Summary
          </CardTitle>
          <CardDescription>
            How market theater names are resolved against theater_metadata and EntTelligence
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold">{data.total_market_theaters}</p>
              <p className="text-sm text-muted-foreground">Total Market Theaters</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-green-600">{data.metadata_matched}</p>
              <p className="text-sm text-muted-foreground">Metadata Matched</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-blue-600">{data.enttelligence_matched}</p>
              <p className="text-sm text-muted-foreground">EntTelligence Matched</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Non-Trivial Matches */}
      {data.non_trivial_matches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              Non-Trivial Matches ({data.non_trivial_matches.length})
            </CardTitle>
            <CardDescription>
              Theaters resolved through normalization, aliases, or fuzzy matching
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border max-h-[400px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Market Name</TableHead>
                    <TableHead>Resolved Name</TableHead>
                    <TableHead className="w-[120px]">Method</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.non_trivial_matches.map((m, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-sm">{m.json_name}</TableCell>
                      <TableCell className="text-sm">{m.resolved_name}</TableCell>
                      <TableCell>{getMethodBadge(m.method)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Known Aliases */}
      {data.aliases.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              Known Aliases ({data.aliases.length})
            </CardTitle>
            <CardDescription>
              Hand-verified name mappings stored in theater_name_mapping table
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>EntTelligence Name</TableHead>
                    <TableHead>Fandango Name</TableHead>
                    <TableHead className="w-[100px]">Confidence</TableHead>
                    <TableHead className="w-[80px]">Verified</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.aliases.map((a) => (
                    <TableRow key={a.enttelligence_name}>
                      <TableCell className="text-sm">{a.enttelligence_name}</TableCell>
                      <TableCell className="text-sm">{a.fandango_name}</TableCell>
                      <TableCell>
                        {a.match_confidence != null ? `${(a.match_confidence * 100).toFixed(0)}%` : '—'}
                      </TableCell>
                      <TableCell>
                        {a.is_verified ? (
                          <Badge variant="default" className="text-xs">Yes</Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">No</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Unmatched Theaters */}
      {data.unmatched_theaters.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              Unmatched Theaters ({data.unmatched_theaters.length})
            </CardTitle>
            <CardDescription>
              Market theaters with no matching entry in theater_metadata
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {data.unmatched_theaters.map((name) => (
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
