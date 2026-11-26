#!/usr/bin/env python3
"""
Giai đoạn 3 (Nhánh AI - Hinh): Nhận diện Tán Cọ Dầu (Palm) bằng YOLO & Xuất GeoJSON Schema 4.4.B
Đồ án: Xử lý ảnh viễn thám & WebGIS
"""

import argparse
import json
import logging
import math
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
os.environ["YOLO_VERBOSE"] = "False"
logging.getLogger("ultralytics").setLevel(logging.ERROR)

import numpy as np
import rasterio
import torch
import torchvision
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.enums import MaskFlags
from ultralytics import YOLO

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from extract_rgb import extract_and_stretch_rgb, resolve_input_raster

DEFAULT_MODEL_PATH = "docs/best.pt"

# Quy ước ánh xạ nhãn theo Docs/note_hinh_tan_cay.md (mặc định nhận class palm)
PALM_CLASS_ALIASES = {"palm", "oil_palm", "tree", "0"}
COLOR_MAP = {
    "palm": "#00FF00",       # Xanh lá Neon (nổi bật trên nền tán cây)
    "person": "#FF00FF",     # Tím hồng
    "vehicle": "#00FFFF",    # Xanh lơ
    "building": "#FF0000",   # Đỏ
    "machinery": "#FF9900",  # Cam
    "other": "#FFFF00",      # Vàng
}


def resolve_model_path(model_arg: str | None) -> str:
    """Ưu tiên weights fine-tuned docs/best.pt; tuyệt đối không âm thầm fallback về COCO."""
    if model_arg:
        if not os.path.exists(model_arg):
            raise FileNotFoundError(f"Không tìm thấy tệp weights YOLO: {model_arg}")
        return model_arg

    if os.path.exists(DEFAULT_MODEL_PATH):
        return DEFAULT_MODEL_PATH

    raise FileNotFoundError(
        f"Chưa tìm thấy checkpoint đã huấn luyện tại {DEFAULT_MODEL_PATH}. "
        "Hãy hoàn tất Giai đoạn 4 (train_palm_yolo.py) hoặc truyền --model tường minh."
    )


def load_or_extract_rgb(rgb_path: str, source_raster: str = "auto") -> str:
    """Đảm bảo ortho_rgb_3band.tif tồn tại và đồng bộ với nguồn ưu tiên (COG 4.4.A nếu có)."""
    resolved_src = resolve_input_raster(source_raster)
    resolved_src_abs = os.path.abspath(resolved_src)

    needs_extract = not os.path.exists(rgb_path)
    if not needs_extract:
        try:
            with rasterio.open(rgb_path) as existing:
                src_tag = existing.tags().get("SOURCE_RASTER")
                if src_tag != resolved_src_abs:
                    print(
                        f"Nguồn raster thay đổi ({src_tag} -> {resolved_src_abs}); trích xuất lại RGB..."
                    )
                    needs_extract = True
                elif os.path.getmtime(resolved_src_abs) > os.path.getmtime(rgb_path):
                    print(f"Tệp nguồn {resolved_src} mới hơn {rgb_path}; trích xuất lại RGB...")
                    needs_extract = True
        except Exception:
            needs_extract = True

    if needs_extract:
        extract_and_stretch_rgb(input_path=resolved_src, output_tif=rgb_path)

    return rgb_path


def compute_pixel_size_meters(src_crs, transform, width: int, height: int) -> tuple[float, float]:
    """Tính kích thước 1 pixel theo mét (lấy trực tiếp nếu hệ chiếu UTM, hoặc quy đổi UTM tại tâm nếu EPSG:4326)."""
    if src_crs and src_crs.is_projected:
        return abs(float(transform.a)), abs(float(transform.e))

    cx, cy = width / 2.0, height / 2.0
    lon0, lat0 = transform * (cx, cy)
    lon1, lat1 = transform * (cx + 1.0, cy + 1.0)
    utm_zone = int(math.floor((lon0 + 180.0) / 6.0) + 1)
    epsg_utm = f"EPSG:{32600 + utm_zone if lat0 >= 0 else 32700 + utm_zone}"
    to_utm = Transformer.from_crs(src_crs or "EPSG:4326", epsg_utm, always_xy=True)
    x0, y0 = to_utm.transform(lon0, lat0)
    x1, y1 = to_utm.transform(lon1, lat1)
    return abs(x1 - x0), abs(y1 - y0)


def read_rgb_and_mask(rgb_tif_path: str):
    """Đọc ảnh RGB 8-bit, mask hợp lệ và metadata không gian từ GeoTIFF RGB."""
    with rasterio.open(rgb_tif_path) as src:
        width, height = src.width, src.height
        src_crs = src.crs
        transform = src.transform

        r = src.read(1)
        g = src.read(2)
        b = src.read(3)
        rgb_img = np.dstack([r, g, b])

        mask_flags = src.mask_flag_enums[0] if src.mask_flag_enums else []
        internal_mask = src.read_masks(1)
        if MaskFlags.per_dataset in mask_flags or internal_mask.min() == 0:
            valid_mask = internal_mask > 0
        else:
            valid_mask = (r > 0) | (g > 0) | (b > 0)

    return rgb_img, valid_mask, width, height, src_crs, transform


def compute_forestry_stats(
    final_boxes: list[dict],
    valid_mask: np.ndarray,
    px_w_m: float,
    px_h_m: float,
) -> dict:
    """Tính tổng số tán, diện tích hợp lệ (ha), mật độ cọ/ha và phân bố đường kính tán (m)."""
    valid_area_ha = float(valid_mask.sum()) * (px_w_m * px_h_m) / 10000.0
    diameters_m = []
    for item in final_boxes:
        x1, y1, x2, y2 = item["box"]
        w_m = (x2 - x1) * px_w_m
        h_m = (y2 - y1) * px_h_m
        diam = (w_m + h_m) / 2.0
        item["diameter_m"] = round(diam, 2)
        diameters_m.append(diam)

    density = (len(final_boxes) / valid_area_ha) if valid_area_ha > 0 else 0.0
    stats = {
        "total_palms": len(final_boxes),
        "valid_area_ha": round(valid_area_ha, 4),
        "density_per_ha": round(density, 2),
        "pixel_size_m": [round(px_w_m, 5), round(px_h_m, 5)],
        "crown_diameter_m": {
            "min": round(min(diameters_m), 2) if diameters_m else 0.0,
            "mean": round(float(np.mean(diameters_m)), 2) if diameters_m else 0.0,
            "median": round(float(np.median(diameters_m)), 2) if diameters_m else 0.0,
            "max": round(max(diameters_m), 2) if diameters_m else 0.0,
        },
    }
    return stats


def export_geojson(
    final_boxes: list[dict],
    transform,
    src_crs,
    output_geojson: str,
) -> int:
    """Chuyển đổi pixel bounding box sang EPSG:4326 Polygon và ghi GeoJSON chuẩn Schema 4.4.B."""
    is_wgs84 = (src_crs.to_epsg() == 4326) if src_crs else False
    transformer = None if is_wgs84 else Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    def _to_lonlat(px: float, py: float) -> tuple[float, float]:
        gx, gy = transform * (px, py)
        if transformer is None:
            return float(gx), float(gy)
        lon, lat = transformer.transform(gx, gy)
        return float(lon), float(lat)

    features = []
    for idx, item in enumerate(final_boxes, 1):
        x1, y1, x2, y2 = item["box"]
        corners_px = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
        gps_corners = [
            [round(lon, 7), round(lat, 7)]
            for lon, lat in (_to_lonlat(px, py) for px, py in corners_px)
        ]

        c_lon, c_lat = _to_lonlat((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [gps_corners]},
            "properties": {
                "id": idx,
                "class_name": item["class_name"],
                "confidence": round(item["conf"], 3),
                "tile_id": item["tile_id"],
                "center_lon": round(c_lon, 7),
                "center_lat": round(c_lat, 7),
            },
        })

    out_dir = os.path.dirname(output_geojson)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_geojson, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)
    return len(features)


def save_visualization(
    rgb_img: np.ndarray,
    final_boxes: list[dict],
    output_visualized: str,
    width: int,
    height: int,
) -> None:
    """Vẽ bounding boxes lên ảnh xem trước kích thước tối đa 2400px."""
    if not output_visualized or not final_boxes:
        return
    scale = 2400.0 / max(width, height)
    vw, vh = int(width * scale), int(height * scale)
    pil_img = Image.fromarray(rgb_img).resize((vw, vh), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(pil_img)

    for item in final_boxes:
        bx1, by1, bx2, by2 = item["box"]
        sx1, sy1, sx2, sy2 = int(bx1 * scale), int(by1 * scale), int(bx2 * scale), int(by2 * scale)
        cname = item["class_name"]
        color = COLOR_MAP.get(cname, "#00FF00")
        draw.rectangle([sx1, sy1, sx2, sy2], outline=color, width=3)
        draw.text((sx1 + 2, max(0, sy1 - 12)), f"{cname} {item['conf']:.2f}", fill=color)

    out_dir = os.path.dirname(output_visualized)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pil_img.save(output_visualized, quality=90)


def sliding_window_yolo_detection(
    rgb_tif_path: str,
    output_geojson: str,
    output_raw_json: str,
    output_stats_json: str,
    output_visualized: str | None = None,
    model_path: str | None = None,
    device: str = "cpu",
    tile_size: int = 640,
    overlap: float = 0.15,
    conf_thresh: float = 0.25,
    nms_iou_thresh: float = 0.50,
    min_box_valid_ratio: float = 0.50,
) -> None:
    resolved_model = resolve_model_path(model_path)
    rgb_img, valid_mask, width, height, src_crs, transform = read_rgb_and_mask(rgb_tif_path)
    px_w_m, px_h_m = compute_pixel_size_meters(src_crs, transform, width, height)

    model = YOLO(resolved_model)
    class_names = model.names

    step = int(tile_size * (1.0 - overlap))
    x_coords = list(range(0, width, step))
    y_coords = list(range(0, height, step))
    total_tiles = len(x_coords) * len(y_coords)

    raw_detections = []
    skipped_background = 0
    filtered_nodata_boxes = 0
    valid_tiles_count = 0

    t_start = time.perf_counter()

    for r_idx, y in enumerate(y_coords):
        for c_idx, x in enumerate(x_coords):
            tile_id = f"r{r_idx:03d}_c{c_idx:03d}"
            x_end = min(x + tile_size, width)
            y_end = min(y + tile_size, height)

            tile_valid = valid_mask[y:y_end, x:x_end]
            if float(tile_valid.mean()) < 0.05:
                skipped_background += 1
                continue

            patch = rgb_img[y:y_end, x:x_end]
            ph, pw, _ = patch.shape
            valid_tiles_count += 1

            if ph < tile_size or pw < tile_size:
                padded = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)
                padded[:ph, :pw] = patch
                patch_to_infer = padded
            else:
                patch_to_infer = patch

            results = model.predict(patch_to_infer, conf=conf_thresh, device=device, verbose=False)
            for res in results:
                for box in res.boxes:
                    bx1, by1, bx2, by2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())

                    if bx1 >= pw or by1 >= ph:
                        continue
                    gx1 = max(0.0, float(bx1 + x))
                    gy1 = max(0.0, float(by1 + y))
                    gx2 = min(float(x_end), float(bx2 + x))
                    gy2 = min(float(y_end), float(by2 + y))
                    if gx2 <= gx1 or gy2 <= gy1:
                        continue

                    orig_name = str(class_names.get(cls_id, cls_id)).strip().lower()
                    if orig_name not in PALM_CLASS_ALIASES:
                        continue

                    # Lọc bỏ box nằm chủ yếu trên nền NoData
                    ix1, iy1, ix2, iy2 = int(gx1), int(gy1), max(int(gx2), int(gx1) + 1), max(int(gy2), int(gy1) + 1)
                    cx = min(width - 1, max(0, int((gx1 + gx2) / 2.0)))
                    cy = min(height - 1, max(0, int((gy1 + gy2) / 2.0)))
                    box_mask_ratio = float(valid_mask[iy1:iy2, ix1:ix2].mean())
                    if not valid_mask[cy, cx] or box_mask_ratio < min_box_valid_ratio:
                        filtered_nodata_boxes += 1
                        continue

                    raw_detections.append({
                        "box": [gx1, gy1, gx2, gy2],
                        "conf": conf,
                        "class_name": "palm",
                        "orig_name": orig_name,
                        "tile_id": tile_id,
                    })

    t_infer_total = time.perf_counter() - t_start
    ms_per_tile = (t_infer_total / max(valid_tiles_count, 1)) * 1000.0

    raw_dir = os.path.dirname(output_raw_json)
    if raw_dir:
        os.makedirs(raw_dir, exist_ok=True)
    with open(output_raw_json, "w", encoding="utf-8") as f:
        json.dump(raw_detections, f, ensure_ascii=False, indent=2)

    final_boxes = []
    if raw_detections:
        boxes_t = torch.tensor([d["box"] for d in raw_detections], dtype=torch.float32)
        scores_t = torch.tensor([d["conf"] for d in raw_detections], dtype=torch.float32)
        for k in torchvision.ops.nms(boxes_t, scores_t, nms_iou_thresh):
            final_boxes.append(raw_detections[k.item()])

    stats = compute_forestry_stats(final_boxes, valid_mask, px_w_m, px_h_m)
    feature_count = export_geojson(final_boxes, transform, src_crs, output_geojson)

    stats_dir = os.path.dirname(output_stats_json)
    if stats_dir:
        os.makedirs(stats_dir, exist_ok=True)
    with open(output_stats_json, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    save_visualization(rgb_img, final_boxes, output_visualized, width, height)

    print("Thông tin ảnh đầu vào:")
    print(f"  Tệp RGB: {rgb_tif_path} ({width} x {height} px, {src_crs})")
    print(f"  GSD quy đổi: {px_w_m:.4f} x {px_h_m:.4f} m/px (Diện tích hợp lệ: {stats['valid_area_ha']:.2f} ha)")
    print("\nQuá trình nhận diện Tán Cọ Dầu (YOLO):")
    print(f"  Mô hình: {resolved_model} | Thiết bị: {device.upper()}")
    print(f"  Sliding Window: {tile_size}x{tile_size} px, overlap {int(overlap * 100)}%")
    print(f"  Ô hợp lệ: {valid_tiles_count}/{total_tiles} (bỏ {skipped_background} ô NoData; lọc {filtered_nodata_boxes} box rìa)")
    print(f"  Thời gian suy luận: {t_infer_total:.2f}s ({ms_per_tile:.1f} ms/ô)")
    print(f"  Kết quả: {len(raw_detections)} box thô -> {len(final_boxes)} tán sau NMS -> {feature_count} GeoJSON Features")
    print(f"  Mật độ cọ: {stats['density_per_ha']:.1f} cây/ha | Đường kính tán TB: {stats['crown_diameter_m']['mean']:.2f} m")
    print(f"\nĐã xuất: {output_geojson}, {output_stats_json}, {output_raw_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nhận diện Tán Cọ Dầu trên ảnh UAV & Xuất GeoJSON WGS84")
    parser.add_argument("--rgb", default="data/outputs/ortho_rgb_3band.tif", help="Đường dẫn GeoTIFF RGB")
    parser.add_argument("--multispectral", default="auto", help="Nguồn COG/Orthomosaic (mặc định auto: ưu tiên COG)")
    parser.add_argument("--output-geojson", default="data/outputs/detections.geojson", help="File GeoJSON 4.4.B")
    parser.add_argument("--output-raw", default="data/outputs/detections_raw.json", help="File JSON trước NMS")
    parser.add_argument("--output-stats", default="data/outputs/palm_stats.json", help="File thống kê lâm nghiệp")
    parser.add_argument("--output-vis", default="data/outputs/detections_visualized.jpg", help="Ảnh trực quan")
    parser.add_argument("--model", default=None, help=f"Weights YOLO (mặc định: {DEFAULT_MODEL_PATH})")
    parser.add_argument("--device", default="cpu", help="Thiết bị tính toán (mặc định: cpu)")
    parser.add_argument("--tile-size", type=int, default=640, help="Kích thước tile (px)")
    parser.add_argument("--overlap", type=float, default=0.15, help="Tỷ lệ chồng lấp (spec: 0.15)")
    parser.add_argument("--conf", type=float, default=0.25, help="Ngưỡng confidence (spec: 0.25)")
    parser.add_argument("--iou", type=float, default=0.50, help="Ngưỡng IoU NMS (spec: 0.50)")

    args = parser.parse_args()
    rgb_file = load_or_extract_rgb(args.rgb, args.multispectral)

    sliding_window_yolo_detection(
        rgb_tif_path=rgb_file,
        output_geojson=args.output_geojson,
        output_raw_json=args.output_raw,
        output_stats_json=args.output_stats,
        output_visualized=args.output_vis,
        model_path=args.model,
        device=args.device,
        tile_size=args.tile_size,
        overlap=args.overlap,
        conf_thresh=args.conf,
        nms_iou_thresh=args.iou,
    )
