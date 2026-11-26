# Hợp Đồng Dữ Liệu Giữa Các Nhánh (Data Contract)

Tài liệu này chốt quy ước định dạng đầu vào / đầu ra giữa các nhánh trong pipeline để đảm bảo đồng bộ không gian và tích hợp trơn tru lên WebGIS & Notebook demo. Mọi script và kiểm thử đều phải tuân thủ các ràng buộc dưới đây (đồng bộ với mục 4.4 trong [README.md](../README.md)).

---

## A. Đầu vào chung — COG (`data/outputs/cog_multispectral.tif`)

- **Người bàn giao:** Minh (xác minh gốc) & Nam Anh (`scripts/01_gdal_cog_preprocessing.py`, `scripts/validate_cog.py`).
- **Thông số bắt buộc:**
  - **Số band:** `5` (`Blue`, `Green`, `Red`, `RedEdge`, `NIR` — đọc theo `Description`, **không** dùng `src.count` để suy band).
  - **Chỉ số band (1-based):** `1 = Blue`, `2 = Green`, `3 = Red`, `4 = RedEdge`, `5 = NIR`.
  - **Kiểu dữ liệu:** `uint16` (DN thô `0–65535`, không có scale/offset; bắt buộc ép `float32` trước khi tính chỉ số phổ).
  - **CRS:** `EPSG:32630` (WGS 84 / UTM zone 30N).
  - **Pixel size:** `0.0413 m × 0.0413 m` (`4419 × 4434` px = `19,593,846` pixel).
  - **Mask:** Mask nội bộ `PER_DATASET` trên cả 5 band (`0` = nền/bỏ, `255` = hợp lệ; ~`75.01%` hợp lệ). Pixel ngoài mask phải có giá trị `0` ở mọi band.
  - **Cấu trúc COG:** `LAYOUT=COG`, `COMPRESSION=DEFLATE`, `PREDICTOR=2`, block `512 × 512`, overviews ≥ 4 mức (`2, 4, 8, 16`).

---

## B. Kết quả AI Object Detection — `data/outputs/detections.geojson`

- **Chủ sở hữu:** Hinh (`scripts/02_yolo_drone_detection.py`) → **Người tiêu dùng:** Đức (WebGIS), Quang Anh (Notebook), Minh (QA).
- **Hệ quy chiếu:** `EPSG:4326` (`[lon, lat]`). Leaflet tự chiếu lên nền Web Mercator.
- **Cấu trúc GeoJSON:**

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-5.1896994, 5.9269804],
          [-5.1896209, 5.9269804],
          [-5.1896209, 5.9268928],
          [-5.1896994, 5.9268928],
          [-5.1896994, 5.9269804]
        ]]
      },
      "properties": {
        "id": 1,
        "class_name": "palm",
        "confidence": 0.952,
        "tile_id": "r003_c004",
        "center_lon": -5.1896602,
        "center_lat": 5.9269366
      }
    }
  ]
}
```

- **Ràng buộc kiểm thử (`scripts/test_outputs.py`):**
  1. `type == "FeatureCollection"`.
  2. `geometry.type == "Polygon"`, ring khép kín `>= 5` điểm (điểm đầu == điểm cuối), tọa độ nằm trong `[-180, 180] × [-90, 90]`.
  3. `properties` có **đúng 6 trường bắt buộc**: `id`, `class_name`, `confidence`, `tile_id`, `center_lon`, `center_lat` (không chứa trường thừa như `center_gps`).
  4. `class_name` thuộc tập cố định: `{"vehicle", "building", "machinery", "palm", "person", "other"}` (trên `plot_B03` dùng `palm`).
  5. `0.0 <= confidence <= 1.0`.
  6. `tile_id` khớp regex `^r\d+_c\d+$`.
- **Ghi chú đối chiếu:** `data/outputs/detections_person_baseline.geojson` (12 box `person`) chỉ lưu để đối chiếu baseline COCO cũ, **không** dùng làm số liệu chính thức.

---

## C. Kết quả Phân tích phổ & LULC — `data/outputs/lulc_summary.json`

- **Chủ sở hữu:** Quang Anh (`scripts/03_spectral_ndvi_analysis.py`) → **Người tiêu dùng:** Đức (WebGIS), Minh (QA & Báo cáo).
- **Cấu trúc JSON:**

```json
{
  "crs": "EPSG:32630",
  "pixel_size_m": 0.0413,
  "pixel_area_m2": 0.00170569,
  "total_valid_area_ha": 2.51,
  "total_valid_area_m2": 25068.08,
  "total_valid_pixel_count": 14696741,
  "excluded_pixel_count": {
    "outside_mask": 4895991,
    "saturated": 1114,
    "zero_denominator": 0
  },
  "ndvi_thresholds": [0.4, 0.1, -0.15],
  "classes": [
    {
      "id": 1,
      "name": "Cây xanh tốt",
      "ndvi_range": [0.4, 1.0],
      "pixel_count": 5732176,
      "area_m2": 9777.32,
      "area_ha": 0.9777,
      "percent": 39.0
    }
  ]
}
```

- **Ràng buộc & Bất biến kiểm tra chéo:**
  1. `ndvi_thresholds = [t1, t2, t3]` thỏa `1.0 >= t1 > t2 > t3 >= -1.0`.
  2. `classes` gồm đủ 4 lớp `id = 1..4` (`Cây xanh tốt`, `Thảm cỏ / cây bụi`, `Thực vật thưa / khô`, `Đất trống / đất lộ`); `ndvi_range` phải sinh động từ `ndvi_thresholds`, không hard-code.
  3. `sum(c["pixel_count"] for c in classes) == total_valid_pixel_count`.
  4. `total_valid_pixel_count + sum(excluded_pixel_count.values()) == width * height` (`19,593,846` px trên COG chuẩn).
  5. `sum(c["percent"] for c in classes)` ≈ `100.0` (sai số làm tròn `±0.05`).

---

## D. TiTiler Tile URLs (`web/tiles.json`) & Notebook Demo (`notebooks/04_demo_pipeline.ipynb`)

1. **TiTiler (`scripts/make_titiler_urls.py` → `web/tiles.json`):**
   - RGB: `bidx=3&bidx=2&bidx=1`
   - CIR: `bidx=5&bidx=3&bidx=2`
   - NDVI: `expression=(b5-b3)/(b5+b3)&rescale=-0.2,0.8&colormap_name=rdylgn`
   - NDRE: `expression=(b5-b4)/(b5+b4)&rescale=-0.2,0.6&colormap_name=rdylgn`
2. **Notebook demo (`notebooks/04_demo_pipeline.ipynb`):**
   - Chỉ đọc `data/outputs/*`, không ghi đè output của các script `01`, `02`, `03`.
   - Đọc COG ở độ phân giải giảm (`out_shape`) để tổng thời gian chạy `< 30 giây`.
   - Không chạy YOLO trong notebook — chỉ vẽ lại từ `data/outputs/detections.geojson`.
