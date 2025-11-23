// 型定義を一箇所にまとめることで、App.tsxとControlPanel.tsxの間の循環参照を防ぎます

export interface LegendItem {
  speed: number;
  color: string;
}

export interface AppState {
  selectedProbeFile: string;
  selectedLinkFile: string;
  dateRange: { start: Date; end: Date };
  timeRange: { start: string; end: string };
  pitch: number;
  routeGeometry: any | null; // GeoJSON
  analysisResult: { htmlUrl: string } | null;
  isAnalyzing: boolean;
}
