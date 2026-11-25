# Note cho Hinh — Chuyển nhánh YOLO sang nhận diện tán cọ dầu

> Trạng thái: **đã chốt hướng**, đang chờ triển khai. Người nhận: Hinh. Người duyệt: Minh.
> Ngày tạo: 24/11/2026.

## 1. Quyết định

- **Dừng** hướng YOLO-COCO zero-shot cho `person`/`vehicle` trên plot_B03. Kết quả 12 box đã kiểm chứng là **false positive** do domain gap (xem `docs/yolo_qa.md` Mục 3), không dùng làm số liệu báo cáo.
- **Chuyển sang** fine-tune YOLO để nhận diện **tán cọ dầu** (class `palm`) trên chính plot_B03.
- **Giữ nguyên** pipeline: tiling → inference → NMS → pixel→GPS → GeoJSON → Leaflet. Chỉ đổi model, class và nguồn nhãn.

## 2. Vì sao hướng này đúng

1. **Đúng mục đích của dataset.** Bài mô tả dữ liệu (Lammoglia et al., 2024, *Data in Brief*, `doi:10.1016/j.dib.2024.110664`) ghi rõ dataset dùng để *"detect and count individual trees"*.
2. **Kích thước đối tượng khớp model.** Ở GSD ~4,3 cm:
   - Người: ~0,5 m → **~12 px** → COCO không thể nhận.
   - Tán cọ: 2–5 m → **50–120 px** → đúng vùng YOLO xử lý tốt.
3. **Có ý nghĩa thực địa.** Kết quả cho số cây, mật độ cọ/ha, phân bố đường kính tán — dùng được cho phần LULC và WebGIS, không chỉ để "demo".

## 3. Phạm vi

| Hạng mục | Chốt |
|---|---|
| Dữ liệu | plot_B03, ortho hiện có (`data/orthomosaic/multispectral_ortho.tif`) — **không tải plot khác** |
| Số class | **1 class duy nhất: `palm`** |
| CRS / COG | Không đổi |
| Output | `data/outputs/detections.geojson`, schema 4.4.B |

## 4. Thay đổi Hợp đồng dữ liệu 4.4.B

Thêm `palm` vào danh mục class:

```
person, vehicle, building, machinery, palm, other
```

Schema GeoJSON **không đổi** (vẫn `id, class_name, confidence, tile_id, center_lon, center_lat`), chỉ có thêm giá trị mới cho `class_name`.

Cần sửa đồng bộ 3 chỗ:
- [ ] `README.md` mục 4.4.B (danh mục class)
- [ ] `scripts/test_outputs.py` (whitelist class)
- [ ] `docs/yolo_qa.md` (bảng class + kết luận)

## 5. Quy tắc gán nhãn (bắt buộc tuân thủ)

**Gán:**
- Box ôm sát mép lá ngoài cùng của tán.
- Tán nhìn rõ, sắc nét, tách khỏi tán bên cạnh.
- Mỗi tán = 1 box.

**Không gán:**
- Tán bị nhòe do motion blur hoặc nằm trên đường ghép ảnh.
- Tán bị che > 50% hoặc chồng lên tán khác không tách được.
- Tán nhỏ < 1,5 m đường kính (cây non, không đủ đặc trưng).
- Box bao gồm nhiều tán.
- Vùng đất trống, bụi cỏ, bóng cây.

**Giữ ảnh âm (hard negative):** tile chỉ có đất trống/bụi (ví dụ tile `r03_c01`) vẫn đưa vào tập train với file nhãn rỗng.

## 6. Cấu trúc dữ liệu huấn luyện

```
data/yolo_palm/
├── images/
│   ├── train/*.jpg
│   └── val/*.jpg
├── labels/
│   ├── train/*.txt
│   └── val/*.txt
└── data.yaml
```

- Tile **640×640**, overlap 15% — dùng lại logic cắt tile của `scripts/extract_rgb.py`.
- Chỉ lấy tile có **≥ 95% pixel hợp lệ** (bỏ tile rìa trắng).
- Ưu tiên tile sắc nét, cọ trồng hàng (mẫu tốt: `r05_c05`). Hạn chế tile rừng rậm chồng tán.
- Chia **80/20 theo tile**, không chia theo box — tránh rò rỉ dữ liệu.

## 7. Khối lượng

- **15–20 tile**, khoảng **400–700 instance**.
- Nếu dưới **300 instance**: thiếu, phải thêm tile.
- Ước lượng thời gian gán: **4–6 giờ** (có thể giảm nếu pre-label bằng model palm có sẵn trên Roboflow).

## 8. Huấn luyện

| Thông số | Giá trị |
|---|---|
| Base model | `yolo11n.pt` (nếu kết quả kém thì thử `yolo11s.pt`) |
| `imgsz` | 640 |
| `epochs` | 60–80 |
| `batch` | 16 |
| Thiết bị | **Colab T4** (train CPU quá chậm) |
| Augment | mặc định, tắt mosaic ở 10 epoch cuối |

Lưu lại: `best.pt`, `results.csv`, `confusion_matrix.png` → đưa vào `docs/`.

> Lưu ý: trong `docs/yolo_qa.md` có ghi "yolo11n quá nhỏ, 0 phát hiện" — đó là kết quả với **person ~12 px**, không áp dụng cho tán cọ 50–120 px. Với tán cọ, nano thường đủ; nếu thiếu thì mới lên `s`.

## 9. Output bàn giao

- `data/outputs/detections.geojson` — class `palm`, đúng schema 4.4.B.
- Thống kê: **tổng số tán, mật độ tán/ha, phân bố đường kính tán (m)**.
- Ảnh QA: overlay detection trên ortho (1 ảnh) + confusion matrix (1 ảnh).
- Cập nhật `docs/yolo_qa.md`: **precision / recall / mAP50 trên tập val** — số thật, không ước lượng.

## 10. Kết quả person cũ

- **Không xoá.** Đổi tên thành `data/outputs/detections_person_baseline.geojson` và giữ làm **phụ lục "negative result"**.
- Dùng để so sánh: zero-shot COCO (thất bại) vs fine-tune trên domain UAV (có kết quả). Đây là điểm cộng học thuật.

## 11. Mốc thời gian

| Mốc | Việc | Deadline |
|---|---|---|
| M1 | Xong bộ tile + nhãn | __/__ |
| M2 | Xong train + eval trên val | __/__ |
| M3 | Tích hợp WebGIS + viết mục báo cáo | __/__ |

> Nếu tới M2 mà `mAP50 < 0.5`, báo Minh ngay để chốt phương án dự phòng, không tự kéo dài.

## 12. Việc cần Minh duyệt

- [x] Thêm class `palm` vào contract 4.4.B — đã cập nhật `README.md`, `scripts/test_outputs.py`, `docs/yolo_qa.md`.
- [x] Chốt tên class: **`palm`** (không dùng `oil_palm`, nhất quán với `data/yolo_palm/`).
- [x] Đổi tên file person cũ thành `data/outputs/detections_person_baseline.geojson`.

## 13. Lưu ý trung thực

- Chưa xác nhận loài 100%. Hình thái tán là **palm**, gần như chắc là **cọ dầu** (*Elaeis guineensis*); dừa hầu như không trồng ở Divo (nội địa). Nếu có điều kiện đối chiếu ảnh mặt đất/thực địa thì xác nhận lại.
- Kết quả val phải báo cáo đúng, kể cả khi thấp. Không viết "nhận diện chính xác" khi chưa có confusion matrix.
