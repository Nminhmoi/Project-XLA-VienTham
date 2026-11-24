#!/usr/bin/env python3
"""
Ngày 05 (Nam Anh): Đo thời gian tải tile TiTiler theo zoom cho từng lớp (RGB/CIR/NDVI/NDRE).

Cần TiTiler đang chạy (scripts/run_titiler.bat | .sh) và web/tiles.json đã được sinh.

    python scripts/benchmark_tiles.py                     # z14–z20, tối đa 9 tile/zoom
    python scripts/benchmark_tiles.py --zmin 16 --zmax 22 --out docs/tile_benchmark.md

Mỗi zoom lấy các tile phủ vùng ảnh (lấy mẫu tối đa --max-tiles ô quanh tâm), gọi 2 lượt:
lượt 1 = "lạnh" (GDAL chưa cache), lượt 2 = "nóng". Mọi phản hồi khác 200 được tính là lỗi.
"""

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

import morecantile  # có sẵn khi cài titiler


def fetch(url):
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = r.read()
            return r.status, (time.perf_counter() - t) * 1000, len(body)
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - t) * 1000, 0
    except Exception:
        return 0, (time.perf_counter() - t) * 1000, 0


def tiles_for_zoom(tms, bounds, z, max_tiles):
    w, s, e, n = bounds
    tiles = list(tms.tiles(w, s, e, n, [z]))
    cx, cy = (w + e) / 2, (s + n) / 2
    center = tms.tile(cx, cy, z)
    tiles.sort(key=lambda t: (t.x - center.x) ** 2 + (t.y - center.y) ** 2)
    return tiles[:max_tiles]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="web/tiles.json")
    ap.add_argument("--zmin", type=int, default=14)
    ap.add_argument("--zmax", type=int, default=20)
    ap.add_argument("--max-tiles", type=int, default=9)
    ap.add_argument("--out", default="docs/tile_benchmark.md")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    tms = morecantile.tms.get("WebMercatorQuad")

    try:
        urllib.request.urlopen(cfg["titiler"] + "/healthz", timeout=5)
    except Exception:
        raise SystemExit(f"Không kết nối được TiTiler tại {cfg['titiler']} — hãy chạy scripts/run_titiler trước.")

    rows, errors = [], []
    for layer in cfg["layers"]:
        for z in range(args.zmin, args.zmax + 1):
            tiles = tiles_for_zoom(tms, cfg["bounds_wgs84"], z, args.max_tiles)
            cold, warm, sizes = [], [], []
            for t in tiles:
                url = layer["url"].format(z=t.z, x=t.x, y=t.y)
                for bucket in (cold, warm):
                    code, ms, size = fetch(url)
                    if code != 200:
                        errors.append((layer["id"], z, t.x, t.y, code))
                    else:
                        bucket.append(ms)
                        sizes.append(size)
            rows.append({
                "layer": layer["id"], "z": z, "n": len(tiles),
                "cold_ms": statistics.median(cold) if cold else None,
                "warm_ms": statistics.median(warm) if warm else None,
                "max_ms": max(cold + warm) if cold + warm else None,
                "kb": statistics.mean(sizes) / 1024 if sizes else None,
                "fail": sum(1 for e in errors if e[0] == layer["id"] and e[1] == z),
            })
            r = rows[-1]
            fmt = lambda v: "-" if v is None else f"{v:.0f}"
            print(f"{r['layer']:<5} z{z:<2} {r['n']} tile  lạnh {fmt(r['cold_ms'])} ms  "
                  f"nóng {fmt(r['warm_ms'])} ms  max {fmt(r['max_ms'])} ms  lỗi {r['fail']}")

    fmt = lambda v, d=0: "-" if v is None else f"{v:.{d}f}"
    lines = [
        "# Đo hiệu năng tile TiTiler",
        "",
        f"- Server: `{cfg['titiler']}` — COG: `{cfg['cog']}`",
        f"- Zoom {args.zmin}–{args.zmax}, tối đa {args.max_tiles} tile/zoom quanh tâm ảnh, mỗi tile gọi 2 lượt "
        "(lạnh = lần đầu, nóng = lần lặp). Thời gian là trung vị, tính bằng ms, đo từ phía client.",
        f"- Thời điểm đo: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Lớp | Zoom | Số tile | Lạnh (ms) | Nóng (ms) | Max (ms) | Kích thước TB (KB) | Lỗi |",
        "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for r in rows:
        lines.append(f"| {r['layer']} | {r['z']} | {r['n']} | {fmt(r['cold_ms'])} | {fmt(r['warm_ms'])} | "
                     f"{fmt(r['max_ms'])} | {fmt(r['kb'], 1)} | {r['fail']} |")
    lines += ["", f"**Tổng số lỗi (khác HTTP 200): {len(errors)}**"]
    if errors:
        lines += ["", "| Lớp | z | x | y | HTTP |", "| :--- | :---: | :---: | :---: | :---: |"]
        lines += [f"| {l} | {z} | {x} | {y} | {c} |" for l, z, x, y, c in errors[:50]]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nĐã ghi {args.out} — tổng lỗi: {len(errors)}")


if __name__ == "__main__":
    main()
