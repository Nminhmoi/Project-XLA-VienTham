# URL tile TiTiler cho WebGIS (Nhánh Nam Anh)

> Đã kiểm thử với **TiTiler 2.4.1** + **rasterio 1.5.2 / GDAL 3.12**: cả 4 lớp trả về HTTP 200, PNG 256×256 RGBA, vùng ngoài mask trong suốt, CORS mở cho mọi origin.
> Ngưỡng `rescale` của RGB/CIR trong `web/tiles.json` được sinh **tự động từ COG thật** khi chạy `run_titiler`; các số trong tài liệu này chỉ là ví dụ.

## 1. Khởi chạy

```bash
# Windows
scripts\run_titiler.bat
# macOS / Linux
bash scripts/run_titiler.sh
```

Script sẽ: kiểm tra có `data/outputs/cog_multispectral.tif` → chạy `scripts/make_titiler_urls.py` để ghi `web/tiles.json` → mở TiTiler tại `http://localhost:8000` (Swagger: `/docs`).
Đổi cổng: `set PORT=8001` (Windows) hoặc `PORT=8001 bash scripts/run_titiler.sh`.

Chỉ cần URL (không mở server): `python scripts/make_titiler_urls.py`.

## 2. Bốn lớp tile

Thay `<COG>` bằng **đường dẫn tuyệt đối** tới COG đã URL-encode (script tự làm), ví dụ `D%3A%2FProject%2Fdata%2Foutputs%2Fcog_multispectral.tif`.

| Lớp | Tham số | Ghi chú |
| :--- | :--- | :--- |
| RGB màu tự nhiên | `bidx=3&bidx=2&bidx=1&rescale=<r>&rescale=<g>&rescale=<b>` | Red, Green, Blue |
| CIR hồng ngoại giả | `bidx=5&bidx=3&bidx=2&rescale=<nir>&rescale=<r>&rescale=<g>` | Thực vật hiện màu đỏ |
| NDVI | `expression=%28b5-b3%29%2F%28b5%2Bb3%29&rescale=-0.2,0.8&colormap_name=rdylgn` | `(b5-b3)/(b5+b3)` |
| NDRE (thêm) | `expression=%28b5-b4%29%2F%28b5%2Bb4%29&rescale=0,0.5&colormap_name=rdylgn` | `(b5-b4)/(b5+b4)` |

Mẫu đầy đủ:

```
http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<COG>&bidx=3&bidx=2&bidx=1&rescale=5214,11786&rescale=9042,10458&rescale=6059,7939
http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<COG>&bidx=5&bidx=3&bidx=2&rescale=20920,49091&rescale=5214,11786&rescale=9042,10458
http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<COG>&expression=%28b5-b3%29%2F%28b5%2Bb3%29&rescale=-0.2,0.8&colormap_name=rdylgn
```

## 3. Ba lỗi đã gặp với URL cũ trong README

| URL cũ | Kết quả thực tế | Sửa |
| :--- | :--- | :--- |
| `bands=3,2,1` | **HTTP 400** — TiTiler bỏ qua `bands` (chỉ dùng cho STAC), trả cả 5 band uint16 → không mã hóa được PNG | Dùng `bidx=3&bidx=2&bidx=1` |
| `expression=(b5-b3)/(b5+b3)` (không encode) | **HTTP 400** `Invalid expression syntax` — dấu `+` trong query bị hiểu là dấu cách | Encode `+` thành `%2B` (encode cả biểu thức cho chắc) |
| RGB/CIR không có `rescale` | PNG 16-bit, trình duyệt hiển thị gần như đen | Thêm `rescale` theo phân vị 2–98% từng band |
| `url=file:///...` trên Windows | Dễ lỗi đường dẫn | Dùng đường dẫn tuyệt đối thường `D:/...` (GDAL đọc trực tiếp) |

## 4. Nhúng vào Leaflet (cho Đức)

```js
const cfg = await fetch("tiles.json").then(r => r.json());   // web/tiles.json
const [w, s, e, n] = cfg.bounds_wgs84;
const overlays = {};
for (const l of cfg.layers) {
  overlays[l.name] = L.tileLayer(l.url, {
    bounds: [[s, w], [n, e]],        // không gọi tile ngoài vùng ảnh -> không có 404
    minZoom: cfg.minZoom,
    maxNativeZoom: cfg.maxNativeZoom, // 22: độ phân giải gốc 0,0413 m
    maxZoom: 23,
    tileSize: 256,
  });
}
overlays[cfg.layers[0].name].addTo(map);
L.control.layers(baseMaps, overlays).addTo(map);
map.fitBounds([[s, w], [n, e]]);
```

- Web phải được mở qua HTTP (không mở `index.html` bằng `file://` vì `fetch` sẽ bị chặn): `python -m http.server 5500 -d web` rồi vào `http://localhost:5500`.
- CORS: TiTiler mặc định cho phép mọi origin (`TITILER_API_CORS_ORIGINS=*`, đã đặt lại trong `run_titiler`). Đã kiểm tra preflight `OPTIONS` từ `http://localhost:5500` trả `access-control-allow-origin` đúng.
- GeoJSON YOLO là EPSG:4326, tile là EPSG:3857 — Leaflet tự chiếu, **không** đổi tọa độ thủ công.

## 5. Zoom

Khu vực chỉ ~183 × 183 m. TiTiler báo `minzoom=17`, `maxzoom=22` cho COG này. Zoom 14–16 vẫn trả tile (đọc overview nhỏ nhất, ảnh chỉ vài pixel); chi tiết thật bắt đầu từ z18. Đặt `maxNativeZoom: 22` để Leaflet phóng to tile z22 khi zoom sâu hơn thay vì gọi tile không tồn tại.

Kết quả đo thời gian: xem `docs/tile_benchmark.md` (sinh bằng `python scripts/benchmark_tiles.py`).
