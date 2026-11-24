#!/usr/bin/env python3
"""
Giai đoạn 5 (Nam Anh): Sinh URL tile TiTiler (RGB / CIR / NDVI / NDRE) cho Leaflet.

Ngưỡng rescale của RGB/CIR lấy từ phân vị 2–98% của pixel hợp lệ (đọc overview, chỉ vài giây),
nên ảnh không bị tối/cháy khi đổi dữ liệu. Không cần server đang chạy.

    python scripts/make_titiler_urls.py
    python scripts/make_titiler_urls.py --host http://localhost:8000 --cog data/outputs/cog_multispectral.tif

Đầu ra:
    web/tiles.json          cấu hình lớp tile cho web (Đức đọc bằng fetch)
    in ra màn hình          URL copy-paste được
"""

import argparse
import json
import os
from urllib.parse import quote

import numpy as np
import rasterio

# Band theo hợp đồng 4.4.A: 1 Blue, 2 Green, 3 Red, 4 RedEdge, 5 NIR
RGB = (3, 2, 1)
CIR = (5, 3, 2)
NDVI = "(b5-b3)/(b5+b3)"
NDRE = "(b5-b4)/(b5+b4)"
TILE_PATH = "/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png"


def band_percentiles(cog_path, p_low, p_high):
    with rasterio.open(cog_path) as ds:
        if tuple(ds.descriptions) != ("Blue", "Green", "Red", "RedEdge", "NIR"):
            raise SystemExit(f"Description band không đúng hợp đồng: {ds.descriptions}")
        shape = (max(1, ds.height // 8), max(1, ds.width // 8))
        stats, bounds = {}, None
        for b in range(1, 6):
            arr = ds.read(b, out_shape=shape, masked=True).compressed()
            lo, hi = np.percentile(arr, (p_low, p_high))
            stats[b] = (int(lo), int(hi))
        from rasterio.warp import transform_bounds
        bounds = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    return stats, bounds


def build_url(host, cog_abs, params):
    q = [("url", cog_abs)] + params
    # quote toàn bộ giá trị: '+' trong expression PHẢI thành %2B, nếu không server hiểu là dấu cách
    query = "&".join(f"{k}={quote(str(v), safe=',-.')}" for k, v in q)
    return f"{host}{TILE_PATH}?{query}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cog", default="data/outputs/cog_multispectral.tif")
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--p-low", type=float, default=2)
    ap.add_argument("--p-high", type=float, default=98)
    ap.add_argument("--out-json", default="web/tiles.json")
    args = ap.parse_args()

    cog_abs = os.path.abspath(args.cog).replace("\\", "/")  # Windows: D:/... vẫn đọc được
    st, bounds = band_percentiles(args.cog, args.p_low, args.p_high)

    def bands_params(bands):
        p = [("bidx", b) for b in bands]
        p += [("rescale", f"{st[b][0]},{st[b][1]}") for b in bands]
        return p

    index_params = lambda expr, rescale: [("expression", expr), ("rescale", rescale),
                                          ("colormap_name", "rdylgn")]
    layers = [
        {"id": "rgb", "name": "Ảnh trực giao RGB (3,2,1)", "url": build_url(args.host, cog_abs, bands_params(RGB))},
        {"id": "cir", "name": "Màu giả hồng ngoại CIR (5,3,2)", "url": build_url(args.host, cog_abs, bands_params(CIR))},
        {"id": "ndvi", "name": "NDVI (b5-b3)/(b5+b3)", "url": build_url(args.host, cog_abs, index_params(NDVI, "-0.2,0.8"))},
        {"id": "ndre", "name": "NDRE (b5-b4)/(b5+b4)", "url": build_url(args.host, cog_abs, index_params(NDRE, "0,0.5"))},
    ]
    config = {
        "titiler": args.host,
        "cog": cog_abs,
        "bounds_wgs84": [round(v, 7) for v in bounds],  # [west, south, east, north]
        "minZoom": 14,
        "maxNativeZoom": 22,
        "rescale_percentiles": [args.p_low, args.p_high],
        "band_rescale": {f"b{b}": list(v) for b, v in st.items()},
        "layers": layers,
    }
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"COG    : {cog_abs}")
    print("Rescale: " + ", ".join(f"b{b}={lo}-{hi}" for b, (lo, hi) in st.items()))
    print(f"Bounds : {config['bounds_wgs84']}\n")
    for l in layers:
        print(f"[{l['id']}] {l['name']}\n{l['url']}\n")
    print(f"Đã ghi {args.out_json}")


if __name__ == "__main__":
    main()
