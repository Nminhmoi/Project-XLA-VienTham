#!/usr/bin/env bash
# Giai đoạn 5 (Nam Anh): Khởi chạy TiTiler phục vụ COG cho WebGIS (macOS / Linux)
# Chạy: bash scripts/run_titiler.sh        (đổi cổng: PORT=8001 bash scripts/run_titiler.sh)
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
COG="data/outputs/cog_multispectral.tif"
PY="${PYTHON:-python3}"

if [ ! -f "$COG" ]; then
  echo "[LỖI] Không tìm thấy $COG. Tải từ Drive nhóm hoặc chạy: $PY scripts/01_gdal_cog_preprocessing.py"
  exit 1
fi

export TITILER_API_CORS_ORIGINS="*"          # CORS cho web chạy ở cổng khác
export GDAL_CACHEMAX=512
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR

echo "Cập nhật web/tiles.json ..."
"$PY" scripts/make_titiler_urls.py --host "http://localhost:$PORT"

echo
echo "TiTiler: http://localhost:$PORT/docs   (Ctrl+C để dừng)"
exec "$PY" -m uvicorn titiler.application.main:app --host "$HOST" --port "$PORT"
