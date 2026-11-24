# Band order và thông số raster

Tài liệu này ghi lại quy ước band và lưới không gian dùng trong pipeline. Các chỉ số band dưới đây là chỉ số 1-based của GeoTIFF; cần kiểm tra metadata raster nếu thay dữ liệu đầu vào.

> **Trạng thái xác minh:** đã kiểm tra ngày 24/11/2026 bằng `rasterio 1.5.2` (GDAL bundled) trên đúng 2 file đang dùng trong repo. Khi tái tạo dữ liệu, chạy lại các lệnh ở mục cuối và cập nhật bảng nếu số liệu thay đổi.

## Nguồn dữ liệu

Raster **không nằm trong Git** (`.gitignore` loại `data/*` để tránh đẩy file nặng lên repo). Sau khi clone, cần tải dữ liệu từ link chia sẻ của nhóm và đặt đúng đường dẫn:

| File | Đường dẫn đặt | Kích thước tham khảo |
|---|---|---:|
| Orthomosaic nguồn | `data/orthomosaic/multispectral_ortho.tif` | 280.159.231 bytes |
| COG phân tích | `data/outputs/cog_multispectral.tif` | 178.894.282 bytes |

- **Link chia sẻ dữ liệu:** https://drive.google.com/drive/folders/1utZOlnebbJuRFI5CFB2lojtcmggOzom6 — thư mục Drive của nhóm, dữ liệu không tự có sau khi clone. Cần quyền truy cập cho cả 5 thành viên trước cuối Ngày 1.
- Kích thước file chỉ để phát hiện tải thiếu/hỏng; nếu lệch đáng kể thì tải lại trước khi chạy pipeline.
- Điều kiện tiên quyết của sprint: COG phải có mặt **trước cuối Ngày 1** vì cả 3 nhánh kỹ thuật đều đọc từ file này.

## Raster nguồn: `data/orthomosaic/multispectral_ortho.tif`

Kích thước 4396 × 4411 pixel, CRS EPSG:4326 (WGS 84) và pixel size địa lý `(0.000000373333, -0.000000373813)` độ. Raster có 6 band; `Description` của từng band xác nhận thứ tự: 1 Blue, 2 Green, 3 Red, 4 RedEdge, 5 NIR, 6 Alpha. Band 6 có `ColorInterp=Alpha` và là mask thực tế của ảnh nguồn; file **không khai báo `nodata`**, mask đọc qua alpha (0 = không hợp lệ, 65535 = hợp lệ, chiếm 75,61% số pixel).

Lưu ý khi xuất ảnh từ nguồn: band 1 đang có `ColorInterp=Gray`, các band 2–5 là `Undefined`. Không dựa vào `ColorInterp` để suy ra band; luôn chọn band tường minh (RGB = `3,2,1`) và gán lại `ColorInterp` khi xuất ảnh màu.

Cấu trúc lưu trữ nguồn: GeoTIFF tiled 256 × 256, nén LZW, interleave pixel, có overview các mức `2, 4, 8, 16, 32`.

## Thứ tự band phân tích

| Band | Tên | Dải phổ tham khảo | Sử dụng |
|---:|---|---:|---|
| 1 | Blue | 450–490 nm | Thành phần ảnh RGB |
| 2 | Green | 520–570 nm | Thành phần ảnh RGB |
| 3 | Red | 630–690 nm | RGB và NDVI |
| 4 | RedEdge | 700–740 nm | NDRE |
| 5 | NIR (Near-Infrared) | 800–900 nm | NDVI, NDRE và CIR |

Dải bước sóng chỉ mang tính tham khảo; giá trị cảm biến thực tế phụ thuộc thiết bị và metadata của dataset.

## COG phân tích: `data/outputs/cog_multispectral.tif`

| Thuộc tính | Giá trị |
|---|---|
| CRS | EPSG:32630 — WGS 84 / UTM zone 30N |
| Pixel size | 0.0413 m × 0.0413 m (kích thước pixel theo trục Y trong GeoTransform thường là −0.0413 m) |
| Kích thước | 4419 × 4434 pixel |
| Số band phân tích | 5 — Blue, Green, Red, RedEdge, NIR |
| Band description | `Blue, Green, Red, RedEdge, NIR` (đây là bằng chứng chốt thứ tự band, mạnh hơn chỉ số band) |
| Mask | Mask nội bộ `PER_DATASET` trên cả 5 band; giá trị 0 là pixel không hợp lệ/nền, 255 là pixel hợp lệ |
| Tỷ lệ pixel hợp lệ | **75,01%** = 14.697.861 / 19.593.846 pixel (mask COG); mask alpha của ảnh nguồn là **75,61%** = 14.660.836 / 19.390.756 pixel |
| Overviews | 4 mức `2, 4, 8, 16`, resampling `CUBIC` |

COG hiển thị `LAYOUT=COG`, `COMPRESSION=DEFLATE`, `PREDICTOR=2` (đọc qua tag `IMAGE_STRUCTURE`) và block 512 × 512. Raster nguồn có 6 band; band Alpha thứ 6 không nằm trong 5 band phân tích của COG.

**Chênh lệch 75,61% (nguồn) và 75,01% (COG):** phép warp/reproject sang UTM bổ sung ~166.000 pixel rìa không hợp lệ, nên mask COG nhỏ hơn alpha nguồn khoảng 0,6 điểm phần trăm. Khi báo cáo diện tích, dùng tỷ lệ của COG (75,01%), không dùng số của ảnh nguồn.

Các pixel bị mask đã được ghi giá trị 0 ở cả 5 band trong COG (không chỉ mask = 0), nên có thể kiểm tra chéo: số pixel 0 của band ≈ số pixel mask = 0.

## Chỉ số band dùng trong công thức

- RGB: Red = band 3, Green = band 2, Blue = band 1 (thứ tự hiển thị RGB: `3,2,1`).
- NDVI: `(NIR - Red) / (NIR + Red)` = `(B5 - B3) / (B5 + B3)`.
- NDRE: `(NIR - RedEdge) / (NIR + RedEdge)` = `(B5 - B4) / (B5 + B4)`.
- Áp mask trước khi tính toán; đánh dấu pixel không hợp lệ và mẫu số bằng 0 là NoData/không hợp lệ.

**Bắt buộc ép kiểu trước khi tính chỉ số:** dữ liệu là `uint16` thô (0–65535), không có scale/offset. Nếu cộng trực tiếp trên `uint16`, `B5 + B3` có thể vượt 65535 và bị tràn số (wrap-around), cho NDVI/NDRE sai mà không báo lỗi. Luôn ép `float32` trước khi cộng/chia, ví dụ:

```python
red = src.read(3).astype("float32")
nir = src.read(5).astype("float32")
ndvi = (nir - red) / (nir + red)
ndvi[src.read_masks(1) == 0] = np.nan
```

## Kiểm tra khi thay hoặc tái tạo dữ liệu

Các lệnh kiểm tra nhanh (chạy sau khi tải hoặc tái tạo dữ liệu):

```bash
gdalinfo -stats data/orthomosaic/multispectral_ortho.tif
gdalinfo -stats data/outputs/cog_multispectral.tif
```

Kỳ vọng: nguồn có 5 kênh phổ theo thứ tự trên cộng band Alpha thứ 6; COG có 5 band với `Description` đúng thứ tự, CRS EPSG:32630, pixel size 0.0413 m, mask `PER_DATASET` và tỷ lệ hợp lệ ~75,0%. `gdalinfo -stats` báo `STATISTICS_VALID_PERCENT=100` cho từng band; **giá trị này không đo tỷ lệ pixel hợp lệ của mask nội bộ** — muốn biết tỷ lệ thật phải đọc mask:

```python
import rasterio, numpy as np
with rasterio.open("data/outputs/cog_multispectral.tif") as ds:
    m = ds.read_masks(1)
    print((m > 0).mean() * 100)  # ~75.01
```

Không suy ra ý nghĩa band từ số lượng band (`src.count`) hoặc mặc định thứ tự nếu metadata không khớp. Nếu thứ tự band thay đổi, cập nhật chỉ số trong script, công thức và cấu hình TiTiler đồng thời.
