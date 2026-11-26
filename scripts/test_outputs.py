#!/usr/bin/env python3
"""
Kiểm thử tính toàn vẹn và hợp lệ của các tệp kết quả đầu ra theo Hợp đồng Dữ liệu 4.4.B
Tác giả: Dương Hữu Hinh
"""

import json
import os
import re
import sys
import rasterio

ALLOWED_CLASSES = {"vehicle", "building", "machinery", "person", "palm", "other"}
REQUIRED_PROPS = {"id", "class_name", "confidence", "tile_id", "center_lon", "center_lat"}


def validate_geojson(geojson_path: str) -> bool:
    """Kiểm tra chặt chẽ GeoJSON theo Schema 4.4.B (EPSG:4326 lon/lat, 6 thuộc tính bắt buộc)."""
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        print(f"  Lỗi: GeoJSON type phải là FeatureCollection, nhận được {data.get('type')}")
        return False

    features = data.get("features", [])
    print(f"  Định dạng: FeatureCollection | Tổng số Features: {len(features)}")

    for i, feat in enumerate(features, start=1):
        geom = feat.get("geometry", {})
        if geom.get("type") != "Polygon":
            print(f"  Lỗi Feature #{i}: geometry.type phải là Polygon")
            return False

        coords = geom.get("coordinates", [])
        if not coords or len(coords[0]) < 5 or coords[0][0] != coords[0][-1]:
            print(f"  Lỗi Feature #{i}: Polygon chưa khép kín (>= 5 điểm)")
            return False

        for lon, lat in coords[0]:
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                print(f"  Lỗi Feature #{i}: Tọa độ ({lon}, {lat}) không phải EPSG:4326 (có thể quên reproject UTM)")
                return False

        props = feat.get("properties", {})
        missing_keys = REQUIRED_PROPS - set(props.keys())
        if missing_keys:
            print(f"  Lỗi Feature #{i}: Thiếu trường {missing_keys}")
            return False
        if "center_gps" in props:
            print(f"  Lỗi Feature #{i}: Còn trường thừa center_gps")
            return False
        if props["class_name"] not in ALLOWED_CLASSES:
            print(f"  Lỗi Feature #{i}: class_name '{props['class_name']}' không thuộc {ALLOWED_CLASSES}")
            return False
        if not (0.0 <= float(props["confidence"]) <= 1.0):
            print(f"  Lỗi Feature #{i}: confidence {props['confidence']} ngoài [0, 1]")
            return False
        if not re.match(r"^r\d+_c\d+$", str(props["tile_id"])):
            print(f"  Lỗi Feature #{i}: tile_id '{props['tile_id']}' sai định dạng rXXX_cYYY")
            return False

    if features:
        p0 = features[0]["properties"]
        print(
            f"  Mẫu Feature #1: id={p0['id']}, class={p0['class_name']}, "
            f"conf={p0['confidence']}, tile={p0['tile_id']}, "
            f"lon={p0['center_lon']}, lat={p0['center_lat']}"
        )
    print("  Trạng thái Schema 4.4.B: Hợp lệ 100%")
    return True


def test_all() -> int:
    ok = True

    print("Kiểm tra tệp GeoTIFF RGB (data/outputs/ortho_rgb_3band.tif):")
    rgb_path = "data/outputs/ortho_rgb_3band.tif"
    if os.path.exists(rgb_path):
        with rasterio.open(rgb_path) as ds:
            mask = ds.read_masks(1)
            valid_pct = float((mask > 0).mean() * 100.0)
            src_tag = ds.tags().get("SOURCE_RASTER", "không rõ")
            print(f"  Kích thước: {ds.width} x {ds.height} px | CRS: {ds.crs}")
            print(f"  Kênh: {ds.count} {ds.descriptions} | Mask hợp lệ: {valid_pct:.2f}%")
            print(f"  Nguồn trích xuất: {src_tag}")
    else:
        print("  Trạng thái: Chưa có tệp")

    geojson_path = "data/outputs/detections.geojson"
    print(f"\nKiểm tra tệp GeoJSON ({geojson_path}) theo Schema 4.4.B:")
    if os.path.exists(geojson_path):
        if not validate_geojson(geojson_path):
            ok = False
    else:
        print("  Trạng thái: Chưa có tệp (đang chờ chạy suy luận mô hình tán cọ dầu)")

    print("\nKiểm tra tệp thống kê lâm nghiệp (data/outputs/palm_stats.json):")
    stats_path = "data/outputs/palm_stats.json"
    if os.path.exists(stats_path):
        with open(stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
        print(
            f"  Tổng tán: {stats.get('total_palms')} | "
            f"Diện tích: {stats.get('valid_area_ha')} ha | "
            f"Mật độ: {stats.get('density_per_ha')} cây/ha"
        )
    else:
        print("  Trạng thái: Chưa có tệp (sẽ sinh cùng detections.geojson ở Bước 5)")

    print("\nKiểm tra ảnh trực quan (docs/figures/detections_palm.jpg):")
    vis_path = "docs/figures/detections_palm.jpg"
    if os.path.exists(vis_path):
        print(f"  Dung lượng: {os.path.getsize(vis_path) / (1024 * 1024):.2f} MB | Trạng thái: Hợp lệ")
    else:
        print("  Trạng thái: Chưa có tệp")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(test_all())
