#!/usr/bin/env python3
"""
Step 1: Trích xuất ảnh True Color RGB từ Orthomosaic Đa phổ 5 bands.
Tác giả: Dương Hữu Hinh
Môn học: Xử lý ảnh viễn thám & WebGIS
"""

import os
import argparse
import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from PIL import Image

def extract_and_stretch_rgb(
    input_path: str,
    output_tif: str,
    output_preview: str = None,
    p_low: float = 2.0,
    p_high: float = 98.0
):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy tệp: {input_path}")

    with rasterio.open(input_path) as src:
        width, height = src.width, src.height
        count = src.count
        crs = src.crs
        profile = src.profile.copy()
        
        if count < 3:
            raise ValueError(f"Ảnh cần có tối thiểu 3 bands để tạo ảnh RGB, hiện chỉ có {count} bands.")

        # Quy ước dải phổ theo band_order.md: Band 1: Blue, Band 2: Green, Band 3: Red
        r_raw = src.read(3)
        g_raw = src.read(2)
        b_raw = src.read(1)

    # Mặt nạ lọc dữ liệu hợp lệ: loại bỏ vùng biên 65535 (bão hòa/nodata) và điểm 0
    valid_mask = (r_raw < 65500) & (g_raw < 65500) & (b_raw < 65500) & (r_raw > 0)
    valid_ratio = (valid_mask.sum() / valid_mask.size) * 100

    print("Thông tin ảnh đa phổ:")
    print(f"  Tệp nguồn: {input_path}")
    print(f"  Kích thước: {width} x {height} px, {count} bands")
    print(f"  Hệ toạ độ: {crs}")
    print(f"  Tỷ lệ dữ liệu hợp lệ: {valid_ratio:.2f}%")

    def stretch_band(band_data, mask):
        vals = band_data[mask]
        p_min, p_max = np.percentile(vals, (p_low, p_high))
        stretched = np.zeros_like(band_data, dtype=np.uint8)
        clipped = np.clip(band_data, p_min, p_max)
        stretched[mask] = ((clipped[mask] - p_min) / (p_max - p_min + 1e-8) * 255.0).astype(np.uint8)
        return stretched, int(p_min), int(p_max)

    r_8u, r_min, r_max = stretch_band(r_raw, valid_mask)
    g_8u, g_min, g_max = stretch_band(g_raw, valid_mask)
    b_8u, b_min, b_max = stretch_band(b_raw, valid_mask)

    print("\nChuẩn hoá dải màu (Contrast Stretch):")
    print(f"  Kênh Đỏ (Band 3): {r_min} - {r_max}")
    print(f"  Kênh Xanh lục (Band 2): {g_min} - {g_max}")
    print(f"  Kênh Xanh lam (Band 1): {b_min} - {b_max}")

    # Cấu hình lưu trữ GeoTIFF RGB 3 kênh
    profile.update(
        driver="GTiff",
        dtype=rasterio.uint8,
        count=3,
        nodata=0,
        compress="deflate",
        photometric="RGB"
    )

    os.makedirs(os.path.dirname(output_tif), exist_ok=True)
    with rasterio.open(output_tif, "w", **profile) as dst:
        dst.write(r_8u, 1)
        dst.write(g_8u, 2)
        dst.write(b_8u, 3)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")
        dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue]

    print("\nTệp đầu ra:")
    tif_size_mb = os.path.getsize(output_tif) / (1024 * 1024)
    print(f"  GeoTIFF RGB: {output_tif} ({tif_size_mb:.2f} MB)")

    # Xuất ảnh preview (thumbnail)
    if output_preview:
        os.makedirs(os.path.dirname(output_preview), exist_ok=True)
        rgb_stack = np.dstack([r_8u, g_8u, b_8u])
        preview_img = Image.fromarray(rgb_stack)
        preview_img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        preview_img.save(output_preview, quality=90)
        print(f"  Ảnh xem trước: {output_preview}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trích xuất và chuẩn hóa RGB từ Orthomosaic Đa phổ")
    parser.add_argument("--input", default="data/orthomosaic/multispectral_ortho.tif", help="Đường dẫn file GeoTIFF đầu vào")
    parser.add_argument("--output-tif", default="data/outputs/ortho_rgb_3band.tif", help="Đường dẫn file GeoTIFF RGB đầu ra")
    parser.add_argument("--output-preview", default="data/outputs/ortho_rgb_preview.jpg", help="Đường dẫn file ảnh preview JPEG")
    parser.add_argument("--p-low", type=float, default=2.0, help="Phân vị dưới để cắt contrast (mặc định 2.0)")
    parser.add_argument("--p-high", type=float, default=98.0, help="Phân vị trên để cắt contrast (mặc định 98.0)")

    args = parser.parse_args()
    extract_and_stretch_rgb(
        input_path=args.input,
        output_tif=args.output_tif,
        output_preview=args.output_preview,
        p_low=args.p_low,
        p_high=args.p_high
    )
