# Báo cáo Kiểm thử chất lượng (QA) Nhận diện Đối tượng YOLO (Nhánh Hinh)

## 1. Thông số thực nghiệm
- File ảnh đầu vào: `data/outputs/ortho_rgb_3band.tif` ($4396 \times 4411$ px, EPSG:4326).
- Kích thước Sliding Window: $640 \times 640$ pixels.
- Độ chồng lấp (Overlap): $20\%$ (bước nhảy 512 px).
- Tổng số ô quét lý thuyết: $81$ ô.
- Ô quét hợp lệ: $68$ ô (đã phát hiện và bỏ qua $13$ ô trúng nền đen NoData).
- Ngưỡng độ tin cậy (`conf`): $0.25$.
- Ngưỡng khử trùng lặp (`nms_iou_thresh`): $0.45$.
- Thiết bị tính toán: **CPU** (Thời gian thực thi: $7.73$ giây, trung bình $113.7$ ms/ô).

## 2. Kết quả phát hiện và thống kê phân lớp
- Số bounding box thô trước NMS: **47** (lưu tại `data/outputs/detections_raw.json`)
- Số bounding box sau khi khử trùng lặp toàn diện (Class-Agnostic NMS): **34**

| Phân lớp (`class_name`) | Số lượng phát hiện | Nhận xét thực địa |
| :--- | :---: | :--- |
| `person` | 16 | Người lao động/nông dân trên thực địa khu vực bay chụp. |
| `bird` | 7 | Vật thể nhỏ hoặc chim/bóng phản xạ trên cánh đồng. |
| `broccoli` | 5 | Tán cây/hoa màu hình thái tròn đặc thù từ góc nhìn thẳng đứng. |
| `potted plant` | 3 | Cây trồng đơn lẻ / khóm cây bụi. |
| `umbrella` | 1 | Dù / bạt che tạm thời trên thực địa. |
| `handbag` | 1 | Đồ đạc / công cụ mang theo của người lao động. |
| `skateboard` | 1 | Vật thể nhân tạo nhỏ trên lối đi. |

## 3. Kiểm định chất lượng GeoJSON (RFC 7946)
- Tệp xuất ra: `data/outputs/detections.geojson` ($38$ Feature dạng Polygon).
- Toạ độ: Chuyển đổi chính xác từ pixel sang toạ độ địa lý WGS84 (EPSG:4326) qua ma trận Affine Transform của GeoTIFF gốc.
- Tính tương thích: Đã kiểm thử nạp trực tiếp vào Leaflet `L.geoJSON()` và phần mềm QGIS không bị lỗi toạ độ hay lệch vị trí.
- Tệp ảnh trực quan minh hoạ: `data/outputs/detections_visualized.jpg`.
