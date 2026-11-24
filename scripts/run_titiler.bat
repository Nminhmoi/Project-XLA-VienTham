@echo off
REM Giai đoạn 5 (Nam Anh): Khởi chạy TiTiler phục vụ COG cho WebGIS (Windows)
REM Chạy: double-click hoặc  scripts\run_titiler.bat   (đổi cổng: set PORT=8001 trước khi chạy)
chcp 65001 >nul
setlocal

REM Luôn chạy từ thư mục gốc repo, bất kể gọi từ đâu
cd /d "%~dp0.."

if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=8000
set COG=data\outputs\cog_multispectral.tif

if not exist "%COG%" (
  echo [LOI] Khong tim thay %COG%. Tai tu Drive nhom hoac chay: python scripts\01_gdal_cog_preprocessing.py
  exit /b 1
)

REM CORS: cho phep web (Live Server :5500, http.server, file://) goi tile. TiTiler mac dinh da la "*".
set TITILER_API_CORS_ORIGINS=*
REM Toi uu doc COG cuc bo
set GDAL_CACHEMAX=512
set GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR

echo Cap nhat web\tiles.json ...
python scripts\make_titiler_urls.py --host http://localhost:%PORT% || exit /b 1

echo.
echo TiTiler: http://localhost:%PORT%/docs   (Ctrl+C de dung)
python -m uvicorn titiler.application.main:app --host %HOST% --port %PORT%
