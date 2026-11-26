# Hướng dẫn cài đặt và vận hành nhánh YOLO (Thành viên Hinh)

## 1. Môi trường yêu cầu
- Python 3.10+ (đã kiểm chứng trên Python 3.14 macOS/Windows).
- Cài đặt thư viện từ file gốc:
  ```bash
  pip install -r requirements.txt
  ```
  Các thư viện cốt lõi của nhánh AI: `ultralytics`, `torch`, `torchvision`, `rasterio`, `pyproj`, `pillow`, `opencv-python`, `numpy`, `pyyaml`.

## 2. Mô hình nhận diện
- **Hướng hiện tại:** Fine-tune **`yolo11n.pt`** (hoặc `yolo11s.pt`) để nhận diện chuyên biệt **tán cọ dầu (class `palm`)** trên plot_B03 (xem `Docs/note_hinh_tan_cay.md`).
- **Weights sau fine-tune:** Lưu tại `docs/best.pt`.
- **Thiết bị suy luận:** **CPU** (đảm bảo đồng nhất trên macOS và Windows).

## 3. Chuỗi lệnh chuẩn theo Pipeline dự án
1. **Tách ảnh RGB 8-bit chuẩn hóa** (ưu tiên `data/outputs/cog_multispectral.tif` theo Hợp đồng 4.4.A, fallback sang `data/orthomosaic/multispectral_ortho.tif` nếu chưa có COG):
   ```bash
   python3 scripts/extract_rgb.py
   ```
2. **Cắt tile 640×640 (overlap 15%) chuẩn bị gán nhãn:**
   ```bash
   python3 scripts/prepare_palm_dataset.py
   ```
3. **Kiểm tra bộ dữ liệu sau khi gán nhãn chuẩn tại `data/yolo_palm/labels/`:**
   ```bash
   python3 scripts/test_dataset.py
   ```
4. **Huấn luyện fine-tune YOLO (`batch=4`, `epochs=150` cho tập tile nhỏ):**
   ```bash
   python3 scripts/train_palm_yolo.py --model yolo11n.pt --batch 4 --epochs 150
   ```
5. **Chạy suy luận toàn ảnh & xuất GeoJSON Schema 4.4.B + thống kê mật độ cọ/ha:**
   ```bash
   python3 scripts/02_yolo_drone_detection.py --model docs/best.pt --conf 0.25 --iou 0.50
   ```
6. **Kiểm thử hợp đồng dữ liệu đầu ra:**
   ```bash
   python3 scripts/test_outputs.py
   ```
