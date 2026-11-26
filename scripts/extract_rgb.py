#!/usr/bin/env python3
"""
Trích xuất ảnh True Color RGB (8-bit) từ COG 5-band (EPSG:32630) hoặc Orthomosaic (EPSG:4326).
Tác giả: Dương Hữu Hinh
Tuân thủ Hợp đồng 4.4.A: ưu tiên data/outputs/cog_multispectral.tif, đọc band theo Description.
"""

import argparse
import os
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import ColorInterp, MaskFlags

DEFAULT_COG_PATH = "data/outputs/cog_multispectral.tif"
DEFAULT_ORTHO_PATH = "data/orthomosaic/multispectral_ortho.tif"


def resolve_input_raster(input_path: str | None = None) -> str:
    """Ưu tiên COG chuẩn 4.4.A; chỉ fallback sang orthomosaic nguồn khi chưa có COG."""
    if input_path and input_path != "auto":
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Không tìm thấy tệp đầu vào: {input_path}")
        return input_path

    if os.path.exists(DEFAULT_COG_PATH):
        return DEFAULT_COG_PATH
    if os.path.exists(DEFAULT_ORTHO_PATH):
        print(
            f"Cảnh báo: Chưa có {DEFAULT_COG_PATH}, tạm fallback sang {DEFAULT_ORTHO_PATH} (EPSG:4326)."
        )
        return DEFAULT_ORTHO_PATH

    raise FileNotFoundError(
        f"Không tìm thấy cả {DEFAULT_COG_PATH} lẫn {DEFAULT_ORTHO_PATH}."
    )


def find_rgb_band_indices(src: rasterio.DatasetReader) -> tuple[int, int, int]:
    """Xác định chỉ số 1-based của (Red, Green, Blue) qua band Description theo README 2.2."""
    desc_map = {}
    for idx, desc in enumerate(src.descriptions or (), start=1):
        if desc:
            desc_map[desc.strip().lower()] = idx

    if {"red", "green", "blue"}.issubset(desc_map.keys()):
        return desc_map["red"], desc_map["green"], desc_map["blue"]

    if src.count < 3:
        raise ValueError(f"Ảnh cần tối thiểu 3 band để tách RGB, hiện chỉ có {src.count} band.")

    print("Cảnh báo: Raster thiếu Description chuẩn; dùng quy ước fallback Red=3, Green=2, Blue=1.")
    return 3, 2, 1


def get_valid_mask(
    src: rasterio.DatasetReader,
    r_raw: np.ndarray,
    g_raw: np.ndarray,
    b_raw: np.ndarray,
) -> np.ndarray:
    """
    Xác định mặt nạ hợp lệ (valid mask):
    1. Alpha band (theo ColorInterp.alpha hoặc band 6 nguồn)
    2. Mask nội bộ PER_DATASET của COG (src.read_masks(1))
    3. Nodata khai báo
    4. Fallback lọc biên 0 và 65535 cho ảnh uint16 chưa gắn mask
    """
    for idx, ci in enumerate(src.colorinterp or (), start=1):
        if ci == ColorInterp.alpha:
            print(f"  Sử dụng Mask từ Alpha band {idx}")
            return src.read(idx) > 0

    if src.count >= 6:
        print("  Sử dụng Mask từ Band 6 (Alpha nguồn)")
        return src.read(6) > 0

    mask_flags = src.mask_flag_enums[0] if src.mask_flag_enums else []
    internal_mask = src.read_masks(1)
    if MaskFlags.per_dataset in mask_flags or internal_mask.min() == 0:
        print("  Sử dụng Mask nội bộ Raster (read_masks)")
        return internal_mask > 0

    if src.nodata is not None:
        print(f"  Sử dụng NoData khai báo: {src.nodata}")
        return (r_raw != src.nodata) & (g_raw != src.nodata) & (b_raw != src.nodata)

    if np.issubdtype(r_raw.dtype, np.integer) and r_raw.max() > 255:
        print("  Fallback: Lọc nền biên (loại giá trị 0 và 65535)")
        return (
            (r_raw > 0) & (r_raw < 65535)
            & (g_raw > 0) & (g_raw < 65535)
            & (b_raw > 0) & (b_raw < 65535)
        )

    print("  Fallback: Lọc nền đen (giá trị 0)")
    return (r_raw > 0) | (g_raw > 0) | (b_raw > 0)


def stretch_rgb_joint(
    r_raw: np.ndarray,
    g_raw: np.ndarray,
    b_raw: np.ndarray,
    valid_mask: np.ndarray,
    p_low: float,
    p_high: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """
    Kéo dải tương phản chung (joint percentile) trên cả 3 kênh RGB để hạn chế lệch sắc
    trên ảnh DN thô chưa hiệu chuẩn, đồng thời giữ giá trị hợp lệ trong [1, 255] (0 = NoData).
    """
    sample = np.concatenate([
        r_raw[valid_mask][::4],
        g_raw[valid_mask][::4],
        b_raw[valid_mask][::4],
    ])
    p_min, p_max = np.percentile(sample, (p_low, p_high))
    denom = max(float(p_max - p_min), 1e-6)

    def _scale_channel(band: np.ndarray) -> np.ndarray:
        out = np.zeros_like(band, dtype=np.uint8)
        scaled = (band[valid_mask].astype(np.float32) - p_min) / denom
        # Giữ pixel hợp lệ trong [1, 255] để không trùng với giá trị NoData = 0
        out[valid_mask] = np.clip(np.round(scaled * 254.0 + 1.0), 1, 255).astype(np.uint8)
        return out

    return _scale_channel(r_raw), _scale_channel(g_raw), _scale_channel(b_raw), float(p_min), float(p_max)


def extract_and_stretch_rgb(
    input_path: str | None,
    output_tif: str,
    output_preview: str | None = None,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> str:
    """Trích xuất GeoTIFF RGB 8-bit kèm mask nội bộ và metadata nguồn."""
    resolved_input = resolve_input_raster(input_path)

    with rasterio.open(resolved_input) as src:
        width, height = src.width, src.height
        count = src.count
        crs = src.crs
        profile = src.profile.copy()

        red_idx, green_idx, blue_idx = find_rgb_band_indices(src)
        r_raw = src.read(red_idx)
        g_raw = src.read(green_idx)
        b_raw = src.read(blue_idx)

        print("Thông tin ảnh đa phổ:")
        print(f"  Tệp nguồn: {resolved_input}")
        print(f"  Thứ tự band sử dụng: Red={red_idx}, Green={green_idx}, Blue={blue_idx}")
        valid_mask = get_valid_mask(src, r_raw, g_raw, b_raw)

    valid_ratio = (valid_mask.sum() / valid_mask.size) * 100.0
    print(f"  Kích thước: {width} x {height} px, {count} bands")
    print(f"  Hệ toạ độ: {crs}")
    print(f"  Tỷ lệ dữ liệu hợp lệ: {valid_ratio:.2f}%")

    r_8u, g_8u, b_8u, p_min, p_max = stretch_rgb_joint(
        r_raw, g_raw, b_raw, valid_mask, p_low, p_high
    )
    print(f"  Dải stretch chung (p{p_low:g}-p{p_high:g}): {p_min:.0f} - {p_max:.0f}")

    # Loại bỏ các key profile nguồn không tương thích với GTiff RGB thường
    for key in ("tiled", "blockxsize", "blockysize"):
        profile.pop(key, None)

    profile.update(
        driver="GTiff",
        dtype=rasterio.uint8,
        count=3,
        nodata=0,
        compress="deflate",
        photometric="RGB",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    out_dir = os.path.dirname(output_tif)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    mask_u8 = (valid_mask.astype(np.uint8) * 255)
    with rasterio.open(output_tif, "w", **profile) as dst:
        dst.write(r_8u, 1)
        dst.write(g_8u, 2)
        dst.write(b_8u, 3)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")
        dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue]
        dst.write_mask(mask_u8)
        dst.update_tags(
            SOURCE_RASTER=os.path.abspath(resolved_input),
            SOURCE_CRS=str(crs),
        )

    tif_size_mb = os.path.getsize(output_tif) / (1024 * 1024)
    print("\nTệp đầu ra:")
    print(f"  GeoTIFF RGB: {output_tif} ({tif_size_mb:.2f} MB)")

    if output_preview:
        prev_dir = os.path.dirname(output_preview)
        if prev_dir:
            os.makedirs(prev_dir, exist_ok=True)
        rgb_stack = np.dstack([r_8u, g_8u, b_8u])
        preview_img = Image.fromarray(rgb_stack)
        preview_img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        preview_img.save(output_preview, quality=90)
        print(f"  Ảnh xem trước: {output_preview}")

    return output_tif


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Trích xuất và chuẩn hóa RGB 8-bit từ COG / Orthomosaic"
    )
    parser.add_argument(
        "--input",
        default="auto",
        help=f"Đường dẫn GeoTIFF đầu vào (mặc định auto: ưu tiên {DEFAULT_COG_PATH})",
    )
    parser.add_argument(
        "--output-tif",
        default="data/outputs/ortho_rgb_3band.tif",
        help="Đường dẫn file GeoTIFF RGB đầu ra",
    )
    parser.add_argument(
        "--output-preview",
        default="data/outputs/ortho_rgb_preview.jpg",
        help="Đường dẫn file ảnh preview JPEG",
    )
    parser.add_argument("--p-low", type=float, default=2.0, help="Phân vị dưới (mặc định 2.0)")
    parser.add_argument("--p-high", type=float, default=98.0, help="Phân vị trên (mặc định 98.0)")

    args = parser.parse_args()
    extract_and_stretch_rgb(
        input_path=args.input,
        output_tif=args.output_tif,
        output_preview=args.output_preview,
        p_low=args.p_low,
        p_high=args.p_high,
    )
