# Kế Hoạch & Các Bước Xử Lý: Nhận Diện Tán Cọ Dầu (Palm Tree Detection) Bằng YOLO

> **Tài liệu tham chiếu:** `docs/note_hinh_tan_cay.md`  
> **Người thực hiện:** Hinh (Nhánh AI / YOLO)  
> **Người duyệt:** Minh / User  
> **Dữ liệu thực nghiệm:** Plot B03 (`data/orthomosaic/multispectral_ortho.tif` / `data/outputs/ortho_rgb_3band.tif`)  
> **Mục tiêu:** Chuyển đổi từ hướng zero-shot COCO sang fine-tune YOLO nhận diện chuyên biệt tán cọ dầu (`palm`), xuất dữ liệu chuẩn WebGIS Schema 4.4.B và thống kê chỉ số lâm nghiệp.  
> **Quy tắc làm việc:** Với mỗi giai đoạn, trình bày chi tiết hướng xử lý code để người dùng duyệt và xác nhận trước khi thực hiện chỉnh sửa hoặc chạy script.

---

## 1. Tổng Quan & Bối Cảnh Chuyển Đổi

- **Vấn đề đã xác nhận:** Ở độ phân giải mặt đất GSD ~4.3 cm/pixel, đối tượng người (~0.5 m) chỉ chiếm ~12 pixel — quá nhỏ so với ngưỡng nhận diện của YOLO COCO, dẫn đến 12 box trước đó là *false positive* do domain gap.
- **Xử lý triệt để:** **Không bảo lưu** các kết quả cũ (đã xóa toàn bộ file `detections.geojson`, `detections_raw.json`, `detections_visualized.jpg`).
- **Giải pháp tối ưu:** Chuyển sang nhận diện **tán cọ dầu** (kích thước 2–5 m, tương đương 50–120 pixel). Đây là kích thước lý tưởng cho kiến trúc YOLO, khớp chính xác mục đích nguyên bản của bộ dữ liệu (Lammoglia et al., 2024: *"detect and count individual trees"*).
- **Kế thừa kiến trúc:** Giữ nguyên 100% pipeline kỹ thuật: Cắt tile (tiling) $\to$ Suy luận (inference) $\to$ Khử trùng lặp (NMS) $\to$ Chuyển đổi tọa độ Affine (Pixel $\to$ GPS EPSG:4326) $\to$ Xuất GeoJSON $\to$ Tích hợp WebGIS Leaflet.

---

## 2. Quy Trình Xử Lý Chi Tiết (5 Giai Đoạn)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Giai đoạn 1: Dọn dẹp kết quả cũ & Đồng bộ Hợp đồng Dữ liệu 4.4.B       │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ Giai đoạn 2: Cắt Tile, Chọn mẫu đại diện & Lập bộ dữ liệu gán nhãn     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ Giai đoạn 3: Gán nhãn Bounding Box (Annotation) chuẩn YOLO             │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ Giai đoạn 4: Huấn luyện Fine-tune mô hình YOLO trên Google Colab T4    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────────────┐
│ Giai đoạn 5: Tích hợp Pipeline suy luận toàn ảnh, Thống kê & QA        │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Giai đoạn 1: Dọn Dẹp Kết Quả Cũ & Cập Nhật Hợp Đồng Dữ Liệu (Đang thực hiện)

1. **Xóa sạch kết quả cũ:**
   - Xóa bỏ triệt để các file kết quả cũ phát hiện người:
     `rm -f data/outputs/detections.geojson data/outputs/detections_raw.json data/outputs/detections_visualized.jpg`
2. **Cập nhật Hợp đồng Dữ liệu (Schema 4.4.B):**
   - Thêm lớp `palm` vào danh mục class cho phép:
     `ALLOWED_CLASSES = {"vehicle", "building", "machinery", "person", "palm", "other"}`
   - Trình duyệt và đồng bộ hóa code/tài liệu ở 3 vị trí:
     - [ ] `README.md` (Mục 4.4.B Data Contract, bảng phân công nhiệm vụ).
     - [ ] `scripts/test_outputs.py` (Whitelist kiểm tra class `palm`).
     - [ ] `docs/yolo_qa.md` (Ghi nhận chuyển hướng tán cọ dầu và cấu trúc QA mới).

---

### Giai đoạn 2: Cắt Tile & Chuẩn Bị Bộ Dữ Liệu Huấn Luyện

1. **Cắt tile tự động từ ảnh Ortho RGB:**
   - Sử dụng ảnh chuẩn hóa: `data/outputs/ortho_rgb_3band.tif` ($4396 \times 4411$ px).
   - Kích thước ô cắt: **$640 \times 640$ pixels**, bước nhảy (stride): $544$ px (độ chồng lấp **$15\%$** đúng spec).
2. **Lọc tile chất lượng cao:**
   - Chỉ giữ các tile có **tỷ lệ pixel hợp lệ $\ge 95\%$** (loại bỏ triệt để các tile mép viền, nền trắng NoData).
   - Lọc ra khoảng 15–20 tile đại diện:
     - Ưu tiên các tile có mật độ cọ rõ nét, trồng theo hàng lối đều đặn (ví dụ vùng `r05_c05`).
     - Bổ sung 1–2 tile âm cứng (*hard negative*: đất trống, đường nội đồng, bụi cỏ không có tán cọ như `r03_c01`) với file nhãn rỗng.
3. **Phân chia tập dữ liệu Train / Val:**
   - **Quy tắc bắt buộc:** Chia **80% Train / 20% Val theo Tile** (tuyệt đối không chia theo box để tránh rò rỉ dữ liệu giữa các ảnh).
   - Cấu trúc thư mục:
     ```
     data/yolo_palm/
     ├── images/
     │   ├── train/   # 12-16 ảnh .jpg (640x640)
     │   └── val/     # 3-4 ảnh .jpg (640x640)
     ├── labels/
     │   ├── train/   # File .txt tương ứng (YOLO format)
     │   └── val/     # File .txt tương ứng
     └── data.yaml    # Cấu hình dataset
     ```
   - Nội dung file `data/yolo_palm/data.yaml`:
     ```yaml
     path: ../data/yolo_palm
     train: images/train
     val: images/val
     names:
       0: palm
     ```

---

### Giai đoạn 3: Gán Nhãn Bounding Box (Annotation)

1. **Quy tắc gán nhãn nghiêm ngặt:**
   - **Gán (Positive):**
     - Bounding box ôm sát viền lá ngoài cùng của tán cọ.
     - Tán sắc nét, nhìn rõ tâm và hình thái tỏa tròn đặc trưng.
     - Mỗi tán cây tương ứng duy nhất 1 box (`class: 0`).
   - **Không gán (Negative/Ignore):**
     - Tán bị nhòe nặng do mép ghép ảnh (ortho seamline) hoặc motion blur.
     - Tán bị che khuất $> 50\%$ hoặc lồng ghép không thể tách biệt.
     - Cây con quá nhỏ (đường kính $< 1.5$ m, tương đương $< 35$ px).
     - Không vẽ 1 box gom nhiều tán gần nhau.
2. **Khối lượng & Chiến lược tăng tốc:**
   - **Chỉ tiêu:** 15–20 tile, đạt **400 – 700 instance** (tối thiểu $> 300$ instance).
   - **Công cụ:** LabelImg, CVAT, hoặc Roboflow.
   - **Mẹo tối ưu:** Sử dụng mô hình palm pre-trained có sẵn trên Roboflow Universe để gán nhãn tự động bước đầu (*pre-label*), sau đó kiểm tra và nắn chỉnh thủ công $\to$ giảm thời gian từ 5 giờ xuống còn 1.5–2 giờ.

---

### Giai đoạn 4: Huấn Luyện Fine-Tune Mô Hình (`scripts/train_palm_yolo.py`)

1. **Cấu hình huấn luyện (Training Specs — đã chỉnh cho tập tile nhỏ):**
   - **Môi trường:** CPU cục bộ (Apple Silicon ~2–4 phút cho 150 epoch trên 13 tile) hoặc Google Colab T4.
   - **Base Model:** `yolo11n.pt` (kích thước nhỏ nhẹ, tốc độ cao; nếu mAP chưa đạt mới thử `yolo11s.pt`).
   - **Lưu ý quan trọng về Batch & Epoch:** Vì tập train chỉ có ~12–16 tile, **không dùng `batch=16`** (gây 1 step/epoch, thiếu bước cập nhật gradient). Cần dùng **`batch=4`** và **`epochs=150`** (`patience=35`, `close_mosaic=15`) để mô hình hội tụ đầy đủ.
   - **Tham số tối ưu:**
     ```bash
     python3 scripts/train_palm_yolo.py --model yolo11n.pt --batch 4 --epochs 150 --close-mosaic 15
     ```
2. **Đánh giá & Trích xuất kết quả:**
   - Đánh giá trên tập Validation: Precision, Recall, $mAP_{50}$, $mAP_{50-95}$.
   - **Điều kiện dừng/nghiệm thu (Checkpoint M2):** $mAP_{50} \ge 0.50$. *(Nếu $< 0.50$, báo ngay cho Minh để xem xét bổ sung nhãn hoặc chuyển sang `yolo11s.pt`)*.
   - Thu thập artifacts xuất ra thư mục `docs/`:
     - Trọng số tối ưu: `best.pt`
     - Bảng số liệu: `results.csv`
     - Đồ thị đánh giá: `confusion_matrix.png`, `val_batch0_labels.jpg`, `val_batch0_pred.jpg`.

---

### Giai đoạn 5: Tích Hợp Suy Luận Toàn Ảnh, Thống Kê & Bàn Giao WebGIS

1. **Cập nhật script suy luận `scripts/02_yolo_drone_detection.py`:**
   - Tải trọng số `best.pt` đã fine-tune cho class `palm`.
   - Cắt tile sliding window toàn ảnh ($640 \times 640$, overlap 15%).
   - Áp dụng Class-Agnostic NMS ($IoU = 0.50$, $conf \ge 0.25$).
   - Chuyển đổi tọa độ Affine: $(x, y) \to (\text{lon}, \text{lat})$ theo EPSG:4326.
   - Xuất file kết quả chuẩn Schema 4.4.B: `data/outputs/detections.geojson`.
2. **Tính toán số liệu phân tích lâm nghiệp (Forestry Metrics):**
   - **Tổng số cây:** Số lượng Feature hợp lệ trong file GeoJSON.
   - **Mật độ tán cây (cây/ha):**
     $$\text{Mật độ} = \frac{\text{Tổng số cây}}{\text{Diện tích lô đất (ha)}}$$
   - **Phân bố đường kính tán ($m$):** Tính từ kích thước bounding box $(w, h)$ nhân với GSD ($0.043\text{ m/px}$).
3. **Kiểm thử tự động & Báo cáo QA:**
   - Chạy kiểm tra chuẩn schema:
     ```bash
     python3 scripts/test_outputs.py
     ```
   - Cập nhật tài liệu `docs/yolo_qa.md`: Báo cáo số liệu val chính thức, ma trận nhầm lẫn từ mô hình fine-tuned.

---

## 3. Phân Công & Mốc Thời Gian Triển Khai (Milestones)

| Mốc | Nội dung công việc | Đầu ra (Deliverables) | Dự kiến |
|:---:|:---|:---|:---:|
| **M1** | Dọn dẹp dữ liệu cũ, chuẩn bị tile và gán nhãn 15–20 tile | Thư mục `data/yolo_palm/` hoàn chỉnh nhãn train/val | Ngày 1 |
| **M2** | Fine-tune YOLO trên Colab T4, đánh giá val ($mAP_{50} \ge 0.5$) | `best.pt`, `results.csv`, `confusion_matrix.png` | Ngày 2 |
| **M3** | Chạy inference toàn ảnh, xuất GeoJSON 4.4.B & thống kê mật độ | `data/outputs/detections.geojson`, `docs/yolo_qa.md` | Ngày 3 |
| **M4** | Tích hợp WebGIS (bàn giao bạn Đức), hoàn thiện mục báo cáo | WebGIS hiển thị tán cọ, mục báo cáo Word hoàn chỉnh | Ngày 4 |
