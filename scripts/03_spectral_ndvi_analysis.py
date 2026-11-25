"""Giai đoạn 4 — Phân tích phổ NDVI/NDRE, phân lớp LULC và tính diện tích.

Đầu vào : data/outputs/cog_multispectral.tif
          (1 = Blue, 2 = Green, 3 = Red, 4 = RedEdge, 5 = NIR; EPSG:32630; mask nội bộ)
Đầu ra  : data/outputs/ndvi.tif            Float32, NaN = không hợp lệ
          data/outputs/ndre.tif            Float32, NaN = không hợp lệ
          data/outputs/lulc_class.tif      Byte, 0 = nodata, 1..4 = lớp LULC
          data/outputs/lulc_summary.json   Diện tích từng lớp (theo docs hợp đồng dữ liệu, mục 4.4.C)
          data/outputs/spectral_stats.json Thống kê NDVI/NDRE (min/max/mean/std/percentile)
          data/outputs/ndvi_preview.png    Ảnh xem nhanh NDVI (colormap RdYlGn, nền trong suốt)

Chạy:
    python scripts/03_spectral_ndvi_analysis.py
    python scripts/03_spectral_ndvi_analysis.py --window 1709 1717 1000 1000   # thử trên crop

Quy ước: KHÔNG suy band từ src.count — luôn dùng index tường minh (3 = Red, 4 = RedEdge, 5 = NIR).
Pixel bị loại: ngoài mask, band bị bão hòa (= 65535 với uint16), hoặc mẫu số = 0.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "outputs" / "cog_multispectral.tif"
DEFAULT_OUTDIR = ROOT / "data" / "outputs"

BAND_RED, BAND_REDEDGE, BAND_NIR = 3, 4, 5

# id, tên, khoảng NDVI (để ghi JSON). Ranh giới đúng theo GIAI ĐOẠN 4 trong README:
#   NDVI > 0.45 -> 1 ; 0.20 <= NDVI <= 0.45 -> 2 ; 0 <= NDVI < 0.20 -> 3 ; NDVI < 0 -> 4
LULC_CLASSES = [
    (1, "Cây xanh tốt", [0.45, 1.0]),
    (2, "Thảm cỏ / cây thưa", [0.20, 0.45]),
    (3, "Đất trống / nhà cửa", [0.00, 0.20]),
    (4, "Mặt nước / trũng ẩm", [-1.0, 0.00]),
]
LULC_NODATA = 0

PREVIEW_VMIN, PREVIEW_VMAX = -0.2, 0.8  # khớp rescale NDVI của TiTiler


def normalized_difference(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b) trên pixel hợp lệ; NaN ở pixel không hợp lệ hoặc mẫu số = 0."""
    a = a.astype(np.float32, copy=False)
    b = b.astype(np.float32, copy=False)
    denom = a + b
    ok = valid & (denom != 0)
    out = np.full(a.shape, np.nan, dtype=np.float32)
    np.divide(a - b, denom, out=out, where=ok)
    return out


def classify_ndvi(ndvi: np.ndarray) -> np.ndarray:
    """Phân 4 lớp LULC theo ngưỡng NDVI; NaN -> LULC_NODATA."""
    cls = np.full(ndvi.shape, LULC_NODATA, dtype=np.uint8)
    finite = np.isfinite(ndvi)
    cls[finite & (ndvi > 0.45)] = 1
    cls[finite & (ndvi >= 0.20) & (ndvi <= 0.45)] = 2
    cls[finite & (ndvi >= 0.00) & (ndvi < 0.20)] = 3
    cls[finite & (ndvi < 0.00)] = 4
    return cls


def index_stats(arr: np.ndarray) -> dict:
    v = arr[np.isfinite(arr)]
    if v.size == 0:
        return {"valid_pixel_count": 0}
    p = np.percentile(v, [2, 25, 50, 75, 98])
    return {
        "valid_pixel_count": int(v.size),
        "min": round(float(v.min()), 4),
        "max": round(float(v.max()), 4),
        "mean": round(float(v.mean(dtype=np.float64)), 4),
        "std": round(float(v.std(dtype=np.float64)), 4),
        "p2": round(float(p[0]), 4),
        "p25": round(float(p[1]), 4),
        "median": round(float(p[2]), 4),
        "p75": round(float(p[3]), 4),
        "p98": round(float(p[4]), 4),
    }


def build_summary(cls: np.ndarray, crs: str, pixel_size_m: float, pixel_area_m2: float,
                  excluded: dict) -> dict:
    counts = np.bincount(cls.ravel(), minlength=len(LULC_CLASSES) + 1)
    total_px = int(counts[1:].sum())
    total_m2 = total_px * pixel_area_m2
    classes = []
    for cid, name, rng in LULC_CLASSES:
        n = int(counts[cid])
        m2 = n * pixel_area_m2
        classes.append({
            "id": cid,
            "name": name,
            "ndvi_range": rng,
            "pixel_count": n,
            "area_m2": round(m2, 2),
            "area_ha": round(m2 / 10_000, 4),
            "percent": round(100 * n / total_px, 2) if total_px else 0,
        })
    return {
        "crs": crs,
        "pixel_size_m": round(pixel_size_m, 6),
        "pixel_area_m2": round(pixel_area_m2, 8),
        "total_valid_area_ha": round(total_m2 / 10_000, 2),
        "total_valid_area_m2": round(total_m2, 2),
        "total_valid_pixel_count": total_px,
        "excluded_pixel_count": excluded,
        "classes": classes,
    }


def write_preview(ndvi: np.ndarray, path: Path, max_side: int) -> tuple[int, int]:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import colormaps
    from matplotlib.colors import Normalize

    step = max(1, int(np.ceil(max(ndvi.shape) / max_side)))
    small = ndvi[::step, ::step]
    rgba = colormaps["RdYlGn"](Normalize(PREVIEW_VMIN, PREVIEW_VMAX, clip=True)(small))
    rgba[~np.isfinite(small), 3] = 0.0
    import matplotlib.pyplot as plt
    plt.imsave(path, rgba)
    return small.shape


def run(input_path: Path, outdir: Path, window: Window | None = None,
        preview_max_side: int = 1500) -> dict:
    t0 = time.perf_counter()
    outdir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(input_path) as src:
        if src.count < BAND_NIR:
            raise ValueError(f"Cần >= {BAND_NIR} band (Blue, Green, Red, RedEdge, NIR); file có {src.count}.")
        if src.crs is None or not src.crs.is_projected:
            raise ValueError(f"CRS phải là hệ phẳng (mét) để tính diện tích; nhận được {src.crs}.")

        res_x, res_y = src.res
        pixel_area_m2 = abs(res_x * res_y)
        transform = src.window_transform(window) if window is not None else src.transform

        red = src.read(BAND_RED, window=window)
        rededge = src.read(BAND_REDEDGE, window=window)
        nir = src.read(BAND_NIR, window=window)
        in_mask = src.read_masks(BAND_RED, window=window) > 0
        if src.nodata is not None:
            in_mask &= (red != src.nodata) & (rededge != src.nodata) & (nir != src.nodata)

        sat_value = np.iinfo(red.dtype).max if np.issubdtype(red.dtype, np.integer) else None
        if sat_value is not None:
            saturated = in_mask & ((red == sat_value) | (rededge == sat_value) | (nir == sat_value))
        else:
            saturated = np.zeros_like(in_mask)
        valid = in_mask & ~saturated

        ndvi = normalized_difference(nir, red, valid)
        ndre = normalized_difference(nir, rededge, valid)
        del red, rededge, nir

        zero_denominator = int((valid & ~np.isfinite(ndvi)).sum())
        cls = classify_ndvi(ndvi)

        base = {
            "driver": "GTiff", "height": ndvi.shape[0], "width": ndvi.shape[1], "count": 1,
            "crs": src.crs, "transform": transform, "tiled": True,
            "blockxsize": 512, "blockysize": 512, "compress": "deflate", "BIGTIFF": "IF_SAFER",
        }
        crs_str = src.crs.to_string()

    fprofile = {**base, "dtype": "float32", "nodata": np.nan, "predictor": 3}
    for name, arr, desc in (("ndvi.tif", ndvi, "NDVI (b5-b3)/(b5+b3)"),
                            ("ndre.tif", ndre, "NDRE (b5-b4)/(b5+b4)")):
        with rasterio.open(outdir / name, "w", **fprofile) as dst:
            dst.write(arr, 1)
            dst.set_band_description(1, desc)

    with rasterio.open(outdir / "lulc_class.tif", "w",
                       **{**base, "dtype": "uint8", "nodata": LULC_NODATA, "predictor": 2}) as dst:
        dst.write(cls, 1)
        dst.set_band_description(1, "LULC: 1 Cay tot, 2 Co/thua, 3 Dat, 4 Nuoc")
        dst.write_colormap(1, {0: (0, 0, 0, 0), 1: (26, 150, 65, 255), 2: (166, 217, 106, 255),
                               3: (215, 160, 90, 255), 4: (43, 131, 186, 255)})

    summary = build_summary(cls, crs_str, abs(res_x), pixel_area_m2, {
        "outside_mask": int((~in_mask).sum()),
        "saturated": int(saturated.sum()),
        "zero_denominator": zero_denominator,
    })
    try:
        input_label = Path(input_path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        input_label = Path(input_path).name
    stats = {"input": input_label, "window": None if window is None else
             [int(window.col_off), int(window.row_off), int(window.width), int(window.height)],
             "ndvi": index_stats(ndvi), "ndre": index_stats(ndre)}

    (outdir / "lulc_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "spectral_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    write_preview(ndvi, outdir / "ndvi_preview.png", preview_max_side)

    stats["summary"] = summary
    stats["elapsed_s"] = round(time.perf_counter() - t0, 2)
    return stats


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="NDVI/NDRE + LULC + dien tich tu COG 5 band.")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="COG 5 band (mac dinh: %(default)s)")
    p.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Thu muc output (mac dinh: %(default)s)")
    p.add_argument("--window", type=int, nargs=4, metavar=("COL", "ROW", "W", "H"),
                   help="Chi xu ly mot cua so (vd: --window 1709 1717 1000 1000)")
    p.add_argument("--preview-max-side", type=int, default=1500, help="Canh dai nhat cua ndvi_preview.png")
    return p.parse_args(argv)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    if not args.input.exists():
        print(f"[LỖI] Không tìm thấy {args.input}", file=sys.stderr)
        return 1
    window = Window(*args.window) if args.window else None
    r = run(args.input, args.outdir, window, args.preview_max_side)

    s = r["summary"]
    print(f"Input : {r['input']}" + (f"  window={r['window']}" if r["window"] else ""))
    for key in ("ndvi", "ndre"):
        st = r[key]
        if st["valid_pixel_count"]:
            print(f"{key.upper():5}: min {st['min']:.3f}  max {st['max']:.3f}  mean {st['mean']:.3f}  "
                  f"median {st['median']:.3f}  ({st['valid_pixel_count']:,} px)")
    print(f"Tổng diện tích hợp lệ: {s['total_valid_area_m2']:,.2f} m² = {s['total_valid_area_ha']} ha  "
          f"| bị loại: {s['excluded_pixel_count']}")
    for c in s["classes"]:
        print(f"  {c['id']}. {c['name']:<22} {c['area_m2']:>12,.2f} m²  {c['area_ha']:>8.4f} ha  {c['percent']:>6.2f}%")
    print(f"Output: {args.outdir}  ({r['elapsed_s']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
