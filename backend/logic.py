import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from shapely.geometry import shape, Point, LineString
import re

# --- 1. 定数と設定 (mosaic.py準拠) ---
FONT_FAMILY = "Noto Sans CJK JP"

# 渋滞判定しきい値 (km/h)
SPEED_THRESHOLD_LOCAL = 20
SPEED_THRESHOLD_MOTORWAY = 40
BNAQ_INTERVAL_M = 100  # リサンプリング間隔(m)

# 色スケール定義 (mosaic.pyより)
_colors = [
    "rgb(255, 0, 0)",       # 00-10: Red
    "rgb(255, 69, 0)",      # 10-20: Red-Orange
    "rgb(255, 165, 0)",     # 20-30: Orange
    "rgb(255, 255, 0)",     # 30-40: Yellow
    "rgb(154, 205, 50)",    # 40-50: Yellow-Green
    "rgb(0, 128, 0)",       # 50-60: Green
    "rgb(0, 255, 255)",     # 60-70: Cyan
    "rgb(0, 0, 139)"        # 70-80: DarkBlue
]

SPEED_COLORS_DISCRETE = [
    [0.000, _colors[0]], [0.125, _colors[0]],
    [0.125, _colors[1]], [0.250, _colors[1]],
    [0.250, _colors[2]], [0.375, _colors[2]],
    [0.375, _colors[3]], [0.500, _colors[3]],
    [0.500, _colors[4]], [0.625, _colors[4]],
    [0.625, _colors[5]], [0.750, _colors[5]],
    [0.750, _colors[6]], [0.875, _colors[6]],
    [0.875, _colors[7]], [1.000, _colors[7]]
]

BN_COLORS = [
    [0.0, "rgb(255, 255, 255)"],
    [0.0001, "rgb(255, 255, 0)"],
    [0.25, "rgb(255, 255, 0)"],
    [0.2501, "rgb(255, 165, 0)"],
    [0.50, "rgb(255, 165, 0)"],
    [0.5001, "rgb(255, 0, 0)"],
    [0.75, "rgb(255, 0, 0)"],
    [0.7501, "rgb(139, 0, 0)"],
    [1.0, "rgb(139, 0, 0)"]
]

AQ_COLORS = [
    [0.0, "rgb(255, 255, 255)"],
    [0.0001, "rgb(193, 201, 212)"],
    [0.25, "rgb(193, 201, 212)"],
    [0.2501, "rgb(132, 147, 169)"],
    [0.50, "rgb(132, 147, 169)"],
    [0.5001, "rgb(70, 93, 125)"],
    [0.75, "rgb(70, 93, 125)"],
    [0.7501, "rgb(8, 39, 82)"],
    [1.0, "rgb(8, 39, 82)"]
]


# --- 2. データ解析ロジック ---

def process_geojson_files(probe_paths, route_geometry=None):
    # --- 1. Load & Merge GeoJSONs ---
    # route_geometryがある場合は、それに基づいてリンクをソートする

    all_features = []
    for path in probe_paths:
        if not os.path.exists(path): continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'features' in data:
                all_features.extend(data['features'])

    if not all_features:
        raise ValueError("No features found in probe data.")

    # ルート形状が指定されている場合、それに沿ってソート
    if route_geometry:
        try:
            route_line = shape(route_geometry)
            # 各リンクの重心をルート上に投影し、その距離でソート
            # 同時に、ルートからの距離が遠すぎるリンクを除外することも可能（今回はソートのみ）

            def get_proj_dist(feat):
                geom = shape(feat['geometry'])
                return route_line.project(geom.centroid)

            # ソート実行
            all_features.sort(key=get_proj_dist)
            print(f"Sorted {len(all_features)} features along the route.")

            # TODO: 方向判定（逆走データの除外など）はここに追加可能
            # 現状は「指定ルートに近い順」に並べることで、Start->Endの順序を保証する

        except Exception as e:
            print(f"Error sorting features by route: {e}")
            # エラー時はそのまま（元の順序）

    # --- 2. Extract Data for Mosaic ---
    # 距離の積み上げ計算
    # ソート済みであることを前提に、各リンクの長さを足していく

    x_bounds = [0.0]
    current_dist = 0.0

    # データを格納するリスト
    spd_list = []
    bn_list = []
    aq_list = []

    # 時間帯ごとのデータを保持するための構造
    # TomTomデータは通常、1つのFeature内に複数の時間帯データを持つか、
    # あるいは時間帯ごとにFeatureが分かれているかによる。
    # ここでは「各Featureが特定の区間を表し、その中に時系列データがある」または
    # 「Feature自体は区間形状のみで、データは別」のパターンがあるが、
    # 前回のinspect結果から、featuresの中身は未確認。
    #   もしfeatures[i].propertiesに時系列データが入っているならそれを展開する。

    # 仮定: 各Featureは「ある区間」のデータであり、propertiesに平均速度などが入っている
    # もし時系列データ（24時間分）を作るなら、各Featureから24時間分のデータを抽出する必要がある。

    # ここでは既存のロジック（単純なリスト作成）を、ソートされたfeatureに対して行う形に修正する。
    # ただし、モザイク図は「縦軸：時間、横軸：距離」なので、
    # 各距離区間（Feature）ごとに、24時間分のデータが必要。

    # 既存コードのデータ抽出ロジックを尊重しつつ、ソート順序を適用する。

    # 抽出用ヘルパー
    def extract_hourly_data(feat):
        # プロパティから時間ごとの速度などを取得するロジック
        # ※ 実際のデータ構造に合わせて調整が必要
        # ここでは仮に properties['averageSpeed'] などを参照しているが、
        # 実際には `timeSets` や `summaries` との紐付けが必要かもしれない。
        # いったん、既存のロジックがどうなっていたかを確認し、それに合わせる。
        props = feat.get('properties', {})

        # ダミーロジック: もし詳細な時系列キーがない場合、単一値を全時間に適用（仮）
        # 実際にはTomTomデータに応じたパースが必要
        spd = props.get('averageSpeed', 0)
        bn = props.get('bnIndex', 0) # 仮
        aq = props.get('jamFactor', 0) # 仮

        # 24時間分（または指定ピッチ分）の配列を返す
        # ここでは簡易的に単一値を返す（後で展開）
        return spd, bn, aq

    # 既存の実装を見ると、`df` を使ってピボットしていた。
    # したがって、まずは全FeatureからDataFrameを作成する。

    rows = []
    for i, feat in enumerate(all_features):
        props = feat.get('properties', {})
        geom = shape(feat['geometry'])
        link_len_km = geom.length * 111.32 # 簡易換算 (度->km) または props['length']
        if 'length' in props:
            link_len_km = props['length'] / 1000.0

        # 始点からの距離（ソート済みなので積み上げ）
        start_dist = current_dist
        end_dist = current_dist + link_len_km
        current_dist = end_dist

        x_bounds.append(end_dist)

        # 時系列データの抽出
        # TomTom GeoJSONの構造に依存。
        # inspect結果の `timeSets` などがトップレベルにあったことから、
        # Feature側には `segmentId` などがあり、それと紐付いている可能性がある。
        # しかし、ここでは「Feature内にデータがある」と仮定して進める（既存ロジック踏襲）。

        # もし既存ロジックが `pd.read_json` で一括読み込みしていたなら、
        # それを `all_features` (ソート済み) から再構築する必要がある。

        rows.append(props)

    df = pd.DataFrame(rows)

    # --- 以下、既存のデータフレーム処理ロジックへ続く ---
    # ただし、x_bounds はここで計算したものを使う必要がある。

    # Placeholder for the rest of the logic that would use df and x_bounds
    # This function would typically return df_l, df_s, df_t, and x_bounds
    # For now, returning dummy values to make it syntactically correct.
    return None, None, None, x_bounds


def parse_single_geojson(filepath, route_geometry=None, sort_by_route=False):
    print(f"[Logic] Parsing: {os.path.basename(filepath)}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Logic Error] {e}")
        return None, None, None

    if "features" not in data or not data["features"]:
        return None, None, None

    # --- Sort & Filter Features by Route Geometry ---
    feats = [f for f in data["features"] if f.get("geometry") and f["geometry"]["type"] == "LineString"]

    if route_geometry:
        try:
            route_line = shape(route_geometry)

            # 方向一致率のチェック
            forward_count = 0
            total_checked = 0

            valid_feats_with_dist = []

            for feat in feats:
                geom = shape(feat['geometry'])
                coords = list(geom.coords)
                if len(coords) < 2: continue

                d_start = route_line.project(Point(coords[0]))
                d_end = route_line.project(Point(coords[-1]))

                if d_end > d_start:
                    forward_count += 1

                total_checked += 1
                if sort_by_route:
                    valid_feats_with_dist.append((d_start, feat))

            if total_checked > 0:
                match_ratio = forward_count / total_checked
                print(f"[Logic] Direction match ratio: {match_ratio:.2f} ({forward_count}/{total_checked})")

                if match_ratio < 0.5:
                    print(f"[Logic] Skipping {os.path.basename(filepath)}: Direction mismatch (Ratio: {match_ratio:.2f})")
                    return None, None, None

            if sort_by_route:
                # ソート実行 (d_start順)
                valid_feats_with_dist.sort(key=lambda x: x[0])
                feats = [x[1] for x in valid_feats_with_dist]
                print(f"[Logic] Sorted {len(feats)} features by route geometry.")
            else:
                # ソートせず元の順序を維持
                pass

        except Exception as e:
            print(f"Warning: Failed to check/sort direction by route: {e}")

    # --- Extract Time Sets ---
    time_set_map = {}
    try:
        # timeSetsはトップレベルプロパティにある場合と、features[0]にある場合がある
        # inspect結果ではトップレベルのpropertiesにあったが、GeoJSON標準ではトップレベルにpropertiesはない
        # しかしTomTomはトップレベルに置くことがある、あるいはRoot objectの直下

        # まずRoot直下のpropertiesを探す（標準外だが）
        root_props = data.get("properties", {})
        if "timeSets" in root_props:
            print("[Logic] Parsing timeSets from root properties...")
            for ts in root_props["timeSets"]:
                ts_name = ts["name"]
                ts_id = ts["@id"] # 型変換なし

                # 正規表現で HH:MM を抽出 (例: "00:00-01:00" -> "00:00")
                match = re.search(r"(\d{1,2}):(\d{2})", str(ts_name))
                if match:
                    h = int(match.group(1))
                    m = int(match.group(2))
                    time_str = f"{h:02d}:{m:02d}"
                    time_set_map[ts_id] = time_str
                    # print(f"  Mapped timeSet {ts_id} ({ts_name}) -> {time_str}")
                else:
                    print(f"  [Warning] Could not parse time from timeSet name: {ts_name}")

            print(f"[Logic] Parsed {len(time_set_map)} timeSets.")

        # なければfeatures[0]のpropertiesを探す（Metadata Featureの場合があるため data["features"] を見る）
        elif data.get("features") and "properties" in data["features"][0] and "timeSets" in data["features"][0]["properties"]:
            print("[Logic] Parsing timeSets from data['features'][0] properties...")
            metadata = data["features"][0]
            for ts in metadata["properties"]["timeSets"]:
                ts_name = ts["name"]
                ts_id = ts["@id"] # 型変換なし

                match = re.search(r"(\d{1,2}):(\d{2})", str(ts_name))
                if match:
                    h = int(match.group(1))
                    m = int(match.group(2))
                    time_str = f"{h:02d}:{m:02d}"
                    time_set_map[ts_id] = time_str
                else:
                    print(f"  [Warning] Could not parse time from timeSet name: {ts_name}")

            print(f"[Logic] Parsed {len(time_set_map)} timeSets.")

    except Exception as e:
        print(f"[Logic Error] Failed to parse timeSets: {e}")
        return None, None, None

    if not time_set_map:
        # フォールバック: 0-23時
        time_set_map = {i: f"{i:02d}:00" for i in range(24)}

    links_list = []
    speed_dict = {t: {} for t in time_set_map.values()}
    tt_dict = {t: {} for t in time_set_map.values()}

    prev_end_km = 0.0
    lid = 0

    for f in feats:
        try:
            p = f["properties"]
            dist_m = float(p.get("distance", 0))
            # もしdistanceがない場合はgeometryから計算
            if dist_m == 0:
                dist_m = shape(f["geometry"]).length * 111320 # 簡易

            dist_km = dist_m / 1000.0
            frc = int(p.get("frc", -1))

            links_list.append({
                "link_id": lid,
                "link_length_km": dist_km,
                "start_distance_km": prev_end_km,
                "end_distance_km": prev_end_km + dist_km,
                "frc": frc
            })

            # 時系列データの取得
            # segmentTimeResults または summaries を探す
            results = p.get("segmentTimeResults", [])
            # もしsegmentTimeResultsがない場合、summaries（トップレベル）との紐付けが必要だが
            # ここではFeature内にデータがあると仮定（既存ロジック）

            for res in results:
                ts_id = res.get("timeSet") # 型変換なし
                tname = time_set_map.get(ts_id)

                if tname:
                    s = res.get("harmonicAverageSpeed")
                    t = res.get("averageTravelTime")

                    speed_dict[tname][lid] = float(s) if s is not None else np.nan
                    tt_dict[tname][lid] = float(t) if t is not None else np.nan

            prev_end_km += dist_km
            lid += 1
        except:
            continue

    if not links_list: return None, None, None

    df_l = pd.DataFrame(links_list)
    df_s = pd.DataFrame.from_dict(speed_dict, orient="index").sort_index()
    df_t = pd.DataFrame.from_dict(tt_dict, orient="index").sort_index()

    return df_l, df_s, df_t


def calculate_bn_aq_binary(df_links, df_speed, th_local, th_motor):
    is_congested = pd.DataFrame(False, index=df_speed.index, columns=df_speed.columns)
    link_frc_series = df_links.set_index("link_id")["frc"]

    for col in df_speed.columns:
        frc = link_frc_series.get(col, -1)
        th = th_motor if frc == 0 else th_local
        val = df_speed[col]
        is_congested[col] = (val < th) & (val > 0)

    df_bn = pd.DataFrame(0.0, index=df_speed.index, columns=df_speed.columns)
    df_aq = pd.DataFrame(0.0, index=df_speed.index, columns=df_speed.columns)

    cong_arr = is_congested.values
    if cong_arr.shape[1] > 1:
        current = cong_arr[:, :-1]
        downstream = cong_arr[:, 1:]
        df_bn.iloc[:, :-1] = (current & ~downstream).astype(float)
        df_aq.iloc[:, :-1] = (current & downstream).astype(float)

    return df_bn, df_aq


def generate_dynamic_speed_colorscale(legend_config):
    if not legend_config:
        return SPEED_COLORS_DISCRETE, 80

    sorted_legends = sorted(legend_config, key=lambda x: x['speed'])
    max_speed = sorted_legends[-1]['speed']

    scale = []
    prev_norm = 0.0
    for item in sorted_legends:
        speed_val = item['speed']
        color = item['color']
        norm_val = min(speed_val / max_speed, 1.0)
        scale.append([prev_norm, color])
        scale.append([norm_val, color])
        prev_norm = norm_val

    return scale, max_speed


def create_sparse_ticks(x_bounds, min_gap_km=0.3):
    """
    リンク境界(x_bounds)全てに目盛りを振るが、
    ラベル(数値)は重ならないように間引く。
    """
    tick_vals = x_bounds
    tick_text = []
    last_val = -999.0

    for x in x_bounds:
        # 最初の点(0)は表示、以降はmin_gap_km以上離れていれば表示
        if x == 0 or (x - last_val >= min_gap_km):
            tick_text.append(f"{x:.1f}")
            last_val = x
        else:
            tick_text.append("")

    return tick_vals, tick_text


def create_plot_common_fig(x_bounds, y_coords, z_spd, z_bn, z_aq, total_km, title, legend_config=None, direction="LtoR"):
    speed_scale, speed_zmax = generate_dynamic_speed_colorscale(legend_config)

    # X軸: リンク境界に目盛り、ラベルは間引く
    x_tick_vals, x_tick_text = create_sparse_ticks(x_bounds, min_gap_km=0.4)
    # 上段・中段用（目盛りはあるがラベルはなし）
    x_tick_text_empty = [""] * len(x_tick_vals)

    # Y軸(1時間ごと) - 上段用
    y_tick_vals_1h = []
    y_tick_text_1h = []
    # Y軸(3時間ごと) - 中・下段用
    y_tick_vals_3h = []
    y_tick_text_3h = []

    for t in y_coords:
        try:
            h = int(t.split(':')[0])
            # 1時間ごと
            y_tick_vals_1h.append(t)
            y_tick_text_1h.append(f"{h:02d}:00")

            # 3時間ごと
            if h % 3 == 0:
                y_tick_vals_3h.append(t)
                y_tick_text_3h.append(f"{h:02d}:00")
            else:
                y_tick_vals_3h.append(t)
                y_tick_text_3h.append("")
        except:
            y_tick_vals_1h.append(t)
            y_tick_text_1h.append("")
            y_tick_vals_3h.append(t)
            y_tick_text_3h.append("")

    row_heights = [0.50, 0.20, 0.20]
    vs = 0.05

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=vs, row_heights=row_heights, subplot_titles=("", "", ""))

    y3_h = row_heights[2]
    y3_bot = 0
    y2_bot = y3_h + vs
    y2_h = row_heights[1]
    y1_bot = y2_bot + y2_h + vs
    y1_h = row_heights[0]

    fig.add_trace(go.Heatmap(
        x=x_bounds, y=y_coords, z=z_spd, colorscale=speed_scale, zmin=0, zmax=speed_zmax,
        colorbar=dict(len=y1_h, y=y1_bot + y1_h/2, x=1.01), name="速度", xgap=0.5, ygap=0.5
    ), row=1, col=1)

    fig.add_trace(go.Heatmap(
        x=x_bounds, y=y_coords, z=z_bn, colorscale=BN_COLORS, zmin=0, zmax=1,
        colorbar=dict(len=y2_h, y=y2_bot + y2_h/2, x=1.01), name="BN", xgap=0.5, ygap=0.5
    ), row=2, col=1)

    fig.add_trace(go.Heatmap(
        x=x_bounds, y=y_coords, z=z_aq, colorscale=AQ_COLORS, zmin=0, zmax=1,
        colorbar=dict(len=y3_h, y=y3_bot + y3_h/2, x=1.01), name="AQ", xgap=0.5, ygap=0.5
    ), row=3, col=1)

    # 進行方向設定
    if direction == "RtoL":
        annot_text = "← 進行方向"
        annot_x = 1.0
        annot_anchor = "right"
        xaxis_range = [total_km, 0] # 反転
    else:
        annot_text = "進行方向 →"
        annot_x = 0.0
        annot_anchor = "left"
        xaxis_range = [0, total_km]

    fig.update_layout(
        title=dict(text=title, font=dict(size=18, family=FONT_FAMILY), y=0.98),
        height=1000, margin=dict(l=60, r=100, t=140, b=50), font=dict(family=FONT_FAMILY),
        plot_bgcolor='rgb(245, 245, 245)',
        # 進行方向ラベル
        annotations=[dict(x=annot_x, y=1.01, xref="paper", yref="paper", text=annot_text, showarrow=False, font=dict(size=14, color="black"), xanchor=annot_anchor, yanchor="bottom")],

        # 上段: 1時間刻み
        yaxis1=dict(title="平均旅行速度(km/h)", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals_1h, ticktext=y_tick_text_1h),
        # 中段: 3時間刻み
        yaxis2=dict(title="BN指数", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals_3h, ticktext=y_tick_text_3h),
        # 下段: 3時間刻み
        yaxis3=dict(title="渋滞影響値(AQ)", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals_3h, ticktext=y_tick_text_3h),

        # X軸共通設定
        xaxis1=dict(tickmode="array", tickvals=x_tick_vals, ticktext=x_tick_text_empty, ticks="outside", showticklabels=True, range=xaxis_range),
        xaxis2=dict(tickmode="array", tickvals=x_tick_vals, ticktext=x_tick_text_empty, ticks="outside", showticklabels=True, range=xaxis_range),
        xaxis3=dict(title="距離 (km)", tickmode="array", tickvals=x_tick_vals, ticktext=x_tick_text, range=xaxis_range, ticks="outside", showticklabels=True),

        hovermode="closest"
    )

    return fig


def run_mosaic_analysis(input_dir, output_dir, target_files, config):
    sum_speed_mosaic = None
    sum_bn_mosaic = None
    sum_aq_mosaic = None
    base_links = None
    valid_count = 0

    th_local = SPEED_THRESHOLD_LOCAL
    th_motor = SPEED_THRESHOLD_MOTORWAY

    # ルート形状を取得
    route_geometry = config.get('route_geometry')

    print(f"[Logic] Processing {len(target_files)} files...")

    for fname in target_files:
        fpath = os.path.join(input_dir, fname)
        if not os.path.exists(fpath): continue

        # ルート形状を渡してパース（内部でソートされる）
        d_lnk, d_spd, d_tt = parse_single_geojson(fpath, route_geometry)
        if d_lnk is None: continue

        d_spd = d_spd.fillna(0)
        bn_binary, aq_binary = calculate_bn_aq_binary(d_lnk, d_spd, th_local, th_motor)

        if sum_speed_mosaic is None:
            sum_speed_mosaic = d_spd.copy()
            sum_bn_mosaic = bn_binary.copy()
            sum_aq_mosaic = aq_binary.copy()
            base_links = d_lnk
        else:
            if d_spd.shape == sum_speed_mosaic.shape:
                sum_speed_mosaic = sum_speed_mosaic.add(d_spd, fill_value=0)
                sum_bn_mosaic = sum_bn_mosaic.add(bn_binary, fill_value=0)
                sum_aq_mosaic = sum_aq_mosaic.add(aq_binary, fill_value=0)
            else:
                print(f"Skipping {fname}: Link structure mismatch")
                continue

        valid_count += 1

    if valid_count == 0:
        print("[Logic] No valid files found (direction mismatch or other errors).")
        return None

    avg_speed_mosaic = sum_speed_mosaic / valid_count
    avg_bn_mosaic = sum_bn_mosaic / valid_count
    avg_aq_mosaic = sum_aq_mosaic / valid_count

    # --- Time Range Filtering & Reindexing ---
    start_time_str = config.get('start_time', '00:00')
    end_time_str = config.get('end_time', '23:00')
    # time_pitch is in minutes (e.g., 60)
    pitch_min = int(config.get('time_pitch', 60))

    # Create full time index
    # Dummy date is used to generate time range
    full_range = pd.date_range(start=f"2000-01-01 {start_time_str}", end=f"2000-01-01 {end_time_str}", freq=f"{pitch_min}T")
    full_time_index = [t.strftime("%H:%M") for t in full_range]

    # Reindex to ensure all time slots are present and sorted
    # fill_value=0 means missing data is treated as 0 km/h (congested) or 0 (no bottleneck)
    avg_speed_mosaic = avg_speed_mosaic.reindex(full_time_index, fill_value=0)
    avg_bn_mosaic = avg_bn_mosaic.reindex(full_time_index, fill_value=0)
    avg_aq_mosaic = avg_aq_mosaic.reindex(full_time_index, fill_value=0)

    title = f"平均旅行速度モザイク図 (可変長区間)    対象期間: {config.get('start_date')} - {config.get('end_date')}"
    x_bounds = base_links["start_distance_km"].tolist() + [base_links["end_distance_km"].iloc[-1]]
    total_km = base_links["end_distance_km"].max()
    legend_config = config.get('speed_legend')
    direction = config.get('direction', 'LtoR')
    print(f"[Logic] Direction: {direction}")

    print("[Logic] Generating Plot...")
    fig = create_plot_common_fig(
        x_bounds, avg_speed_mosaic.index,
        avg_speed_mosaic.values, avg_bn_mosaic.values, avg_aq_mosaic.values,
        total_km, title, legend_config, direction=direction
    )

    out_html = "result_mosaic.html"
    out_path = os.path.join(output_dir, out_html)
    fig.write_html(out_path)
    print(f"[Logic] Saved to {out_path}")

    return {
        "html_url": f"/results/{out_html}",
        "summary": {
            "processed_files": valid_count,
            "total_distance_km": total_km
        }
    }
