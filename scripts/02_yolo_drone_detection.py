#!/usr/bin/env python3
"""
Giai đoạn 3 (Thành viên Hinh): AI Object Detection trên ảnh Drone & Geo-referencing GeoJSON
Đồ án: Xử lý ảnh viễn thám & WebGIS
Tuân thủ Hợp đồng dữ liệu 4.4.B (Schema chuẩn cho WebGIS Leaflet)
"""

import os
import sys
import time
import json
import logging
import warnings
import argparse

warnings.filterwarnings("ignore")
os.environ["YOLO_VERBOSE"] = "False"
logging.getLogger("ultralytics").setLevel(logging.ERROR)

import numpy as np
import rasterio
from pyproj import Transformer
from PIL import Image, ImageDraw
import torch
import torchvision
from ultralytics import YOLO

# Bảng ánh xạ COCO sang danh mục chuẩn 4.4.B: vehicle, building, machinery, person, other
# Loại bỏ các nhãn ngoài domain nông nghiệp (broccoli, potted plant, skateboard, bird, v.v.)
CLASS_MAPPING = {
    "person": "person",
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "bicycle": "vehicle",
    "airplane": "vehicle",
    "boat": "vehicle",
    "train": "vehicle"
}

def load_or_extract_rgb(rgb_path: str, multispectral_path: str):
    """Đảm bảo file ảnh RGB 3 kênh đã tồn tại."""
    if os.path.exists(rgb_path):
        return rgb_path

    print(f"Chưa có tệp {rgb_path}, tiến hành trích xuất từ {multispectral_path}...")
    import subprocess
    cmd = [
        sys.executable,
        "scripts/extract_rgb.py",
        "--input", multispectral_path,
        "--output-tif", rgb_path
    ]
    subprocess.run(cmd, check=True)
    return rgb_path

def sliding_window_yolo_detection(
    rgb_tif_path: str,
    output_geojson: str,
    output_raw_json: str,
    output_visualized: str = None,
    model_name: str = "yolov8m.pt",
    device: str = "cpu",
    tile_size: int = 640,
    overlap: float = 0.15,
    conf_thresh: float = 0.25,
    nms_iou_thresh: float = 0.50
):
    # 1. Đọc dữ liệu ảnh và siêu dữ liệu địa lý
    with rasterio.open(rgb_tif_path) as src:
        width = src.width
        height = src.height
        src_crs = src.crs
        transform = src.transform

        r = src.read(1)
        g = src.read(2)
        b = src.read(3)
        rgb_img = np.dstack([r, g, b])
        del r, g, b

    # Chuẩn bị bộ chuyển đổi toạ độ sang WGS84 (EPSG:4326) nếu CRS chưa phải EPSG:4326
    is_wgs84 = src_crs.to_epsg() == 4326 if src_crs else True
    if not is_wgs84:
        transformer = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    # 2. Khởi tạo mô hình YOLO
    model = YOLO(model_name)
    class_names = model.names

    # 3. Phân mảnh ảnh dạng Cửa sổ trượt (Sliding Window Tiles)
    step = int(tile_size * (1.0 - overlap))
    x_coords = list(range(0, width, step))
    y_coords = list(range(0, height, step))
    total_tiles = len(x_coords) * len(y_coords)

    raw_detections = []
    skipped_background = 0
    valid_tiles_count = 0

    t_start = time.perf_counter()

    for r_idx, y in enumerate(y_coords):
        for c_idx, x in enumerate(x_coords):
            tile_id = f"r{r_idx:03d}_c{c_idx:03d}"
            x_end = min(x + tile_size, width)
            y_end = min(y + tile_size, height)
            
            patch = rgb_img[y:y_end, x:x_end]
            ph, pw, _ = patch.shape

            # Bỏ qua ô cắt chủ yếu là nền đen (NoData)
            if np.mean(patch) < 3.0:
                skipped_background += 1
                continue

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
                    bx2 = min(bx2, float(pw))
                    by2 = min(by2, float(ph))

                    orig_name = class_names[cls_id]

                    # Chỉ giữ các lớp thuộc danh mục chuẩn (person, vehicle, building, machinery)
                    # Bỏ các lớp rác do Domain Gap COCO (broccoli, potted plant, skateboard, bird, v.v.)
                    if orig_name in CLASS_MAPPING:
                        target_class = CLASS_MAPPING[orig_name]
                        gx1 = float(bx1 + x)
                        gy1 = float(by1 + y)
                        gx2 = float(bx2 + x)
                        gy2 = float(by2 + y)

                        raw_detections.append({
                            "box": [gx1, gy1, gx2, gy2],
                            "conf": conf,
                            "class_name": target_class,
                            "orig_name": orig_name,
                            "tile_id": tile_id
                        })

    t_infer_total = time.perf_counter() - t_start
    ms_per_tile = (t_infer_total / max(valid_tiles_count, 1)) * 1000.0

    # Lưu tệp thô trước NMS theo hợp đồng dữ liệu
    os.makedirs(os.path.dirname(output_raw_json), exist_ok=True)
    with open(output_raw_json, "w", encoding="utf-8") as f:
        json.dump(raw_detections, f, ensure_ascii=False, indent=2)

    # 4. Áp dụng Khử trùng lặp toàn diện (Class-Agnostic NMS)
    final_boxes = []
    if raw_detections:
        boxes_tensor = torch.tensor([d["box"] for d in raw_detections])
        scores_tensor = torch.tensor([d["conf"] for d in raw_detections])

        keep_indices = torchvision.ops.nms(boxes_tensor, scores_tensor, nms_iou_thresh)
        for k in keep_indices:
            final_boxes.append(raw_detections[k.item()])

    # Thống kê phân lớp
    stats = {}
    for item in final_boxes:
        cname = item["class_name"]
        stats[cname] = stats.get(cname, 0) + 1

    print("Thông tin ảnh đầu vào:")
    print(f"  Tệp: {rgb_tif_path}")
    print(f"  Kích thước: {width} x {height} px")
    print(f"  Hệ toạ độ: {src_crs}")

    print("\nQuá trình nhận diện (YOLO):")
    print(f"  Mô hình: {model_name}")
    print(f"  Thiết bị tính toán: {device.upper()}")
    print(f"  Kỹ thuật: Sliding Window (tile {tile_size}x{tile_size}, overlap {int(overlap * 100)}%)")
    print(f"  Ô quét hợp lệ: {valid_tiles_count}/{total_tiles} (đã bỏ qua {skipped_background} ô nền đen)")
    print(f"  Thời gian suy luận: {t_infer_total:.2f} giây (trung bình {ms_per_tile:.1f} ms/ô)")
    print(f"  Số đối tượng hợp lệ: {len(raw_detections)} thô -> {len(final_boxes)} sau khi khử trùng lặp (NMS)")

    print("\nThống kê đối tượng theo phân lớp:")
    for cname, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cname}: {count}")

    # 5. Ánh xạ Pixel -> GPS (WGS84 Lon/Lat) và xuất GeoJSON chuẩn Schema 4.4.B
    features = []
    for idx, item in enumerate(final_boxes, 1):
        x1, y1, x2, y2 = item["box"]

        # Toạ độ 4 góc polygon khép kín (5 điểm)
        p_top_left = transform * (x1, y1)
        p_top_right = transform * (x2, y1)
        p_bottom_right = transform * (x2, y2)
        p_bottom_left = transform * (x1, y2)

        corners = [p_top_left, p_top_right, p_bottom_right, p_bottom_left, p_top_left]

        if not is_wgs84:
            gps_corners = []
            for gx, gy in corners:
                lon, lat = transformer.transform(gx, gy)
                gps_corners.append([round(lon, 7), round(lat, 7)])
        else:
            gps_corners = [[round(gx, 7), round(gy, 7)] for gx, gy in corners]

        # Toạ độ tâm đối tượng (tách riêng center_lon và center_lat theo schema 4.4.B)
        center_pixel_x = (x1 + x2) / 2.0
        center_pixel_y = (y1 + y2) / 2.0
        center_geo_x, center_geo_y = transform * (center_pixel_x, center_pixel_y)
        if not is_wgs84:
            c_lon, c_lat = transformer.transform(center_geo_x, center_geo_y)
        else:
            c_lon, c_lat = center_geo_x, center_geo_y

        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [gps_corners]
            },
            "properties": {
                "id": idx,
                "class_name": item["class_name"],
                "confidence": round(item["conf"], 3),
                "tile_id": item["tile_id"],
                "center_lon": round(c_lon, 7),
                "center_lat": round(c_lat, 7)
            }
        }
        features.append(feat)

    geojson_output = {
        "type": "FeatureCollection",
        "features": features
    }

    os.makedirs(os.path.dirname(output_geojson), exist_ok=True)
    with open(output_geojson, "w", encoding="utf-8") as f:
        json.dump(geojson_output, f, ensure_ascii=False, indent=2)

    # 6. Tạo ảnh trực quan hoá Bounding Boxes
    if output_visualized and final_boxes:
        scale_factor = 2400.0 / max(width, height)
        vw = int(width * scale_factor)
        vh = int(height * scale_factor)

        pil_img = Image.fromarray(rgb_img).resize((vw, vh), Image.Resampling.BILINEAR)
        draw = ImageDraw.Draw(pil_img)

        color_map = {
            "person": "#FF00FF",   # Tím hồng
            "vehicle": "#00FF00",  # Xanh lá
            "building": "#FF0000", # Đỏ
            "machinery": "#FF9900" # Cam
        }

        for item in final_boxes:
            bx1, by1, bx2, by2 = item["box"]
            sx1 = int(bx1 * scale_factor)
            sy1 = int(by1 * scale_factor)
            sx2 = int(bx2 * scale_factor)
            sy2 = int(by2 * scale_factor)

            cname = item["class_name"]
            color = color_map.get(cname, "#00FF00")
            conf = item["conf"]

            draw.rectangle([sx1, sy1, sx2, sy2], outline=color, width=3)
            label = f"{cname} {conf:.2f}"
            draw.text((sx1 + 2, max(0, sy1 - 12)), label, fill=color)

        os.makedirs(os.path.dirname(output_visualized), exist_ok=True)
        pil_img.save(output_visualized, quality=90)

    print("\nTệp kết quả đầu ra:")
    print(f"  GeoJSON: {output_geojson} ({len(features)} Features)")
    print(f"  Raw Detections: {output_raw_json} ({len(raw_detections)} đối tượng thô)")
    if output_visualized:
        print(f"  Ảnh trực quan: {output_visualized}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Object Detection trên ảnh UAV & Xuất GeoJSON WGS84")
    parser.add_argument("--rgb", default="data/outputs/ortho_rgb_3band.tif", help="Đường dẫn file GeoTIFF RGB")
    parser.add_argument("--multispectral", default="data/orthomosaic/multispectral_ortho.tif", help="File đa phổ dự phòng")
    parser.add_argument("--output-geojson", default="data/outputs/detections.geojson", help="File GeoJSON đầu ra")
    parser.add_argument("--output-raw", default="data/outputs/detections_raw.json", help="File JSON kết quả thô")
    parser.add_argument("--output-vis", default="data/outputs/detections_visualized.jpg", help="File ảnh kết quả trực quan")
    parser.add_argument("--model", default="yolov8m.pt", help="Checkpoint mô hình YOLO (mặc định yolov8m.pt)")
    parser.add_argument("--device", default="cpu", help="Thiết bị tính toán (mặc định: cpu)")
    parser.add_argument("--tile-size", type=int, default=640, help="Kích thước ô cắt (pixel)")
    parser.add_argument("--overlap", type=float, default=0.15, help="Độ chồng lấp (spec: 0.15)")
    parser.add_argument("--conf", type=float, default=0.25, help="Ngưỡng độ tin cậy confidence (spec: 0.25)")
    parser.add_argument("--iou", type=float, default=0.50, help="Ngưỡng IoU cho NMS khử trùng lặp (spec: 0.50)")

    args = parser.parse_args()
    rgb_file = load_or_extract_rgb(args.rgb, args.multispectral)

    sliding_window_yolo_detection(
        rgb_tif_path=rgb_file,
        output_geojson=args.output_geojson,
        output_raw_json=args.output_raw,
        output_visualized=args.output_vis,
        model_name=args.model,
        device=args.device,
        tile_size=args.tile_size,
        overlap=args.overlap,
        conf_thresh=args.conf,
        nms_iou_thresh=args.iou
    )
