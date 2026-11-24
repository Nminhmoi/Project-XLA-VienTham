#!/usr/bin/env python3
"""
Giai đoạn 2 (Nam Anh): Kiểm tra COG theo hợp đồng dữ liệu 4.4.A.

    python scripts/validate_cog.py                       # mặc định data/outputs/cog_multispectral.tif
    python scripts/validate_cog.py <cog.tif> --markdown  # in bảng Markdown để dán vào docs/cog_spec.md

Thoát với mã 1 nếu có mục FAIL (dùng được trong CI / trước khi bàn giao).
"""

import argparse
import os
import sys

import numpy as np
import rasterio
from rasterio.enums import MaskFlags
from rio_cogeo.cogeo import cog_validate

EXPECTED_BANDS = ("Blue", "Green", "Red", "RedEdge", "NIR")
EXPECTED_EPSG = 32630
EXPECTED_RES = 0.0413


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="data/outputs/cog_multispectral.tif")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        sys.exit(f"Không tìm thấy {args.path}")

    rows = []  # (mục, giá trị thực tế, đạt?)

    is_cog, errors, warnings = cog_validate(args.path, quiet=True)
    rows.append(("rio cogeo validate", "hợp lệ" if is_cog else f"lỗi: {errors}", is_cog))
    for w in warnings:
        rows.append(("  cảnh báo rio-cogeo", w, True))

    with rasterio.open(args.path) as ds:
        st = ds.tags(ns="IMAGE_STRUCTURE")
        rows.append(("LAYOUT", st.get("LAYOUT", "-"), st.get("LAYOUT") == "COG"))
        rows.append(("COMPRESSION", st.get("COMPRESSION", "-"), st.get("COMPRESSION") == "DEFLATE"))
        rows.append(("PREDICTOR", st.get("PREDICTOR", "-"), st.get("PREDICTOR") == "2"))

        blocks = set(ds.block_shapes)
        rows.append(("Block (tile)", ", ".join(f"{w}x{h}" for h, w in blocks), blocks == {(512, 512)}))

        ovr = ds.overviews(1)
        rows.append(("Overviews", f"{len(ovr)} mức {ovr}", len(ovr) >= 4))

        rows.append(("Số band", str(ds.count), ds.count == 5))
        rows.append(("Description", ", ".join(d or "?" for d in ds.descriptions),
                     tuple(ds.descriptions) == EXPECTED_BANDS))
        rows.append(("Kiểu dữ liệu", ds.dtypes[0], set(ds.dtypes) == {"uint16"}))

        epsg = ds.crs.to_epsg() if ds.crs else None
        rows.append(("CRS", f"EPSG:{epsg}", epsg == EXPECTED_EPSG))
        rx, ry = ds.res
        rows.append(("Pixel size", f"{rx:.6f} x {ry:.6f} m",
                     abs(rx - EXPECTED_RES) < 1e-6 and abs(ry - EXPECTED_RES) < 1e-6))
        rows.append(("Kích thước", f"{ds.width} x {ds.height} px", True))

        flags = ds.mask_flag_enums
        per_ds = all(f == [MaskFlags.per_dataset] for f in flags)
        rows.append(("Mask Flags", "PER_DATASET x5" if per_ds else str(flags), per_ds))

        mask = ds.read_masks(1) > 0
        valid_pct = mask.mean() * 100
        rows.append(("Tỷ lệ pixel hợp lệ", f"{valid_pct:.2f}% ({mask.sum():,} / {mask.size:,})",
                     20 < valid_pct <= 100))

        # Bất biến: ngoài mask = 0 ở mọi band; trong mask không có pixel 0 ở mọi band (tránh 0/0)
        out_nonzero = 0
        in_allzero = np.ones(mask.shape, dtype=bool)
        for i in range(1, ds.count + 1):
            b = ds.read(i)
            out_nonzero += int((b[~mask] != 0).sum())
            in_allzero &= b == 0
            del b
        in_allzero = int((in_allzero & mask).sum())
        rows.append(("Pixel ngoài mask khác 0", str(out_nonzero), out_nonzero == 0))
        rows.append(("Pixel trong mask = 0 ở mọi band", str(in_allzero), in_allzero == 0))

        size_mb = os.path.getsize(args.path) / 1e6
        rows.append(("Dung lượng", f"{size_mb:.1f} MB", True))

    ok = all(r[2] for r in rows)
    if args.markdown:
        print(f"Kết quả `validate_cog.py` cho `{args.path}`:\n")
        print("| Mục | Giá trị | Đạt |\n| :--- | :--- | :---: |")
        for name, val, good in rows:
            print(f"| {name.strip()} | {val} | {'✅' if good else '❌'} |")
    else:
        print(f"Kiểm tra COG: {args.path}\n")
        for name, val, good in rows:
            print(f"  [{'PASS' if good else 'FAIL'}] {name:<32} {val}")
    print(f"\nKẾT LUẬN: {'ĐẠT' if ok else 'KHÔNG ĐẠT'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
