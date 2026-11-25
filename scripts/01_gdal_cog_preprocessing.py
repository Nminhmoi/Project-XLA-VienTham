#!/usr/bin/env python3
"""
Giai đoạn 2 (Nam Anh): Chuẩn hóa Orthomosaic đa phổ -> Cloud-Optimized GeoTIFF (COG).

Một lệnh tái tạo data/outputs/cog_multispectral.tif từ ortho gốc của Metashape:
  1. Kiểm tra band (theo Description), CRS, pixel size, alpha/mask.
  2. Tách alpha (band 6) thành mask 0/255, bỏ band alpha khỏi dữ liệu.
  3. Reproject sang EPSG:32630 (UTM 30N), pixel 0.0413 m
     - dữ liệu: bilinear, có dùng alpha nguồn để không trộn pixel nền vào rìa ảnh
     - mask   : nearest
  4. Ghi pixel ngoài mask = 0 ở cả 5 band, gắn mask nội bộ PER_DATASET.
  5. Xuất COG: DEFLATE + PREDICTOR=2, tile 512, overviews tự động.

Chạy từ thư mục gốc repo:
    python scripts/01_gdal_cog_preprocessing.py
    python scripts/01_gdal_cog_preprocessing.py --input <ortho.tif> --output <cog.tif>

Dùng rasterio (có GDAL đi kèm), chạy được trên Windows/macOS/Linux, không cần OSGeo4W.
"""

import argparse
import os
import sys
import time

import numpy as np
import rasterio
import rasterio.shutil
from rasterio.enums import ColorInterp, Resampling
from rasterio.warp import calculate_default_transform, reproject

SPECTRAL = ["Blue", "Green", "Red", "RedEdge", "NIR"]
ALIASES = {
    "blue": "Blue", "b": "Blue",
    "green": "Green", "g": "Green",
    "red": "Red", "r": "Red",
    "rededge": "RedEdge", "red edge": "RedEdge", "red_edge": "RedEdge", "re": "RedEdge",
    "nir": "NIR", "near-infrared": "NIR", "near infrared": "NIR", "nearinfrared": "NIR",
}


def find_spectral_bands(src, band_order_arg):
    """Trả về list index (1-based) theo thứ tự Blue, Green, Red, RedEdge, NIR."""
    if band_order_arg:
        idx = [int(v) for v in band_order_arg.split(",")]
        if len(idx) != 5:
            sys.exit("--band-order cần đúng 5 số, ví dụ 1,2,3,4,5")
        return idx

    found = {}
    for i, desc in enumerate(src.descriptions, 1):
        name = ALIASES.get((desc or "").strip().lower())
        if name:
            found[name] = i
    missing = [n for n in SPECTRAL if n not in found]
    if missing:
        sys.exit(
            f"Không xác định được band {missing} từ Description {src.descriptions}.\n"
            "Kiểm tra bằng gdalinfo rồi chỉ định tường minh, ví dụ: --band-order 1,2,3,4,5"
        )
    return [found[n] for n in SPECTRAL]


def find_alpha_band(src):
    for i in range(1, src.count + 1):
        desc = (src.descriptions[i - 1] or "").strip().lower()
        if src.colorinterp[i - 1] == ColorInterp.alpha or desc == "alpha":
            return i
    return None


def read_source_mask(src, alpha_idx):
    """Mask nguồn dạng uint8: 255 = hợp lệ, 0 = nền."""
    if alpha_idx:
        print(f"  Mask nguồn : band {alpha_idx} (Alpha)")
        return np.where(src.read(alpha_idx) > 0, 255, 0).astype("uint8")
    # read_masks đã xử lý cả mask nội bộ lẫn nodata khai báo
    m = src.read_masks(1)
    if m.min() == 0:
        print("  Mask nguồn : mask nội bộ / nodata của raster")
    else:
        print("  Mask nguồn : KHÔNG có alpha/mask/nodata -> coi toàn bộ pixel là hợp lệ")
    return np.where(m > 0, 255, 0).astype("uint8")


def main():
    ap = argparse.ArgumentParser(description="Ortho đa phổ -> COG 5 band EPSG:32630 có mask")
    ap.add_argument("--input", default="data/orthomosaic/multispectral_ortho.tif")
    ap.add_argument("--output", default="data/outputs/cog_multispectral.tif")
    ap.add_argument("--dst-crs", default="EPSG:32630")
    ap.add_argument("--res", type=float, default=0.0413, help="Pixel size đầu ra (mét)")
    ap.add_argument("--band-order", help="Index 5 band Blue,Green,Red,RedEdge,NIR nếu thiếu Description")
    ap.add_argument("--overview-resampling", default="cubic",
                    help="cubic (giống COG hiện tại) | average | bilinear | nearest")
    ap.add_argument("--keep-temp", action="store_true", help="Giữ file trung gian để debug")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"Không tìm thấy {args.input} (tải từ Drive nhóm, xem docs/band_order.md)")

    t0 = time.perf_counter()
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    tmp_path = os.path.join(out_dir, "_tmp_ortho_utm_masked.tif")

    with rasterio.open(args.input) as src:
        print("1) Kiểm tra raster nguồn")
        print(f"  Tệp        : {args.input}")
        print(f"  Kích thước : {src.width} x {src.height} px, {src.count} band, {src.dtypes[0]}")
        print(f"  CRS        : {src.crs}")
        print(f"  Pixel size : {src.res[0]:.10g} x {src.res[1]:.10g}")
        print(f"  Description: {src.descriptions}")
        if src.crs is None:
            sys.exit("Raster nguồn không có CRS -> không thể reproject.")

        bands = find_spectral_bands(src, args.band_order)
        alpha_idx = find_alpha_band(src)
        print("  Band dùng  : " + ", ".join(f"{n}=b{i}" for n, i in zip(SPECTRAL, bands)))
        if alpha_idx in bands:
            sys.exit("Band alpha trùng với band phổ, kiểm tra lại --band-order.")

        src_mask = read_source_mask(src, alpha_idx)
        print(f"  Hợp lệ     : {(src_mask > 0).mean() * 100:.2f}% pixel nguồn")

        print(f"\n2) Reproject -> {args.dst_crs}, pixel {args.res} m")
        dst_tr, dst_w, dst_h = calculate_default_transform(
            src.crs, args.dst_crs, src.width, src.height, *src.bounds, resolution=args.res
        )
        print(f"  Lưới đích  : {dst_w} x {dst_h} px, gốc ({dst_tr.c:.4f}, {dst_tr.f:.4f})")

        warp_kw = dict(src_transform=src.transform, src_crs=src.crs,
                       dst_transform=dst_tr, dst_crs=args.dst_crs)

        dst_mask = np.zeros((dst_h, dst_w), dtype="uint8")
        reproject(src_mask, dst_mask, resampling=Resampling.nearest,
                  src_nodata=0, dst_nodata=0, **warp_kw)
        valid = dst_mask > 0

        profile = dict(driver="GTiff", width=dst_w, height=dst_h, count=5, dtype=src.dtypes[0],
                       crs=args.dst_crs, transform=dst_tr, tiled=True, blockxsize=512,
                       blockysize=512, compress="deflate", predictor=2, bigtiff="IF_SAFER")

        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), \
                rasterio.open(tmp_path, "w", **profile) as tmp:
            for out_i, (name, src_i) in enumerate(zip(SPECTRAL, bands), 1):
                # Ghép [band, alpha] để GDAL bỏ qua pixel nền khi nội suy bilinear
                pair = np.stack([src.read(src_i), src_mask.astype(src.dtypes[0])])
                dst = np.zeros((2, dst_h, dst_w), dtype=src.dtypes[0])
                reproject(pair, dst, resampling=Resampling.bilinear,
                          src_alpha=2, dst_alpha=2, **warp_kw)
                if out_i == 1:
                    # Pixel mép: mask nearest nói hợp lệ nhưng bilinear không có nguồn hợp lệ
                    # -> loại khỏi mask để tránh giá trị 0 (NDVI = 0/0). Alpha giống nhau cho mọi band.
                    valid &= dst[1] > 0
                    dst_mask[~valid] = 0
                band = dst[0]
                band[~valid] = 0
                tmp.write(band, out_i)
                tmp.set_band_description(out_i, name)
                print(f"  b{out_i} {name:<8} xong")
                del pair, dst, band
            tmp.colorinterp = [ColorInterp.gray] + [ColorInterp.undefined] * 4
            tmp.write_mask(dst_mask)
        print(f"  Hợp lệ     : {valid.mean() * 100:.2f}% pixel đích")

    print("\n3) Xuất COG")
    rasterio.shutil.copy(
        tmp_path, args.output, driver="COG",
        COMPRESS="DEFLATE", PREDICTOR="2", BLOCKSIZE="512", BIGTIFF="IF_SAFER",
        OVERVIEWS="AUTO", RESAMPLING=args.overview_resampling.upper(),
    )
    if not args.keep_temp:
        os.remove(tmp_path)

    with rasterio.open(args.output) as cog:
        m = cog.read_masks(1, out_shape=(cog.height // 8, cog.width // 8))
        print(f"  Tệp        : {args.output} ({os.path.getsize(args.output) / 1e6:.1f} MB)")
        print(f"  Kích thước : {cog.width} x {cog.height} px, {cog.count} band")
        print(f"  CRS        : {cog.crs}, pixel {cog.res[0]:.4f} m")
        print(f"  Description: {cog.descriptions}")
        print(f"  Overviews  : {cog.overviews(1)}")
        print(f"  Hợp lệ     : ~{(m > 0).mean() * 100:.2f}% (ước lượng trên overview)")
    print(f"\nHoàn tất sau {time.perf_counter() - t0:.1f} s. "
          f"Kiểm tra: python scripts/validate_cog.py {args.output}")


if __name__ == "__main__":
    main()
