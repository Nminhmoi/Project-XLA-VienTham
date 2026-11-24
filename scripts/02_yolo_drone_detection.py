#!/usr/bin/env python3
"""
Giai đoạn 3 (Thành viên Hinh): AI Object Detection trên ảnh Drone & Geo-referencing GeoJSON
Đồ án: Xử lý ảnh viễn thám & WebGIS
Thực thi suy luận thuần CPU (tương thích đa nền tảng Windows/macOS/Linux)
"""

import os
import sys
import time
import json
import logging
import warnings
import argparse

# Tắt cảnh báo phụ và đặt chế độ im lặng cho Ultralytics
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
    output_visualized: str = None,
    model_name: str = "yolov8m.pt",
    device: str = "cpu",
    tile_size: int = 640,
    overlap: float = 0.20,
    conf_thresh: float = 0.25,
    nms_iou_thresh: float = 0.45,
    filter_classes: list = None
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

    # 2. Khởi tạo mô hình YOLO chạy trên CPU
    model = YOLO(model_name)
    class_names = model.names

    # 3. Tính toán các lát cắt (Sliding Window Tiles)
    step = int(tile_size * (1.0 - overlap))
    x_coords = list(range(0, width, step))
    y_coords = list(range(0, height, step))
    total_tiles = len(x_coords) * len(y_coords)

    raw_detections = []
    skipped_background = 0
    valid_tiles_count = 0

    # Bắt đầu tính thời gian suy luận trên CPU
    t_start = time.perf_counter()

    for y in y_coords:
        for x in x_coords:
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

            # Suy luận trực tiếp trên CPU
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

                    cls_name = class_names[cls_id]
                    if filter_classes and cls_name not in filter_classes:
                        continue

                    gx1 = float(bx1 + x)
                    gy1 = float(by1 + y)
                    gx2 = float(bx2 + x)
                    gy2 = float(by2 + y)

                    raw_detections.append([gx1, gy1, gx2, gy2, conf, cls_id])

    t_infer_total = time.perf_counter() - t_start
    ms_per_tile = (t_infer_total / max(valid_tiles_count, 1)) * 1000.0

    # Lưu kết quả phát hiện thô trước NMS theo hợp đồng dữ liệu
    raw_output_path = "data/outputs/detections_raw.json"
    os.makedirs(os.path.dirname(raw_output_path), exist_ok=True)
    raw_list = []
    for d in raw_detections:
        raw_list.append({
            "box": [round(float(v), 1) for v in d[:4]],
            "confidence": round(float(d[4]), 3),
            "class_id": int(d[5]),
            "class_name": class_names[int(d[5])]
        })
    with open(raw_output_path, "w", encoding="utf-8") as f:
        json.dump(raw_list, f, ensure_ascii=False, indent=2)

    # 4. Áp dụng Khử trùng lặp toàn diện (Class-Agnostic NMS)
    # Loại bỏ triệt để cả hộp trùng lặp cùng lớp lẫn các hộp khác lớp bị nhận nhầm đè lên nhau
    final_boxes = []
    if raw_detections:
        det_tensor = torch.tensor(raw_detections)
        all_boxes = det_tensor[:, :4]
        all_scores = det_tensor[:, 4]
        all_classes = det_tensor[:, 5]

        # NMS toàn cục (Agnostic NMS)
        keep_indices = torchvision.ops.nms(all_boxes, all_scores, nms_iou_thresh)
        for k in keep_indices:
            box = all_boxes[k].tolist()
            conf = float(all_scores[k].item())
            cls_id = int(all_classes[k].item())
            final_boxes.append({
                "box": box,
                "conf": conf,
                "cls_id": cls_id,
                "class_name": class_names[cls_id]
            })

    # Thống kê số lượng từng loại đối tượng
    stats = {}
    for item in final_boxes:
        cname = item["class_name"]
        stats[cname] = stats.get(cname, 0) + 1

    # Hiển thị thông tin tổng hợp
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
    print(f"  Số đối tượng: {len(raw_detections)} thô -> {len(final_boxes)} sau khi khử trùng lặp toàn diện (NMS)")

    print("\nThống kê đối tượng theo phân lớp:")
    for cname, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cname}: {count}")

    # 5. Ánh xạ Pixel -> GPS (WGS84 Lon/Lat) và xuất GeoJSON
    features = []
    for idx, item in enumerate(final_boxes, 1):
        x1, y1, x2, y2 = item["box"]

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

        center_pixel_x = (x1 + x2) / 2.0
        center_pixel_y = (y1 + y2) / 2.0
        center_geo_x, center_geo_y = transform * (center_pixel_x, center_pixel_y)
        if not is_wgs84:
            c_lon, c_lat = transformer.transform(center_geo_x, center_geo_y)
        else:
            c_lon, c_lat = center_geo_x, center_geo_y

        feat = {
            "type": "Feature",
            "id": idx,
            "geometry": {
                "type": "Polygon",
                "coordinates": [gps_corners]
            },
            "properties": {
                "id": idx,
                "class_name": item["class_name"],
                "confidence": round(item["conf"], 3),
                "center_gps": [round(c_lon, 7), round(c_lat, 7)],
                "bbox_pixel": [round(v, 1) for v in item["box"]]
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

    # 6. Tạo ảnh trực quan hoá Bounding Boxes (Visualized Image)
    if output_visualized and final_boxes:
        scale_factor = 2400.0 / max(width, height)
        vw = int(width * scale_factor)
        vh = int(height * scale_factor)

        pil_img = Image.fromarray(rgb_img).resize((vw, vh), Image.Resampling.BILINEAR)
        draw = ImageDraw.Draw(pil_img)

        color_map = {
            "car": "#00FF00",
            "truck": "#FF9900",
            "bus": "#FFFF00",
            "boat": "#00FFFF",
            "person": "#FF00FF",
            "airplane": "#0099FF",
            "building": "#FF0000"
        }

        for item in final_boxes:
            bx1, by1, bx2, by2 = item["box"]
            sx1 = int(bx1 * scale_factor)
            sy1 = int(by1 * scale_factor)
            sx2 = int(bx2 * scale_factor)
            sy2 = int(by2 * scale_factor)

            cname = item["class_name"]
            color = color_map.get(cname, "#33FF33")
            conf = item["conf"]

            draw.rectangle([sx1, sy1, sx2, sy2], outline=color, width=3)
            label = f"{cname} {conf:.2f}"
            draw.text((sx1 + 2, max(0, sy1 - 12)), label, fill=color)

        os.makedirs(os.path.dirname(output_visualized), exist_ok=True)
        pil_img.save(output_visualized, quality=90)

    print("\nTệp kết quả đầu ra:")
    print(f"  GeoJSON: {output_geojson} ({len(features)} đối tượng)")
    if output_visualized:
        print(f"  Ảnh trực quan: {output_visualized}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Object Detection trên ảnh UAV & Xuất GeoJSON WGS84")
    parser.add_argument("--rgb", default="data/outputs/ortho_rgb_3band.tif", help="Đường dẫn file GeoTIFF RGB")
    parser.add_argument("--multispectral", default="data/orthomosaic/multispectral_ortho.tif", help="File đa phổ dự phòng")
    parser.add_argument("--output-geojson", default="data/outputs/detections.geojson", help="File GeoJSON đầu ra")
    parser.add_argument("--output-vis", default="data/outputs/detections_visualized.jpg", help="File ảnh kết quả trực quan")
    parser.add_argument("--model", default="yolov8m.pt", help="Checkpoint mô hình YOLO (mặc định yolov8m.pt)")
    parser.add_argument("--device", default="cpu", help="Thiết bị tính toán (mặc định: cpu)")
    parser.add_argument("--tile-size", type=int, default=640, help="Kích thước ô cắt (pixel)")
    parser.add_argument("--overlap", type=float, default=0.20, help="Độ chồng lấp (0.0 - 0.5)")
    parser.add_argument("--conf", type=float, default=0.25, help="Ngưỡng độ tin cậy confidence")
    parser.add_argument("--iou", type=float, default=0.45, help="Ngưỡng IoU cho NMS khử trùng lặp")

    args = parser.parse_args()
    rgb_file = load_or_extract_rgb(args.rgb, args.multispectral)

    sliding_window_yolo_detection(
        rgb_tif_path=rgb_file,
        output_geojson=args.output_geojson,
        output_visualized=args.output_vis,
        model_name=args.model,
        device=args.device,
        tile_size=args.tile_size,
        overlap=args.overlap,
        conf_thresh=args.conf,
        nms_iou_thresh=args.iou
    )
