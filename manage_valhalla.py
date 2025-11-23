import os
import subprocess
import sys
import time


import argparse

# --- .env 読み込み機能 (標準ライブラリのみ) ---
def load_env_file():
    """カレントディレクトリの .env ファイルを読み込んで環境変数にセットする"""
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        print(f"Loading config from {env_path}...")
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # コメントや空行はスキップ
                    if not line or line.startswith('#'):
                        continue
                    # KEY=VALUE 形式をパース
                    if '=' in line:
                        key, val = line.split('=', 1)
                        # クォートがあれば除去
                        val = val.strip().strip('"').strip("'")
                        os.environ[key.strip()] = val
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}")


# スクリプト実行時に読み込み
load_env_file()

# --- 設定 ---
# PBFファイル名 (.envから取得、設定がなければデフォルト値を使用)
# ユーザー様の要望通り、環境変数からファイル名を取得します
PBF_FILENAME = os.getenv("PBF_FILENAME", "kanto-251121.osm.pbf")

# ディレクトリ設定
CURRENT_DIR = os.getcwd()
CUSTOM_FILES_DIR = os.path.join(CURRENT_DIR, "custom_files")
VALHALLA_IMAGE = "ghcr.io/valhalla/valhalla:latest"
CONTAINER_NAME = "valhalla_route"
PORT = 8002


def run_command(cmd, description):
    print(f"--- {description} ---")
    try:
        subprocess.check_call(cmd, shell=True)
        print("-> Success.\n")
    except subprocess.CalledProcessError as e:
        print(f"Error during: {description}")
        sys.exit(1)


def is_data_built():
    """必要なデータファイル（configとタイル）が存在するか確認"""
    config_path = os.path.join(CUSTOM_FILES_DIR, "valhalla.json")
    tiles_path = os.path.join(CUSTOM_FILES_DIR, "valhalla_tiles.tar")
    # タイルはディレクトリの場合とtarの場合があるため両方チェック
    tiles_dir = os.path.join(CUSTOM_FILES_DIR, "valhalla_tiles")

    return os.path.exists(config_path) and (os.path.exists(tiles_path) or os.path.exists(tiles_dir))


def build_valhalla():
    """Valhallaのデータを構築する"""
    print(f"Building Valhalla data using '{PBF_FILENAME}'... (This may take a while)")

    # PBFファイルの存在確認 (ビルド前にも再確認)
    pbf_path_host = os.path.join(CUSTOM_FILES_DIR, PBF_FILENAME)
    if not os.path.exists(pbf_path_host):
        print(f"Error: PBF file '{PBF_FILENAME}' not found in custom_files directory.")
        sys.exit(1)

    # 1. Config生成
    cmd_config = f"""
    docker run --rm -v "{CUSTOM_FILES_DIR}":/custom_files {VALHALLA_IMAGE} \
        valhalla_build_config \
        --mjolnir-tile-dir /custom_files/valhalla_tiles \
        --mjolnir-tile-extract /custom_files/valhalla_tiles.tar \
        --mjolnir-timezone /custom_files/timezones.sqlite \
        --mjolnir-admin /custom_files/admins.sqlite \
        > "{os.path.join(CUSTOM_FILES_DIR, 'valhalla.json')}"
    """
    run_command(cmd_config, "Generating Config")

    # 2. Admins生成
    cmd_admins = f"""
    docker run --rm -v "{CUSTOM_FILES_DIR}":/custom_files {VALHALLA_IMAGE} \
        valhalla_build_admins \
        --config /custom_files/valhalla.json \
        /custom_files/{PBF_FILENAME}
    """
    run_command(cmd_admins, "Building Admins")

    # 3. Tiles生成
    # メモリ不足対策としてスレッド数を制限 (デフォルトはコア数分使うため)
    cmd_tiles = f"""
    docker run --rm -v "{CUSTOM_FILES_DIR}":/custom_files {VALHALLA_IMAGE} \
        valhalla_build_tiles \
        --config /custom_files/valhalla.json \
        --concurrency 2 \
        /custom_files/{PBF_FILENAME}
    """
    run_command(cmd_tiles, "Building Tiles")


def start_server():
    """サーバーコンテナを起動する"""
    print("Starting Valhalla Server...")

    # 既存の同名コンテナがあれば停止・削除
    subprocess.call(f"docker rm -f {CONTAINER_NAME}", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    # サーバー起動
    # スレッド数はマシンスペックに合わせて調整可能です (ここでは4)
    cmd_serve = f"""
    docker run -dt --name {CONTAINER_NAME} -p {PORT}:8002 -v "{CUSTOM_FILES_DIR}":/custom_files \
        {VALHALLA_IMAGE} \
        valhalla_service /custom_files/valhalla.json 4
    """
    run_command(cmd_serve, "Starting Service Container")

    print(f"Valhalla is running on http://localhost:{PORT}")


def main():
    parser = argparse.ArgumentParser(description="Manage Valhalla Server")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of Valhalla data")
    args = parser.parse_args()

    # 起動前のチェック
    print(f"Target PBF Filename: {PBF_FILENAME}")

    pbf_path = os.path.join(CUSTOM_FILES_DIR, PBF_FILENAME)
    if not os.path.exists(pbf_path):
        print(f"Error: PBF file not found at {pbf_path}")
        print(f"Please ensure '{PBF_FILENAME}' is in the 'custom_files' directory.")
        print("You can change the filename in the .env file.")
        sys.exit(1)

    if args.rebuild or not is_data_built():
        if args.rebuild:
            print("Rebuild requested.")
        else:
            print("Data not found. Starting build process...")
        build_valhalla()
    else:
        print("Data already built. Skipping build process.")
        print("Use --rebuild to force rebuild.")

    start_server()


if __name__ == "__main__":
    main()
