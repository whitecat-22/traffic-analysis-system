import React, { useEffect, useState } from 'react';
import { Calendar, FileText, Play, Loader2, Upload, Settings2, Plus, Trash2, X } from 'lucide-react';
import type { AppState, LegendItem } from '../types'; // 型定義をtypes.tsからインポート
 // 型定義をtypes.tsからインポート
import axios from 'axios';

interface Props {
  state: AppState;
  setState: React.Dispatch<React.SetStateAction<AppState>>;
  onAnalyzeComplete: () => void;
}

const ControlPanel: React.FC<Props> = ({ state, setState, onAnalyzeComplete }) => {
  // ガード処理: 親コンポーネントのレンダリング都合でstateが空の場合は描画しない
  if (!state) return null;

  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const [showLegendModal, setShowLegendModal] = useState(false);
  const [legendSettings, setLegendSettings] = useState<LegendItem[]>([
    { speed: 10, color: '#ff0000' },
    { speed: 20, color: '#ff4500' },
    { speed: 40, color: '#ffff00' },
    { speed: 60, color: '#00ff00' },
    { speed: 80, color: '#0000ff' },
  ]);

  const fetchFiles = async () => {
    try {
      const res = await axios.get('http://localhost:8000/files');
      if (res.data && Array.isArray(res.data.files)) {
        setAvailableFiles(res.data.files);
      }
    } catch (e) {
      console.error("Failed to fetch files", e);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;

    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);

    setIsUploading(true);
    try {
      await axios.post('http://localhost:8000/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      await fetchFiles();
      setState(prev => ({ ...prev, selectedProbeFile: file.name }));
      alert("アップロード完了");
    } catch (error) {
      console.error("Upload failed", error);
      alert("アップロードに失敗しました");
    } finally {
      setIsUploading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!state.selectedProbeFile) {
      alert("データファイルを選択してください（アップロードが必要です）");
      return;
    }

    setState(prev => ({ ...prev, isAnalyzing: true }));

    try {
      const response = await axios.post('http://localhost:8000/analyze', {
        probe_data_path: state.selectedProbeFile,
        link_data_path: state.selectedLinkFile,
        start_date: state.dateRange.start.toISOString(),
        end_date: state.dateRange.end.toISOString(),
        start_time: state.timeRange.start,
        end_time: state.timeRange.end,
        time_pitch: state.pitch,
        route_geometry: state.routeGeometry,
        speed_legend: legendSettings
      });

      if (response.data.status === 'success') {
        setState(prev => ({
          ...prev,
          analysisResult: { htmlUrl: `http://localhost:8000${response.data.results.html_url}` }
        }));
        onAnalyzeComplete();
      }
    } catch (error: any) {
      console.error("Analysis failed", error);
      const msg = error.response?.data?.detail || "分析処理に失敗しました";
      alert(`エラー: ${msg}`);
    } finally {
      setState(prev => ({ ...prev, isAnalyzing: false }));
    }
  };

  const updateLegend = (index: number, field: keyof LegendItem, value: any) => {
    const newSettings = [...legendSettings];
    newSettings[index] = { ...newSettings[index], [field]: value };
    newSettings.sort((a, b) => a.speed - b.speed);
    setLegendSettings(newSettings);
  };

  const addLegend = () => {
    setLegendSettings(prev => [...prev, { speed: 100, color: '#000000' }].sort((a, b) => a.speed - b.speed));
  };

  const removeLegend = (index: number) => {
    setLegendSettings(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="p-6 space-y-8 relative">
      <header>
        <h1 className="text-2xl font-bold text-slate-800">Traffic Analysis</h1>
        <p className="text-sm text-slate-500 mt-1">交通流モザイク図作成ツール</p>
      </header>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
          <FileText size={16} /> Data Source
        </h2>

        <div className="space-y-3">
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center hover:bg-gray-50 transition-colors relative">
            <input
                type="file"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={handleFileUpload}
                accept=".geojson,.json,.csv"
            />
            <div className="flex flex-col items-center justify-center text-gray-500">
                {isUploading ? <Loader2 className="animate-spin mb-2" /> : <Upload className="mb-2" />}
                <span className="text-xs font-medium">ドラッグ＆ドロップ または クリックしてアップロード</span>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">プローブデータを選択</label>
            <select
              className="w-full border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
              value={state.selectedProbeFile}
              onChange={(e) => setState(prev => ({ ...prev, selectedProbeFile: e.target.value }))}
            >
              <option value="">選択してください</option>
              {availableFiles.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">道路リンクデータ (DRM/OSM)</label>
            <select
              className="w-full border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
              value={state.selectedLinkFile}
              onChange={(e) => setState(prev => ({ ...prev, selectedLinkFile: e.target.value }))}
            >
              <option value="">選択してください</option>
              {availableFiles.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
        </div>
      </section>

      <hr className="border-gray-100" />

      <section>
        <button
          onClick={() => setShowLegendModal(true)}
          className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium"
        >
          <Settings2 size={14} /> 凡例設定（速度・色）を変更
        </button>
      </section>

      <hr className="border-gray-100" />

      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
          <Calendar size={16} /> Period & Time
        </h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">日付</label>
            <input type="date" className="w-full border p-2 rounded-md text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">集計ピッチ</label>
            <div className="flex rounded-md shadow-sm" role="group">
                {[15, 30, 60].map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setState(prev => ({ ...prev, pitch: p }))}
                    className={`px-3 py-1.5 text-xs font-medium border ${
                      state.pitch === p
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    } ${p === 15 ? 'rounded-l-md' : ''} ${p === 60 ? 'rounded-r-md' : ''}`}
                  >
                    {p}{t.minutes}
                  </button>
                ))}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">開始時刻</label>
            <input
              type="time"
              value={state.timeRange.start}
              onChange={(e) => setState(prev => ({...prev, timeRange: {...prev.timeRange, start: e.target.value}}))}
              className="w-full border p-2 rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">終了時刻</label>
            <input
              type="time"
              value={state.timeRange.end}
              onChange={(e) => setState(prev => ({...prev, timeRange: {...prev.timeRange, end: e.target.value}}))}
              className="w-full border p-2 rounded-md text-sm"
            />
          </div>
        </div>
      </section>

      <div className="pt-4">
        <button
          onClick={handleAnalyze}
          disabled={state.isAnalyzing}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-xl shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {state.isAnalyzing ? (
            <>
              <Loader2 className="animate-spin" size={20} />
              Processing...
            </>
          ) : (
            <>
              <Play size={20} fill="currentColor" />
              Run Analysis
            </>
          )}
        </button>
      </div>

      {/* Legend Modal Overlay */}
      {showLegendModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-96 p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">凡例設定 (速度範囲)</h3>
              <button onClick={() => setShowLegendModal(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="space-y-3">
              <p className="text-xs text-gray-500">※設定した速度以下の範囲に色が適用されます</p>
              {legendSettings.map((item, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    type="number"
                    value={item.speed}
                    onChange={(e) => updateLegend(idx, 'speed', parseInt(e.target.value))}
                    className="w-20 border p-1 rounded text-sm"
                  />
                  <span className="text-sm text-gray-600">km/h以下</span>
                  <input
                    type="color"
                    value={item.color}
                    onChange={(e) => updateLegend(idx, 'color', e.target.value)}
                    className="w-10 h-8 p-0 border rounded cursor-pointer"
                  />
                  <button onClick={() => removeLegend(idx)} className="text-red-400 hover:text-red-600">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              <button
                onClick={addLegend}
                className="w-full py-2 mt-2 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:bg-gray-50 flex items-center justify-center gap-1 text-sm"
              >
                <Plus size={16} /> 追加
              </button>
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setShowLegendModal(false)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              >
                完了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ControlPanel;
