"""QA nhánh phổ (Ngày 05) — kiểm tra output của scripts/03_spectral_ndvi_analysis.py.

Đọc  : data/outputs/cog_multispectral.tif, ndvi.tif, ndre.tif, lulc_class.tif,
       lulc_summary.json, detections.geojson (tán cọ của nhánh YOLO, chỉ đọc)
Ghi  : data/outputs/spectral_qa.json      kết quả kiểm tra + bảng số liệu
       docs/figures/spectral_qa_*.png     hình minh họa cho docs/spectral_qa.md

Chạy (sau khi đã chạy script 03):
    python scripts/qa_spectral.py
Mã thoát 0 = mọi kiểm tra ĐẠT, 1 = có kiểm tra KHÔNG ĐẠT.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs"
FIG = ROOT / "docs" / "figures"

_spec = importlib.util.spec_from_file_location("spectral", ROOT / "scripts" / "03_spectral_ndvi_analysis.py")
spectral = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spectral)

BAND_NAMES = ["Blue", "Green", "Red", "RedEdge", "NIR"]
CLASS_IDS = [1, 2, 3, 4]
CLASS_SHORT = {1: "1 Cây xanh tốt", 2: "2 Cỏ / cây bụi", 3: "3 Thưa / khô", 4: "4 Đất trống"}
COLORS = {cid: "#%02x%02x%02x" % spectral.LULC_COLORS[cid][:3] for cid in CLASS_IDS}
INK, MUTED, GRID = "#1f2328", "#59636e", "#d0d7de"

# Ba vùng crop 700x700 (col, row) dùng để đối chiếu trực quan với RGB
CROPS = {
    "Đất trống tây bắc": (900, 1300),
    "Vùng chuyển tiếp": (1500, 1900),
    "Rừng cọ": (2600, 2300),
}
CROP = 700


class Report:
    def __init__(self):
        self.checks = []

    def check(self, name: str, ok: bool, detail: str):
        self.checks.append({"name": name, "pass": bool(ok), "detail": detail})
        print(f"  [{'ĐẠT' if ok else 'LỖI'}] {name}: {detail}")

    @property
    def all_pass(self):
        return all(c["pass"] for c in self.checks)


def class_means(values: np.ndarray, cls: np.ndarray) -> dict:
    """Trung bình của values theo từng lớp (bỏ NaN)."""
    v = values.ravel().astype(np.float64)
    c = cls.ravel()
    ok = np.isfinite(v)
    s = np.bincount(c[ok], weights=v[ok], minlength=5)
    n = np.bincount(c[ok], minlength=5)
    return {cid: (float(s[cid] / n[cid]) if n[cid] else float("nan")) for cid in CLASS_IDS}


def stretch(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(rgb[:, mask], [2, 98])
    img = np.clip((rgb.astype(np.float32) - lo) / (hi - lo), 0, 1).transpose(1, 2, 0)
    img[~mask] = 1.0
    return img


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.perf_counter()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    FIG.mkdir(parents=True, exist_ok=True)
    rep = Report()
    summary = json.loads((OUT / "lulc_summary.json").read_text(encoding="utf-8"))
    thr = tuple(summary["ndvi_thresholds"])

    with rasterio.open(OUT / "cog_multispectral.tif") as src:
        mask = src.read_masks(1) > 0
        transform, crs = src.transform, src.crs
        bands = {i: src.read(i) for i in range(1, 6)}
    with rasterio.open(OUT / "ndvi.tif") as ds:
        ndvi = ds.read(1)
        ndvi_tf = ds.transform
    with rasterio.open(OUT / "ndre.tif") as ds:
        ndre = ds.read(1)
    with rasterio.open(OUT / "lulc_class.tif") as ds:
        cls = ds.read(1)

    # ------------------------------------------------------------------ 1. Diện tích
    print("1) Diện tích")
    pa = abs(transform.a * transform.e)
    rep.check("Diện tích 1 pixel = |ΔX·ΔY|", abs(pa - summary["pixel_area_m2"]) < 1e-8,
              f"{pa:.8f} m² (JSON {summary['pixel_area_m2']})")
    sat = mask & np.logical_or.reduce([bands[b] == 65535 for b in (3, 4, 5)])
    zero = mask & ~sat & ((bands[5].astype(np.int64) + bands[3]) == 0)
    expected_px = int(mask.sum() - sat.sum() - zero.sum())
    counts = np.bincount(cls.ravel(), minlength=5)
    rep.check("Pixel phân lớp = mask − bão hòa − mẫu số 0", expected_px == summary["total_valid_pixel_count"] == int(counts[1:].sum()),
              f"{int(mask.sum()):,} − {int(sat.sum()):,} − {int(zero.sum()):,} = {expected_px:,}; JSON {summary['total_valid_pixel_count']:,}; raster {int(counts[1:].sum()):,}")
    json_counts = [c["pixel_count"] for c in summary["classes"]]
    rep.check("Số pixel từng lớp: JSON = raster", json_counts == [int(counts[c]) for c in CLASS_IDS],
              ", ".join(f"lớp {c}: {int(counts[c]):,}" for c in CLASS_IDS))
    sum_m2 = sum(c["area_m2"] for c in summary["classes"])
    rep.check("Tổng diện tích các lớp = tổng hợp lệ", abs(sum_m2 - summary["total_valid_area_m2"]) <= 0.02,
              f"{sum_m2:,.2f} m² vs {summary['total_valid_area_m2']:,.2f} m²")
    total_m2 = expected_px * pa
    rep.check("Tổng hợp lệ = số pixel × diện tích pixel", abs(total_m2 - summary["total_valid_area_m2"]) <= 0.01,
              f"{expected_px:,} × {pa:.8f} = {total_m2:,.2f} m² = {total_m2 / 1e4:.4f} ha")
    pct = sum(c["percent"] for c in summary["classes"])
    rep.check("Tổng phần trăm ≈ 100", abs(pct - 100) <= 0.05, f"{pct:.2f}% (sai số làm tròn từng lớp)")

    # ------------------------------------------------------------------ 2. Nhất quán raster
    print("2) Nhất quán giữa NDVI và LULC")
    rep.check("NaN ở NDVI ⇔ lớp 0 ở LULC", bool(np.array_equal(np.isnan(ndvi), cls == 0)),
              f"{int(np.isnan(ndvi).sum()):,} pixel NaN")
    recls = spectral.classify_ndvi(ndvi, thr)
    mism = int((recls != cls).sum())
    rep.check("Phân lớp lại từ ndvi.tif khớp lulc_class.tif", mism == 0, f"{mism} pixel lệch, ngưỡng {list(thr)}")
    fin = ndvi[np.isfinite(ndvi)]
    rep.check("NDVI nằm trong [−1, 1]", bool(fin.min() >= -1 and fin.max() <= 1),
              f"min {fin.min():.3f}, max {fin.max():.3f}")
    sugg = spectral.suggest_thresholds(ndvi)
    rounded = tuple(round(t / 0.05) * 0.05 for t in sugg)
    rep.check("Otsu tính lại, làm tròn 0,05 = ngưỡng đang dùng", all(abs(a - b) < 1e-9 for a, b in zip(rounded, thr)),
              f"Otsu {[round(t, 3) for t in sugg]} → {[round(t, 2) for t in rounded]}")

    # ------------------------------------------------------------------ 3. Phổ từng lớp
    print("3) Phổ trung bình từng lớp")
    profile = {cid: {} for cid in CLASS_IDS}
    for b in range(1, 6):
        m = class_means(bands[b], cls)
        for cid in CLASS_IDS:
            profile[cid][BAND_NAMES[b - 1]] = round(m[cid], 1)
    for name, arr in (("NDVI", ndvi), ("NDRE", ndre)):
        m = class_means(arr, cls)
        for cid in CLASS_IDS:
            profile[cid][name] = round(m[cid], 4)
    for cid in CLASS_IDS:
        p = profile[cid]
        print(f"  lớp {cid}: " + "  ".join(f"{k} {v}" for k, v in p.items()))
    nd = [profile[c]["NDVI"] for c in CLASS_IDS]
    rep.check("NDVI trung bình giảm dần lớp 1 → 4", all(a > b for a, b in zip(nd, nd[1:])), str(nd))
    ratio = [float(profile[c]["NIR"] / profile[c]["Red"]) for c in CLASS_IDS]
    rep.check("Tỉ số NIR/Red giảm dần lớp 1 → 4", all(a > b for a, b in zip(ratio, ratio[1:])),
              str([round(r, 2) for r in ratio]))
    rep.check("Lớp 1: NIR cao nhất, Red thấp nhất (đặc trưng thực vật)",
              profile[1]["NIR"] == max(profile[c]["NIR"] for c in CLASS_IDS)
              and profile[1]["Red"] == min(profile[c]["Red"] for c in CLASS_IDS),
              f"NIR {profile[1]['NIR']:.0f}, Red {profile[1]['Red']:.0f}")
    rep.check("Lớp 4: Red > NIR (đặc trưng đất trống trên DN chưa hiệu chuẩn)",
              profile[4]["Red"] > profile[4]["NIR"], f"Red {profile[4]['Red']:.0f} > NIR {profile[4]['NIR']:.0f}")
    re = [profile[c]["NDRE"] for c in CLASS_IDS]
    rep.check("NDRE trung bình lớp 1 > lớp 4", re[0] > re[3], str(re))

    # ------------------------------------------------------------------ 4. Đối chiếu RGB
    print("4) Đối chiếu NDVI với RGB")
    rng = np.random.default_rng(0)
    idx = np.flatnonzero(cls.ravel() > 0)
    idx = rng.choice(idx, size=min(500_000, idx.size), replace=False)
    r, g, b = (bands[i].ravel()[idx].astype(np.float64) for i in (3, 2, 1))
    s = r + g + b
    exg = (2 * g - r - b) / np.where(s > 0, s, 1)   # Excess Green chuẩn hóa — chỉ dùng kênh nhìn thấy
    corr = float(np.corrcoef(ndvi.ravel()[idx], exg)[0, 1])
    rep.check("Tương quan NDVI ↔ chỉ số xanh từ RGB (ExG) dương", corr > 0.3, f"Pearson r = {corr:.3f} (500 000 pixel mẫu)")

    # ------------------------------------------------------------------ 5. Đối chiếu tán cọ (YOLO)
    print("5) Đối chiếu với tán cọ phát hiện bởi YOLO (nhánh Hinh)")
    palm = None
    det_path = OUT / "detections.geojson"
    if det_path.exists():
        from pyproj import Transformer
        from rasterio.features import rasterize
        gj = json.loads(det_path.read_text(encoding="utf-8"))
        feats = [f for f in gj["features"] if f["properties"].get("class_name") == "palm"]
        to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        shapes = []
        for f in feats:
            ring = [to_utm.transform(x, y) for x, y in f["geometry"]["coordinates"][0]]
            shapes.append(({"type": "Polygon", "coordinates": [ring]}, 1))
        inside = rasterize(shapes, out_shape=cls.shape, transform=transform, fill=0, dtype="uint8") == 1
        inside &= cls > 0
        in_counts = np.bincount(cls[inside], minlength=5)
        share_in = {cid: 100 * in_counts[cid] / in_counts[1:].sum() for cid in CLASS_IDS}
        share_all = {cid: 100 * counts[cid] / counts[1:].sum() for cid in CLASS_IDS}
        veg_in = share_in[1] + share_in[2]
        palm = {"n_boxes": len(feats), "pixels_in_boxes": int(in_counts[1:].sum()),
                "percent_in_boxes": {c: round(share_in[c], 2) for c in CLASS_IDS},
                "percent_whole_plot": {c: round(share_all[c], 2) for c in CLASS_IDS}}
        rep.check("Trong box tán cọ, lớp 1+2 chiếm đa số", veg_in > 70,
                  f"{veg_in:.1f}% (lớp 1: {share_in[1]:.1f}% trong box so với {share_all[1]:.1f}% toàn ảnh; {len(feats)} box)")
        rep.check("Trong box tán cọ, lớp 4 (đất) ít hơn toàn ảnh", share_in[4] < share_all[4],
                  f"{share_in[4]:.1f}% so với {share_all[4]:.1f}%")
    else:
        print("  (bỏ qua — chưa có detections.geojson)")

    # ------------------------------------------------------------------ 6. Bóng đổ
    print("6) Pixel tối (nghi bóng đổ)")
    bright = sum(bands[i].astype(np.float32) for i in range(1, 6))
    valid = cls > 0
    p5 = float(np.percentile(bright[valid], 5))
    dark = valid & (bright <= p5)
    dark_counts = np.bincount(cls[dark], minlength=5)
    dark_share = {cid: round(100 * dark_counts[cid] / dark_counts[1:].sum(), 2) for cid in CLASS_IDS}
    print("  5% pixel tối nhất rơi vào: " + ", ".join(f"lớp {c} {v}%" for c, v in dark_share.items()))

    # ------------------------------------------------------------------ 7. Độ nhạy ngưỡng
    print("7) Độ nhạy diện tích khi dịch từng ngưỡng ±0,05")
    base = {cid: counts[cid] / counts[1:].sum() * 100 for cid in CLASS_IDS}
    sens = []
    for k in range(3):
        for d in (-0.05, 0.05):
            t = list(thr)
            t[k] = round(t[k] + d, 4)
            c2 = np.bincount(spectral.classify_ndvi(ndvi, t).ravel(), minlength=5)
            pc = {cid: c2[cid] / c2[1:].sum() * 100 for cid in CLASS_IDS}
            delta = {cid: round(pc[cid] - base[cid], 2) for cid in CLASS_IDS}
            sens.append({"threshold": f"t{k + 1}", "shift": d, "new": t, "delta_percent_points": delta})
            print(f"  t{k + 1} {d:+.2f} → " + ", ".join(f"lớp {c} {v:+.2f}" for c, v in delta.items()))
    max_shift = max(abs(v) for s_ in sens for v in s_["delta_percent_points"].values())

    # ------------------------------------------------------------------ Hình
    print("8) Vẽ hình → docs/figures/")
    cmap = ListedColormap(["#ffffff"] + [COLORS[c] for c in CLASS_IDS])
    legend = [Patch(facecolor=COLORS[c], edgecolor=GRID, label=CLASS_SHORT[c]) for c in CLASS_IDS]

    # (a) phổ trung bình theo lớp
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(5)
    for cid in CLASS_IDS:
        y = [profile[cid][b] for b in BAND_NAMES]
        ax.plot(x, y, color=COLORS[cid], linewidth=2, marker="o", markersize=8,
                markeredgecolor="white", markeredgewidth=1.5, label=CLASS_SHORT[cid])
        ax.annotate(CLASS_SHORT[cid], (x[-1], y[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK)
    ax.set_xticks(x, BAND_NAMES)
    ax.set_xlim(-0.3, 5.6)
    ax.set_ylabel("DN trung bình (chưa hiệu chuẩn)", color=MUTED, fontsize=9)
    ax.set_title("Phổ trung bình từng lớp LULC", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    style(ax)
    fig.tight_layout()
    fig.savefig(FIG / "spectral_qa_profile.png", dpi=110)
    plt.close(fig)

    # (b) histogram NDVI + ngưỡng
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    edges = np.linspace(-0.7, 0.9, 161)
    h, _ = np.histogram(fin, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    bin_cls = spectral.classify_ndvi(centers.astype(np.float32), thr)
    ax.bar(centers, h / 1e3, width=edges[1] - edges[0], color=[COLORS[c] for c in bin_cls], linewidth=0)
    for k, t in enumerate(thr):
        ax.axvline(t, color=INK, linewidth=1, linestyle="--")
        ax.annotate(f"t{k + 1} = {t:+.2f}", (t, 1.0), xycoords=("data", "axes fraction"), xytext=(0, 3),
                    textcoords="offset points", fontsize=9, color=INK, ha="center", va="bottom")
    ax.set_xlabel("NDVI", color=MUTED, fontsize=9)
    ax.set_ylabel("Số pixel (nghìn)", color=MUTED, fontsize=9)
    ax.set_title("Phân bố NDVI và 3 ngưỡng Otsu", loc="left", color=INK, fontsize=11, pad=18)
    ax.legend(handles=legend, frameon=False, fontsize=8, loc="upper left")
    style(ax)
    fig.tight_layout()
    fig.savefig(FIG / "spectral_qa_histogram.png", dpi=110)
    plt.close(fig)

    # (c) RGB | NDVI | LULC trên 3 vùng
    fig, axes = plt.subplots(len(CROPS), 3, figsize=(10.5, 3.6 * len(CROPS)), layout="constrained")
    for row, (title, (c0, r0)) in enumerate(CROPS.items()):
        sl = (slice(r0, r0 + CROP), slice(c0, c0 + CROP))
        rgb = np.stack([bands[i][sl] for i in (3, 2, 1)])
        axes[row, 0].imshow(stretch(rgb, mask[sl]))
        im = axes[row, 1].imshow(ndvi[sl], cmap="RdYlGn", vmin=-0.2, vmax=0.8)
        axes[row, 2].imshow(cls[sl], cmap=cmap, vmin=0, vmax=4, interpolation="nearest")
        axes[row, 0].set_ylabel(title, fontsize=10, color=INK)
        for col, name in enumerate(("RGB (band 3-2-1)", "NDVI", "LULC")):
            axes[row, col].set_xticks([])
            axes[row, col].set_yticks([])
            if row == 0:
                axes[row, col].set_title(name, fontsize=10, color=INK)
    cb = fig.colorbar(im, ax=axes, location="right", shrink=0.4, pad=0.02)
    cb.set_label("NDVI (cột giữa)", fontsize=9, color=MUTED)
    fig.legend(handles=legend, loc="outside lower center", ncol=4, frameon=False, fontsize=9)
    fig.savefig(FIG / "spectral_qa_crops.png", dpi=90)
    plt.close(fig)

    # (d) thành phần lớp trong box tán cọ vs toàn ảnh
    if palm:
        fig, ax = plt.subplots(figsize=(7.5, 2.8))
        rows = [("Trong box tán cọ", palm["percent_in_boxes"]), ("Toàn ảnh", palm["percent_whole_plot"])]
        for y, (label, pcts) in enumerate(rows):
            left = 0.0
            for cid in CLASS_IDS:
                w = pcts[cid]
                ax.barh(y, w, left=left, color=COLORS[cid], edgecolor="white", linewidth=2, height=0.6)
                if w >= 7:
                    ax.text(left + w / 2, y, f"{w:.0f}%", ha="center", va="center", fontsize=9,
                            color="white" if cid in (1, 4) else INK)
                left += w
        ax.set_yticks([0, 1], [r[0] for r in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("% diện tích", color=MUTED, fontsize=9)
        ax.set_title(f"Thành phần LULC trong {palm['n_boxes']} box tán cọ (YOLO) so với toàn ảnh",
                     loc="left", color=INK, fontsize=11)
        ax.legend(handles=legend, frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.35))
        style(ax)
        ax.grid(False)
        fig.tight_layout()
        fig.savefig(FIG / "spectral_qa_palm.png", dpi=110, bbox_inches="tight")
        plt.close(fig)

    result = {
        "all_pass": rep.all_pass,
        "checks": rep.checks,
        "ndvi_thresholds": list(thr),
        "class_profile_mean": {str(c): profile[c] for c in CLASS_IDS},
        "ndvi_exg_pearson_r": round(corr, 4),
        "palm_check": None if palm is None else {**palm,
            "percent_in_boxes": {str(k): v for k, v in palm["percent_in_boxes"].items()},
            "percent_whole_plot": {str(k): v for k, v in palm["percent_whole_plot"].items()}},
        "dark_5pct_class_share": {str(c): v for c, v in dark_share.items()},
        "threshold_sensitivity": [{**s_, "delta_percent_points": {str(k): v for k, v in s_["delta_percent_points"].items()}}
                                  for s_ in sens],
        "threshold_sensitivity_max_abs_pp": round(max_shift, 2),
    }
    (OUT / "spectral_qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    n_ok = sum(c["pass"] for c in rep.checks)
    print(f"\nKẾT LUẬN: {'ĐẠT' if rep.all_pass else 'KHÔNG ĐẠT'} ({n_ok}/{len(rep.checks)} kiểm tra) "
          f"— {time.perf_counter() - t0:.1f} s")
    return 0 if rep.all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
