# ĐỒ ÁN / BÀI TẬP LỚN: XỬ LÝ ẢNH VIỄN THÁM & HỆ THỐNG WEBGIS
**Đề tài:** Xây dựng Pipeline Xử lý ảnh UAV Đa phổ (Multispectral Drone Imagery: RGB + NIR): Trực giao hóa (Metashape), Nắn chỉnh tọa độ (GDAL), AI Object Detection (YOLO), Phân tích chỉ số phổ (NDVI/LULC) và Trực quan hóa WebGIS (TiTiler + Leaflet.js).

---

## 📌 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG

Dự án sử dụng **DUY NHẤT 1 Bộ dữ liệu ảnh Drone Đa phổ (Multispectral UAV Dataset: Blue, Green, Red, RedEdge, NIR)** xuyên suốt toàn bộ quy trình:

```
                  [Ảnh UAV Đa phổ thô (MicaSense RedEdge / DJI Multispectral)]
                                                ↓
                    [1. Ghép ảnh & Trực giao hóa (Agisoft Metashape Pro)]
                                                ↓
                       [File Orthomosaic GeoTIFF Đa phổ (5 Bands, WGS84)]
                                                ↓
                    [2. Chuẩn hóa & Nắn chỉnh GCP bằng GDAL -> Xuất COG]
                                                ↓
             ┌──────────────────────────────────┴──────────────────────────────────┐
             ↓                                                                     ↓
  [3. Nhánh Phân tích phổ & LULC]                                    [4. Nhánh AI - Object Detection]
   • Trích kênh Red (Band 3) & NIR (Band 5)                           • Trích kênh RGB (Bands 1, 2, 3)
   • Tính chỉ số NDVI & NDRE                                          • Cắt ảnh cửa sổ trượt (Tiling/SAHI)
   • Phân ngưỡng LULC (Cây khỏe, Cây thưa, Đất, Nước)                 • Dự đoán bằng YOLO (xe cộ, nhà cửa,...)
   • Tính diện tích thực tế (m² / ha) theo GSD                        • Ánh xạ tọa độ: Pixel -> GPS (GeoJSON)
             └──────────────────────────────────┬──────────────────────────────────┘
                                                ↓
                     [5. Phục vụ Dữ liệu Bản đồ (TiTiler COG Tile Server)]
                        - Dynamic RGB Tiles: bands=3,2,1
                        - Dynamic NDVI Tiles: expression=(b5-b3)/(b5+b3)
                                                ↓
                     [6. WebGIS Dashboard (HTML5 / CSS3 / Leaflet.js)]
                        - Bản đồ nền OpenStreetMap / Google Satellite
                        - Chuyển đổi linh hoạt giữa Ortho RGB, CIR và NDVI
                        - Bật/tắt lớp AI Bounding Box (Click xem thông tin)
                        - Bảng thống kê diện tích LULC & đối tượng phát hiện
```

---

## 🎯 2. BỘ DỮ LIỆU ĐỀ XUẤT (UNIFIED MULTISPECTRAL DATASET)

* **Bộ dữ liệu chuẩn:** **Agisoft Multispectral Sample Dataset (MicaSense RedEdge)** hoặc **DJI Phantom 4 Multispectral Agricultural Dataset**.
* **Tải mẫu chính thức từ Agisoft:** [Agisoft Sample Data](https://www.agisoft.com/downloads/sample-data/) (chọn mục *Multispectral*).
* **Đặc tính kỹ thuật:**
  * Kênh 1: **Blue** (475 nm)
  * Kênh 2: **Green** (560 nm)
  * Kênh 3: **Red** (668 nm)
  * Kênh 4: **RedEdge** (717 nm)
  * Kênh 5: **Near-Infrared - NIR** (840 nm)
  * Mỗi vị trí chụp đồng thời tạo ra 5 ảnh đơn kênh tương ứng với 5 dải sóng + siêu dữ liệu GPS (Exif).

---

## 🛠 3. CHI TIẾT TỪNG GIAI ĐOẠN THỰC HIỆN

### GIAI ĐOẠN 1: Ghép ảnh trực giao đa phổ bằng Agisoft Metashape Pro

1. **Khởi động và Nhập dữ liệu:**
   * Mở Agisoft Metashape Pro.
   * Chọn `Workflow` $\rightarrow$ `Add Photos...` $\rightarrow$ Chọn toàn bộ ảnh (cả 5 kênh).
   * Khi hộp thoại hỏi: *"Add multi-camera system?"* $\rightarrow$ Chọn **Yes** (Phần mềm sẽ tự gom 5 ảnh thành 1 trạm chụp đa phổ có 5 cảm biến).
2. **Hiệu chuẩn phản xạ (Calibrate Reflectance - Tùy chọn nếu có ảnh tấm chuẩn):**
   * Vào `Tools` $\rightarrow$ `Calibrate Reflectance` để chuẩn hóa giá trị phản xạ quang học.
3. **Thực hiện Workflow ghép ảnh:**
   * **Bước 1:** `Workflow` $\rightarrow$ `Align Photos` (Accuracy: High/Medium, Generic + Reference preselection).
   * **Bước 2:** `Workflow` $\rightarrow$ `Build Depth Maps` & `Build Dense Cloud` (Quality: Medium).
   * **Bước 3:** `Workflow` $\rightarrow$ `Build DEM` (Dựa trên Dense Cloud, hệ tọa độ WGS 84 / UTM).
   * **Bước 4:** `Workflow` $\rightarrow$ `Build Orthomosaic` (Surface: DEM, Blending mode: Mosaic).
4. **Xuất file GeoTIFF Đa phổ:**
   * Chọn `File` $\rightarrow$ `Export` $\rightarrow$ `Export Orthomosaic` $\rightarrow$ `Export JPEG/TIFF/PNG...`
   * Đặt định dạng: `TIFF/GeoTIFF (*.tif)`, tích chọn **Write GeoTIFF tags**.
   * Lưu thành: `data/orthomosaic/multispectral_ortho.tif`.

---

### GIAI ĐOẠN 2: Nắn chỉnh tọa độ & Tối ưu COG bằng GDAL

1. **Kiểm tra thông số ảnh GeoTIFF:**
   ```bash
   gdalinfo data/orthomosaic/multispectral_ortho.tif
   ```
   *(Xác nhận ảnh có 5 Bands và đã có hệ tọa độ UTM hoặc WGS 84).*

2. **Nắn chỉnh tọa độ bằng GCP (Nếu ảnh bị lệch so với OpenStreetMap):**
   * Chấm 4 - 6 điểm đặc trưng (GCPs) trên ảnh và đối chiếu tọa độ chuẩn trên OpenStreetMap/QGIS.
   * Gán GCPs và warp lại:
     ```bash
     gdal_translate -gcp <pix_x> <pix_y> <lon> <lat> data/orthomosaic/multispectral_ortho.tif temp_gcp.tif
     gdalwarp -tps -r bilinear temp_gcp.tif data/orthomosaic/ortho_aligned.tif
     ```

3. **Chuyển đổi thành Cloud-Optimized GeoTIFF (COG) 5 Bands:**
   ```bash
   gdal_translate data/orthomosaic/ortho_aligned.tif data/outputs/cog_multispectral.tif \
     -co TILED=YES \
     -co COMPRESS=DEFLATE \
     -co COPY_SRC_OVERVIEWS=YES
   gdaladdo -r average data/outputs/cog_multispectral.tif 2 4 8 16 32
   ```

---

### GIAI ĐOẠN 3: AI Object Detection (YOLO) & Chuyển đổi Pixel $\rightarrow$ GPS

1. **Tách 3 kênh màu RGB từ file GeoTIFF để đưa vào YOLO:**
   * Dùng thư viện Python `rasterio` trích xuất Band 3 (Red), Band 2 (Green), Band 1 (Blue) lưu thành ảnh RGB phục vụ nhận diện.
2. **Cắt ảnh dạng cửa sổ trượt (Tiling/Sliding Window):**
   * Do ảnh trực giao rất lớn (hàng chục nghìn pixel), chia ảnh thành các ô kích thước $640 \times 640$ pixel với độ overlap $15\%$.
3. **Nhận diện bằng YOLO (YOLOv8 / YOLOv11):**
   * Dùng checkpoint pre-trained (phát hiện xe cộ, nhà kho, máy móc) hoặc model đã fine-tune cho ảnh UAV.
   * Lọc bỏ bounding boxes trùng lặp ở vùng overlap bằng thuật toán Non-Maximum Suppression (NMS).
4. **Ánh xạ tọa độ Pixel $\rightarrow$ Tọa độ Địa lý (Lon/Lat):**
   * Sử dụng ma trận `GeoTransform` của GeoTIFF để đổi $(x_{min}, y_{min}, x_{max}, y_{max})$ pixel thành tọa độ kinh độ/vĩ độ chuẩn WGS84:
     $$\text{Geo\_X} = GT_0 + X_{pixel} \times GT_1 + Y_{pixel} \times GT_2$$
     $$\text{Geo\_Y} = GT_3 + X_{pixel} \times GT_4 + Y_{pixel} \times GT_5$$
5. **Xuất file GeoJSON:**
   * Lưu toàn bộ bounding boxes cùng thuộc tính (`class_name`, `confidence`) vào file `data/outputs/detections.geojson`.

---

### GIAI ĐOẠN 4: Phân tích phổ NDVI/NDRE & Tính diện tích lớp phủ (LULC)

1. **Tính toán chỉ số thực vật chuẩn:**
   * **NDVI (Normalized Difference Vegetation Index):**
     $$\text{NDVI} = \frac{\text{NIR (Band 5)} - \text{Red (Band 3)}}{\text{NIR (Band 5)} + \text{Red (Band 3)}}$$
   * **NDRE (Normalized Difference Red Edge Index):**
     $$\text{NDRE} = \frac{\text{NIR (Band 5)} - \text{RedEdge (Band 4)}}{\text{NIR (Band 5)} + \text{RedEdge (Band 4)}}$$

2. **Phân loại lớp phủ mặt đất (LULC Thresholding):**
   * $\text{NDVI} > 0.45$: **Cây xanh tốt / Rừng / Tán cây dày**
   * $0.20 \le \text{NDVI} \le 0.45$: **Thảm cỏ / Cây trồng thưa**
   * $0.00 \le \text{NDVI} < 0.20$: **Đất trống / Đường giao thông / Nhà cửa**
   * $\text{NDVI} < 0.00$: **Mặt nước / Vùng trũng ẩm**

3. **Tính diện tích thực tế ($m^2$ và Héc-ta):**
   * Đọc độ phân giải mặt đất (Pixel size: $\Delta X, \Delta Y$ tính bằng mét từ hệ UTM):
     $$\text{Diện tích 1 pixel} = |\Delta X \times \Delta Y| \quad (m^2)$$
   * $\text{Tổng diện tích lớp} = \text{Tổng số pixel của lớp} \times \text{Diện tích 1 pixel}$.
   * Xuất báo cáo diện tích ra dạng JSON hoặc bảng thống kê cho Web (`data/outputs/lulc_summary.json`).

---

### GIAI ĐOẠN 5: Tile Server (TiTiler) & WebGIS Dashboard (Leaflet.js)

1. **Khởi chạy TiTiler phục vụ Dynamic Tiling cho COG 5-band:**
   ```bash
   uvicorn titiler.application.main:app --host 0.0.0.0 --port 8000
   ```
2. **Các đường dẫn Tile linh hoạt cung cấp cho Leaflet:**
   * **Màu tự nhiên (True Color RGB):**
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&bands=3,2,1`
   * **Màu giả hồng ngoại (Color Infrared - CIR):**
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&bands=5,3,2`
   * **Bản đồ nhiệt NDVI thời gian thực:**
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&expression=(b5-b3)/(b5+b3)&rescale=-0.2,0.8&colormap_name=rdylgn`

3. **Giao diện WebGIS (HTML/CSS + Leaflet.js):**
   * **Bản đồ nền (Base Maps):** OpenStreetMap, Google Satellite.
   * **Layer Control:** Cho phép người dùng chuyển đổi giữa:
     * *Ảnh trực giao màu tự nhiên (RGB)*
     * *Ảnh màu giả hồng ngoại (CIR)*
     * *Bản đồ chỉ số thực vật NDVI*
     * *Lớp Bounding Boxes YOLO (`detections.geojson`)*
   * **Popup thông tin:** Click vào vật thể để xem tên đối tượng, độ tin cậy, tọa độ GPS.
   * **Dashboard Widget:** Thống kê tổng số lượng đối tượng và tỷ lệ diện tích các lớp phủ (Cây xanh, Đất trống, Mặt nước).

---

## 📅 4. KẾ HOẠCH TIẾN ĐỘ 2 TUẦN (SPRINT ROADMAP 14 NGÀY)

> **Tổng thời gian:** 14 Ngày (2 Tuần)  
> **Nguyên tắc chạy nhanh (Sprint):** Leader xuất dữ liệu ngay trong 2 ngày đầu; các thành viên chạy song song 3 nhánh trong 4 ngày tiếp theo; tuần thứ 2 tập trung tích hợp WebGIS và hoàn thiện báo cáo/slide.

```
TUẦN 1 (Ngày 01 - 07): TẬP TRUNG XỬ LÝ DỮ LIỆU & RẼ NHÁNH KỸ THUẬT
Day 01-02: Leader chạy Metashape xuất GeoTIFF 5-band
Day 03-05: Chạy song song: GDAL/COG (TV2) | YOLO Detection (TV3) | Phổ NDVI (TV4)
Day 06-07: TV5 dựng khung WebGIS đón dữ liệu; kiểm tra độ khớp dữ liệu

TUẦN 2 (Ngày 08 - 14): TÍCH HỢP HỆ THỐNG WEBGIS & HOÀN THIỆN ĐỒ ÁN
Day 08-10: Nhúng TiTiler + Leaflet, nạp GeoJSON & bảng diện tích LULC
Day 11-12: Test toàn hệ thống, Leader viết báo cáo & làm Slide
Day 13-14: Tổng duyệt Demo, kiểm tra rà soát và nộp bài / thuyết trình
```

---

### 🟢 TUẦN 1: TẠO DỮ LIỆU & XỬ LÝ CHUYÊN SÂU TỪNG PHẦN (NGÀY 01 – NGÀY 07)

| Ngày | Thành viên | Nhiệm vụ cụ thể | Sản phẩm bàn giao bắt buộc |
| :---: | :--- | :--- | :--- |
| **Ngày 01 – 02** | **Minh**<br>*(Leader)* | • Tải dataset đa phổ (MicaSense RedEdge/DJI).<br>• Cài Metashape Pro, cấu hình Multi-camera.<br>• Chạy quy trình: Align $\rightarrow$ Dense Cloud $\rightarrow$ DEM $\rightarrow$ Build Ortho.<br>• Xuất file GeoTIFF 5 bands và phân phát cho cả nhóm. | **File `multispectral_ortho.tif`** (5 bands, WGS84/UTM). |
| **Ngày 01 – 02** | **Các thành viên** | • Cài đặt môi trường làm việc: Python, GDAL, PyTorch/YOLOv8, Leaflet.<br>• Đọc kỹ luồng dữ liệu và API liên quan. | Môi trường code sẵn sàng trên máy từng người. |
| **Ngày 03 – 05** | **Nam Anh** | • Dùng GDAL kiểm tra tọa độ, gán GCP nắn chỉnh nếu lệch OSM.<br>• Build file COG 5 bands và cấu hình chạy server TiTiler. | Script `01_gdal_cog_preprocessing.py`, file `cog_multispectral.tif`, URL Tile Server. |
| **Ngày 03 – 05** | **Hinh** | • Trích 3 bands RGB, viết code cắt sliding window ($640 \times 640$).<br>• Chạy YOLO phát hiện vật thể và ánh xạ Affine Transform (Pixel $\rightarrow$ GPS). | Script `02_yolo_drone_detection.py`, file `detections.geojson`. |
| **Ngày 03 – 05** | **Quang Anh** | • Trích Band 3 (Red), 4 (RE), 5 (NIR) tính chỉ số NDVI/NDRE.<br>• Phân ngưỡng lớp phủ (Cây, Đất, Nước) và tính diện tích ($m^2$, ha) theo GSD. | Script `03_spectral_ndvi_analysis.py`, file `lulc_summary.json`. |
| **Ngày 06 – 07** | **Đức** | • Dựng khung giao diện Web (HTML/CSS), tích hợp Leaflet và nền OSM.<br>• Lập trình Layer Control và khung Dashboard Widget. | Khung WebGIS `index.html` sẵn sàng đón dữ liệu. |
| **Ngày 06 – 07** | **Cả nhóm & Leader** | • **Mốc chốt Tuần 1:** Ghép thử nghiệm các sản phẩm trung gian (Tile, GeoJSON, LULC json) xem có lỗi định dạng hay lệch tọa độ không. | Biên bản test mốc Tuần 1 đạt yêu cầu. |

---

### 🔴 TUẦN 2: TÍCH HỢP WEBGIS, VIẾT BÁO CÁO & NGHIỆM THU (NGÀY 08 – NGÀY 14)

| Ngày | Thành viên | Nhiệm vụ cụ thể | Sản phẩm bàn giao bắt buộc |
| :---: | :--- | :--- | :--- |
| **Ngày 08 – 10** | **Minh**<br>*(Phối hợp NA, H, QA)* | • Nhúng dynamic tile từ TiTiler (RGB, CIR, NDVI nhiệt) vào Leaflet.<br>• Tải lớp vector `detections.geojson` (click hiện popup thông tin vật thể).<br>• Nhúng biểu đồ / widget thống kê diện tích LULC từ `lulc_summary.json`. | Ứng dụng WebGIS Dashboard chạy mượt mà, đầy đủ tính năng. <br>• Soát lỗi toàn bộ mã nguồn trên kho lưu trữ chung. | 
| **Ngày 08 – 10** | **Nam Anh, Hinh, Quang Anh** | • Viết phần giải thích kỹ thuật và chụp ảnh kết quả thực nghiệm để đưa vào báo cáo:<br>  - NA: Quy trình nắn chỉnh GCP, tối ưu COG, cơ chế TiTiler.<br>  - H: Cấu trúc mô hình YOLO, thuật toán cắt ảnh và Affine Transform.<br>  - QA: Cơ sở lý thuyết NDVI/NDRE, công thức đo diện tích mặt đất. | Bản thảo nội dung chuyên môn gửi Leader. |
| **Ngày 11 – 12** | **Tất cả** | • Tổng hợp toàn văn Báo cáo đồ án (`BaoCao_DoAn.docx`).<br>• Thiết kế Slide thuyết trình hoàn chỉnh (`Slide_ThuyetTrinh.pptx`).<br>•Báo cáo hoàn chỉnh, Slide thuyết trình chuyên nghiệp. |
| **Ngày 11 – 12** | **Đức** | • Tinh chỉnh giao diện: Thanh trượt Opacity, chỉnh responsive hiển thị đẹp.<br>• Quay video ngắn (1-2 phút) demo WebGIS làm phương án dự phòng khi báo cáo. | Mã nguồn Web hoàn thiện, Video demo sản phẩm. |
| **Ngày 13** | **Cả nhóm** | • **Tổng duyệt lần cuối:** Chạy thử kịch bản thuyết trình và demo trực tiếp toàn bộ pipeline từ đầu đến cuối trước nhóm. | Nhóm nắm vững kịch bản, sẵn sàng trả lời câu hỏi phản biện. |
| **Ngày 14** | **Cả nhóm** | • **BÁO CÁO CHÍNH THỨC / NỘP ĐỒ ÁN CHO GIẢNG VIÊN.** | Điểm số tối đa cho toàn đội! |

---

## 📁 5. CẤU TRÚC THƯ MỤC DỰ ÁN

```plaintext
Project_XLA_VienTham/
├── data/
│   ├── raw_multispectral/          # Thư mục chứa tập ảnh gốc (Blue, Green, Red, RE, NIR)
│   ├── orthomosaic/                # File GeoTIFF 5-band xuất từ Metashape
│   └── outputs/
│       ├── cog_multispectral.tif   # File COG 5-band sau khi nắn chỉnh
│       ├── detections.geojson      # Bounding boxes YOLO định dạng GPS
│       └── lulc_summary.json       # Kết quả thống kê diện tích LULC
├── scripts/
│   ├── 01_gdal_cog_preprocessing.py # Script GDAL kiểm tra tọa độ, gán GCP và build COG
│   ├── 02_yolo_drone_detection.py   # Script trích RGB, cắt slice, chạy YOLO & xuất GeoJSON
│   └── 03_spectral_ndvi_analysis.py # Script tính NDVI/NDRE, phân loại LULC & tính diện tích m²
├── web/
│   ├── index.html                   # Giao diện WebGIS Dashboard
│   ├── css/
│   │   └── style.css                # Style giao diện bản đồ và bảng thống kê
│   └── js/
│       └── main.js                  # Logic Leaflet kết nối TiTiler và nạp GeoJSON
├── docs/
│   ├── BaoCao_DoAn.docx             # Báo cáo tổng kết đồ án
│   ├── Slide_ThuyetTrinh.pptx       # Slide thuyết trình
│   └── demo_video.mp4               # Video quay màn hình demo WebGIS
├── requirements.txt                 # Danh sách thư viện Python cần thiết
└── README.md                        # Hướng dẫn chi tiết dự án
```
