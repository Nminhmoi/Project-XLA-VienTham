# Báo Cáo Kiểm Thử Chất Lượng (QA) — Nhận Diện Tán Cọ Dầu YOLO (Nhánh Hinh)

> **Cập nhật ngày 26/11/2026:**
> - **Đã chuyển hướng & hoàn tất nghiệm thu:** Hủy bỏ hoàn toàn kết quả YOLO-COCO cũ (12 box `person` false positive), hoàn thành fine-tune mô hình **`yolo11n.pt`** nhận diện **tán cọ dầu (class `palm`)** trên `plot_B03`.
> - **Đạt tiêu chuẩn M2:** `mAP50 = 0.7319 >= 0.50` trên tập validation (`Precision = 0.7147`, `Recall = 0.7037`).
> - **Xuất bàn giao WebGIS:** `data/outputs/detections.geojson` (**289 Features**, chuẩn Schema 4.4.B) và `data/outputs/palm_stats.json`.

---

## 1. Cơ Sở Khoa Học & Điều Chỉnh Kỹ Thuật

| Tiêu chí so sánh | Hướng cũ: YOLO-COCO (`person`/`vehicle`) | Hướng mới: Fine-tuned YOLO (`palm`) |
| :--- | :--- | :--- |
| **Kích thước đối tượng** | Người ~0.5 m $\to$ **~12 px** (quá nhỏ đối với YOLO) | Tán cọ 2–12 m $\to$ **73–303 px** (TB ~114 px, tối ưu cho YOLO) |
| **Độ phù hợp Dataset** | Không phù hợp góc nhìn nadir từ trên cao | Khớp mục tiêu dataset (Lammoglia et al., 2024: *"detect and count individual trees"*) |
| **Kết quả thực nghiệm** | **Đã hủy bỏ toàn bộ** | **289 tán**, mật độ **115.33 cây/ha**, đạt Schema 4.4.B |

### Các lỗi kỹ thuật quan trọng đã phát hiện và khắc phục:
1. **Chuẩn hóa RGB (`scripts/extract_rgb.py`):** Dữ liệu gốc `multispectral_ortho.tif` là DN thô 16-bit chưa hiệu chuẩn bức xạ (`Blue p50=23525 > Red p50=16293`). Đã chuyển sang kéo tương phản chung (`stretch_rgb_joint`), đọc band qua `Description` (`Red=3, Green=2, Blue=1`), ghi kèm internal mask và ưu tiên đọc `cog_multispectral.tif` theo Hợp đồng 4.4.A.
2. **Chất lượng bộ nhãn (`data/yolo_palm/`):** Loại bỏ hoàn toàn nhãn heuristic `ExG` cũ (từng gây lỗi bỏ sót cọ trưởng thành ngả tím và gán nhầm cỏ dại, chỉ đạt `mAP50 = 0.4240`), thay bằng **318 nhãn kiểm tra trực quan** (`264` Train trên 31 tile, `54` Val trên 6 tile, kèm 4 tile âm 0 nhãn; kiểm định 100% qua `scripts/test_dataset.py`).
3. **Sửa siêu tham số train (`scripts/train_palm_yolo.py`):** Chuyển từ `batch=16` (chỉ 1 bước gradient/epoch) sang `batch=4, epochs=150, close_mosaic=15` giúp mô hình hội tụ thực sự (`mAP50` tăng từ `0.4240` lên `0.7319`).
4. **Sửa lỗi truyền sai kênh RGB $\to$ BGR & lọc mảnh mép tile (`scripts/02_yolo_drone_detection.py`):** Ultralytics `model.predict(np.ndarray)` nhận đầu vào BGR như OpenCV `cv2.imread()`. Sau khi đảo `patch[:, :, ::-1]`, các tán cọ lớn màu sẫm được phát hiện đầy đủ, đồng thời bổ sung `suppress_tile_edge_fragments()` để loại bỏ các nửa box bị cắt tại đường viền chồng lấp 15% giữa các tile.

---

## 2. Kết Quả Huấn Luyện & Kiểm Định Validation (Giai đoạn 4 — Checkpoint M2)

- **Lệnh thực thi:**
  ```bash
  python3 scripts/train_palm_yolo.py --model yolo11n.pt --batch 4 --epochs 150 --patience 35 --close-mosaic 15
  ```
- **Cấu hình:** `yolo11n.pt` (2,597,051 tham số), `imgsz=640`, `batch=4`, `epochs=150` (`0.222` giờ trên CPU `Apple M1 Pro`).
- **Tập dữ liệu:** 31 tile Train (`264` box, gồm 3 tile âm rỗng) / 6 tile Val (`54` box, gồm 1 tile âm `r003_c001`, 1 tile thưa `r003_c002`, 4 tile tán cọ `r002_c004`, `r004_c003`, `r006_c003`, `r006_c004`).

| Lần chạy | Cấu hình & Nhãn | Precision (P) | Recall (R) | $mAP_{50}$ | $mAP_{50-95}$ | Kết luận M2 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| Thử nghiệm cũ (đã bỏ) | `batch=16`, 70 epoch, nhãn `ExG` | 0.3292 | 0.6726 | 0.4240 | 0.2013 | ❌ Chưa đạt (`< 0.50`) |
| **Bản chính thức (`docs/best.pt`)** | **`batch=4`, 150 epoch, 318 nhãn trực quan** | **0.7147** | **0.7037** | **0.7319** | **0.3182** | ✅ **Đạt chuẩn M2** ($\ge 0.50$) |

- **Ghi nhận ma trận nhầm lẫn (`docs/confusion_matrix.png`):** Tại tập Val `54` nhãn, số lượng khớp đúng đạt **54/54** ở mức ngưỡng thấp nội bộ của YOLO `val` (khi tính kèm các ứng viên nền độ tin cậy thấp trước hậu xử lý; chi tiết trực quan xem `runs/palm_detect/yolo11n_palm/val_batch0_pred.jpg`, trong đó tile âm `r003_c001` hầu như sạch hoàn toàn và toàn bộ tán cọ lớn/trung bình đều nhận `conf = 0.6–0.9`).

---

## 3. Kết Quả Suy Luận Toàn Ảnh & Thống Kê Lâm Nghiệp (Giai đoạn 5)

- **Lệnh thực thi:**
  ```bash
  python3 scripts/02_yolo_drone_detection.py --model docs/best.pt --conf 0.25 --iou 0.50
  ```
- **Nguồn ảnh & Tham số:** `data/outputs/ortho_rgb_3band.tif` (`4396 × 4411 px`, EPSG:4326, fallback từ `data/orthomosaic/multispectral_ortho.tif` do máy chưa có `cog_multispectral.tif`), tile `640×640`, overlap `15%`, `66/81` ô hợp lệ, thời gian suy luận CPU **`2.81 giây`** (`42.7 ms/ô`).

### Đối chiếu nhất quán 3 con số đầu ra:
- **Số box thô hợp lệ trước NMS (`data/outputs/detections_raw.json`):** **`399`**
- **Số tán sau NMS (`IoU = 0.50`) & lọc cắt mép tile:** **`289`**
- **Số Feature trong tệp GeoJSON (`data/outputs/detections.geojson`):** **`289`** (khớp 100%)

### Thống kê lâm nghiệp (`data/outputs/palm_stats.json`):
| Chỉ số | Giá trị thực tế |
| :--- | :---: |
| **Tổng số tán phát hiện (`class_name = "palm"`)** | **289** |
| **Diện tích hợp lệ lô plot_B03** | **2.5059 ha** |
| **Mật độ tán cây** | **115.33 cây/ha** |
| **Đường kính tán nhỏ nhất / Trung vị / Trung bình / Lớn nhất** | **2.07 m / 3.78 m / 4.49 m / 12.44 m** |

---

## 4. Kiểm Định Schema 4.4.B & Lưu Ý Trung Thực

- Đã chạy kiểm thử tự động `python3 scripts/test_outputs.py`: **`detections.geojson` đạt chuẩn Schema 4.4.B 100%** (Polygon khép kín EPSG:4326 lon/lat, đủ 6 trường `id`, `class_name`, `confidence`, `tile_id`, `center_lon`, `center_lat`, `class_name` chỉ chứa `palm`). Ảnh trực quan toàn vùng: `data/outputs/detections_visualized.jpg` (`2.28 MB`).
- **Lưu ý trung thực (Mục 13 `Docs/note_hinh_tan_cay.md`):**
  1. Hình thái tán nhận diện là **tán dạng cọ hình sao (`palm`)**, bao gồm cả cây cọ dầu trưởng thành (*Elaeis guineensis*, tán 5–12 m) và các tán dạng cọ trẻ/cây một lá mầm hình sao (2–4.5 m) phân bố xen canh trên plot_B03, chưa có khảo sát thực địa trực tiếp tại Divo để phân biệt 100% loài cho nhóm cây non.
  2. Trên máy Hinh hiện chưa có `data/outputs/cog_multispectral.tif` (EPSG:32630) nên script tự fallback sang `multispectral_ortho.tif` (EPSG:4326); mã nguồn đã sẵn sàng tự ưu tiên COG khi có tệp 4.4.A.
