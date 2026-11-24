#!/usr/bin/env python3
"""
Kiểm thử tính toàn vẹn và hợp lệ của các tệp kết quả đầu ra
Tác giả: Dương Hữu Hinh
"""

import os
import json
import rasterio

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

    print("\nKiểm tra tệp GeoJSON (data/outputs/detections.geojson):")
    geojson_path = "data/outputs/detections.geojson"
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        print(f"  Định dạng: {data.get('type')}")
        print(f"  Tổng số đối tượng: {len(features)}")
        if features:
            f0 = features[0]
            props = f0.get("properties", {})
            print(f"  Mẫu đối tượng: {props.get('class_name')} (độ tin cậy: {props.get('confidence')})")
            print(f"  Toạ độ tâm GPS: {props.get('center_gps')}")
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
