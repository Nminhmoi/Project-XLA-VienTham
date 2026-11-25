# [Bản nháp báo cáo] Giai đoạn 2 — Chuẩn hóa dữ liệu & COG; Giai đoạn 5 — Phục vụ tile bằng TiTiler

*Người viết: Nam Anh. Gửi Minh để ghép vào `BaoCao_DoAn.docx`. Các chỗ đánh dấu ⬜ cần điền số đo trên dữ liệu thật.*

---

## 2.1. Mục tiêu

Orthomosaic xuất từ Agisoft Metashape chưa dùng trực tiếp được cho phân tích và WebGIS. Có ba vấn đề: (i) ảnh ở hệ tọa độ địa lý EPSG:4326, kích thước pixel tính bằng độ nên không đổi ra diện tích được; (ii) có thêm một band Alpha thứ 6 lẫn với 5 band phổ; (iii) cấu trúc lưu trữ (tile 256, nén LZW, overview đặt trước ảnh gốc) không tối ưu cho việc đọc từng phần qua mạng. Giai đoạn 2 chuyển ảnh này thành một **Cloud-Optimized GeoTIFF (COG)** 5 band, ở hệ chiếu UTM, có mask nội bộ. Đây là đầu vào chung cho nhánh YOLO, nhánh NDVI/LULC và tile server.

## 2.2. Dữ liệu đầu vào

| Thuộc tính | Giá trị |
| :--- | :--- |
| Tệp | `multispectral_ortho.tif` (Metashape Pro 2.3.2) |
| Kích thước | 4396 × 4411 px, 6 band `uint16` |
| CRS | EPSG:4326, pixel ≈ 3,73 × 10⁻⁷ độ |
| Band | 1 Blue, 2 Green, 3 Red, 4 RedEdge, 5 NIR, 6 Alpha (theo `Description`) |
| Vùng hợp lệ | Alpha > 0: 75,61% số pixel; vùng nền mang giá trị trắng |

## 2.3. Quy trình chuẩn hóa

**Chọn hệ tọa độ.** Tâm khu vực ở khoảng 5,927°N, 5,190°W. Số múi UTM là ⌊(−5,190 + 180) / 6⌋ + 1 = 30, nằm ở bán cầu Bắc, nên chọn **EPSG:32630 (WGS 84 / UTM zone 30N)**. Ở hệ chiếu này pixel có kích thước bằng mét, nên diện tích một pixel là |ΔX·ΔY| = 0,0413² = 0,00170569 m². Đây là cơ sở để tính diện tích LULC.

**Xác định band.** Thứ tự band được đọc từ trường `Description` của GeoTIFF, không suy ra từ số lượng band. Nếu metadata thiếu, script dừng lại và yêu cầu chỉ định thủ công. Làm vậy để tránh lỗi âm thầm khi dữ liệu thay đổi.

**Xử lý mask.** Band Alpha được tách thành mask nhị phân 0/255 và loại khỏi dữ liệu. Sau khi chiếu lại, mask được gắn vào COG dưới dạng **mask nội bộ (PER_DATASET)**. Mọi phần mềm dựa trên GDAL (QGIS, rasterio, TiTiler) đều tự hiểu loại mask này. Pixel nền được ghi giá trị 0 ở cả 5 band.

**Nội suy khi chiếu lại.** Mask dùng nội suy *nearest neighbour* để giữ đúng giá trị nhị phân. Dữ liệu phổ dùng *bilinear*, kèm khai báo band alpha nguồn để GDAL **bỏ qua pixel nền** khi nội suy. Nếu không khai báo, các pixel ở rìa vùng chụp sẽ bị trộn với giá trị nền trắng 65535 và cho NDVI sai. Những pixel rìa mà mask nearest coi là hợp lệ nhưng phép bilinear không có nguồn hợp lệ cũng bị loại khỏi mask, để không sinh pixel 0 (NDVI = 0/0).

**Công cụ.** Toàn bộ quy trình nằm trong một script Python, `scripts/01_gdal_cog_preprocessing.py`. Script dùng rasterio, có GDAL đi kèm. Nó thay cho chuỗi 5 lệnh `gdal_translate`/`gdalwarp`/VRT, chạy được trên Windows và macOS mà không cần OSGeo4W. Chạy lại cho ra file giống hệt từng byte, nên kết quả tái lập được.

## 2.4. Cloud-Optimized GeoTIFF

COG là một GeoTIFF bình thường nhưng được sắp xếp lại bên trong để đọc được từng phần:

- **Tile 512 × 512:** ảnh được chia thành các khối độc lập. Muốn đọc một vùng nhỏ chỉ cần đọc vài khối, không phải cả file.
- **Overview (kim tự tháp ảnh):** các bản thu nhỏ ×2, ×4, ×8, ×16 được lưu sẵn. Khi bản đồ ở zoom nhỏ, server đọc overview thay vì ảnh gốc.
- **Thứ tự lưu:** metadata và overview nằm ở đầu file, ảnh gốc ở cuối. Nhờ vậy client chỉ cần gửi một vài HTTP Range request là có đủ thông tin.
- **Nén DEFLATE + PREDICTOR=2:** mỗi pixel được lưu dưới dạng hiệu số với pixel bên trái trước khi nén. Cách này hiệu quả với dữ liệu nguyên `uint16` biến thiên trơn. Đây là nén không mất dữ liệu nên giá trị phổ được giữ nguyên.

## 2.5. Kết quả

| Thuộc tính | Giá trị |
| :--- | :--- |
| Kích thước | 4419 × 4434 px (~182,5 × 183,1 m) |
| Band | 5: Blue, Green, Red, RedEdge, NIR (`uint16`) |
| CRS / pixel | EPSG:32630 / 0,0413 m |
| Mask | PER_DATASET, 75,01% pixel hợp lệ (nguồn 75,61%) |
| Nén / layout | DEFLATE + PREDICTOR=2 / COG, tile 512 |
| Overviews | 4 mức (2, 4, 8, 16) |
| Dung lượng | ~179 MB (nguồn 280 MB) |

Tỷ lệ hợp lệ giảm từ 75,61% xuống 75,01%. Lý do là lưới UTM bị xoay nhẹ so với lưới địa lý, nên thêm một dải pixel rìa nằm ngoài vùng chụp. Khi tính diện tích phải dùng tỷ lệ của COG.

**Kiểm tra.** Script `scripts/validate_cog.py` kiểm tra 16 tiêu chí, gồm `rio cogeo validate`, cấu trúc COG, CRS, pixel size, tên band, mask, và hai bất biến (ngoài mask = 0; không có pixel hợp lệ nào bằng 0 ở cả 5 band). ⬜ *Dán bảng `validate_cog.py --markdown` trên dữ liệu thật.*

---

## 5.x. Cơ chế phục vụ tile động bằng TiTiler

**Tile tĩnh và tile động.** Cách truyền thống là cắt sẵn hàng nghìn ảnh PNG cho mỗi cấp zoom, và mỗi cách hiển thị (RGB, CIR, NDVI) lại phải cắt một bộ riêng. TiTiler làm khác: nó chỉ giữ **một file COG duy nhất** và sinh tile ngay khi có yêu cầu. Cách tổ hợp band, công thức chỉ số và bảng màu đều truyền qua tham số URL.

**Xử lý một yêu cầu** `GET /cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=...&bidx=...`:

1. Từ (z, x, y), tính ra khung bao của tile trong hệ Web Mercator (EPSG:3857).
2. Chọn mức overview của COG có độ phân giải gần nhất với tile.
3. Đọc đúng các khối 512 × 512 giao với khung bao, rồi chiếu lại từ UTM 30N sang Web Mercator, kích thước 256 × 256.
4. Áp **mask nội bộ**: pixel nền trở thành trong suốt (kênh alpha của PNG).
5. Xử lý giá trị: chọn band (`bidx`), hoặc tính biểu thức (`expression=(b5-b3)/(b5+b3)`) trên số thực; kéo giãn về 0–255 (`rescale`); tô màu (`colormap_name=rdylgn`).
6. Mã hóa thành PNG và trả cho Leaflet.

**Bốn lớp cung cấp cho WebGIS.**

| Lớp | Tham số |
| :--- | :--- |
| RGB | `bidx=3,2,1` (ba tham số `bidx` riêng), `rescale` theo phân vị 2–98% từng band |
| CIR | `bidx=5,3,2`; thực vật có NIR cao nên hiện màu đỏ |
| NDVI | `expression=(b5-b3)/(b5+b3)`, `rescale=-0.2,0.8`, `colormap_name=rdylgn` |
| NDRE | `expression=(b5-b4)/(b5+b4)`, `rescale=0,0.5`, `colormap_name=rdylgn` |

Ngưỡng `rescale` của RGB/CIR do script `make_titiler_urls.py` tính tự động từ COG và ghi vào `web/tiles.json`. Nhờ vậy web luôn khớp với dữ liệu hiện tại, không phải sửa tay.

**Các vấn đề kỹ thuật đã xử lý.**

- Với TiTiler 2.x, tham số `bands=` trong thiết kế ban đầu không còn tác dụng; phải dùng `bidx`.
- Dấu `+` trong biểu thức NDVI phải mã hóa thành `%2B`, nếu không server hiểu là dấu cách và báo lỗi cú pháp.
- Dữ liệu `uint16` cần `rescale`, nếu không tile ra PNG 16-bit và hiển thị gần như đen.
- Web và TiTiler chạy ở hai cổng khác nhau nên cần CORS. TiTiler mặc định cho phép mọi origin; đã kiểm tra bằng yêu cầu preflight.
- Trên Windows, dùng đường dẫn tuyệt đối dạng `D:/...` thay cho `file:///`.

**Hiệu năng.** Script `benchmark_tiles.py` gọi mỗi tile hai lượt (lạnh/nóng) ở zoom 14–22, với tối đa 9 tile mỗi zoom. Kết quả chạy thử trên máy phát triển (COG giả lập cùng kích thước): mọi tile trả HTTP 200. Từ z15 trở lên, thời gian trung vị khoảng 20–45 ms/tile; z14 chậm hơn (80–220 ms) vì phải đọc overview nhỏ nhất rồi chiếu lại cả ảnh vào một tile. ⬜ *Điền bảng `docs/tile_benchmark.md` đo trên máy demo với COG thật.*

**Hạn chế.** Dữ liệu là DN thô, chưa hiệu chuẩn phản xạ, nên NDVI/NDRE chỉ có ý nghĩa tương đối và ngưỡng `rescale` của chỉ số là quy ước hiển thị. TiTiler đọc file cục bộ, phù hợp cho demo một máy. Muốn triển khai nhiều người dùng thì cần đặt COG lên object storage (S3/HTTP) và bật cache tile.
