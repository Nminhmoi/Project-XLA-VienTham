# Nhánh phổ NDVI/NDRE & LULC — Quang Anh

Script: `scripts/03_spectral_ndvi_analysis.py` · Test: `tests/test_spectral_ndvi.py`

## Cách chạy

```bash
python scripts/03_spectral_ndvi_analysis.py                              # toàn ảnh (~8 s)
python scripts/03_spectral_ndvi_analysis.py --window 1709 1717 1000 1000 \
       --outdir <thư mục tạm>                                           # thử trên crop 1000×1000
python scripts/03_spectral_ndvi_analysis.py --thresholds 0.42 0.17 -0.14  # thử ngưỡng khác
python scripts/03_spectral_ndvi_analysis.py --suggest-thresholds         # in ngưỡng Otsu
python -m pytest tests -q                                                # 37 test
```

Output trong `data/outputs/`:

| File | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `ndvi.tif`, `ndre.tif` | Float32, nodata = NaN | Cùng lưới với COG (EPSG:32630, 0.0413 m) |
| `lulc_class.tif` | Byte, nodata = 0 | 1 Cây xanh tốt · 2 Cỏ/cây bụi · 3 Thực vật thưa/khô · 4 Đất trống; bảng màu nâu–xanh an toàn cho người mù màu |
| `lulc_summary.json` | JSON | Diện tích, % và `ndvi_range` của 4 lớp; tổng diện tích hợp lệ; số pixel bị loại; `ndvi_thresholds` đã dùng |
| `spectral_stats.json` | JSON | min/max/mean/std/percentile của NDVI, NDRE |
| `ndvi_preview.png` | PNG RGBA | RdYlGn, rescale −0.2…0.8 (giống TiTiler), nền trong suốt |

## Kiểm tra band 3/4/5 và xử lý pixel lỗi

- Band đọc theo index tường minh: 3 = Red, 4 = RedEdge, 5 = NIR (khớp `descriptions` trong COG).
- Chia 0: mẫu số = 0 → NaN (COG tái tạo bằng script 01: 0 px; COG cũ có 6 px, nay đã nằm ngoài mask).
- Mask: pixel ngoài mask nội bộ → NaN / lớp 0 (4 895 991 px).
- Bão hòa: Red = 65535 ở 1 114 px (0,008 %) → loại, vì Red bão hòa làm NDVI âm giả.
- Tính toán trên float32 sau khi ép kiểu (tránh tràn số khi trừ uint16); sai khác so với float64 < 3·10⁻⁸.

## Nhận xét khoảng giá trị (toàn ảnh, 14,70 triệu px hợp lệ)

| Chỉ số | min | p2 | median | mean | p98 | max |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| NDVI | −0,663 | −0,422 | 0,331 | 0,223 | 0,647 | 1,000 |
| NDRE | −0,253 | −0,111 | 0,037 | 0,034 | 0,181 | 0,532 |

- NDVI phân bố hai đỉnh: vùng thực vật (0,3–0,65) và một vùng lớn phía tây bắc có NDVI âm.
- NDRE thấp hơn NDVI nhiều (RedEdge gần NIR) — đúng kỳ vọng; NDRE phù hợp phân biệt sức khỏe cây ở tán dày hơn là phân lớp.
- Crop 1000×1000 ở tâm: NDVI −0,54…0,88, mean 0,38; NDRE −0,14…0,42, mean 0,06.

## Chọn lớp và ngưỡng LULC

Bộ lớp ban đầu (Cây tốt / Cỏ / Đất–nhà cửa / Nước, ngưỡng 0,45 / 0,20 / 0) không hợp với dataset:

- Đối chiếu ảnh RGB: **không có mặt nước, không có nhà cửa**. Mảng 26 % bị xếp "Nước" ở tây bắc thực ra là đất trống / thảm khô (Red cao ~28 200, NIR thấp ~18 000 DN).
- Ảnh **chưa hiệu chuẩn phản xạ** nên NDVI tính trên DN; đất trống ra NDVI âm, ngưỡng lý thuyết (đất 0–0,2) không dùng được.

Đổi sang 4 lớp hợp với rừng: **1 Cây xanh tốt · 2 Thảm cỏ / cây bụi · 3 Thực vật thưa / khô · 4 Đất trống / đất lộ**.

Histogram NDVI có 2 đỉnh (đất ~ −0,33; thực vật ~ 0,45). Ngưỡng cũ 0,45 cắt đúng đỉnh thực vật nên ranh lớp 1/2 tùy tiện. Đã thử 3 bộ ngưỡng:

| Phương án | t1 / t2 / t3 | Cây tốt | Cỏ/bụi | Thưa/khô | Đất |
| :--- | :--- | ---: | ---: | ---: | ---: |
| A — ngưỡng ban đầu | 0,45 / 0,20 / 0,00 | 29,5 % | 33,7 % | 10,6 % | 26,3 % |
| B — k-means 4 cụm | 0,42 / 0,17 / −0,14 | 35,3 % | 29,8 % | 14,9 % | 19,9 % |
| **C — Otsu phân tầng (chọn)** | **0,40 / 0,10 / −0,15** | **39,0 %** | **30,1 %** | **11,5 %** | **19,4 %** |

Otsu phân tầng (toàn ảnh, 14,7 triệu px): Otsu toàn ảnh = 0,109 (thực vật / không thực vật) → t2; Otsu trong nhóm thực vật = 0,397 → t1; trong nhóm không thực vật = −0,174 → t3. Làm tròn tới bội số 0,05 → **0,40 / 0,10 / −0,15**. Tính lại: `python scripts/03_spectral_ndvi_analysis.py --suggest-thresholds`.

Chọn **C** vì so với RGB: tán cây dày (kể cả cọ) vào trọn lớp 1 (A xé tán thành lớp 2); búi cỏ xanh lẫn trên nền khô ở tây bắc ra lớp 3 thay vì gộp hết vào đất. B gần giống C → ngưỡng ổn định. Ngưỡng có cơ sở thống kê, không chọn tay.

Thử ngưỡng khác: `python scripts/03_spectral_ndvi_analysis.py --thresholds 0.42 0.17 -0.14` (ngưỡng đã dùng được ghi vào `lulc_summary.json` → `ndvi_thresholds`).

## Diện tích LULC (tổng 2,51 ha, ngưỡng C)

| Lớp | NDVI | Diện tích (m²) | ha | % |
| :--- | :--- | ---: | ---: | ---: |
| 1 Cây xanh tốt | > 0,40 | 9 777,32 | 0,9777 | 39,00 |
| 2 Thảm cỏ / cây bụi | (0,10; 0,40] | 7 533,79 | 0,7534 | 30,05 |
| 3 Thực vật thưa / khô | [−0,15; 0,10] | 2 886,23 | 0,2886 | 11,51 |
| 4 Đất trống / đất lộ | < −0,15 | 4 870,75 | 0,4871 | 19,43 |

## Giới hạn

- Ngưỡng gắn với COG này (DN chưa hiệu chuẩn); đổi dataset hoặc hiệu chuẩn phản xạ thì phải chọn lại.
- Chưa có ground truth — đánh giá bằng đối chiếu trực quan với RGB.
