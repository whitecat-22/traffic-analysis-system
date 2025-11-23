import React from 'react';
import { Download, ExternalLink } from 'lucide-react';

interface Props {
  resultUrl?: string;
}

const MosaicViewer: React.FC<Props> = ({ resultUrl }) => {
  if (!resultUrl) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-gray-400 bg-gray-50">
        <div className="w-16 h-16 border-4 border-gray-200 border-t-gray-300 rounded-full animate-pulse mb-4"></div>
        <p>分析を実行するとここに結果が表示されます</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col">
      {/* Toolbar */}
      <div className="h-12 bg-white border-b flex items-center justify-between px-4 shadow-sm z-10">
        <h3 className="font-semibold text-gray-700">Analysis Report</h3>
        <div className="flex gap-2">
          <a
            href={resultUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
          >
            <ExternalLink size={16} /> 新しいタブで開く
          </a>
          <button className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-600 text-white hover:bg-blue-700 rounded-md transition-colors shadow-sm">
            <Download size={16} /> PNG保存
          </button>
        </div>
      </div>

      {/* Iframe Container for Plotly HTML */}
      <div className="flex-1 bg-gray-100 relative overflow-hidden">
        <iframe
          src={resultUrl}
          className="w-full h-full border-none"
          title="Mosaic Plot"
        />
      </div>
    </div>
  );
};

export default MosaicViewer;
