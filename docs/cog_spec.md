# Đặc tả COG và cách tái tạo (Nhánh Nam Anh)

## 1. Đặc tả `data/outputs/cog_multispectral.tif`

| Thuộc tính | Giá trị yêu cầu | Lý do |
| :--- | :--- | :--- |
| Số band | 5: Blue, Green, Red, RedEdge, NIR (ghi trong `Description`) | Hợp đồng 4.4.A; band Alpha của Metashape bị loại |
| Kiểu dữ liệu | `uint16` (DN thô, không scale/offset) | Giữ nguyên giá trị phổ; ép `float32` trước khi tính chỉ số |
| CRS | EPSG:32630 (WGS 84 / UTM 30N) | Hệ chiếu đơn vị mét → tính diện tích đúng |
| Pixel size | 0,0413 × 0,0413 m | Bằng GSD của orthomosaic |
| Kích thước | 4419 × 4434 px (~182,5 × 183,1 m) | Do `calculate_default_transform` sinh từ biên ảnh nguồn |
| Mask | Nội bộ `PER_DATASET`, 0 = nền, 255 = hợp lệ | Thay band Alpha; TiTiler/rasterio tự hiểu |
| Pixel nền | Ghi 0 ở cả 5 band | Kiểm tra chéo được, không lẫn nền trắng 65535 của Metashape |
| Layout | COG, tile 512 × 512 | Đọc từng phần qua HTTP/tile server |
| Nén | DEFLATE + `PREDICTOR=2` | Predictor ngang hợp với số nguyên `uint16` |
| Overviews | Tự động (`OVERVIEWS=AUTO`), 4 mức 2/4/8/16, resampling CUBIC | Hiển thị nhanh khi zoom nhỏ |
| BigTIFF | `IF_SAFER` | Tự bật nếu file có thể vượt 4 GB |

## 2. Tái tạo bằng một lệnh

```bash
python scripts/01_gdal_cog_preprocessing.py
# tương đương: --input data/orthomosaic/multispectral_ortho.tif --output data/outputs/cog_multispectral.tif
python scripts/validate_cog.py
```

Script thay cho chuỗi 5 lệnh GDAL ở README mục 2.4–2.5 (tách alpha, bỏ band 6, `gdalwarp` dữ liệu, `gdalwarp` mask, VRT gắn mask, `gdal_translate -of COG`). Chỉ dùng `rasterio` (có GDAL đi kèm) nên chạy được trên Windows/macOS mà không cần OSGeo4W.

Các bước bên trong:

1. **Kiểm tra nguồn:** in số band, CRS, pixel size, `Description`. Band phổ được xác định **theo tên trong `Description`**, không theo `src.count`. Nếu thiếu tên thì dừng và yêu cầu `--band-order 1,2,3,4,5`.
2. **Mask nguồn:** band có `ColorInterp=Alpha` hoặc tên `Alpha` → mask 0/255. Không có alpha thì dùng mask nội bộ/nodata; không có gì thì coi toàn bộ là hợp lệ (có cảnh báo).
3. **Reproject:** mask dùng `nearest`; dữ liệu dùng `bilinear` **có khai báo alpha nguồn**, để GDAL không trộn nền trắng 65535 vào pixel rìa ảnh. Pixel rìa mà mask nearest cho là hợp lệ nhưng bilinear không có nguồn hợp lệ sẽ bị loại khỏi mask (tránh pixel 0 → NDVI = 0/0).
4. **Ghi tạm** GeoTIFF tiled kèm mask nội bộ, rồi **copy sang driver COG** (GDAL tự dựng overview cho cả dữ liệu lẫn mask). File tạm bị xóa (giữ lại bằng `--keep-temp`).

Tham số tùy chọn: `--dst-crs`, `--res`, `--band-order`, `--overview-resampling average` (nếu muốn overview giữ trung bình phổ thay cho CUBIC).

Thời gian chạy: ~23 giây cho ảnh 4396 × 4411 px trên máy thử, RAM đỉnh ~0,8 GB (xử lý từng band). Chạy lại hai lần cho ra file **giống hệt từng byte** → kết quả tái lập được.

## 3. Kiểm tra (`scripts/validate_cog.py`)

Script kiểm tra 16 mục và trả mã thoát 1 nếu có mục không đạt:

- `rio cogeo validate` (thư viện `rio-cogeo`);
- `LAYOUT=COG`, `COMPRESSION=DEFLATE`, `PREDICTOR=2`, block 512 × 512, overviews ≥ 4 mức;
- 5 band đúng `Description`, `uint16`, EPSG:32630, pixel 0,0413 m;
- mask `PER_DATASET` trên cả 5 band, tỷ lệ pixel hợp lệ;
- bất biến: pixel ngoài mask = 0 ở mọi band; không có pixel hợp lệ nào bằng 0 ở cả 5 band.

`python scripts/validate_cog.py --markdown` in thẳng bảng kết quả để dán vào báo cáo.
Kết quả `validate_cog.py` cho `data/outputs/cog_multispectral.tif`:

| Mục | Giá trị | Đạt |
| :--- | :--- | :---: |
| rio cogeo validate | hợp lệ | ✅ |
| LAYOUT | COG | ✅ |
| COMPRESSION | DEFLATE | ✅ |
| PREDICTOR | 2 | ✅ |
| Block (tile) | 512x512 | ✅ |
| Overviews | 4 mức [2, 4, 8, 16] | ✅ |
| Số band | 5 | ✅ |
| Description | Blue, Green, Red, RedEdge, NIR | ✅ |
| Kiểu dữ liệu | uint16 | ✅ |
| CRS | EPSG:32630 | ✅ |
| Pixel size | 0.041300 x 0.041300 m | ✅ |
| Kích thước | 4419 x 4434 px | ✅ |
| Mask Flags | PER_DATASET x5 | ✅ |
| Tỷ lệ pixel hợp lệ | 75.01% (14,697,855 / 19,593,846) | ✅ |
| Pixel ngoài mask khác 0 | 0 | ✅ |
| Pixel trong mask = 0 ở mọi band | 0 | ✅ |
| Dung lượng | 178.9 MB | ✅ |

KẾT LUẬN: ĐẠT
### 3.1. Kết quả trên dữ liệu thử (giả lập)

Chạy trên ortho giả lập có cùng cấu trúc với file thật (4396 × 4411 px, 6 band uint16, EPSG:4326, alpha band 6, nền trắng 65535):

| Mục | Giá trị | Đạt |
| :--- | :--- | :---: |
| rio cogeo validate | hợp lệ | ✅ |
| LAYOUT | COG | ✅ |
| COMPRESSION | DEFLATE | ✅ |
| PREDICTOR | 2 | ✅ |
| Block (tile) | 512x512 | ✅ |
| Overviews | 4 mức [2, 4, 8, 16] | ✅ |
| Số band | 5 | ✅ |
| Description | Blue, Green, Red, RedEdge, NIR | ✅ |
| Kiểu dữ liệu | uint16 | ✅ |
| CRS | EPSG:32630 | ✅ |
| Pixel size | 0.041300 x 0.041300 m | ✅ |
| Kích thước | 4419 x 4434 px | ✅ |
| Mask Flags | PER_DATASET x5 | ✅ |
| Tỷ lệ pixel hợp lệ | 72.81% (giả lập; file thật ~75,0%) | ✅ |
| Pixel ngoài mask khác 0 | 0 | ✅ |
| Pixel trong mask = 0 ở mọi band | 0 | ✅ |

Lưới đầu ra (4419 × 4434 px) **trùng khớp** với COG thật hiện có của nhóm. Đối chứng: chạy `validate_cog.py` trên ortho nguồn cho kết quả KHÔNG ĐẠT ở 10 mục (6 band, EPSG:4326, LZW, tile 256, không có layout COG…), đúng như mong đợi.

### 3.2. Kết quả trên dữ liệu thật

> ⬜ Chạy `python scripts/01_gdal_cog_preprocessing.py && python scripts/validate_cog.py --markdown` trên `multispectral_ortho.tif` thật rồi dán bảng vào đây.
> Số kỳ vọng (từ COG hiện có, `docs/band_order.md`): 4419 × 4434 px, hợp lệ ~75,01%, ~179 MB.
