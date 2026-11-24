# Báo cáo Kiểm thử chất lượng (QA) Nhận diện Đối tượng YOLO (Nhánh Hinh)

> ⚠️ **Kết luận chất lượng (đọc trước):** 12 box lớp `person` trong `detections.geojson` là kết quả **baseline** của YOLOv8m-COCO, **chưa được kiểm chứng thực địa**. Kiểm tra thủ công trên ảnh crop cho thấy **đa số là dương tính giả (false positive)** do domain gap: box nằm trên tán lá, đất trống hoặc rìa nền trắng, kích thước 0,23–26 m không tương thích với người thật. Kết quả này **chỉ dùng để kiểm thử pipeline/WebGIS**, không dùng làm số liệu "số người phát hiện" trong báo cáo. Muốn có kết quả thực địa cần fine-tune model trên dữ liệu UAV.

## 1. Thông số thực nghiệm chốt số liệu
- **Lệnh thực thi:**
  ```bash
  python3 scripts/02_yolo_drone_detection.py --model yolov8m.pt --device cpu --tile-size 640 --overlap 0.15 --conf 0.25 --iou 0.50
  ```
- **Thông số cấu hình:**
  - Mô hình (`model`): `yolov8m.pt` (25.9M tham số).
  - Thiết bị tính toán (`device`): **CPU** (Đồng nhất đa nền tảng macOS/Windows).
  - Kích thước ô cắt (`tile_size`): $640 \times 640$ pixels.
  - Độ chồng lấp (`overlap`): $15\%$ (bước nhảy 544 px) — *Đúng chuẩn Spec 4.3*.
  - Ngưỡng độ tin cậy (`conf`): $0.25$ — *Đúng chuẩn Spec 4.3*.
  - Ngưỡng khử trùng lặp (`iou`): $0.50$ (Class-Agnostic NMS) — *Đúng chuẩn Spec 4.3*.
  - Tổng số ô quét: 81 ô (67 ô hợp lệ, 14 ô nền đen NoData được bỏ qua).
  - Thời gian suy luận trên CPU: **7.67 giây** (trung bình 114.5 ms/ô).

## 2. Thống kê số liệu phát hiện (Dữ liệu nhất quán)
Ba con số dữ liệu đã được đối chiếu và khớp nhau hoàn toàn:
- **Số box thô hợp lệ trước NMS (`detections_raw.json`):** **16**
- **Số box sau khử trùng lặp NMS (`IoU = 0.50`):** **12**
- **Số Feature trong tệp GeoJSON (`detections.geojson`):** **12**

| Phân lớp chuẩn (Schema 4.4.B) | Số lượng phát hiện | Ghi chú |
| :--- | :---: | :--- |
| `person` | 12 | Box lớp `person` do model COCO gán; **chưa kiểm chứng thực địa**, phần lớn là false positive (xem Mục 3) |
| `vehicle` | 0 | Không có box `vehicle` sau lọc/mapping |
| **Tổng cộng** | **12 box baseline** | **Khớp 100% số Feature trong GeoJSON; không đồng nghĩa 12 người thật** |

## 3. Giới hạn kết quả và kiểm chứng thủ công

- **Kích thước box không hợp lệ về mặt vật lý.** Với pixel 0,0413 m, 12 box `person` có kích thước từ **5,6 × 6,2 px (0,23 × 0,26 m)** đến **91,3 × 636,1 px (3,8 × 26,3 m)**. Một người thực tế chỉ khoảng 0,4–0,6 m rộng × 1,6–1,8 m cao (≈ 10–15 × 39–44 px). Phần lớn box hoặc quá nhỏ, hoặc lớn hơn người hàng chục lần.
- **Kiểm tra trực quan.** Cắt ảnh nguồn tại đúng 12 bounding box và phóng to: không box nào chứa người; nội dung là tán lá, đất trống, bóng cây và vùng rìa nền trắng. Các box lớn (#3, #5, #6, #9) phủ cả vùng nền/rìa ảnh.
- **Phân bố bất thường.** Box tập trung ở rìa ảnh và trên tán rừng — nơi mô hình COCO thường phản ứng với kết cấu/độ tương phản, không phải vị trí có đối tượng.
- **Kết luận.** Đây là false positive do domain gap; **không sử dụng 12 box này làm số liệu nhận diện thực địa**. Giá trị của kết quả nằm ở việc chứng minh pipeline (tiling → inference → NMS → pixel→GPS → GeoJSON) chạy đúng và đúng schema.

## 4. Phân tích giới hạn Domain Gap (Lý do lọc bỏ nhãn rác)
- **Bản chất hiện tượng:** Mô hình YOLOv8 được tiền huấn luyện (pre-trained) trên tập dữ liệu COCO (chủ yếu là ảnh chụp phối cảnh ngang tầm mắt con người). Khi áp dụng trực tiếp mô hình này lên ảnh viễn thám UAV với góc nhìn thẳng đứng từ trên cao (nadir view) trên cánh đồng, xuất hiện sai lệch miền dữ liệu rõ rệt (**Domain Gap**).
- **Hệ quả thực nghiệm:** Kết cấu bề mặt hình thái tròn xoăn của các khóm tán lá/cây bụi nhìn từ trên cao có đặc trưng thị giác tương đồng với các lớp `broccoli`, `potted plant` trong COCO; một số bóng phản xạ hoặc vật thể nhỏ bị gán nhầm thành `bird`, `handbag`, `umbrella`, `skateboard`. Đây hoàn toàn là các **dương tính giả (False Positives)** do lệch miền dữ liệu, không phải đặc trưng thực địa.
- **Giải pháp xử lý:** Tuân thủ nghiêm ngặt Hợp đồng dữ liệu 4.4.B, áp dụng bộ lọc phân lớp (Class Filtering & Mapping): chỉ giữ lại các nhãn thuộc danh mục chuẩn (`person`, `vehicle`, `building`, `machinery`, `other`), loại bỏ các nhãn nhiễu ngoài domain. Lưu ý: "sạch" ở đây chỉ có nghĩa **đúng danh mục schema**, **không** có nghĩa các box còn lại là nhận diện đúng — như phân tích tại Mục 3, 12 box `person` vẫn là false positive.

## 5. Giải trình các sai lệch kỹ thuật so với Spec gốc
1. **Dữ liệu đầu vào (Tạm đọc Ortho EPSG:4326 thay vì COG):**
   - *Lý do:* Theo tiến độ Sprint 7 ngày, tệp COG `data/outputs/cog_multispectral.tif` thuộc trách nhiệm của Nam Anh (TV2) xuất bản ở Ngày 01–02. Để không làm nghẽn tiến độ nhánh AI của Hinh, script được chạy trực tiếp trên file trực giao nguồn `data/orthomosaic/multispectral_ortho.tif` (có cùng toạ độ và kênh phổ).
   - *Tính tương thích:* Mã nguồn `02_yolo_drone_detection.py` đã tích hợp sẵn cơ chế nhận diện tự động; khi Nam Anh bàn giao COG, hệ thống sẽ tự động ưu tiên nạp COG mà không cần sửa code.
2. **Lựa chọn mô hình (`yolov8m.pt` thay vì `yolo11n.pt`):**
   - *Lý do (có số liệu đối đầu thực nghiệm):* Đã thực nghiệm trực tiếp `yolo11n.pt` (Nano, 2.6M tham số) trên bộ ảnh với `conf=0.25`: mô hình nano quá nhỏ, không đủ năng lực biểu diễn để trích xuất vật thể nhỏ góc nhìn từ trên cao, dẫn đến **0 phát hiện** cho cả `person` lẫn `vehicle`.
   - *Hiệu quả:* Mô hình `yolov8m.pt` (Medium, 25.9M tham số) cho ra 12 box lớp `person` trong 7.67 giây trên CPU, đủ để chạy demo pipeline. Tuy nhiên **chất lượng nhận diện chưa đạt**: các box là false positive do domain gap (Mục 3), nên không thể coi là "nhận diện chính xác".
3. **Các tham số đã chuẩn hóa 100% về đúng Spec:**
   - Độ chồng lấp: Đã đưa về đúng **15%** (bước nhảy 544 px).
   - Ngưỡng IoU: Đã đưa về đúng **0.50**.
   - Ngưỡng confidence: Đã đưa về đúng **0.25**.

## 6. Kiểm định Schema Hợp đồng dữ liệu 4.4.B
Tệp `data/outputs/detections.geojson` đã được kiểm thử tự động bằng `scripts/test_outputs.py` và xác nhận đạt chuẩn **schema** 100% (chỉ kiểm tra cấu trúc/thuộc tính, **không** đánh giá độ chính xác nhận diện):
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
            [-5.1896773, 5.9275229],
            [-5.1896637, 5.9275229],
            [-5.1896637, 5.9275086],
            [-5.1896773, 5.9275086],
            [-5.1896773, 5.9275229]
          ]
        ]
      },
      "properties": {
        "id": 1,
        "class_name": "person",
        "confidence": 0.48,
        "tile_id": "r000_c004",
        "center_lon": -5.1896773,
        "center_lat": 5.9275229
      }
    }
  ]
}
```
- Không còn trường `center_gps` dạng mảng; đã tách độc lập thành `center_lon` và `center_lat`.
- Bổ sung trường truy vết ô cắt `tile_id` (ví dụ `r000_c004`).
- Thuộc tính `class_name` chỉ chứa nhãn nằm trong danh mục cho phép.
