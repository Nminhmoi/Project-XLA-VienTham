# Hướng dẫn cài đặt và thiết lập môi trường YOLO (Nhánh Hinh)

## 1. Môi trường yêu cầu
- Python 3.10+ (Đã xác minh và chạy tốt trên Python 3.14 macOS/Windows).
- Các thư viện cốt lõi:
  ```bash
  pip install ultralytics pyproj rasterio pillow torch torchvision
  ```

## 2. Mô hình nhận diện
- Model: `yolov8m.pt` (kích thước 49.7 MB).
- Thiết bị tính toán: **CPU** (đảm bảo tính tương thích và đồng nhất 100% trên cả macOS, Windows và Linux mà không phụ thuộc GPU).
- Nguồn tải weights: Tự động tải từ Ultralytics release khi chạy lần đầu hoặc lưu trực tiếp tại thư mục gốc.

## 3. Kiểm thử suy luận (Inference test)
Chạy script kiểm thử để nạp mô hình và suy luận:
```bash
python3 scripts/02_yolo_drone_detection.py --conf 0.25
```
Kết quả kiểm thử cho thấy mô hình hoạt động ổn định trên CPU với tốc độ trung bình ~113.7 ms/ô cắt.
