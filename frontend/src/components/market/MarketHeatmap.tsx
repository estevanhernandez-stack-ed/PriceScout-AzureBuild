import { useMemo } from 'react';
import { MapContainer, TileLayer, Popup, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TheaterMetadata } from '@/hooks/api/useMarketContext';
import { Map as MapIcon } from 'lucide-react';
import L from 'leaflet';

// Fix for leaflet marker icons in React
// @ts-ignore
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png',
});

interface ShowingData {
  theater_name: string;
  avg_price: number;
  presale_occupancy?: number;
  film_title?: string;
  is_competitor?: boolean;
}

interface MarketHeatmapProps {
  theaters: TheaterMetadata[];
  data: ShowingData[];
  marketName: string;
  metric: 'price' | 'occupancy';
}

export function MarketHeatmap({ theaters, data, marketName, metric }: MarketHeatmapProps) {
  // Filter theaters that have coordinates
  const mappedTheaters = useMemo(() => {
    return theaters
      .filter(t => t.latitude && t.longitude)
      .map(t => {
        const theaterData = data.find(d => d.theater_name === t.theater_name);
        return {
          ...t,
          data: theaterData,
        };
      });
  }, [theaters, data]);

  // Calculate center of the map
  const center = useMemo((): [number, number] => {
    if (mappedTheaters.length === 0) return [39.8283, -98.5795]; // US Center
    
    const lat = mappedTheaters.reduce((sum, t) => sum + (t.latitude || 0), 0) / mappedTheaters.length;
    const lon = mappedTheaters.reduce((sum, t) => sum + (t.longitude || 0), 0) / mappedTheaters.length;
    return [lat, lon];
  }, [mappedTheaters]);

  // Color scale for heatmap
  const getColor = (value: number, type: 'price' | 'occupancy') => {
    if (type === 'price') {
      if (value > 18) return '#ef4444'; // Red (High)
      if (value > 14) return '#f97316'; // Orange
      if (value > 10) return '#eab308'; // Yellow
      return '#22c55e'; // Green (Low)
    } else {
      if (value > 0.8) return '#ef4444'; // Red
      if (value > 0.5) return '#f97316';
      if (value > 0.2) return '#eab308';
      return '#22c55e';
    }
  };

  if (mappedTheaters.length === 0) {
    return (
      <Card className="h-[500px] flex flex-col items-center justify-center text-center p-6 bg-slate-50/50">
        <MapIcon className="h-12 w-12 text-slate-300 mb-4" />
        <CardTitle className="text-slate-500">No Geospatial Data Available</CardTitle>
        <CardDescription className="max-w-xs mt-2">
          Sync theater metadata from EntTelligence to enable the Market Heatmap for {marketName}.
        </CardDescription>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-slate-200 shadow-sm">
      <CardHeader className="bg-slate-50/50 border-b py-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <MapIcon className="h-5 w-5 text-blue-500" />
              Market Heatmap: {marketName}
            </CardTitle>
            <CardDescription>
              Visualizing {metric === 'price' ? 'Average Price' : 'Presale Occupancy'} across the market
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline" className="bg-white">
              {mappedTheaters.length} Theaters Mapped
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0 relative">
        <div className="h-[500px] w-full z-10">
          <MapContainer 
            center={center} 
            zoom={11} 
            style={{ height: '100%', width: '100%' }}
            scrollWheelZoom={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              opacity={0.7}
            />
            {mappedTheaters.map((t) => {
              const val = metric === 'price' ? t.data?.avg_price : t.data?.presale_occupancy;
              const color = val ? getColor(val, metric) : '#94a3b8';
              
              return (
                <CircleMarker
                  key={t.id}
                  center={[t.latitude!, t.longitude!]}
                  radius={12}
                  pathOptions={{
                    fillColor: color,
                    fillOpacity: 0.8,
                    color: '#fff',
                    weight: 2,
                  }}
                >
                  <Popup className="custom-popup">
                    <div className="p-1 space-y-1">
                      <h4 className="font-bold text-slate-900 leading-tight">{t.theater_name}</h4>
                      <p className="text-xs text-slate-500">{t.circuit_name || 'Independent'}</p>
                      <div className="pt-2 border-t mt-2">
                        <div className="flex justify-between items-center gap-4">
                          <span className="text-xs font-medium text-slate-600">Avg Price:</span>
                          <span className="text-sm font-bold text-slate-900">
                            {t.data?.avg_price ? `$${t.data.avg_price.toFixed(2)}` : 'N/A'}
                          </span>
                        </div>
                        {t.data?.presale_occupancy !== undefined && (
                          <div className="flex justify-between items-center gap-4">
                            <span className="text-xs font-medium text-slate-600">Occupancy:</span>
                            <span className="text-sm font-bold text-slate-900">
                              {(t.data.presale_occupancy * 100).toFixed(1)}%
                            </span>
                          </div>
                        )}
                      </div>
                      {t.circuit_name?.includes('Marcus') ? (
                        <Badge className="w-full justify-center mt-2 bg-blue-500 hover:bg-blue-600">Your Theater</Badge>
                      ) : (
                        <Badge variant="outline" className="w-full justify-center mt-2 border-orange-200 text-orange-700 bg-orange-50">Competitor</Badge>
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
            {metric === 'price' ? 'Price Levels' : 'Occupancy'}
          </h5>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#ef4444]" />
              <span className="text-[10px] text-slate-600">{metric === 'price' ? 'High (>$18)' : 'Hot (>80%)'}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#f97316]" />
              <span className="text-[10px] text-slate-600">{metric === 'price' ? 'Premium ($14-18)' : 'Moderate (50-80%)'}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#eab308]" />
              <span className="text-[10px] text-slate-600">{metric === 'price' ? 'Standard ($10-14)' : 'Low (20-50%)'}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-[#22c55e]" />
              <span className="text-[10px] text-slate-600">{metric === 'price' ? 'Value (<$10)' : 'Empty (<20%)'}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
