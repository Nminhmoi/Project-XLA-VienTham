# Báo Cáo Kiểm Thử Chất Lượng (QA) & Kế Hoạch Nhận Diện Tán Cọ Dầu (Nhánh Hinh)

> **Cập nhật ngày 24/11/2026:**
> - Toàn bộ 12 box nhãn `person` trước đây từ mô hình YOLOv8m-COCO zero-shot đã được xác nhận là **dương tính giả (False Positive)** do lệch miền dữ liệu (Domain Gap: người chỉ chiếm ~12 px ở GSD 4.3 cm).
> - **Đã dọn dẹp sạch sẽ:** Toàn bộ kết quả cũ (`detections.geojson`, `detections_raw.json`, `detections_visualized.jpg`) đã được xóa bỏ để chuẩn bị cho dữ liệu mới.
> - **Chuyển hướng chính thức:** Thực hiện fine-tune YOLO trên dữ liệu UAV để nhận diện chuyên biệt **tán cọ dầu (class `palm`)** trên plot B03, bám sát tài liệu chỉ đạo `Docs/note_hinh_tan_cay.md` và kế hoạch `docs/cac_buoc_xu_ly_tan_cay.md`.

---

## 1. Cơ Sở Khoa Học Của Việc Chuyển Hướng

| Tiêu chí so sánh | Hướng cũ: YOLO-COCO (`person`/`vehicle`) | Hướng mới: Fine-tuned YOLO (`palm`) |
| :--- | :--- | :--- |
| **Kích thước đối tượng** | Người ~0.5 m $\to$ **~12 px** (quá nhỏ đối với YOLO) | Tán cọ 2–5 m $\to$ **50–120 px** (kích thước tối ưu) |
| **Độ phù hợp Dataset** | Không phù hợp góc nhìn nadir view từ trên cao | Đúng mục đích gốc của dataset (Lammoglia et al., 2024: *"detect and count individual trees"*) |
| **Ý nghĩa thực địa** | Không có giá trị thực tiễn (100% false positive) | Cung cấp số lượng cây, mật độ cọ/ha, phân bố đường kính tán phục vụ phân tích lâm nghiệp và WebGIS |
| **Trạng thái kết quả** | **Đã hủy bỏ toàn bộ** | **Đang chuẩn bị bộ dữ liệu gán nhãn** |

---

## 2. Thông Số Huấn Luyện & Kiểm Thử Thực Nghiệm (Giai đoạn 4)

- **Lệnh thực thi:** `python3 scripts/train_palm_yolo.py`
- **Cấu hình mô hình:** `yolo11n.pt` (2,597,051 tham số), `imgsz=640`, `epochs=70`, `batch=16`, `close_mosaic=10`.
- **Môi trường chạy thực tế:** CPU (`Apple M1 Pro`), thời gian chạy 70 epoch: `0.041` giờ (~147 giây).
- **Dữ liệu huấn luyện:** 13 tile train (358 instance) / 5 tile val (113 instance), chia 80/20 theo tile độc lập.
- **Chỉ tiêu nghiệm thu (Checkpoint M2):** $mAP_{50} \ge 0.50$ trên tập validation.

### Bảng số liệu đo kiểm trên tập Validation (`best.pt`):
| Mô hình | Số ảnh Val (Instances) | Precision (P) | Recall (R) | $mAP_{50}$ | $mAP_{50-95}$ | Trạng thái M2 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `yolo11n_palm` (epoch 70, `batch=16`) | 5 (113) | **0.3292** | **0.6726** | **0.4240** | **0.2013** | ⚠️ **Chưa đạt M2** ($mAP_{50} < 0.50$) |

**Chi tiết Ma trận nhầm lẫn (`docs/confusion_matrix.png`):**
- True Positive (`palm` $\to$ `palm`): **104** / 113 tán.
- False Negative (`palm` bị sót thành `background`): **9** tán.
- False Positive (`background` bị dự đoán nhầm thành `palm`): **1396** box (chủ yếu ở ngưỡng `conf` thấp `0.3–0.4`).

**Phân tích nguyên nhân $mAP_{50} = 0.4240 < 0.50$:**
1. **Thiếu số bước cập nhật trọng số (Under-training):** Với 13 ảnh train và `batch=16`, mỗi epoch chỉ thực hiện đúng **1 bước gradient step** (70 bước qua 70 epoch). Đến epoch 70, `val/cls_loss` vẫn đang giảm mạnh (`128.997` $\to$ `3.589`) và `mAP50` vẫn đang tăng (`0.2565` ở epoch 50 $\to$ `0.4253` ở epoch 70) nhưng đã dừng train.
2. **Chất lượng nhãn bán tự động (`ExG`):** Kiểm tra trực quan `val_batch0_labels.jpg` cho thấy một số tán cọ màu tối/tím ở `r05_c02` bị bỏ sót, trong khi một số bụi cỏ xanh sáng hoặc mảnh lá được gán nhãn.
3. **Bước tiếp theo theo quy định M2:** Cần báo cáo Minh và chốt phương án xử lý (chỉnh sửa nhãn thủ công / giảm `batch=4` + tăng `epochs=150–200` / thử `yolo11s.pt`) trước khi tiếp tục suy luận toàn ảnh.

---

## 3. Khung Đo Kiểm & Thống Kê Lâm Nghiệp Sau Suy Luận (Giai đoạn 5)

Sau khi hoàn tất suy luận toàn ảnh với NMS ($IoU = 0.50$, $conf \ge 0.25$), các chỉ số sau sẽ được tính toán và công bố:

1. **Tổng số tán cọ dầu phát hiện:** Khớp 100% giữa số box sau NMS và số Feature trong `data/outputs/detections.geojson`.
2. **Diện tích vùng khảo sát (plot B03):** Dự kiến ~2.51 ha.
3. **Mật độ tán cây:** 
   $$\text{Mật độ} = \frac{\text{Tổng số tán cọ phát hiện}}{\text{Diện tích (ha)}} \quad (\text{cây/ha})$$
4. **Phân bố kích thước tán:** Đường kính tán (m) = kích thước box (px) $\times 0.0413$ m/px.

---

## 4. Hợp Đồng Dữ Liệu Schema 4.4.B Cho Lớp `palm`

Tệp `data/outputs/detections.geojson` sẽ tuân thủ nghiêm ngặt Schema 4.4.B:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [-5.1897, 5.9267],
            [-5.1896, 5.9267],
            [-5.1896, 5.9268],
            [-5.1897, 5.9268],
            [-5.1897, 5.9267]
          ]
        ]
      },
      "properties": {
        "id": 1,
        "class_name": "palm",
        "confidence": 0.88,
        "tile_id": "r003_c012",
        "center_lon": -5.1897,
        "center_lat": 5.9267
      }
    }
  ]
}
```
- Lớp đối tượng: `class_name: "palm"`.
- Hệ quy chiếu: EPSG:4326 (WGS 84, Longitude / Latitude).
- Kiểm tra tự động bằng `scripts/test_outputs.py`.
