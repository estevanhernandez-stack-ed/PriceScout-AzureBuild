import { useState, useMemo } from 'react';
import { useTheaterCache } from '@/hooks/api/useMarkets';
import { 
  useUnmatchedTheaters, 
  useMatchTheater, 
  useDiscoverTheater,
  type UnmatchedTheater,
  type TheaterDiscoveryResult
} from '@/hooks/api/useCache';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Link2,
  Link2Off,
  Search,
  Building2,
  MapPin,
  ExternalLink,
  Check,
  X,
  RefreshCw,
  AlertTriangle,
  Settings,
} from 'lucide-react';

export function TheaterMatchingPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTheater, setSelectedTheater] = useState<UnmatchedTheater | null>(null);
  const [matchUrl, setMatchUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [discoveryResults, setDiscoveryResults] = useState<TheaterDiscoveryResult[]>([]);

  const { data: cacheData, isLoading: cacheLoading } = useTheaterCache();
  const {
    data: unmatchedData,
    isLoading: unmatchedLoading,
    refetch: refetchUnmatched,
  } = useUnmatchedTheaters();
  
  const matchMutation = useMatchTheater();
  const discoverMutation = useDiscoverTheater();

  const isLoading = cacheLoading || unmatchedLoading;

  // Get markets for filter dropdown (future use)
  const _markets = useMemo(() => {
    if (!cacheData?.markets) return [];
    return Object.keys(cacheData.markets).sort();
  }, [cacheData]);
  void _markets; // Suppress unused variable warning

  const unmatchedTheaters = unmatchedData?.theaters || [];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'no_match':
        return <Badge variant="destructive">Unmatched</Badge>;
      case 'not_on_fandango':
        return <Badge variant="secondary">Not on Fandango</Badge>;
      case 'closed':
        return <Badge variant="outline">Closed</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const filteredTheaters = unmatchedTheaters.filter(
    (theater) =>
      theater.theater_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      theater.market.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (theater.company?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false)
  );

  const handleDiscover = async () => {
    if (!selectedTheater) return;
    setDiscoveryResults([]);
    
    try {
      const result = await discoverMutation.mutateAsync({
        theater_name: selectedTheater.theater_name
      });
      if (result.all_results) {
        setDiscoveryResults(result.all_results);
      }
      if (result.url) {
        setMatchUrl(result.url);
      }
      if (result.theater_name) {
        setNewName(result.theater_name);
      }
    } catch (error) {
      console.error('Discovery failed:', error);
    }
  };

  const handleMatchTheater = async () => {
    if (!selectedTheater || !matchUrl) return;

    try {
      await matchMutation.mutateAsync({
        theater_name: selectedTheater.theater_name,
        market: selectedTheater.market,
        fandango_url: matchUrl,
        new_name: newName || undefined,
      });
      setSelectedTheater(null);
      setMatchUrl('');
      setNewName('');
      setDiscoveryResults([]);
      refetchUnmatched();
    } catch (error) {
      console.error('Failed to match theater:', error);
    }
  };

  const handleMarkNotOnFandango = async () => {
    if (!selectedTheater) return;

    try {
      await matchMutation.mutateAsync({
        theater_name: selectedTheater.theater_name,
        market: selectedTheater.market,
        not_on_fandango: true,
        external_url: matchUrl || undefined,
      });
      setSelectedTheater(null);
      setMatchUrl('');
      setNewName('');
      setDiscoveryResults([]);
      refetchUnmatched();
    } catch (error) {
      console.error('Failed to update theater:', error);
    }
  };

  const handleMarkClosed = async () => {
    if (!selectedTheater) return;

    try {
      await matchMutation.mutateAsync({
        theater_name: selectedTheater.theater_name,
        market: selectedTheater.market,
        mark_as_closed: true,
      });
      setSelectedTheater(null);
      refetchUnmatched();
    } catch (error) {
      console.error('Failed to update theater:', error);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Calculate summary stats
  const summaryStats = {
    unmatched: unmatchedTheaters.filter((t) => t.status === 'no_match').length,
    notOnFandango: unmatchedTheaters.filter((t) => t.status === 'not_on_fandango').length,
    closed: unmatchedTheaters.filter((t) => t.status === 'closed').length,
    marketsAffected: new Set(unmatchedTheaters.map((t) => t.market)).size,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Theater Matching</h1>
          <p className="text-muted-foreground">
            Match local theaters to Fandango URLs
          </p>
        </div>
        <Badge variant="outline" className="text-sm py-1 px-3">
          <Settings className="mr-1 h-3 w-3" />
          Admin Only
        </Badge>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Link2Off className="h-5 w-5 text-red-500" />
              <span className="text-sm text-muted-foreground">Unmatched</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.unmatched}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              <span className="text-sm text-muted-foreground">Not on Fandango</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.notOnFandango}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <X className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Closed</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.closed}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <MapPin className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Markets Affected</span>
            </div>
            <p className="text-3xl font-bold mt-2">{summaryStats.marketsAffected}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Unmatched Theaters List */}
        <div className="col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Link2Off className="h-5 w-5" />
                Unmatched Theaters
              </CardTitle>
              <CardDescription>
                Select a theater to match or update its status
              </CardDescription>
              <div className="relative mt-2">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search theaters, markets, companies..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8"
                />
              </div>
            </CardHeader>
            <CardContent>
              {filteredTheaters.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  {unmatchedTheaters.length === 0
                    ? 'All theaters are matched!'
                    : 'No theaters match your search.'}
                </p>
              ) : (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {filteredTheaters.map((theater) => (
                    <div
                      key={`${theater.market}-${theater.theater_name}`}
                      className={`flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-colors ${
                        selectedTheater?.theater_name === theater.theater_name &&
                        selectedTheater?.market === theater.market
                          ? 'border-primary bg-primary/5'
                          : 'hover:bg-muted/50'
                      }`}
                      onClick={() => {
                        setSelectedTheater(theater);
                        setMatchUrl('');
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <Building2 className="h-5 w-5 text-muted-foreground" />
                        <div>
                          <p className="font-medium">{theater.theater_name}</p>
                          <p className="text-sm text-muted-foreground">
                            {theater.market}
                            {theater.company && ` • ${theater.company}`}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {getStatusBadge(theater.status)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Matching Panel */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Link2 className="h-5 w-5" />
                Match Theater
              </CardTitle>
              <CardDescription>
                {selectedTheater
                  ? `Matching: ${selectedTheater.theater_name}`
                  : 'Select a theater to match'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {selectedTheater ? (
                <>
                  <div className="space-y-4">
                    <div>
                      <Label className="text-sm font-medium">Theater Name</Label>
                      <p className="text-sm mt-1">{selectedTheater.theater_name}</p>
                    </div>
                    <div>
                      <Label className="text-sm font-medium">Market</Label>
                      <p className="text-sm mt-1">{selectedTheater.market}</p>
                    </div>
                    {selectedTheater.company && (
                      <div>
                        <Label className="text-sm font-medium">Company</Label>
                        <p className="text-sm mt-1">{selectedTheater.company}</p>
                      </div>
                    )}

                    <div className="flex gap-2">
                        <div className="flex-1">
                            <Label htmlFor="fandango-url">Fandango/External URL</Label>
                            <Input
                            id="fandango-url"
                            placeholder="https://www.fandango.com/..."
                            value={matchUrl}
                            onChange={(e) => setMatchUrl(e.target.value)}
                            className="mt-1"
                            />
                        </div>
                        <div className="pt-7">
                            <Button 
                                variant="outline" 
                                size="icon" 
                                onClick={handleDiscover}
                                disabled={discoverMutation.isPending}
                                title="Search Fandango"
                            >
                                <RefreshCw className={`h-4 w-4 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />
                            </Button>
                        </div>
                    </div>

                    {discoveryResults.length > 0 && (
                        <div className="p-3 border rounded-md bg-muted/30 space-y-2">
                            <Label className="text-[10px] uppercase font-bold text-muted-foreground">Search Results</Label>
                            <div className="space-y-1">
                                {discoveryResults.map((result) => (
                                    <button
                                        key={result.url}
                                        onClick={() => {
                                            setMatchUrl(result.url);
                                            setNewName(result.name);
                                        }}
                                        className={`w-full text-left p-2 rounded text-xs transition-colors border ${
                                            matchUrl === result.url ? 'bg-primary/10 border-primary' : 'hover:bg-background border-transparent'
                                        }`}
                                    >
                                        <p className="font-medium truncate">{result.name}</p>
                                        <p className="text-[10px] text-muted-foreground truncate opacity-70">{result.url}</p>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {newName && newName !== selectedTheater.theater_name && (
                        <div className="p-2 border rounded border-blue-200 bg-blue-50/50 flex items-center justify-between">
                            <div className="text-[10px]">
                                <span className="text-muted-foreground">Rename to:</span>
                                <p className="font-medium text-blue-700">{newName}</p>
                            </div>
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setNewName('')}>
                                <X className="h-3 w-3" />
                            </Button>
                        </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-2 mt-4">
                    <Button
                      onClick={handleMatchTheater}
                      disabled={!matchUrl || matchMutation.isPending}
                      className="w-full"
                    >
                      <Check className="mr-2 h-4 w-4" />
                      Confirm Match
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleMarkNotOnFandango}
                      disabled={matchMutation.isPending}
                      className="w-full"
                    >
                      <AlertTriangle className="mr-2 h-4 w-4" />
                      Mark Not on Fandango
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={handleMarkClosed}
                      disabled={matchMutation.isPending}
                      className="w-full"
                    >
                      <X className="mr-2 h-4 w-4" />
                      Mark as Closed
                    </Button>
                  </div>

                  <div className="pt-2 mt-2">
                    <a
                      href={`https://www.fandango.com/search?q=${encodeURIComponent(selectedTheater.theater_name)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-500 hover:underline flex items-center gap-1"
                    >
                      Manual Fandango Search
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                </>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Link2Off className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Select a theater from the list to begin matching</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
