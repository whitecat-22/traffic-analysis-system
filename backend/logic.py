import os
import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

def parse_single_geojson(filepath):
    print(f"[Logic] Parsing: {os.path.basename(filepath)}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Logic Error] {e}")
        return None, None, None

    if "features" not in data or not data["features"]:
        return None, None, None

    time_set_map = {}
    try:
        metadata = data["features"][0]
        if "properties" in metadata and "timeSets" in metadata["properties"]:
            for ts in metadata["properties"]["timeSets"]:
                h = ts["name"].split(':')[0]
                time_set_map[str(ts["@id"])] = f"{int(h):02d}:00"
    except:
        pass

    if not time_set_map:
        time_set_map = {str(i): f"{i:02d}:00" for i in range(24)}

    links_list = []
    speed_dict = {t: {} for t in time_set_map.values()}
    tt_dict = {t: {} for t in time_set_map.values()}

    prev_end_km = 0.0
    lid = 0

    feats = [f for f in data["features"] if f.get("geometry") and f["geometry"]["type"] == "LineString"]

    for f in feats:
        try:
            p = f["properties"]
            dist_m = float(p.get("distance", 0))
            dist_km = dist_m / 1000.0
            frc = int(p.get("frc", -1))

            links_list.append({
                "link_id": lid,
                "link_length_km": dist_km,
                "start_distance_km": prev_end_km,
                "end_distance_km": prev_end_km + dist_km,
                "frc": frc
            })

            results = p.get("segmentTimeResults", [])
            for res in results:
                ts_id = str(res.get("timeSet"))
                tname = time_set_map.get(ts_id)
                if not tname: continue

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


def create_custom_ticks(x_bounds, label_interval_km=0.5):
    tick_vals = x_bounds
    tick_text = [""] * len(x_bounds)
    total_km = x_bounds[-1]

    targets = np.arange(0, total_km + 0.001, label_interval_km)

    for t in targets:
        idx = (np.abs(np.array(x_bounds) - t)).argmin()
        tick_text[idx] = f"{t:.1f}"

    return tick_vals, tick_text


def create_plot_common_fig(x_bounds, y_coords, z_spd, z_bn, z_aq, total_km, title, legend_config=None):
    speed_scale, speed_zmax = generate_dynamic_speed_colorscale(legend_config)
    x_tick_vals, x_tick_text = create_custom_ticks(x_bounds, 0.5)

    y_tick_vals = []
    y_tick_text = []
    for t in y_coords:
        try:
            h = int(t.split(':')[0])
            if h % 3 == 0:
                y_tick_vals.append(t)
                y_tick_text.append(f"{h:02d}:00")
            else:
                y_tick_vals.append(t)
                y_tick_text.append("")
        except:
            y_tick_vals.append(t)
            y_tick_text.append("")

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

    fig.update_layout(
        title=dict(text=title, font=dict(size=18, family=FONT_FAMILY), y=0.98),
        height=1000, margin=dict(l=60, r=100, t=100, b=50), font=dict(family=FONT_FAMILY),
        plot_bgcolor='rgb(245, 245, 245)',
        annotations=[dict(x=0, y=0.98, xref="paper", yref="paper", text="進行方向 →", showarrow=False, font=dict(size=14, color="black"), xanchor="left")],
        yaxis1=dict(title="平均旅行速度(km/h)", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals, ticktext=y_tick_text),
        yaxis2=dict(title="BN指数", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals, ticktext=y_tick_text),
        yaxis3=dict(title="渋滞影響値(AQ)", autorange="reversed", dtick=1, tickmode="array", tickvals=y_tick_vals, ticktext=y_tick_text),
        xaxis3=dict(title="距離 (km)", tickmode="array", tickvals=x_tick_vals, ticktext=x_tick_text, range=[0, total_km]),
        hovermode="closest"
    )

    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(showticklabels=True, row=3, col=1)

    return fig


def run_mosaic_analysis(input_dir, output_dir, target_files, config):
    sum_speed_mosaic = None
    sum_bn_mosaic = None
    sum_aq_mosaic = None
    base_links = None
    valid_count = 0

    th_local = SPEED_THRESHOLD_LOCAL
    th_motor = SPEED_THRESHOLD_MOTORWAY

    print(f"[Logic] Processing {len(target_files)} files...")

    for fname in target_files:
        fpath = os.path.join(input_dir, fname)
        if not os.path.exists(fpath): continue

        d_lnk, d_spd, d_tt = parse_single_geojson(fpath)
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
        raise ValueError("No valid data files processed.")

    avg_speed_mosaic = sum_speed_mosaic / valid_count
    avg_bn_mosaic = sum_bn_mosaic / valid_count
    avg_aq_mosaic = sum_aq_mosaic / valid_count

    title = f"平均旅行速度モザイク図 (可変長区間)    対象期間: {config.get('start_date')} - {config.get('end_date')}"
    x_bounds = base_links["start_distance_km"].tolist() + [base_links["end_distance_km"].iloc[-1]]
    total_km = base_links["end_distance_km"].max()
    legend_config = config.get('speed_legend')

    print("[Logic] Generating Plot...")
    fig = create_plot_common_fig(
        x_bounds, avg_speed_mosaic.index,
        avg_speed_mosaic.values, avg_bn_mosaic.values, avg_aq_mosaic.values,
        total_km, title, legend_config
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
