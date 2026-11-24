# Nhánh phổ NDVI/NDRE & LULC — Quang Anh

Script: `scripts/03_spectral_ndvi_analysis.py` · Test: `tests/test_spectral_ndvi.py`

## Cách chạy

```bash
python scripts/03_spectral_ndvi_analysis.py                              # toàn ảnh (~8 s)
python scripts/03_spectral_ndvi_analysis.py --window 1709 1717 1000 1000 \
       --outdir <thư mục tạm>                                           # thử trên crop 1000×1000
python -m pytest tests -q                                                # 21 test
```

Output trong `data/outputs/`:

| File | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `ndvi.tif`, `ndre.tif` | Float32, nodata = NaN | Cùng lưới với COG (EPSG:32630, 0.0413 m) |
| `lulc_class.tif` | Byte, nodata = 0 | 1 Cây tốt · 2 Cỏ/thưa · 3 Đất · 4 Nước; có bảng màu |
| `lulc_summary.json` | JSON | Đúng schema mục 4.4.C; thêm `total_valid_area_m2`, `total_valid_pixel_count`, `excluded_pixel_count` |
| `spectral_stats.json` | JSON | min/max/mean/std/percentile của NDVI, NDRE |
| `ndvi_preview.png` | PNG RGBA | RdYlGn, rescale −0.2…0.8 (giống TiTiler), nền trong suốt |

## Kiểm tra band 3/4/5 và xử lý pixel lỗi

- Band đọc theo index tường minh: 3 = Red, 4 = RedEdge, 5 = NIR (khớp `descriptions` trong COG).
- Chia 0: mẫu số = 0 → NaN (toàn ảnh có 6 px).
- Mask: pixel ngoài mask nội bộ → NaN / lớp 0 (4 895 985 px).
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

## Diện tích LULC (tổng 2,51 ha)

| Lớp | Diện tích (m²) | ha | % |
| :--- | ---: | ---: | ---: |
| 1 Cây xanh tốt (NDVI > 0,45) | 7 391,55 | 0,7392 | 29,49 |
| 2 Thảm cỏ / cây thưa (0,20–0,45) | 8 436,14 | 0,8436 | 33,65 |
| 3 Đất trống / nhà cửa (0–0,20) | 2 645,08 | 0,2645 | 10,55 |
| 4 Mặt nước / trũng ẩm (< 0) | 6 595,31 | 0,6595 | 26,31 |

## Việc cần QA tiếp (Ngày 5)

- Lớp 4 "Mặt nước" chiếm 26 %, chủ yếu ở mảng tây bắc. Cần đối chiếu ảnh RGB xem đây là nước thật hay đất ẩm/bóng/vùng phản xạ lạ; nếu không phải nước, cân nhắc thêm điều kiện NIR thấp cho lớp nước.
