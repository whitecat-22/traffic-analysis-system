import React, { useState } from 'react';
import Map, { NavigationControl, Source, Layer, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapPin } from 'lucide-react';
import axios from 'axios';

const MAP_STYLES = {
  gsi: {
    version: 8,
    sources: {
      gsi: {
        type: 'raster',
        tiles: ['https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>'
      }
    },
    layers: [{ id: 'gsi-raster', type: 'raster', source: 'gsi', minzoom: 0, maxzoom: 18 }]
  },
  osm: {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '&copy; OpenStreetMap Contributors'
      }
    },
    layers: [{ id: 'osm-raster', type: 'raster', source: 'osm', minzoom: 0, maxzoom: 19 }]
  }
};

interface Props {
  routeGeometry: any;
  setRouteGeometry: (geo: any) => void;
}

const MapComponent: React.FC<Props> = ({ routeGeometry, setRouteGeometry }) => {
  const [viewState, setViewState] = useState({
    longitude: 139.7671,
    latitude: 35.6812,
    zoom: 10
  });

  const [points, setPoints] = useState<[number, number][]>([]); // [lon, lat]
  const [baseMap, setBaseMap] = useState<'gsi' | 'osm'>('osm');
  const [isLoadingRoute, setIsLoadingRoute] = useState(false);

  const fetchRoute = async (currentPoints: [number, number][]) => {
    if (currentPoints.length < 2) return;

    setIsLoadingRoute(true);
    try {
      // バックエンド経由でValhallaにリクエスト
      const response = await axios.post('http://localhost:8000/map-match', currentPoints);

      if (response.data && response.data.geometry) {
        // GeoJSON形式でルートが返ってくることを想定
        const routeFeature = {
          type: 'Feature',
          geometry: response.data.geometry,
          properties: response.data.properties || {}
        };
        setRouteGeometry(routeFeature);
      }
    } catch (error) {
      console.error("Failed to fetch route:", error);
      // エラー時は何もしないか、直線を引くフォールバック（バックエンド側でも対応済み）
    } finally {
      setIsLoadingRoute(false);
    }
  };

  const handleMapClick = async (event: any) => {
    const { lng, lat } = event.lngLat;
    const newPoints: [number, number][] = [...points, [lng, lat]];
    setPoints(newPoints);

    // 2点以上でルート探索実行
    if (newPoints.length >= 2) {
      await fetchRoute(newPoints);
    }
  };

  // リセット機能
  const resetMap = () => {
    setPoints([]);
    setRouteGeometry(null);
  };

  return (
    <div className="w-full h-full relative">
      {/* Map Tools */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <div className="bg-white rounded-lg shadow-md p-1 flex text-sm">
          <button
            onClick={() => setBaseMap('osm')}
            className={`px-3 py-1 rounded-md ${baseMap === 'osm' ? 'bg-blue-100 text-blue-700 font-bold' : 'text-gray-600'}`}
          >
            OSM
          </button>
          <button
            onClick={() => setBaseMap('gsi')}
            className={`px-3 py-1 rounded-md ${baseMap === 'gsi' ? 'bg-blue-100 text-blue-700 font-bold' : 'text-gray-600'}`}
          >
            地理院地図
          </button>
        </div>
        <button
            onClick={resetMap}
            className="bg-white px-3 py-1.5 rounded-lg shadow-md text-sm font-bold text-red-500 hover:bg-red-50"
        >
            Reset
        </button>
      </div>

      <Map
        {...viewState}
        onMove={evt => setViewState(evt.viewState)}
        style={{ width: '100%', height: '100%' }}
        mapStyle={MAP_STYLES[baseMap] as any}
        onClick={handleMapClick}
        cursor={isLoadingRoute ? 'wait' : (points.length < 2 ? 'crosshair' : 'grab')}
      >
        <NavigationControl position="bottom-right" />

        {points.map((p, idx) => (
          <Marker key={idx} longitude={p[0]} latitude={p[1]} anchor="bottom">
            <div className="relative group">
              <MapPin
                size={32}
                className={idx === 0 ? "text-green-600" : idx === points.length - 1 ? "text-red-600" : "text-blue-600"}
                fill="white"
              />
              <span className="absolute -top-6 left-1/2 transform -translate-x-1/2 bg-white px-1.5 py-0.5 rounded shadow text-xs font-bold opacity-0 group-hover:opacity-100 transition-opacity">
                {idx === 0 ? "Start" : idx === points.length - 1 ? "End" : `Via ${idx}`}
              </span>
            </div>
          </Marker>
        ))}

        {routeGeometry && (
          <Source id="route" type="geojson" data={routeGeometry}>
            <Layer
              id="route-line"
              type="line"
              layout={{ 'line-join': 'round', 'line-cap': 'round' }}
              paint={{
                'line-color': '#3b82f6',
                'line-width': 6,
                'line-opacity': 0.8
              }}
            />
          </Source>
        )}
      </Map>

      <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 bg-white/90 backdrop-blur px-4 py-2 rounded-full shadow-lg text-xs font-medium text-gray-600 pointer-events-none">
        {isLoadingRoute ? "ルートを計算中..." : (
          points.length === 0 ? "地図をクリックして起点を設定してください" : "地図をクリックして経由地・終点を設定してください"
        )}
      </div>
    </div>
  );
};

export default MapComponent;
