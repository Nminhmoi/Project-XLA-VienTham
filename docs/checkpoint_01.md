# Báo Cáo Nghiệm Thu Checkpoint 1 (Ngày 03)

- **Người nghiệm thu:** Minh (Leader)
- **Ngày kiểm tra:** 26/11/2026
- **Điều kiện đạt CP1 (mục 4.5 [README.md](../README.md)):** 3 script `01_gdal_cog_preprocessing.py`, `02_yolo_drone_detection.py`, `03_spectral_ndvi_analysis.py` chạy được trên COG và sinh output thô.
- **Kết luận chung:** **ĐẠT CHECKPOINT 1** (cả 3 nhánh lõi đều có script chạy sạch và output hợp lệ trên `data/outputs/cog_multispectral.tif`).

---

## 1. Kết quả kiểm tra từng nhánh

### 1.1. Nhánh GDAL / COG (Nam Anh)
- **Script:** `scripts/01_gdal_cog_preprocessing.py` (`--help` exit `0`), `scripts/validate_cog.py`.
- **Kiểm tra thực tế (`python scripts/validate_cog.py` trên `data/outputs/cog_multispectral.tif`):** **ĐẠT (17/17 mục PASS)**
  - `rio cogeo validate`: hợp lệ
  - `LAYOUT=COG`, `COMPRESSION=DEFLATE`, `PREDICTOR=2`, block `512×512`, `4` mức overviews `[2, 4, 8, 16]`
  - `5` band (`Blue, Green, Red, RedEdge, NIR`), `uint16`, `EPSG:32630`, pixel size `0.041300 × 0.041300 m`, kích thước `4419 × 4434 px` (`19,593,846` px)
  - Mask `PER_DATASET x5`, tỷ lệ hợp lệ `75.01%` (`14,697,855 / 19,593,846`)
  - Pixel ngoài mask khác 0: `0`; pixel trong mask = 0 ở mọi band: `0`; dung lượng `178.9 MB`.

### 1.2. Nhánh AI / YOLO (Hinh)
- **Script:** `scripts/02_yolo_drone_detection.py` (`--help` exit `0`), `scripts/test_outputs.py`.
- **Kiểm tra thực tế (`python scripts/test_outputs.py`):** **Hợp lệ 100% Schema 4.4.B**
  - `data/outputs/detections.geojson`: `FeatureCollection`, **289** Features (`class_name = palm`), tọa độ `EPSG:4326` hợp lệ, đủ 6 trường bắt buộc.
  - `data/outputs/palm_stats.json`: `289` tán, `2.5059 ha`, mật độ `115.33 cây/ha`.
  - `docs/figures/detections_palm.jpg`: `3.11 MB`, hợp lệ.
  - Đã tách riêng file đối chiếu baseline COCO cũ tại `data/outputs/detections_person_baseline.geojson` (`12` Features `person`).

### 1.3. Nhánh Phổ & LULC (Quang Anh)
- **Script:** `scripts/03_spectral_ndvi_analysis.py`.
- **Kiểm tra thực tế:**
  - `python scripts/03_spectral_ndvi_analysis.py --suggest-thresholds` chạy sạch trên `ndvi.tif`: Otsu phân tầng `t1 = 0.397`, `t2 = 0.109`, `t3 = -0.174`; ngưỡng đang dùng `[0.4, 0.1, -0.15]`.
  - Output hiện hữu đầy đủ trong `data/outputs/`: `ndvi.tif`, `ndre.tif`, `lulc_class.tif`, `ndvi_preview.png`, `spectral_stats.json`, `lulc_summary.json`.
  - Kiểm tra chéo bất biến `lulc_summary.json`:
    - `total_valid_pixel_count` (`14,696,741`) == tổng `pixel_count` 4 lớp (`14,696,741`).
    - `total_valid_pixel_count + excluded_pixel_count` (`14,696,741 + 4,895,991 + 1,114 + 0`) = `19,593,846` (khớp đúng tổng số pixel của COG).
    - Tổng `percent` = `99.99%` (trong ngưỡng sai số làm tròn).

---

## 2. Lỗi & Lưu ý còn lại (theo dõi sang CP2 / CP3)

1. **Biến môi trường `PATH` cho `.venv` trên Windows:** `.venv/pyvenv.cfg` trỏ tới `E:\python` (Python 3.12.12). Nếu `E:\python` chưa nằm trong `PATH`, gọi trực tiếp `.venv\Scripts\python.exe` bị thoát với mã `-1073741515` (`STATUS_DLL_NOT_FOUND`). Cần thêm `E:\python` vào `PATH` (hoặc cập nhật hướng dẫn chạy).
2. **Thiếu `pytest` trong `.venv`:** Lệnh `.venv\Scripts\python.exe -m pytest` báo `No module named pytest`, nên bộ unit test `tests/test_spectral_ndvi.py` chưa chạy qua `pytest` ở lần kiểm tra này. Cần cài `pytest` vào `.venv` trước khi nghiệm thu CP2/CP3.
3. **`data/outputs/ortho_rgb_3band.tif`:** Hiện chưa có sẵn trên đĩa (`test_outputs.py` báo chưa có tệp); không chặn vì `02_yolo_drone_detection.py` tự trích xuất lại từ COG khi cần.
4. **Nhánh WebGIS (`web/`):** Thuộc phạm vi Ngày 03–04 (Đức nhúng tile TiTiler + nạp GeoJSON), sẽ nghiệm thu chi tiết ở **Checkpoint 2**.
