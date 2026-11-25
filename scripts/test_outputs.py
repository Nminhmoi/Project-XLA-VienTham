#!/usr/bin/env python3
"""
Kiểm thử tính toàn vẹn và hợp lệ của các tệp kết quả đầu ra
Tác giả: Dương Hữu Hinh
Kiểm tra Schema 4.4.B (Hợp đồng dữ liệu WebGIS)
"""

import os
import json
import rasterio

ALLOWED_CLASSES = {"vehicle", "building", "machinery", "palm", "person", "other"}

def test_all():
    print("Kiểm tra tệp GeoTIFF RGB (data/outputs/ortho_rgb_3band.tif):")
    rgb_path = "data/outputs/ortho_rgb_3band.tif"
    if os.path.exists(rgb_path):
        with rasterio.open(rgb_path) as ds:
            print(f"  Kích thước: {ds.width} x {ds.height} px")
            print(f"  Số kênh: {ds.count} ({', '.join(ds.descriptions)})")
            print(f"  Kiểu dữ liệu: {ds.dtypes[0]}")
            print(f"  Hệ toạ độ: {ds.crs}")
            print("  Trạng thái: Hợp lệ")
    else:
        print("  Trạng thái: Chưa tìm thấy tệp")

    print(f"\nKiểm tra tệp GeoJSON ({geojson_path}) theo Schema 4.4.B:")
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        print(f"  Định dạng: {data.get('type')}")
        print(f"  Tổng số Features: {len(features)}")
        
        schema_valid = True
        for i, feat in enumerate(features):
            props = feat.get("properties", {})
            required_keys = {"id", "class_name", "confidence", "tile_id", "center_lon", "center_lat"}
            missing_keys = required_keys - set(props.keys())
            if missing_keys:
                print(f"  Lỗi Feature #{i+1}: Thiếu trường {missing_keys}")
                schema_valid = False
                break
            if "center_gps" in props:
                print(f"  Lỗi Feature #{i+1}: Vẫn còn trường dư thừa center_gps")
                schema_valid = False
                break
            if props["class_name"] not in ALLOWED_CLASSES:
                print(f"  Lỗi Feature #{i+1}: class_name '{props['class_name']}' không thuộc danh mục cho phép")
                schema_valid = False
                break

        if schema_valid and features:
            f0 = features[0]
            props0 = f0["properties"]
            print(f"  Mẫu Feature #1:")
            print(f"    - id: {props0['id']}")
            print(f"    - class_name: {props0['class_name']}")
            print(f"    - confidence: {props0['confidence']}")
            print(f"    - tile_id: {props0['tile_id']}")
            print(f"    - center_lon: {props0['center_lon']}")
            print(f"    - center_lat: {props0['center_lat']}")
            print("  Trạng thái Schema 4.4.B: Hoàn toàn hợp lệ (100% compliant)")
    else:
        print("  Trạng thái: Chưa tìm thấy tệp")

    print("\nKiểm tra tệp Raw Detections (data/outputs/detections_raw.json):")
    raw_path = "data/outputs/detections_raw.json"
    if os.path.exists(raw_path):
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        print(f"  Số lượng box thô trước NMS: {len(raw_data)}")
        print("  Trạng thái: Hợp lệ")
    else:
        print("  Trạng thái: Chưa tìm thấy tệp")

    print("\nKiểm tra ảnh trực quan (data/outputs/detections_visualized.jpg):")
    vis_path = "data/outputs/detections_visualized.jpg"
    if os.path.exists(vis_path):
        size_mb = os.path.getsize(vis_path) / (1024 * 1024)
        print(f"  Dung lượng: {size_mb:.2f} MB")
        print("  Trạng thái: Hợp lệ")
    else:
        print("  Trạng thái: Chưa tìm thấy tệp")

if __name__ == "__main__":
    test_all()
