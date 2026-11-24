# ĐỒ ÁN / BÀI TẬP LỚN: XỬ LÝ ẢNH VIỄN THÁM & HỆ THỐNG WEBGIS
**Đề tài:** Xây dựng Pipeline Xử lý ảnh UAV Đa phổ (Multispectral Drone Imagery: RGB + RedEdge + NIR): Trực giao hóa (Metashape), nắn chỉnh và tối ưu dữ liệu không gian (GDAL/COG), AI Object Detection (YOLO), phân tích chỉ số phổ (NDVI/NDRE/LULC) và trực quan hóa WebGIS (TiTiler + Leaflet.js).

---

## 📌 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG

Dự án **ưu tiên sử dụng một bộ dữ liệu UAV đa phổ chính** xuyên suốt các công đoạn Metashape, GDAL, phân tích chỉ số phổ và WebGIS để bảo đảm các kết quả cùng phạm vi địa lý và dễ dàng chồng lớp. Dataset chính nên có 5 dải phổ Blue, Green, Red, RedEdge và NIR. Có thể dùng dataset phụ riêng cho huấn luyện/kiểm thử YOLO hoặc đối chiếu, nhưng phải ghi rõ nguồn, khu vực, thời điểm và không chồng kết quả lên bản đồ chính nếu chúng không cùng hệ quy chiếu/phạm vi không gian.

**Định dạng dữ liệu đầu vào được chọn trong README này (Cách 1):** tại mỗi vị trí/trạm chụp có 5 ảnh đơn kênh riêng biệt, tương ứng 5 dải phổ. Các ảnh của cùng một lần chụp phải được nhận diện và ghép thành cùng một nhóm camera/multi-camera station trong Metashape. Tên file, timestamp và metadata cần được giữ nguyên để phần mềm ghép đúng các kênh.

```
                  [Ảnh UAV đa phổ thô: 5 ảnh đơn kênh cho mỗi vị trí chụp]
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

## 🎯 2. BỘ DỮ LIỆU ĐỀ XUẤT (MULTISPECTRAL UAV DATASET)

### 2.1. Tiêu chí lựa chọn dataset

* **Dataset chính:** Ưu tiên một bộ ảnh UAV đa phổ có đủ 5 dải Blue, Green, Red, RedEdge và Near-Infrared (NIR), được chụp trên cùng khu vực và trong cùng đợt bay.
* **Cách tổ chức ảnh đầu vào:** Chọn dataset dạng **5 ảnh đơn kênh riêng biệt tại mỗi vị trí chụp**. Mỗi nhóm ảnh phải tương ứng cùng một lần phơi sáng/trạm chụp; không ghép ngẫu nhiên ảnh khác thời điểm hoặc khác vị trí.
* **Thông tin định vị:** Ưu tiên GPS/GNSS trong EXIF hoặc metadata đi kèm. Nếu tọa độ nằm trong tệp phụ (CSV/TXT), cần giữ tệp đó và xác định cách nhập vào Metashape.
* **Dữ liệu hỗ trợ:** Ảnh reflectance panel và dữ liệu hiệu chuẩn bức xạ là lợi thế nếu dataset có cung cấp. GCP không bắt buộc phải có sẵn trong dataset; nhóm có thể bổ sung GCP nếu có tọa độ đo/đối chiếu đáng tin cậy.
* **Dataset phụ:** Có thể dùng dataset RGB riêng để huấn luyện hoặc kiểm thử YOLO nếu dataset chính không có nhãn phù hợp. Dataset phụ không được xem là cùng lớp bản đồ với dataset chính trừ khi đã đồng bộ không gian và có căn cứ rõ ràng.

### 2.2. Các dải phổ cần có

| Band logic | Dải phổ | Bước sóng tham khảo | Công dụng |
| :---: | :--- | :---: | :--- |
| 1 | Blue | khoảng 450–490 nm | Thành phần ảnh RGB |
| 2 | Green | khoảng 520–570 nm | Thành phần ảnh RGB |
| 3 | Red | khoảng 630–690 nm | RGB và NDVI |
| 4 | RedEdge | khoảng 700–740 nm | NDRE |
| 5 | Near-Infrared (NIR) | khoảng 800–900 nm | NDVI, NDRE và CIR |

**Lưu ý về bước sóng:** Các giá trị trên là khoảng tham khảo, không phải điều kiện phải khớp chính xác. Bước sóng trung tâm thực tế phụ thuộc model cảm biến. Khi viết báo cáo, phải ghi thông số theo datasheet/metadata của đúng cảm biến và dataset được sử dụng, không tự gán các giá trị 475, 560, 668, 717, 840 nm nếu chưa xác minh.

**Lưu ý về thứ tự band:** Band 1–5 trong các phần dưới đây là thứ tự logic quy ước (Blue, Green, Red, RedEdge, NIR). Sau khi xuất Orthomosaic, cần dùng `gdalinfo`/metadata để kiểm tra thứ tự band thực tế. Nếu thứ tự xuất khác quy ước, phải cập nhật lại chỉ số band trong toàn bộ script, công thức và URL TiTiler.

### 2.3. Nguồn dataset tham khảo

* **Agisoft Sample Data:** [Agisoft Sample Data](https://www.agisoft.com/downloads/sample-data/)
* **DJI Phantom 4 Multispectral:** có 5 cảm biến đơn sắc (Blue, Green, Red, RedEdge, NIR) và camera RGB. Cần kiểm tra cấu trúc file, metadata và giấy phép truy cập của dataset cụ thể.
* **MicaSense RedEdge:** có thể dùng nếu bộ dữ liệu cụ thể cung cấp đủ các kênh cần thiết, ảnh đơn kênh đồng bộ và metadata. Tên dòng cảm biến không thay thế việc kiểm tra nội dung dataset.

---

## 🛠 3. CHI TIẾT TỪNG GIAI ĐOẠN THỰC HIỆN

### GIAI ĐOẠN 1: Ghép ảnh trực giao đa phổ bằng Agisoft Metashape Pro

> **Lưu ý:** Quy trình dưới đây áp dụng cho **Agisoft Metashape Pro 2.3.2**. Một số tên lệnh đã khác bản 1.x (ví dụ `Build Point Cloud` thay cho `Build Dense Cloud`, `Export Orthomosaic...` thay cho `Export JPEG/TIFF/PNG...`).

#### 1.1. Nhập dữ liệu

1. Mở Agisoft Metashape Pro, tạo project mới và lưu ngay thành `data/orthomosaic/plot_B03_multispectral.psx`.
2. `Workflow` → `Add Photos...` → chọn **toàn bộ 250 file TIF** trong `Image multi` (50 trạm × 5 kênh).
3. Khi hộp thoại hỏi *"Add multi-camera system?"* → chọn **Yes**.
   * Metashape gom 5 ảnh cùng trạm thành 1 camera group → Workspace hiển thị **50 camera groups**, không phải 250 camera rời.
4. **Không** add 50 ảnh RGB `.JPG` vào cùng chunk này. Đó là camera khác, không cùng hệ 5 kênh; nếu cần dùng cho YOLO thì xử lý ở nhánh riêng.

Kiểm tra nhanh trước khi chạy: mỗi group phải có đúng 5 ảnh (Blue, Green, Red, RedEdge, NIR). Nếu thấy 50 camera lẻ không có group → đã chọn `Single camera`, phải xóa và add lại.

#### 1.2. Hiệu chuẩn phản xạ (tùy chọn)

Chỉ làm khi dataset có ảnh chụp tấm chuẩn phản xạ (reflectance panel):

* `Tools` → `Calibrate Reflectance...`

Nếu không có ảnh panel, bỏ qua bước này và **ghi rõ trong báo cáo** rằng dữ liệu là DN thô, NDVI/NDRE chỉ có ý nghĩa **tương đối**.

#### 1.3. Chuỗi xử lý chính

| Bước | Lệnh trong Metashape 2.3.2 | Tham số cho plot_B03 |
| :---: | :--- | :--- |
| 1 | `Workflow` → **`Align Photos...`** | Accuracy **High**; Generic preselection **ON**; Source preselection **OFF**; Key point limit **40.000**; Tie point limit **4.000–10.000**; Adaptive camera model fitting **ON** |
| 2 | Nút **`Optimize`** trên **Reference** pane → `Optimize Camera Alignment` | Adaptive camera model fitting **ON**; các mục còn lại để mặc định |
| 3 | `File` → **`Save`** (bắt buộc, `.psx`) | — |
| 4 | `Workflow` → **`Build Point Cloud...`** | Quality **Medium**; Depth filtering **Moderate**; Calculate point colors **OFF** |
| 5 | `Workflow` → **`Build DEM...`** | Source data **Point Cloud** (hoặc `Depth Maps` nếu muốn nhanh); Coordinate system **WGS 84 / UTM zone 30N**; Interpolation **Extrapolated**; Resolution ≈ GSD |
| 6 | `Workflow` → **`Build Orthomosaic...`** | Projection **Planar**; Surface data **DEM**; Coordinate system **WGS 84 / UTM zone 30N**; Pixel size **0.0413 m**; Blending mode **Disabled** (ưu tiên NDVI) hoặc `Mosaic`; Refine seamlines **ON**; Enable color correction **OFF**; Boundary: vẽ polygon biên plot nếu muốn cắt nền |

**Không chạy `Build Model`.** Mesh 3D không cần cho DEM → Orthomosaic và sẽ rất nặng với 250 ảnh.

**Vì sao chọn `Blending mode = Disabled`:** chế độ Mosaic trộn màu giữa các ảnh, làm sai lệch giá trị phổ dùng cho NDVI/NDRE. Chỉ dùng `Mosaic` khi ưu tiên ảnh đẹp để trình bày.

#### 1.4. Xuất GeoTIFF đa phổ

`File` → `Export` → **`Export Orthomosaic...`**

| Tùy chọn | Giá trị |
| :--- | :--- |
| Format | **TIFF/GeoTIFF (*.tif)** |
| Coordinate system | **WGS 84 / UTM zone 30N (EPSG:32630)** |
| Raster Transform | **None** |
| Write GeoTIFF tags | **ON** |
| Write alpha channel | **OFF** (nếu vẫn ra band 6 → xử lý bằng GDAL ở Giai đoạn 2) |
| Compression | **LZW** hoặc **Deflate** |
| BigTIFF | **ON** nếu file > 4 GB |
| Split in blocks | OFF |

Lưu thành: `data/orthomosaic/multispectral_ortho.tif`

#### 1.5. Kiểm tra ngay sau khi xuất

```bash
gdalinfo -stats data/orthomosaic/multispectral_ortho.tif
```

Checklist bắt buộc:

- [ ] **5 band**, thứ tự `Blue, Green, Red, RedEdge, NIR` (không mặc định đúng — phải đọc `Description` từng band).
- [ ] Không có `Band 6 ... ColorInterp=Alpha`.
- [ ] `ID["EPSG",32630]`.
- [ ] `Pixel Size ≈ (0.0413, -0.0413)` — đơn vị **mét**, không phải độ.
- [ ] Không có `NoData` lạ; nếu có alpha thì ghi nhận để chuyển thành mask ở Giai đoạn 2.

> **Kinh nghiệm từ đồ án:** Metashape 2.3.2 có thể vẫn xuất band Alpha dù đã tắt `Write alpha channel` (tùy phiên bản/cấu hình). Khi đó **không cần export lại nhiều lần** — dùng GDAL ở Giai đoạn 2 để bỏ band 6 và chuyển alpha thành mask, kết quả sạch và tái lập được.

---

### GIAI ĐOẠN 2: Chuẩn hóa tọa độ, mask & Tối ưu COG bằng GDAL

> **Thứ tự ưu tiên:**
> 1. Nếu Metashape export thẳng được **5 band + EPSG:32630 + alpha OFF** → chỉ cần làm mục 2.5 (xuất COG).
> 2. Nếu file export còn **6 band / EPSG:4326 / đơn vị độ** → làm đầy đủ mục 2.4 rồi 2.5.

#### 2.1. Kiểm tra thông số ảnh GeoTIFF

```bash
gdalinfo -stats data/orthomosaic/multispectral_ortho.tif
```

Cần đọc và ghi lại 5 thông số: **số band**, **tên từng band**, **CRS**, **pixel size**, **có alpha/nodata hay không**.

#### 2.2. Chọn hệ tọa độ đầu ra

Với dataset plot_B03, GPS trong EXIF ảnh cho tọa độ khoảng **5,927°N – 5,189°W** → thuộc **WGS 84 / UTM zone 30N (EPSG:32630)**.

Bắt buộc dùng hệ **chiếu (projected)**, không dùng `EPSG:4326` (geographic), vì:

* Pixel size phải là **mét** để tính `Diện tích 1 pixel = |ΔX × ΔY| (m²)` ở Giai đoạn 4.
* Nếu ΔX, ΔY tính bằng **độ** thì diện tích m²/ha sẽ sai hoàn toàn.
* TiTiler/Leaflet vẫn nhận COG ở UTM bình thường (tự reproject sang Web Mercator khi render tile).

Xác định zone UTM: `zone = floor((lon + 180) / 6) + 1`. Với `lon = -5,189` → **zone 30**, bán cầu Bắc (lat > 0) → **EPSG:32630**.

#### 2.3. GCP — chỉ khi thực sự cần

* GPS EXIF của camera **không phải** GCP khảo sát mặt đất. Với đồ án này, độ chính xác tương đối đủ dùng cho bản đồ hiện trạng và tính diện tích, nên **không gán GCP**.
* Chỉ bổ sung GCP khi có tọa độ điểm khống chế **đo độc lập** (RTK/PPK hoặc máy toàn đạc). Không lấy điểm trên nền bản đồ trực tuyến rồi coi là GCP chuẩn.
* Khi gán GCP, nhập tọa độ theo đúng CRS của raster đầu ra (thường là UTM), không nhập lon/lat nếu raster đang ở hệ chiếu.

#### 2.4. Chuẩn hóa khi file export chưa đạt (6 band / EPSG:4326)

Chạy trong **OSGeo4W Shell** (đã có sẵn `gdalinfo`, `gdal_translate`, `gdalwarp`).

**Bước 1 — Tách alpha (band 6) thành mask Byte 0/255:**

```bash
gdal_translate -b 6 -ot Byte -scale 0 65535 0 255 -colorinterp gray \
  data/orthomosaic/multispectral_ortho.tif data/orthomosaic/alpha_mask.tif
```

**Bước 2 — Bỏ band 6, giữ 5 band phổ:**

```bash
gdal_translate -b 1 -b 2 -b 3 -b 4 -b 5 \
  data/orthomosaic/multispectral_ortho.tif data/orthomosaic/ortho_5band.tif
```

> Không dùng `src.count` để suy ra band ở bất kỳ script nào. Luôn dùng index tường minh: **3 = Red, 4 = RedEdge, 5 = NIR**.

**Bước 3 — Reproject sang UTM 30N, pixel 0,0413 m:**

```bash
gdalwarp -t_srs EPSG:32630 -tr 0.0413 0.0413 -r bilinear \
  data/orthomosaic/ortho_5band.tif data/orthomosaic/ortho_utm.tif
```

**Bước 4 — Warp mask theo cùng lưới:**

```bash
gdalwarp -t_srs EPSG:32630 -tr 0.0413 0.0413 -r near \
  data/orthomosaic/alpha_mask.tif data/orthomosaic/mask_utm.tif
```

> ⚠️ **Lưu ý quan trọng:** `gdalwarp` **không giữ mask nội bộ** của file nguồn. Vì vậy phải gắn mask lại bằng VRT trước khi xuất COG, nếu không vùng nền (giá trị 0) sẽ bị coi là pixel hợp lệ và làm NDVI ra `0/0` ở rìa ảnh.

**Bước 5 — Gắn mask bằng VRT** (`data/orthomosaic/ortho_masked.vrt`):

```xml
<VRTDataset rasterXSize="4419" rasterYSize="4434">
  <SRS>EPSG:32630</SRS>
  <GeoTransform>257486.5681, 0.0413, 0, 655679.1996, 0, -0.0413</GeoTransform>
  <VRTRasterBand dataType="UInt16" band="1">
    <Description>Blue</Description>
    <SimpleSource>
      <SourceFilename relativeToVRT="1">ortho_utm.tif</SourceFilename>
      <SourceBand>1</SourceBand>
    </SimpleSource>
  </VRTRasterBand>
  <!-- Lặp lại khối VRTRasterBand cho band 2..5: Green, Red, RedEdge, NIR -->
  <MaskBand>
    <VRTRasterBand dataType="Byte">
      <SimpleSource>
        <SourceFilename relativeToVRT="1">mask_utm.tif</SourceFilename>
        <SourceBand>1</SourceBand>
      </SimpleSource>
    </VRTRasterBand>
  </MaskBand>
</VRTDataset>
```

Lấy `rasterXSize`, `rasterYSize` và `GeoTransform` thực tế từ:

```bash
gdalinfo data/orthomosaic/ortho_utm.tif
```

#### 2.5. Xuất Cloud-Optimized GeoTIFF (COG)

```bash
gdal_translate -of COG \
  -co COMPRESS=DEFLATE -co PREDICTOR=2 \
  -co BIGTIFF=IF_SAFER -co OVERVIEWS=AUTO \
  data/orthomosaic/ortho_masked.vrt data/outputs/cog_multispectral.tif
```

`PREDICTOR=2` phù hợp dữ liệu nguyên UInt16. `OVERVIEWS=AUTO` để COG driver tự sinh overview (tương đương `gdaladdo -r average ... 2 4 8 16 32`).

#### 2.6. Kiểm tra kết quả

```bash
gdalinfo -stats data/outputs/cog_multispectral.tif
```

Checklist:

- [ ] `Driver: GTiff/GeoTIFF`, `LAYOUT=COG`, `COMPRESSION=DEFLATE`.
- [ ] `Block=512x512` (tiled) và có `Overviews:` ≥ 4 mức.
- [ ] Đúng **5 band** với `Description = Blue, Green, Red, RedEdge, NIR`.
- [ ] `ID["EPSG",32630]`, `Pixel Size = (0.0413, -0.0413)`.
- [ ] Có `Mask Flags: PER_DATASET` trên cả 5 band.

**Kết quả thực tế của đồ án (plot_B03):**

| Thuộc tính | Giá trị |
| :--- | :--- |
| Kích thước | 4419 × 4434 px |
| Số band | 5 (Blue, Green, Red, RedEdge, NIR) |
| CRS | EPSG:32630 |
| Pixel size | 0.0413 m |
| Mask | PER_DATASET, ~75,0% diện tích COG hợp lệ (alpha nguồn ~75,6%) |
| Nén / Layout | DEFLATE + PREDICTOR=2 / COG, tile 512 |
| Overviews | 4 mức (2209 → 276 px) |
| Dung lượng | ~179 MB |

---

### GIAI ĐOẠN 3: AI Object Detection (YOLO) & Chuyển đổi Pixel $\rightarrow$ GPS

1. **Tách 3 kênh màu RGB từ file GeoTIFF để đưa vào YOLO:**
   * Dùng thư viện Python `rasterio` trích xuất các band Red, Green, Blue theo thứ tự band thực tế đã xác minh trong GeoTIFF, sau đó sắp xếp thành ảnh RGB phục vụ nhận diện. Không giả định band index nếu chưa kiểm tra metadata.
2. **Cắt ảnh dạng cửa sổ trượt (Tiling/Sliding Window):**
   * Do ảnh trực giao rất lớn (hàng chục nghìn pixel), chia ảnh thành các ô kích thước $640 \times 640$ pixel với độ overlap $15\%$.
3. **Nhận diện bằng YOLO (YOLOv8 / YOLOv11):**
   * Dùng checkpoint pre-trained (phát hiện xe cộ, nhà kho, máy móc) hoặc model đã fine-tune cho ảnh UAV.
   * Lọc bỏ bounding boxes trùng lặp ở vùng overlap bằng thuật toán Non-Maximum Suppression (NMS).
4. **Ánh xạ tọa độ Pixel $\rightarrow$ Tọa độ Địa lý (Lon/Lat):**
   * Sử dụng ma trận `GeoTransform` của GeoTIFF để đổi $(x_{min}, y_{min}, x_{max}, y_{max})$ pixel sang tọa độ **của raster**. Với COG của đồ án, đó là **EPSG:32630 — easting/northing, đơn vị mét**:
     $$\text{Geo\_X} = GT_0 + X_{pixel} \times GT_1 + Y_{pixel} \times GT_2$$
     $$\text{Geo\_Y} = GT_3 + X_{pixel} \times GT_4 + Y_{pixel} \times GT_5$$
   * Sau đó **bắt buộc reproject** từ EPSG:32630 sang **EPSG:4326 (lon/lat)** trước khi ghi GeoJSON, vì Leaflet dùng lon/lat:
     ```python
     from pyproj import Transformer
     to_wgs84 = Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)
     lon, lat = to_wgs84.transform(geo_x, geo_y)
     ```
   * **Không** ghi trực tiếp easting/northing vào GeoJSON — bounding box sẽ nằm sai vị trí trên bản đồ.
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
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&bands=3,2,1` (theo quy ước logic: Red, Green, Blue).
   * **Màu giả hồng ngoại (Color Infrared - CIR):**
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&bands=5,3,2` (theo quy ước logic: NIR, Red, Green).
   * Các ví dụ trên chỉ đúng nếu thứ tự band thực tế của GeoTIFF đã được xác nhận là Blue, Green, Red, RedEdge, NIR.
   * **Bản đồ nhiệt NDVI thời gian thực:**
     `http://localhost:8000/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=file:///PATH/cog_multispectral.tif&expression=(b5-b3)/(b5+b3)&rescale=-0.2,0.8&colormap_name=rdylgn` (nếu Red = Band 3 và NIR = Band 5).

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

## 📅 4. KẾ HOẠCH TIẾN ĐỘ 7 NGÀY (SPRINT ROADMAP 7 NGÀY)

> **Tổng thời gian:** 7 ngày (1 tuần cao điểm)  
> **Nhân sự:** 5 thành viên — Minh (Leader), Nam Anh, Hinh, Quang Anh, Đức.  
> **Nguyên tắc sprint:** Ngày 1 chốt dữ liệu gốc và dựng khung; Ngày 2–3 chạy song song 3 nhánh kỹ thuật (GDAL/COG, YOLO, NDVI/LULC) + khung WebGIS; Ngày 4 đóng gói output và tích hợp lần 1; Ngày 5 test toàn hệ thống; Ngày 6 viết báo cáo + đánh bóng; Ngày 7 tổng duyệt và nộp.  
> **Điều kiện tiên quyết:** file `data/outputs/cog_multispectral.tif` (5 band, EPSG:32630, pixel 0.0413 m, có mask) phải có **trước cuối Ngày 1**, vì cả 3 nhánh đều đọc từ file này.

### 4.1. Hiện trạng đầu Sprint (điểm xuất phát)

| Hạng mục | Trạng thái | Ghi chú |
| :--- | :---: | :--- |
| Orthomosaic Metashape | ✅ Xong | `data/orthomosaic/multispectral_ortho.tif` (5 band phổ + alpha) |
| COG 5 band UTM | ✅ Xong | `data/outputs/cog_multispectral.tif` — EPSG:32630, pixel 0.0413 m, mask nội bộ ~75,6% diện tích hợp lệ |
| Band order | ✅ Chốt | 1 = Blue, 2 = Green, 3 = Red, 4 = RedEdge, 5 = NIR |
| YOLO Detection | ✅ Xong | Đã có `scripts/02_yolo_drone_detection.py` + `data/outputs/detections.geojson` |
| NDVI/NDRE/LULC | ⬜ Chưa | Cần script + `lulc_summary.json` |
| WebGIS Dashboard | ⬜ Chưa | Cần `web/index.html` + Leaflet |

> Vì Giai đoạn 1 và 2 đã có sản phẩm, Ngày 1 dùng để **xác minh + script hóa** chứ không chạy lại từ đầu. Nếu buộc phải chạy lại Metashape, dồn vào Ngày 1 và báo Leader ngay để không chặn 3 nhánh còn lại.

### 4.2. Lịch tổng quát 7 ngày

```
NGÀY 01 — CHỐT DỮ LIỆU GỐC & DỰNG KHUNG
  Minh      : xác minh ortho/COG, chốt band order, phát dữ liệu, tạo repo skeleton
  Nam Anh   : script hóa GDAL → COG, dựng TiTiler
  Hinh      : cài YOLO, test inference 1 ảnh
  Quang Anh : thử NDVI/NDRE trên crop nhỏ
  Đức       : khung HTML/CSS + Leaflet + OSM

NGÀY 02 — CHẠY SONG SONG 3 NHÁNH
  Nam Anh   : 3 URL tile (RGB/CIR/NDVI) + docs
  Hinh      : trích RGB + cắt tile 640×640 overlap 15%
  Quang Anh : NDVI/NDRE toàn ảnh
  Đức       : Layer Control + khung Dashboard
  Minh      : chốt data contract, review code

NGÀY 03 — HOÀN THIỆN LÕI XỬ LÝ            ⭐ Checkpoint 1
  Hinh      : YOLO toàn ảnh + NMS
  Quang Anh : phân lớp LULC + tính diện tích
  Nam Anh   : validate COG + tài liệu kỹ thuật
  Đức       : nhúng tile TiTiler vào map
  Minh      : nghiệm thu Checkpoint 1

NGÀY 04 — ĐÓNG GÓI OUTPUT                 ⭐ Checkpoint 2
  Hinh      : pixel → GPS, xuất detections.geojson
  Quang Anh : xuất lulc_summary.json + ảnh NDVI preview
  Đức       : nạp GeoJSON + popup
  Nam Anh   : hỗ trợ tích hợp, xử lý CORS
  Minh      : kiểm tra schema output

NGÀY 05 — TÍCH HỢP TOÀN HỆ THỐNG          ⭐ Checkpoint 3
  Cả nhóm   : test end-to-end 4 lớp, sửa lỗi lệch tọa độ / định dạng
  Quang Anh : dựng notebook demo trực quan (chỉ đọc output)
  Minh      : ghi log lỗi + phân công sửa

NGÀY 06 — BÁO CÁO & ĐÁNH BÓNG
  Mỗi người : viết phần chuyên môn của mình
  Đức       : polish UI responsive + quay video demo
  Quang Anh : chốt notebook + xuất ảnh vào docs/figures/
  Minh      : ghép báo cáo + rà soát số liệu

NGÀY 07 — TỔNG DUYỆT & NỘP                ⭐ Checkpoint 4
  Cả nhóm   : chạy thử kịch bản demo, nộp bài
```

---

### 4.3. Phân công chi tiết theo từng thành viên

> Cột **Xong**: ✅ hoàn thành, 🔄 đang làm, ⬜ chưa bắt đầu. Mỗi thành viên tự cập nhật sau khi hoàn thành việc của ngày tương ứng (kèm output đã bàn giao).

#### 👤 Minh — Leader (dữ liệu gốc, điều phối, báo cáo)

| Ngày | Việc cụ thể | Output bàn giao | Xong |
| :---: | :--- | :--- | :---: |
| 01 | • Chạy `gdalinfo -stats` xác minh `multispectral_ortho.tif` và `cog_multispectral.tif` (5 band, EPSG:32630, pixel 0.0413 m, mask).<br>• Tạo skeleton repo: `scripts/`, `web/css/`, `web/js/`, `docs/`, `data/outputs/`.<br>• Viết `requirements.txt`.<br>• Phát dữ liệu + link repo cho nhóm. | `docs/band_order.md` (bảng band, CRS, pixel size, mask); `requirements.txt`; cấu trúc thư mục chuẩn. | ✅ |
| 02 | • Viết **hợp đồng dữ liệu** (schema `detections.geojson`, `lulc_summary.json`).<br>• Review script của Nam Anh, Hinh, Quang Anh. | `docs/data_contract.md`. | ⬜ |
| 03 | • Nghiệm thu **Checkpoint 1**: 3 script chạy được trên COG, có output thô. | `docs/checkpoint_01.md` (kết quả + lỗi còn lại). | ⬜ |
| 04 | • Kiểm tra output đúng schema.<br>• Nghiệm thu **Checkpoint 2**. | `docs/checkpoint_02.md`. | ⬜ |
| 05 | • Điều phối test end-to-end, ghi log lỗi và phân công sửa. | `docs/test_report.md`. | ⬜ |
| 06 | • Ghép báo cáo từ phần chuyên môn của 4 thành viên.<br>• Rà soát số liệu, hình ảnh, chú thích bảng biểu. | `docs/BaoCao_DoAn.docx` (bản nháp ≥ 80%). | ⬜ |
| 07 | • Chốt bản cuối, tổng duyệt, nộp. | `docs/BaoCao_DoAn.docx` (bản cuối). | ⬜ |

#### 👤 Nam Anh — GDAL/COG + TiTiler

| Ngày | Việc cụ thể | Output bàn giao | Xong |
| :---: | :--- | :--- | :---: |
| 01 | • Viết `scripts/01_gdal_cog_preprocessing.py` tái tạo COG từ ortho gốc: kiểm tra band/CRS, tách alpha → mask, bỏ band 6, reproject `EPSG:32630`, pixel 0.0413 m, xuất COG (`DEFLATE`, `PREDICTOR=2`, overviews). | Script chạy 1 lệnh tái tạo được `data/outputs/cog_multispectral.tif`. | ⬜ |
| 02 | • Chạy TiTiler (`uvicorn titiler.application.main:app --port 8000`).<br>• Xuất 3 URL tile: RGB `bands=3,2,1`; CIR `bands=5,3,2`; NDVI `expression=(b5-b3)/(b5+b3)&rescale=-0.2,0.8&colormap_name=rdylgn`. | `docs/titiler_urls.md` (3 URL copy-paste được); server chạy `localhost:8000`. | ⬜ |
| 03 | • Validate COG: `LAYOUT=COG`, tile 512, overviews ≥ 4 mức, mask nội bộ, `rio cogeo validate`.<br>• Viết tài liệu kỹ thuật. | `docs/cog_spec.md` (thông số COG + cách tái tạo + kết quả validate). | ⬜ |
| 04 | • Viết `scripts/run_titiler.bat`; xử lý CORS; hỗ trợ Đức nhúng tile. | `scripts/run_titiler.bat`; 3 lớp tile load OK trong `web/index.html`. | ⬜ |
| 05 | • Test hiệu năng tile z14–z20, đo thời gian load, sửa lỗi 404/500. | Bảng thời gian load ghi vào `docs/test_report.md`. | ⬜ |
| 06 | • Viết mục báo cáo: Giai đoạn 2 (GDAL/COG) + cơ chế TiTiler. | Bản thảo gửi Minh + ảnh minh họa. | ⬜ |
| 07 | • Trực nhánh tile khi demo. | — | ⬜ |

#### 👤 Hinh — YOLO Detection

| Ngày | Việc cụ thể | Output bàn giao | Xong |
| :---: | :--- | :--- | :---: |
| 01 | • Cài `ultralytics`, tải weights mô hình YOLO.<br>• Test inference ảnh mẫu trên CPU. | `docs/yolo_setup.md`; môi trường chạy tốt trên CPU. | ✅ |
| 02 | • `scripts/02_yolo_drone_detection.py` phần 1: trích RGB (band 3,2,1, contrast stretch 8-bit) → cắt tile 640×640 overlap 15% → xử lý loại bỏ tile nền đen. | `scripts/extract_rgb.py`; `data/outputs/ortho_rgb_3band.tif`. | ✅ |
| 03 | • Chạy YOLO toàn ảnh trên CPU, lọc `conf ≥ 0.25`, gộp box trùng bằng NMS (IoU 0.50). | 16 box thô -> 12 box sau NMS toàn diện (`02_yolo_drone_detection.py`). | ✅ |
| 04 | • Chuyển pixel → GPS bằng `GeoTransform` (ra EPSG:4326), xuất GeoJSON theo schema 4.4.B. | `data/outputs/detections.geojson` (đúng schema, mở được trong QGIS/Leaflet). | ✅ |
| 05 | • QA: lọc box nền NoData, khử trùng lặp, thống kê 12 đối tượng theo lớp (`conf=0.25`). | `docs/yolo_qa.md` (báo cáo QA + ảnh `detections_visualized.jpg`). | ✅ |
| 06 | • Viết mục báo cáo YOLO (kiến trúc, tiling, NMS, affine transform). | Bản thảo chi tiết trong `Docs/KeHoach_PhanChia_Va_HuongXuLy_Hinh.docx`. | ✅ |
| 07 | • Trực nhánh AI khi demo. | Sẵn sàng demo pipeline. | 🔄 |

#### 👤 Quang Anh — NDVI/NDRE & LULC + Notebook demo

| Ngày | Việc cụ thể | Output bàn giao | Xong |
| :---: | :--- | :--- | :---: |
| 01 | • Kiểm tra band 3/4/5; thử NDVI/NDRE trên crop 1000×1000; xử lý chia 0 + mask. | Script/notebook thử nghiệm + nhận xét khoảng giá trị NDVI. | ⬜ |
| 02 | • `scripts/03_spectral_ndvi_analysis.py` phần 1: tính NDVI, NDRE toàn ảnh (Float32, áp mask). | `data/outputs/ndvi.tif`, `data/outputs/ndre.tif` + thống kê min/max/mean. | ⬜ |
| 03 | • Phân ngưỡng 4 lớp LULC theo **GIAI ĐOẠN 4** (Mục 3), lưu raster Byte (1 = Cây tốt, 2 = Cỏ/thưa, 3 = Đất, 4 = Nước). | `data/outputs/lulc_class.tif`. | ⬜ |
| 04 | • Tính diện tích từ pixel 0.0413 m; xuất JSON theo schema; xuất ảnh preview NDVI có colormap. | `data/outputs/lulc_summary.json`; `data/outputs/ndvi_preview.png`. | ⬜ |
| 05 | • QA: tổng diện tích khớp, kiểm tra lớp nước, đối chiếu NDVI với ảnh RGB.<br>• Dựng `notebooks/04_demo_pipeline.ipynb`: đọc COG ở độ phân giải giảm, vẽ RGB/CIR/NDVI/NDRE/LULC, overlay box từ `detections.geojson`. | `docs/spectral_qa.md`; `notebooks/04_demo_pipeline.ipynb` (chạy sẵn, < 30 giây). | ⬜ |
| 06 | • Viết mục báo cáo NDVI/NDRE/LULC + công thức.<br>• Xuất ảnh từ notebook vào `docs/figures/` để chèn báo cáo. | Bản thảo gửi Minh; `docs/figures/` (RGB, CIR, NDVI, LULC, detection overlay). | ⬜ |
| 07 | • Trực nhánh phổ khi demo. | — | ⬜ |

#### 👤 Đức — WebGIS Dashboard

| Ngày | Việc cụ thể | Output bàn giao | Xong |
| :---: | :--- | :--- | :---: |
| 01 | • `web/index.html`, `web/css/style.css`, `web/js/main.js`: Leaflet + OSM + Google Satellite, layout map + sidebar. | Khung web mở được trên trình duyệt. | ⬜ |
| 02 | • Layer Control (RGB/CIR/NDVI), thanh Opacity, khung legend. | `web/js/main.js` có layer control hoạt động. | ⬜ |
| 03 | • Nhúng 3 URL tile của Nam Anh; xử lý lỗi 404/CORS. | 3 lớp tile hiển thị trên bản đồ. | ⬜ |
| 04 | • Load `detections.geojson`, popup (lớp, confidence, tọa độ), style marker theo lớp. | Lớp AI hiển thị + click ra popup. | ⬜ |
| 05 | • Dashboard: đọc `lulc_summary.json`, vẽ bảng + biểu đồ (Chart.js). | Sidebar hiển thị tổng diện tích và % từng lớp. | ⬜ |
| 06 | • Responsive, tinh chỉnh UI, quay video demo 1–2 phút. | `docs/demo_video.mp4`. | ⬜ |
| 07 | • Demo chính thức. | — | ⬜ |

---

### 4.4. Hợp đồng dữ liệu giữa các nhánh (bắt buộc tuân thủ)

**A. Đầu vào chung — COG**

```text
File      : data/outputs/cog_multispectral.tif
Band      : 1 = Blue, 2 = Green, 3 = Red, 4 = RedEdge, 5 = NIR
CRS       : EPSG:32630 (WGS 84 / UTM zone 30N)
Pixel     : 0.0413 m × 0.0413 m
Mask      : nội bộ, 0 = nền (bỏ), 255 = hợp lệ
Quy ước   : KHÔNG dùng src.count để suy ra band; luôn dùng index tường minh (3 = Red, 5 = NIR).
```

**B. `data/outputs/detections.geojson`** (Hinh → Đức)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[[-5.1897, 5.9267], [-5.1896, 5.9267], [-5.1896, 5.9268], [-5.1897, 5.9268], [-5.1897, 5.9267]]] },
      "properties": {
        "id": 1,
        "class_name": "vehicle",
        "confidence": 0.87,
        "tile_id": "r003_c012",
        "center_lon": -5.1897,
        "center_lat": 5.9267
      }
    }
  ]
}
```

* Geometry theo **EPSG:4326 (lon, lat)**, polygon = 4 góc bounding box (Leaflet tự chiếu sang Web Mercator).
* `class_name` dùng danh mục cố định, không đổi tên tùy tiện: `vehicle`, `building`, `machinery`, `person`, `other`.

**C. `data/outputs/lulc_summary.json`** (Quang Anh → Đức)

```json
{
  "crs": "EPSG:32630",
  "pixel_size_m": 0.0413,
  "pixel_area_m2": 0.00170569,
  "total_valid_area_ha": 2.51,
  "classes": [
    { "id": 1, "name": "Cây xanh tốt", "ndvi_range": [0.45, 1.0], "pixel_count": 0, "area_m2": 0, "area_ha": 0, "percent": 0 },
    { "id": 2, "name": "Thảm cỏ / cây thưa", "ndvi_range": [0.20, 0.45], "pixel_count": 0, "area_m2": 0, "area_ha": 0, "percent": 0 },
    { "id": 3, "name": "Đất trống / nhà cửa", "ndvi_range": [0.00, 0.20], "pixel_count": 0, "area_m2": 0, "area_ha": 0, "percent": 0 },
    { "id": 4, "name": "Mặt nước / trũng ẩm", "ndvi_range": [-1.0, 0.00], "pixel_count": 0, "area_m2": 0, "area_ha": 0, "percent": 0 }
  ]
}
```

**D. Notebook demo — `notebooks/04_demo_pipeline.ipynb`** (Quang Anh → cả nhóm)

Notebook là **lớp trình diễn**, không phải lớp xử lý. Ba quy tắc bắt buộc:

1. **Chỉ đọc** `data/outputs/*`, không ghi đè output của script khác.
2. Đọc COG ở **độ phân giải giảm** (`rasterio` + `out_shape`) để toàn notebook chạy **< 30 giây**.
3. **Không chạy YOLO** trong notebook — chỉ vẽ lại `detections.geojson` do Hinh xuất.

### 4.5. Mốc kiểm tra & nghiệm thu (Checkpoints)

| Mốc | Thời điểm | Điều kiện đạt | Người nghiệm thu |
| :---: | :---: | :--- | :--- |
| **CP1** | Cuối Ngày 03 | 3 script `01`, `02`, `03` chạy được trên COG và sinh output thô. | Minh |
| **CP2** | Cuối Ngày 04 | `detections.geojson` + `lulc_summary.json` đúng schema; web load được GeoJSON. | Minh + Đức |
| **CP3** | Cuối Ngày 05 | Web hiển thị đủ 4 lớp (RGB, CIR, NDVI, AI), không lỗi console, tọa độ khớp; notebook chạy dưới 30 giây và hiển thị đủ 5 loại ảnh. | Cả nhóm |
| **CP4** | Ngày 07 | Báo cáo hoàn chỉnh + web demo và notebook chạy end-to-end, không phụ thuộc máy cá nhân. | Cả nhóm |

### 4.6. Rủi ro & phương án dự phòng

| Rủi ro | Ảnh hưởng | Cách xử lý |
| :--- | :--- | :--- |
| Metashape phải chạy lại | Trễ toàn bộ sprint | Dùng COG đã có để 3 nhánh chạy song song; chạy lại Metashape ở luồng riêng, không chặn |
| YOLO không phát hiện được gì (ảnh nông nghiệp ít vật thể) | Nhánh AI rỗng | Hạ `conf`, dùng model fine-tune, hoặc demo trên ảnh RGB phụ; ghi rõ giới hạn trong báo cáo |
| GeoJSON lệch so với tile | Box nằm sai vị trí | Kiểm tra CRS: tile dùng EPSG:3857, GeoJSON dùng EPSG:4326; Leaflet tự chiếu, không tự đổi tọa độ |
| TiTiler không đọc được `file://` trên Windows | Không có tile | Serve thư mục bằng `python -m http.server` hoặc dùng `FileSystemStore`; ghi vào `run_titiler.bat` |
| Hết thời gian viết báo cáo | Thiếu tài liệu nộp | Chốt code trước hết Ngày 05; Ngày 06–07 chỉ viết, sửa lỗi nhỏ và đánh bóng |

---

## 📁 5. CẤU TRÚC THƯ MỤC DỰ ÁN

```plaintext
Project_XLA_VienTham/
├── data/
│   ├── raw_multispectral/          # 5 ảnh đơn kênh cho mỗi vị trí chụp (Blue, Green, Red, RE, NIR)
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
├── notebooks/
│   └── 04_demo_pipeline.ipynb       # Notebook demo trực quan (chỉ đọc output, không xử lý lại)
├── docs/
│   ├── BaoCao_DoAn.docx             # Báo cáo tổng kết đồ án
│   ├── demo_video.mp4               # Video quay màn hình demo WebGIS
│   └── figures/                     # Ảnh xuất từ notebook để chèn báo cáo
├── requirements.txt                 # Danh sách thư viện Python cần thiết
└── README.md                        # Hướng dẫn chi tiết dự án
```
