/**
 * AlternativeContentPanel - Manage Alternative Content (Special Events) films
 *
 * Allows operators to:
 * - View detected AC films (Fathom, Opera, Concerts, etc.)
 * - Run auto-detection to find new AC films
 * - Manually classify films
 * - View circuit AC pricing strategies
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Film,
  Search,
  RefreshCw,
  CheckCircle2,
  Sparkles,
  Settings,
  ChevronDown,
  ChevronUp,
  Loader2,
  Trash2,
} from 'lucide-react';
import {
  useACFilms,
  useRunACDetection,
  useUpdateACFilm,
  useDeleteACFilm,
  useCircuitACPricing,
  getContentTypeLabel,
  getContentTypeColor,
  CONTENT_TYPE_LABELS,
} from '@/hooks/api';

export function AlternativeContentPanel() {
  const [searchQuery, setSearchQuery] = useState('');
  const [contentTypeFilter, setContentTypeFilter] = useState<string>('all');
  const [showCircuitPricing, setShowCircuitPricing] = useState(false);

  // Fetch data
  const {
    data: acFilmsData,
    isLoading: filmsLoading,
    refetch: refetchFilms,
  } = useACFilms({
    search: searchQuery || undefined,
    contentType: contentTypeFilter !== 'all' ? contentTypeFilter : undefined,
    isActive: true,
    limit: 100,
  });

  const { data: circuitPricing } = useCircuitACPricing();

  // Mutations
  const runDetection = useRunACDetection();
  const updateFilm = useUpdateACFilm();
  const deleteFilm = useDeleteACFilm();

  const handleRunDetection = async () => {
    try {
      await runDetection.mutateAsync(90);
      // Refetch to show new films
      refetchFilms();
    } catch (error) {
      console.error('Detection failed:', error);
    }
  };

  const handleVerifyFilm = async (filmId: number) => {
    try {
      await updateFilm.mutateAsync({ filmId, is_verified: true });
    } catch (error) {
      console.error('Failed to verify film:', error);
    }
  };

  const handleUpdateContentType = async (filmId: number, contentType: string) => {
    try {
      await updateFilm.mutateAsync({ filmId, content_type: contentType });
    } catch (error) {
      console.error('Failed to update content type:', error);
    }
  };

  const handleDeleteFilm = async (filmId: number) => {
    try {
      await deleteFilm.mutateAsync(filmId);
    } catch (error) {
      console.error('Failed to delete film:', error);
    }
  };

  const films = acFilmsData?.films ?? [];
  const contentTypes = acFilmsData?.content_types ?? Object.keys(CONTENT_TYPE_LABELS);

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Film className="h-5 w-5 text-purple-500" />
                Alternative Content Management
              </CardTitle>
              <CardDescription>
                Track special events, Fathom films, opera broadcasts, and other alternative content
                that may have different pricing rules.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCircuitPricing(!showCircuitPricing)}
              >
                <Settings className="h-4 w-4 mr-1" />
                Circuit Pricing
                {showCircuitPricing ? (
                  <ChevronUp className="h-4 w-4 ml-1" />
                ) : (
                  <ChevronDown className="h-4 w-4 ml-1" />
                )}
              </Button>
              <Button
                onClick={handleRunDetection}
                disabled={runDetection.isPending}
                size="sm"
              >
                {runDetection.isPending ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4 mr-1" />
                )}
                Run Detection
              </Button>
            </div>
          </div>
        </CardHeader>

        {/* Detection Result */}
        {runDetection.isSuccess && runDetection.data && (
          <CardContent className="pt-0">
            <div className="flex items-center gap-2 text-green-600 bg-green-50 dark:bg-green-950/20 rounded-md p-3">
              <CheckCircle2 className="h-5 w-5" />
              <span className="text-sm">
                Detection complete: Found {runDetection.data.total_unique} films,
                saved {runDetection.data.new_saved} new.
              </span>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Circuit AC Pricing Strategies (Collapsible) */}
      {showCircuitPricing && circuitPricing && circuitPricing.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Circuit AC Pricing Strategies</CardTitle>
            <CardDescription>
              How each circuit handles Alternative Content pricing
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              {circuitPricing.map((strategy) => (
                <div
                  key={strategy.id}
                  className="p-4 rounded-lg border bg-muted/30"
                >
                  <div className="font-medium">{strategy.circuit_name}</div>
                  <div className="text-sm text-muted-foreground mt-1 space-y-1">
                    {strategy.discount_ticket_type && (
                      <div>
                        <span className="text-muted-foreground">Discount Ticket: </span>
                        <Badge variant="secondary" className="text-xs">
                          {strategy.discount_ticket_type}
                        </Badge>
                      </div>
                    )}
                    {strategy.typical_price_min && strategy.typical_price_max && (
                      <div>
                        Price Range: ${strategy.typical_price_min.toFixed(2)} - $
                        {strategy.typical_price_max.toFixed(2)}
                      </div>
                    )}
                    <div>
                      Discount Day Applies:{' '}
                      {strategy.discount_day_applies ? (
                        <Badge variant="default" className="text-xs bg-green-600">Yes</Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs">No</Badge>
                      )}
                    </div>
                    {strategy.notes && (
                      <div className="text-xs text-muted-foreground/80 mt-2 italic">
                        {strategy.notes}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search films..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <Select value={contentTypeFilter} onValueChange={setContentTypeFilter}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Content Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {contentTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {getContentTypeLabel(type)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => refetchFilms()}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Films Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Detected Films ({acFilmsData?.total ?? 0})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {filmsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : films.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Film className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p>No alternative content films detected.</p>
              <p className="text-sm mt-1">
                Click "Run Detection" to scan recent showings.
              </p>
            </div>
          ) : (
            <div className="rounded-md border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Film</TableHead>
                    <TableHead>Content Type</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead className="text-center">Confidence</TableHead>
                    <TableHead className="text-center">Verified</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {films.map((film) => (
                    <TableRow key={film.id}>
                      <TableCell className="max-w-[300px]">
                        <div className="font-medium truncate" title={film.film_title}>
                          {film.film_title}
                        </div>
                        {film.detection_reason && (
                          <div className="text-xs text-muted-foreground truncate" title={film.detection_reason}>
                            {film.detection_reason}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Select
                          value={film.content_type}
                          onValueChange={(value) => handleUpdateContentType(film.id, value)}
                        >
                          <SelectTrigger className="h-8 w-[140px]">
                            <SelectValue>
                              <Badge className={`text-xs ${getContentTypeColor(film.content_type)}`}>
                                {getContentTypeLabel(film.content_type)}
                              </Badge>
                            </SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {contentTypes.map((type) => (
                              <SelectItem key={type} value={type}>
                                {getContentTypeLabel(type)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        {film.content_source ? (
                          <span className="text-sm">{film.content_source}</span>
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge
                          variant={film.detection_confidence >= 0.8 ? 'default' : 'secondary'}
                          className="text-xs"
                        >
                          {Math.round(film.detection_confidence * 100)}%
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        {film.is_verified ? (
                          <CheckCircle2 className="h-5 w-5 text-green-500 mx-auto" />
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleVerifyFilm(film.id)}
                            className="h-8 px-2"
                          >
                            Verify
                          </Button>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteFilm(film.id)}
                          className="h-8 px-2 text-red-500 hover:text-red-700 hover:bg-red-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
