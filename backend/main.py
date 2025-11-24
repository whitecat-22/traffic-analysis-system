import os
import json
import requests
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import re
from dotenv import load_dotenv

# .envファイルの読み込み
load_dotenv()

# ロジックモジュールのインポート
from logic import run_mosaic_analysis

app = FastAPI(title="Traffic Analysis System")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ディレクトリ設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Valhalla設定
# デフォルトは route API を指すようにする
VALHALLA_API_URL = os.getenv("VALHALLA_URL", "http://localhost:8002/route")

# I/O処理用のスレッドプール
executor = ThreadPoolExecutor(max_workers=4)

# --- Models ---
class LegendItem(BaseModel):
    speed: int
    color: str

class AnalysisRequest(BaseModel):
    probe_data_paths: List[str]
    link_data_paths: List[str]
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    time_pitch: int
    route_geometry: Optional[Dict] = None
    speed_legend: Optional[List[Dict]] = None
    direction: str = "LtoR"

# --- Helper Functions ---

def save_bytes_sync(file_path: str, content: bytes):
    """バイトデータを同期的にファイルに書き込む"""
    with open(file_path, "wb") as f:
        f.write(content)

def run_analysis_sync(input_dir, output_dir, target_files, config):
    """解析ロジックを同期的に実行するラッパー"""
    return run_mosaic_analysis(input_dir, output_dir, target_files, config)

def decode_polyline(polyline_str):
    """ValhallaのPolyline (6桁精度) をデコードして [[lon, lat], ...] に変換"""
    index, lat, lng = 0, 0, 0
    coordinates = []
    length = len(polyline_str)
    factor = 1000000.0

    while index < length:
        b, shift, result = 0, 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append([lng / factor, lat / factor])

    return coordinates

# --- Endpoints ---

@app.get("/files")
def list_files():
    try:
        files = [f for f in os.listdir(INPUT_DIR) if f.endswith(('.json', '.geojson', '.csv'))]
        return {"files": files}
    except Exception as e:
        print(f"[API Error] list_files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """複数ファイルの一括アップロード"""
    print(f"[API] Upload request received. Count: {len(files)}")
    saved_files = []
    loop = asyncio.get_running_loop()

    try:
        total_start = time.time()
        for file in files:
            start_time = time.time()
            file_path = os.path.join(INPUT_DIR, file.filename)
            print(f"[API] Processing file: {file.filename} ...")

            content = await file.read()
            await loop.run_in_executor(executor, save_bytes_sync, file_path, content)

            elapsed = time.time() - start_time
            size_kb = len(content) / 1024
            print(f"[API] Saved: {file.filename} ({size_kb:.1f} KB) in {elapsed:.2f}s")
            saved_files.append(file.filename)

        return {"message": "Upload successful", "files": saved_files}

    except Exception as e:
        print(f"[API Error] Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for file in files:
            await file.close()

@app.post("/map-match")
async def map_match(points: List[List[float]] = Body(...)):
    """
    地図上の点列をつなぐルートを探索する (/route APIを使用)
    ※ フロントエンドの「マップマッチング実行」ボタンから呼ばれますが、
      クリック点をつなぐルート探索として実装します。
    """
    if len(points) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 points")

    print(f"\n[API] === Route Calculation Start ===")
    print(f"[API] Request points: {len(points)}")

    # 1. エンドポイント: /route を使用
    # 環境変数 VALHALLA_URL が .../trace_route になっていても .../route に補正
    base_url = VALHALLA_API_URL.rsplit("/", 1)[0]
    route_url = f"{base_url}/route"

    # 2. パラメータ構築 (/route 用)
    # locations: 経由地のリスト
    # type: "break" (確実に止まる点) として指定
    locations = []
    for p in points:
        locations.append({
            "lon": p[0],
            "lat": p[1],
            "type": "break",
            "radius": 50,  # 検索半径を拡大して主要道路を拾いやすくする
            "street_side_tolerance": 50  # 道路からの距離許容値を拡大
        })

    payload = {
        "locations": locations,
        "costing": "auto",
        "units": "kilometers",
        "language": "ja-JP",
        # 道路種別(0->1->2...)を優先し、ループを回避するための設定
        "costing_options": {
            "auto": {
                # 右左折に対するペナルティを増やし、直進性の高い主要道路を優先
                "maneuver_penalty": 35,
                # 路地や私道の利用を制限
                "include_private": False,
                "include_alleys": False,
                "include_driveways": True,
                # 生活道路の利用頻度を下げる
                "use_living_streets": 0.1,
                # サービスロードへのペナルティ
                "service_penalty": 15,
                # 検索半径
                "search_radius": 50
            }
        }
    }

    try:
        print(f"[API] Payload: {json.dumps(payload)}")
    except:
        pass

    loop = asyncio.get_running_loop()

    def call_valhalla():
        # 同期リクエスト
        return requests.post(route_url, json=payload, timeout=15.0)

    try:
        resp = await loop.run_in_executor(executor, call_valhalla)
        print(f"[API] Valhalla Status Code: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            coords = []

            # /route のレスポンス解析: trip -> legs -> shape
            if "trip" in data and "legs" in data["trip"]:
                legs = data["trip"]["legs"]
                print(f"[API] Found {len(legs)} legs.")

                for i, leg in enumerate(legs):
                    shape = leg.get("shape")
                    if isinstance(shape, str):
                        # ポリライン文字列をデコード
                        decoded = decode_polyline(shape)
                        coords.extend(decoded)
                    else:
                        print(f"[API Warning] Leg {i}: Shape is not a string.")

            if coords:
                print(f"[API] Route found. Total coords: {len(coords)}")
                return {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {"matched": True, "method": "route"}
                }
            else:
                print("[API Warning] No coordinates extracted from Valhalla response.")
        else:
            print(f"[API Error] Valhalla returned error: {resp.text}")
            raise HTTPException(status_code=400, detail=f"Valhalla Error: {resp.text}")

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[API Critical Error] Connection failed: {e}")
        import traceback
        traceback.print_exc()

    # 失敗時のフォールバック（直線）
    print("[API] === Using FALLBACK straight line ===")
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": points},
        "properties": {"matched": False, "fallback": True}
    }

@app.post("/analyze")
async def analyze(req: AnalysisRequest):
    """解析実行"""
    loop = asyncio.get_running_loop()
    try:
        print(f"[API] Starting analysis.")
        start_time = time.time()

        result = await loop.run_in_executor(
            executor,
            run_analysis_sync,
            INPUT_DIR,
            OUTPUT_DIR,
            req.probe_data_paths,
            req.dict()
        )

        if result is None:
            raise HTTPException(status_code=404, detail="No valid data found matching the route direction.")

        elapsed = time.time() - start_time
        print(f"[API] Analysis completed in {elapsed:.2f}s")
        return {"status": "success", "results": result}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API Error] Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/results/{filename}")
def get_result_file(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="File not found")

# --- Map Style Proxy & Caching ---

STYLE_CACHE = {}
MAPTILER_KEY = os.getenv("MAPTILER_KEY", "")

def hex_to_gray(hex_str: str) -> str:
    """#RRGGBB をグレースケール #XXXXXX に変換"""
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = "".join([c*2 for c in hex_str])

    if len(hex_str) != 6:
        return "#808080"

    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)

    # 輝度計算
    y = int(0.299 * r + 0.587 * g + 0.114 * b)
    gray = f"{y:02x}"
    return f"#{gray}{gray}{gray}"

def convert_style_to_gray(style_json: dict) -> dict:
    """スタイルJSON内の色定義をグレースケールに置換"""
    style_str = json.dumps(style_json)

    # 正規表現でカラーコードを検出して置換
    # #RRGGBB または #RGB
    def replacer(match):
        color = match.group(0) # "#RRGGBB" (with quotes)
        raw_hex = color.strip('"')
        return f'"{hex_to_gray(raw_hex)}"'

    # 単純なカラーコード置換
    # 注意: 文字列中のカラーコードらしきものも置換してしまうが、スタイル定義上は概ね問題ない
    new_style_str = re.sub(r'"#(?:[0-9a-fA-F]{3}){1,2}"', replacer, style_str)

    return json.loads(new_style_str)

@app.get("/map-style/{style_type}")
def get_map_style(style_type: str):
    """
    地図スタイルをプロキシ取得し、グレースケール化して返す。
    style_type: 'osm' | 'gsi'
    """
    if style_type in STYLE_CACHE:
        return STYLE_CACHE[style_type]

    url = ""
    needs_gray_conversion = False

    if style_type == "osm":
        # MIERUNE Gray (MapTiler)
        # 既にグレーだが、APIキー隠蔽のためにプロキシする
        # もしカラー版を使うなら needs_gray_conversion = True にする
        if not MAPTILER_KEY:
            # キーがない場合はエラーを返すか、フォールバックする
            print("[API Warning] MAPTILER_KEY is not set.")
            raise HTTPException(status_code=500, detail="MapTiler API Key is missing on server.")

        url = f"https://api.maptiler.com/maps/jp-mierune-gray/style.json?key={MAPTILER_KEY}"
        # MIERUNE Grayは元々グレーなので変換不要だが、
        # 完全に彩度を落としたい場合は True にしてもよい
        needs_gray_conversion = False

    elif style_type == "gsi":
        # 地理院地図 淡色
        url = "https://gsi-cyberjapan.github.io/gsivectortile-mapbox-gl-js/pale.json"
        needs_gray_conversion = True

    else:
        raise HTTPException(status_code=400, detail="Unknown style type")

    try:
        # ログ出力時にAPIキーを隠蔽
        safe_url = re.sub(r'key=[^&]+', 'key=***', url)
        print(f"[API] Fetching map style: {safe_url}")

        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch upstream map style")

        data = resp.json()

        if needs_gray_conversion:
            data = convert_style_to_gray(data)

        # キャッシュに保存
        STYLE_CACHE[style_type] = data
        return data

    except Exception as e:
        print(f"[API Error] Map style fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug/inspect-geojson")
def debug_inspect_geojson():
    import glob
    files = glob.glob(os.path.join(INPUT_DIR, "*.geojson"))
    if not files:
        return {"error": "No geojson files found"}

    try:
        with open(files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'features' in data and len(data['features']) > 0:
                return data['features'][0].get('properties', {})
        return {"error": "No features found"}
    except Exception as e:
        return {"error": str(e)}
