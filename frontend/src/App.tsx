import React, { useState, useEffect } from 'react';
import Map, { NavigationControl, Source, Layer, Marker } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import axios from 'axios';
import {
  LayoutDashboard, Map as MapIcon, BarChart3, Settings,
  Calendar as CalIcon, FileText, Play, Upload,
  Plus, Trash2, X, Download, ExternalLink, Search,
  CheckSquare, Square, Loader2, MapPin, ChevronRight,
  Settings2, Clock, CalendarDays, Globe, Infinity as InfinityIcon,
  CheckCircle2, Route as RouteIcon
} from 'lucide-react';

import { TEXTS, Lang, Translation } from './i18n';

// --- Types ---
interface LegendItem { speed: number; color: string; }

interface AppState {
  probeFiles: string[]; linkFiles: string[];
  dateRange: { start: string; end: string };
  timeRange: { start: string; end: string };
  pitch: number; routeGeometry: any | null;
  analysisResult: { htmlUrl: string } | null; isAnalyzing: boolean;
}

// --- Components ---

const UploadSuccessModal: React.FC<{ onClose: () => void, t: Translation }> = ({ onClose, t }) => (
  <div className="absolute inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
    <div className="bg-white rounded-xl shadow-2xl p-6 w-80 flex flex-col items-center text-center">
      <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4 text-green-600">
        <CheckCircle2 size={28} />
      </div>
      <h3 className="text-lg font-bold text-gray-800 mb-2">{t.uploadSuccessTitle}</h3>
      <p className="text-sm text-gray-500 mb-6">{t.uploadSuccessMsg}</p>
      <button onClick={onClose} className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold transition-colors">
        OK
      </button>
    </div>
  </div>
);

const ControlPanel: React.FC<{
  state: AppState; setState: React.Dispatch<React.SetStateAction<AppState>>;
  onAnalyze: (legend: LegendItem[]) => void; lang: Lang;
}> = ({ state, setState, onAnalyze, lang }) => {
  const t = TEXTS[lang];
  const [files, setFiles] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [showLegend, setShowLegend] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const [legend, setLegend] = useState<LegendItem[]>([
    { speed: 20, color: '#ff0000' }, { speed: 40, color: '#ffff00' },
    { speed: 60, color: '#00ff00' }, { speed: 80, color: '#0000ff' }
  ]);

  const fetchFiles = async () => {
    try {
      const res = await axios.get('http://localhost:8000/files');
      if (res.data?.files) setFiles(res.data.files);
    } catch (e) { console.error(e); }
  };
  useEffect(() => { fetchFiles(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const formData = new FormData();
    Array.from(e.target.files).forEach(file => formData.append('files', file));

    setIsUploading(true);
    try {
      await axios.post('http://localhost:8000/upload', formData);
      await fetchFiles();
      setShowSuccess(true);
    } catch {
      alert("Upload failed");
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const toggleFile = (f: string, type: 'probe' | 'link') => {
    setState(prev => {
      const list = type === 'probe' ? prev.probeFiles : prev.linkFiles;
      const newList = list.includes(f) ? list.filter(i => i !== f) : [...list, f];
      return type === 'probe' ? { ...prev, probeFiles: newList } : { ...prev, linkFiles: newList };
    });
  };

  // Legend logic
  const handleSpeedChange = (idx: number, val: string) => {
    const v = parseInt(val); if(isNaN(v)) return;
    setLegend(p => { const n=[...p]; n[idx].speed=v; return n; });
  };
  const handleColorChange = (idx: number, val: string) => {
    setLegend(p => { const n=[...p]; n[idx].color=val; return n; });
  };
  const addRange = () => setLegend(p => {
    const last = p[p.length-1];
    const prev = p.length>1 ? p[p.length-2].speed : 0;
    const updLast = {...last, speed: prev+20};
    return [...p.slice(0,-1), updLast, {speed: updLast.speed+20, color:'#000000'}];
  });
  const removeRange = (i: number) => i!==0 && setLegend(p => p.filter((_, idx) => idx!==i));

  return (
    <div className="w-80 h-full bg-white border-r border-gray-200 flex flex-col font-sans text-gray-700 shadow-xl z-10 relative">
      {/* Header */}
      <div className="p-5 border-b border-gray-100 bg-white">
        <h2 className="text-lg font-bold text-gray-800 tracking-tight">{t.config}</h2>
        <p className="text-[10px] text-gray-400 mt-0.5">{t.param}</p>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar">
        <section>
          <h3 className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <FileText size={12}/> {t.dataSource}
          </h3>
          <div className="border-2 border-dashed border-blue-100 bg-blue-50/30 rounded-xl p-4 mb-3 text-center relative hover:bg-blue-50 hover:border-blue-300 transition-all group cursor-pointer">
            <input type="file" multiple className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onChange={handleUpload} />
            <div className="flex flex-col items-center text-gray-400 group-hover:text-blue-600">
              {isUploading ? <Loader2 className="animate-spin mb-1"/> : <Upload size={18} className="mb-1"/>}
              <span className="text-[10px] font-bold uppercase">{t.upload}</span>
            </div>
          </div>

          {/* Files List */}
          <div className="space-y-3">
            {['probe', 'link'].map(type => (
              <div key={type}>
                <label className="text-[11px] font-bold text-gray-600 mb-1.5 block">{type==='probe'?t.probe:t.link}</label>
                <div className="max-h-32 overflow-y-auto border border-gray-100 rounded-lg bg-gray-50 p-1 custom-scrollbar">
                  {files.map(f => (
                    <div key={f} onClick={() => toggleFile(f, type as any)} className={`flex items-center gap-2 p-1.5 rounded cursor-pointer text-xs transition-colors mb-0.5 ${state[type==='probe'?'probeFiles':'linkFiles'].includes(f) ? 'bg-blue-600 text-white' : 'hover:bg-gray-200 text-gray-600 bg-white'}`}>
                      {state[type==='probe'?'probeFiles':'linkFiles'].includes(f) ? <CheckSquare size={12}/> : <Square size={12} className="opacity-50"/>}
                      <span className="truncate">{f}</span>
                    </div>
                  ))}
                  {files.length===0 && <div className="p-2 text-center text-[10px] text-gray-300">{t.noFiles}</div>}
                </div>
              </div>
            ))}
          </div>
        </section>
        <hr className="border-gray-100"/>

        {/* Period */}
        <section>
          <h3 className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2"><CalIcon size={12}/> {t.period}</h3>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {['start', 'end'].map(k => (
                <div key={k}>
                  <label className="text-[10px] font-bold text-gray-500 uppercase mb-1 flex items-center gap-1"><CalendarDays size={10}/> {k==='start'?t.from:t.to}</label>
                  <input type="date" value={state.dateRange[k as 'start'|'end']} onChange={e => setState(p => ({...p, dateRange: {...p.dateRange, [k]: e.target.value}}))} className="w-full text-xs border border-gray-200 rounded-md px-2 py-1.5 focus:ring-1 ring-blue-500 outline-none bg-gray-50 text-gray-700"/>
                </div>
              ))}
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-500 uppercase mb-1 flex items-center gap-1"><Clock size={10}/> {t.timeRange}</label>
              <div className="flex items-center gap-2">
                <input type="time" value={state.timeRange.start} onChange={e => setState(p => ({...p, timeRange: {...p.timeRange, start: e.target.value}}))} className="flex-1 text-xs border border-gray-200 rounded-md p-1.5 text-center bg-gray-50 outline-none focus:ring-1 ring-blue-500"/>
                <ChevronRight size={12} className="text-gray-300"/>
                <input type="time" value={state.timeRange.end} onChange={e => setState(p => ({...p, timeRange: {...p.timeRange, end: e.target.value}}))} className="flex-1 text-xs border border-gray-200 rounded-md p-1.5 text-center bg-gray-50 outline-none focus:ring-1 ring-blue-500"/>
              </div>
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-500 uppercase mb-1 block">{t.agg}</label>
              <div className="flex gap-1">
                {[15, 30, 60].map(m => (
                  <button key={m} onClick={() => setState(p => ({...p, pitch: m}))} className={`flex-1 py-1 text-[10px] font-bold rounded-md transition-all border ${state.pitch===m ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}>{m}m</button>
                ))}
              </div>
            </div>
          </div>
        </section>
        <hr className="border-gray-100"/>

        <section>
          <button onClick={() => setShowLegend(true)} className="w-full py-2 flex items-center justify-between text-xs font-bold text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-3 hover:bg-blue-100 transition-all group shadow-sm">
            <span className="flex items-center gap-2"><Settings2 size={14}/> {t.legend}</span>
            <span className="bg-white px-1.5 py-0.5 rounded text-[9px] text-blue-600 border border-blue-100">{t.edit}</span>
          </button>
        </section>
      </div>

      <div className="p-5 border-t border-gray-200 bg-gray-50">
        <button onClick={() => onAnalyze(legend)} disabled={state.isAnalyzing} className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold shadow-lg shadow-blue-200 flex items-center justify-center gap-2 text-sm transition-transform active:scale-95 disabled:opacity-50 disabled:shadow-none">
          {state.isAnalyzing ? <><Loader2 className="animate-spin" size={16}/> {t.processing}</> : <><Play size={16} fill="currentColor"/> {t.run}</>}
        </button>
      </div>

      {/* Legend Modal */}
      {showLegend && (
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-xs overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="bg-gray-50 px-4 py-3 border-b border-gray-100 flex justify-between items-center">
              <h3 className="font-bold text-gray-800 text-sm">{t.speedLegend}</h3>
              <button onClick={() => setShowLegend(false)}><X size={16} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-4 space-y-2 max-h-[60vh] overflow-y-auto">
              {legend.map((item, i) => {
                const fromVal = i === 0 ? 0 : legend[i - 1].speed;
                const isLast = i === legend.length - 1;
                return (
                  <div key={i} className="flex items-center gap-2 p-2 bg-gray-50 rounded border border-gray-100">
                    <div className="w-10 text-xs text-right text-gray-500 font-mono bg-gray-100 rounded px-1 py-1 border border-gray-200">{fromVal}</div>
                    <span className="text-gray-400 text-[10px]">~</span>
                    {isLast ? <div className="w-14 text-xs text-center text-gray-500 font-mono bg-gray-100 rounded px-1 py-1 border border-gray-200"><InfinityIcon size={12} className="inline"/></div> :
                      <input type="number" value={item.speed} onChange={(e) => handleSpeedChange(i, e.target.value)} className="w-14 text-xs border rounded px-1 py-1 text-center font-mono focus:ring-1 ring-blue-500 outline-none"/>}
                    <span className="text-[10px] text-gray-400">{t.kmh}</span>
                    <input type="color" value={item.color} onChange={(e) => handleColorChange(i, e.target.value)} className="w-6 h-6 rounded cursor-pointer border-none bg-transparent"/>
                    <button onClick={() => removeRange(i)} disabled={i===0} className={`ml-auto ${i===0?'text-gray-200 cursor-not-allowed':'text-gray-300 hover:text-red-500'}`}><Trash2 size={14}/></button>
                  </div>
                );
              })}
              <button onClick={addRange} className="w-full py-2 mt-2 border border-dashed border-blue-300 rounded text-xs font-bold text-blue-500 hover:bg-blue-50 flex justify-center items-center gap-1 transition-colors"><Plus size={14}/> {t.addRange}</button>
            </div>
            <div className="p-3 border-t border-gray-100 flex justify-end bg-gray-50"><button onClick={() => setShowLegend(false)} className="px-4 py-1.5 bg-blue-600 text-white text-xs font-bold rounded hover:bg-blue-700 shadow-sm">{t.done}</button></div>
          </div>
        </div>
      )}

      {showSuccess && <UploadSuccessModal onClose={() => setShowSuccess(false)} t={t} />}
    </div>
  );
};

// --- Main App ---
export default function App() {
  const [lang, setLang] = useState<Lang>('ja');
  const t = TEXTS[lang];
  const [state, setState] = useState<AppState>({
    probeFiles: [], linkFiles: [],
    dateRange: { start: new Date().toISOString().split('T')[0], end: new Date().toISOString().split('T')[0] },
    timeRange: { start: '00:00', end: '23:00' }, pitch: 60, routeGeometry: null, analysisResult: null, isAnalyzing: false
  });
  const [activeTab, setActiveTab] = useState<'map' | 'result'>('map');
  const [viewState, setViewState] = useState({ longitude: 139.767, latitude: 35.681, zoom: 10 });
  const [mapPoints, setMapPoints] = useState<[number, number][]>([]);
  const [baseMap, setBaseMap] = useState<'osm' | 'gsi'>('osm');
  const [searchText, setSearchText] = useState("");
  const [isMatching, setIsMatching] = useState(false); // マッチング中フラグ

  // 地図クリック: 地点を追加するだけ（経路計算はしない）
  const handleMapClick = (e: any) => {
    const { lng, lat } = e.lngLat;
    const newPoints = [...mapPoints, [lng, lat] as [number, number]];
    setMapPoints(newPoints);

    // 2点以上あれば、確認用の直線（プレビュー）を表示
    if (newPoints.length >= 2) {
      setState(p => ({
        ...p,
        routeGeometry: {
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: newPoints
          }
        }
      }));
    }
  };

  // ボタン押下: マップマッチング実行
  const handleRouteMatch = async () => {
    if (mapPoints.length < 2) return alert("2点以上指定してください");

    setIsMatching(true);
    console.log("Requesting map match for points:", mapPoints);

    try {
      const res = await axios.post('http://localhost:8000/map-match', mapPoints);
      console.log("Map match response:", res.data);

      if (res.data?.geometry) {
        // Valhallaの結果（マッチング済みのLineString）で上書き
        setState(p => ({ ...p, routeGeometry: { type: 'Feature', geometry: res.data.geometry } }));
      } else if (res.data?.fallback) {
        // フォールバック時
         console.warn("Map match fallback used.");
         alert(res.data?.properties?.matched === false ? "ルート探索に失敗したため、直線で表示します。(Valhalla Error)" : "ルートが見つかりませんでした");
      }
    } catch (error: any) {
      console.error("Match error", error);
      const errMsg = error.response?.data?.detail || "通信エラーが発生しました";
      alert(`マップマッチング失敗: ${errMsg}`);
    } finally {
      setIsMatching(false);
    }
  };

  const handleResetRoute = () => {
    setMapPoints([]);
    setState(p => ({ ...p, routeGeometry: null }));
  };

  const handleAnalyze = async (legend: LegendItem[]) => {
    if (state.probeFiles.length === 0) return alert("Please select files.");
    setState(p => ({ ...p, isAnalyzing: true }));
    try {
      const res = await axios.post('http://localhost:8000/analyze', {
        probe_data_paths: state.probeFiles, link_data_paths: state.linkFiles,
        start_date: state.dateRange.start, end_date: state.dateRange.end,
        start_time: state.timeRange.start, end_time: state.timeRange.end,
        time_pitch: state.pitch, route_geometry: state.routeGeometry?.geometry,
        speed_legend: legend
      });
      if (res.data?.results) {
        setState(p => ({ ...p, analysisResult: { htmlUrl: `http://localhost:8000${res.data.results.html_url}` } }));
        setActiveTab('result');
      }
    } catch (e: any) { alert(`Error: ${e.response?.data?.detail}`); }
    finally { setState(p => ({ ...p, isAnalyzing: false })); }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchText) return;

    try {
        const res = await axios.get(`https://nominatim.openstreetmap.org/search`, {
            params: { q: searchText, format: 'json', limit: 1 }
        });
        if (res.data && res.data.length > 0) {
            const { lat, lon } = res.data[0];
            setViewState(p => ({ ...p, latitude: parseFloat(lat), longitude: parseFloat(lon), zoom: 13 }));
        } else {
            alert("場所が見つかりませんでした");
        }
    } catch (e) {
        console.error("Search failed", e);
    }
  };

  return (
    <div className="flex w-screen h-screen bg-gray-50 font-sans overflow-hidden">
      <aside className="w-16 flex-shrink-0 bg-[#1e1e24] text-white flex flex-col items-center py-6 shadow-2xl z-20">
        <div className="mb-8 p-2 bg-blue-600 rounded-xl shadow-lg shadow-blue-900/50 text-white"><LayoutDashboard size={24} /></div>
        <nav className="flex-1 space-y-4 w-full flex flex-col items-center px-2">
          <button onClick={() => setActiveTab('map')} className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all relative group ${activeTab === 'map' ? 'bg-blue-600 text-white shadow-md' : 'bg-transparent text-gray-400 hover:bg-white/10 hover:text-white'}`}><MapIcon size={20} /><span className="absolute left-12 bg-gray-900 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-30 shadow-lg border border-gray-700">{t.mapView}</span></button>
          <button onClick={() => setActiveTab('result')} className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all relative group ${activeTab === 'result' ? 'bg-blue-600 text-white shadow-md' : 'bg-transparent text-gray-400 hover:bg-white/10 hover:text-white'}`}><BarChart3 size={20} /><span className="absolute left-12 bg-gray-900 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-30 shadow-lg border border-gray-700">{t.results}</span></button>
        </nav>
        <div className="pb-4"><button onClick={() => setLang(l => l==='en'?'ja':'en')} className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-white transition-colors font-bold text-xs rounded-full hover:bg-white/10"><Globe size={18}/></button></div>
      </aside>
      <ControlPanel state={state} setState={setState} onAnalyze={handleAnalyze} lang={lang} />
      <main className="flex-1 relative bg-[#f3f4f6] flex flex-col overflow-hidden">
        <header className="h-14 bg-white border-b border-gray-200 px-6 flex items-center justify-end flex-shrink-0 z-10 shadow-sm">
          <form onSubmit={handleSearch} className="flex items-center gap-4">
            <div className="bg-gray-50 px-3 py-1.5 rounded-full flex items-center gap-2 border border-gray-200 focus-within:ring-2 ring-blue-100 transition-all w-64"><Search size={14} className="text-gray-400"/><input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder={t.search} className="bg-transparent text-xs outline-none w-full text-gray-600 placeholder-gray-400"/></div>
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center text-xs font-bold text-white shadow-md border-2 border-white cursor-pointer">U</div>
          </form>
        </header>
        <div className="flex-1 relative w-full h-full">
          {activeTab === 'map' && (
            <div className="w-full h-full relative">
              <div className="absolute top-4 right-4 z-10 flex gap-2">
                <div className="bg-white/95 backdrop-blur shadow-md border border-gray-200 p-1 rounded-lg flex text-xs">
                  <button onClick={() => setBaseMap('osm')} className={`px-3 py-1.5 rounded-md font-medium transition-colors ${baseMap==='osm'?'bg-blue-600 text-white shadow-sm':'text-gray-600 hover:bg-gray-100'}`}>OSM</button>
                  <button onClick={() => setBaseMap('gsi')} className={`px-3 py-1.5 rounded-md font-medium transition-colors ${baseMap==='gsi'?'bg-blue-600 text-white shadow-sm':'text-gray-600 hover:bg-gray-100'}`}>GSI</button>
                </div>

                {/* Route Controls */}
                <div className="flex gap-2">
                    <button
                        onClick={handleRouteMatch}
                        disabled={isMatching || mapPoints.length < 2}
                        className="bg-blue-600 text-white px-4 py-1.5 rounded-lg shadow-md text-xs font-bold hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-1"
                    >
                        {isMatching ? <Loader2 size={12} className="animate-spin"/> : <RouteIcon size={12}/>}
                        {isMatching ? t.matching : t.matchRoute}
                    </button>
                    <button onClick={handleResetRoute} className="bg-white/95 backdrop-blur px-4 py-1.5 rounded-lg shadow-md border border-gray-200 text-xs font-bold text-red-500 hover:bg-red-50 transition-colors">{t.resetRoute}</button>
                </div>
              </div>
              <Map {...viewState} onMove={e => setViewState(e.viewState)} style={{ width: '100%', height: '100%' }} mapStyle={baseMap === 'osm' ? { version: 8, sources: { osm: { type: 'raster', tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256 } }, layers: [{ id: 'osm', type: 'raster', source: 'osm' }] } : { version: 8, sources: { gsi: { type: 'raster', tiles: ['https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'], tileSize: 256 } }, layers: [{ id: 'gsi', type: 'raster', source: 'gsi' }] }} mapLib={maplibregl} onClick={handleMapClick} cursor={mapPoints.length < 2 ? 'crosshair' : 'grab'}>
                <NavigationControl position="bottom-right" />
                {state.routeGeometry && <Source id="route" type="geojson" data={state.routeGeometry}><Layer id="route-bg" type="line" paint={{ 'line-color': '#ffffff', 'line-width': 8, 'line-opacity': 0.8 }} /><Layer id="route-fg" type="line" paint={{ 'line-color': '#3b82f6', 'line-width': 5, 'line-opacity': 0.9 }} /></Source>}
                {mapPoints.map((p, i) => (<Marker key={i} longitude={p[0]} latitude={p[1]} anchor="bottom"><div className="relative group cursor-pointer"><MapPin size={36} className={`drop-shadow-md ${i===0?"text-emerald-500":i===mapPoints.length-1?"text-rose-500":"text-blue-500"}`} fill="white" /><span className="absolute -top-8 left-1/2 -translate-x-1/2 bg-gray-900 text-white px-2 py-1 rounded text-[10px] font-bold shadow-lg whitespace-nowrap z-50">{i===0?"Start":i===mapPoints.length-1?"End":`Via ${i}`}</span></div></Marker>))}
              </Map>
            </div>
          )}
          {activeTab === 'result' && (
            <div className="w-full h-full p-0 flex flex-col">
              {state.analysisResult ? <iframe src={state.analysisResult.htmlUrl} className="w-full h-full border-none bg-gray-100" title="Result"/> : <div className="w-full h-full flex flex-col items-center justify-center text-gray-300 bg-white"><div className="p-6 bg-gray-50 rounded-full shadow-sm mb-4"><BarChart3 size={48} className="text-gray-300"/></div><p className="font-bold text-lg text-gray-400">{t.noResult}</p></div>}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
