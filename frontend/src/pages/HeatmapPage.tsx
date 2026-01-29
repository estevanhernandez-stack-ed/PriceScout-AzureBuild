/**
 * Standalone Heatmap Page
 *
 * Visualizes theater locations and pricing data on an interactive map.
 */

import { useMemo, useState } from 'react';
import { MapContainer, TileLayer, Popup, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useHeatmapData, useBaselineMarkets } from '@/hooks/api';
import { Map as MapIcon, RefreshCw, Filter, Building2, DollarSign, X } from 'lucide-react';
import L from 'leaflet';

// Fix for leaflet marker icons in React
// @ts-ignore
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png',
});

export function HeatmapPage() {
  // Filters
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedCircuit, setSelectedCircuit] = useState<string>('');

  // Data fetching
  const { data: heatmapData, isLoading, refetch } = useHeatmapData({
    market: selectedMarket || undefined,
    circuit: selectedCircuit || undefined,
  });
  const { data: markets } = useBaselineMarkets();

  // Calculate center of the map
  const center = useMemo((): [number, number] => {
    if (!heatmapData || heatmapData.theaters.length === 0) {
      return [39.8283, -98.5795]; // US Center
    }

    const lat = heatmapData.theaters.reduce((sum, t) => sum + t.latitude, 0) / heatmapData.theaters.length;
    const lon = heatmapData.theaters.reduce((sum, t) => sum + t.longitude, 0) / heatmapData.theaters.length;
    return [lat, lon];
  }, [heatmapData]);

  // Color scale for price heatmap
  const getColor = (avgPrice: number | null): string => {
    if (avgPrice === null) return '#94a3b8'; // Gray for no data
    if (avgPrice > 18) return '#ef4444'; // Red (High)
    if (avgPrice > 14) return '#f97316'; // Orange
    if (avgPrice > 10) return '#eab308'; // Yellow
    return '#22c55e'; // Green (Low)
  };

  // Clear filters
  const clearFilters = () => {
    setSelectedMarket('');
    setSelectedCircuit('');
  };

  const hasFilters = selectedMarket || selectedCircuit;

  return (
    <div className="space-y-4">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MapIcon className="h-6 w-6 text-blue-500" />
            Price Heatmap
          </h1>
          <p className="text-slate-500 mt-1">
            Visualize theater pricing across markets
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="py-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Filter className="h-4 w-4" />
              Filters
            </CardTitle>
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Market</Label>
              <Select
                value={selectedMarket || '__all__'}
                onValueChange={(val) => setSelectedMarket(val === '__all__' ? '' : val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All Markets" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All Markets</SelectItem>
                  {markets?.map(m => (
                    <SelectItem key={m.market} value={m.market}>
                      {m.market} ({m.theater_count} theaters)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Circuit</Label>
              <Input
                placeholder="Filter by circuit name..."
                value={selectedCircuit}
                onChange={(e) => setSelectedCircuit(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Stats</Label>
              <div className="flex gap-2 pt-1">
                <Badge variant="outline">
                  {heatmapData?.theaters_with_coords || 0} theaters on map
                </Badge>
                <Badge variant="secondary">
                  {heatmapData?.total_theaters || 0} total
                </Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Map */}
      <Card className="overflow-hidden">
        <CardContent className="p-0 relative">
          {isLoading ? (
            <div className="h-[600px] flex items-center justify-center bg-slate-50">
              <div className="text-center">
                <Skeleton className="h-12 w-12 rounded-full mx-auto mb-4" />
                <p className="text-slate-500">Loading map data...</p>
              </div>
            </div>
          ) : !heatmapData || heatmapData.theaters.length === 0 ? (
            <div className="h-[600px] flex flex-col items-center justify-center bg-slate-50 p-6">
              <MapIcon className="h-16 w-16 text-slate-300 mb-4" />
              <h3 className="text-lg font-semibold text-slate-600">No Theater Data Available</h3>
              <p className="text-slate-500 text-center max-w-md mt-2">
                Theaters need geospatial metadata (latitude/longitude) to appear on the map.
                Sync theater metadata from EntTelligence to enable the heatmap visualization.
              </p>
            </div>
          ) : (
            <>
              <div className="h-[600px] w-full z-10">
                <MapContainer
                  key={`${center[0]}-${center[1]}`}
                  center={center}
                  zoom={selectedMarket ? 10 : 4}
                  style={{ height: '100%', width: '100%' }}
                  scrollWheelZoom={true}
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    opacity={0.8}
                  />
                  {heatmapData.theaters.map((theater) => {
                    const color = getColor(theater.avg_price);

                    return (
                      <CircleMarker
                        key={theater.theater_name}
                        center={[theater.latitude, theater.longitude]}
                        radius={10}
                        pathOptions={{
                          fillColor: color,
                          fillOpacity: 0.8,
                          color: '#fff',
                          weight: 2,
                        }}
                      >
                        <Popup className="custom-popup">
                          <div className="p-1 space-y-2 min-w-[200px]">
                            <h4 className="font-bold text-slate-900 leading-tight">
                              {theater.theater_name}
                            </h4>
                            <p className="text-xs text-slate-500">
                              {theater.circuit_name || 'Independent'}
                              {theater.market && ` | ${theater.market}`}
                            </p>
                            <div className="pt-2 border-t space-y-1">
                              <div className="flex justify-between items-center">
                                <span className="text-xs font-medium text-slate-600">
                                  <DollarSign className="h-3 w-3 inline" /> Avg Price:
                                </span>
                                <span className="text-sm font-bold text-slate-900">
                                  {theater.avg_price ? `$${theater.avg_price.toFixed(2)}` : 'N/A'}
                                </span>
                              </div>
                              <div className="flex justify-between items-center">
                                <span className="text-xs font-medium text-slate-600">
                                  <Building2 className="h-3 w-3 inline" /> Baselines:
                                </span>
                                <span className="text-sm font-bold text-slate-900">
                                  {theater.baseline_count}
                                </span>
                              </div>
                            </div>
                            {theater.formats.length > 0 && (
                              <div className="pt-2 border-t">
                                <span className="text-xs text-slate-500">Formats:</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {theater.formats.slice(0, 5).map(f => (
                                    <Badge key={f} variant="outline" className="text-[10px] px-1.5 py-0">
                                      {f}
                                    </Badge>
                                  ))}
                                  {theater.formats.length > 5 && (
                                    <span className="text-[10px] text-slate-400">
                                      +{theater.formats.length - 5} more
                                    </span>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        </Popup>
                      </CircleMarker>
                    );
                  })}
                </MapContainer>
              </div>

              {/* Legend Overlay */}
              <div className="absolute bottom-4 left-4 z-[1000] bg-white/95 backdrop-blur-sm p-3 rounded-lg border shadow-lg max-w-[180px]">
                <h5 className="text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
                  Avg Baseline Price
                </h5>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#ef4444]" />
                    <span className="text-[10px] text-slate-600">High (&gt;$18)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#f97316]" />
                    <span className="text-[10px] text-slate-600">Premium ($14-18)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#eab308]" />
                    <span className="text-[10px] text-slate-600">Standard ($10-14)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#22c55e]" />
                    <span className="text-[10px] text-slate-600">Value (&lt;$10)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-[#94a3b8]" />
                    <span className="text-[10px] text-slate-600">No data</span>
                  </div>
                </div>
              </div>

              {/* Summary Stats */}
              <div className="absolute top-4 right-4 z-[1000] bg-white/95 backdrop-blur-sm p-3 rounded-lg border shadow-lg">
                <div className="text-xs text-slate-500">
                  Showing <strong className="text-slate-900">{heatmapData.theaters_with_coords}</strong> theaters
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
