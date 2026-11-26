#!/usr/bin/env python3
"""
Kiểm thử tính toàn vẹn và chất lượng bộ dữ liệu gán nhãn Tán cọ dầu (data/yolo_palm)
Tác giả: Dương Hữu Hinh
"""

import argparse
import glob
import os
import sys
import yaml
from PIL import Image


def test_yolo_dataset(dataset_dir: str = "data/yolo_palm", gsd_m: float = 0.0413) -> bool:
    """Kiểm tra cấu trúc data.yaml, cặp ảnh-nhãn, tọa độ YOLO và thống kê kích thước vật lý."""
    print("=" * 65)
    print(" BỘ KIỂM THỬ TỰ ĐỘNG DỮ LIỆU TÁN CỌ DẦU (DATASET INTEGRITY TEST)")
    print("=" * 65)

    yaml_path = os.path.join(dataset_dir, "data.yaml")
    if not os.path.exists(yaml_path):
        print(f"Lỗi: Thiếu tệp {yaml_path}")
        return False

    with open(yaml_path, "r", encoding="utf-8") as yf:
        yaml_data = yaml.safe_load(yf)

    print("\n1. Kiểm tra cấu hình data.yaml:")
    print(f"  - Đường dẫn gốc: {yaml_data.get('path')}")
    print(f"  - Tập train: {yaml_data.get('train')}")
    print(f"  - Tập val: {yaml_data.get('val')}")
    print(f"  - Danh mục lớp: {yaml_data.get('names')}")
    if yaml_data.get("names") != {0: "palm"}:
        print("Lỗi: Lớp trong data.yaml phải là {0: 'palm'}")
        return False

    total_boxes = 0
    empty_label_files = 0
    box_diameters_m = []

    for split in ("train", "val"):
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        imgs = sorted(glob.glob(os.path.join(img_dir, "*.jpg")))
        lbls = sorted(glob.glob(os.path.join(lbl_dir, "*.txt")))

        print(f"\n2. Kiểm tra tập {split.upper()}:")
        print(f"  - Số lượng ảnh (.jpg): {len(imgs)} | Nhãn (.txt): {len(lbls)}")
        if len(imgs) != len(lbls):
            print(f"Lỗi: Lệch số lượng ảnh và file nhãn ở tập {split}!")
            return False

        split_boxes = 0
        for img_path in imgs:
            tid = os.path.splitext(os.path.basename(img_path))[0]
            lbl_path = os.path.join(lbl_dir, f"{tid}.txt")
            if not os.path.exists(lbl_path):
                print(f"Lỗi: Không tìm thấy file nhãn {lbl_path}")
                return False

            with Image.open(img_path) as im:
                if im.size != (640, 640):
                    print(f"Lỗi: Ảnh {img_path} có kích thước {im.size}, yêu cầu (640, 640)")
                    return False

            with open(lbl_path, "r", encoding="utf-8") as lf:
                lines = [line.strip() for line in lf if line.strip()]

            if not lines:
                empty_label_files += 1
                continue

            for line_idx, line in enumerate(lines, start=1):
                parts = line.split()
                if len(parts) != 5:
                    print(f"Lỗi cú pháp dòng {line_idx} tại {lbl_path}")
                    return False
                cls_id = int(parts[0])
                xc, yc, bw, bh = map(float, parts[1:])
                if cls_id != 0:
                    print(f"Lỗi class ID ({cls_id}) != 0 tại {lbl_path}:{line_idx}")
                    return False
                if not (0 < xc < 1 and 0 < yc < 1 and 0 < bw <= 1 and 0 < bh <= 1):
                    print(f"Lỗi tọa độ ngoài [0, 1] tại {lbl_path}:{line_idx}")
                    return False
                if (xc - bw / 2) < -1e-5 or (xc + bw / 2) > 1.00001 or (yc - bh / 2) < -1e-5 or (yc + bh / 2) > 1.00001:
                    print(f"Lỗi box tràn viền tại {lbl_path}:{line_idx}")
                    return False

                diam_px = ((bw + bh) / 2.0) * 640.0
                box_diameters_m.append(diam_px * gsd_m)
                split_boxes += 1

        print(f"  - Số lượng box hợp lệ: {split_boxes}")
        total_boxes += split_boxes

    print(f"\n3. Thống kê kích thước vật lý ({total_boxes} boxes, {empty_label_files} ảnh âm rỗng):")
    if box_diameters_m:
        min_m = min(box_diameters_m)
        max_m = max(box_diameters_m)
        mean_m = sum(box_diameters_m) / len(box_diameters_m)
        print(f"  - Đường kính nhỏ nhất: {min_m:.2f} m ({min_m / gsd_m:.0f} px)")
        print(f"  - Đường kính lớn nhất: {max_m:.2f} m ({max_m / gsd_m:.0f} px)")
        print(f"  - Đường kính trung bình: {mean_m:.2f} m ({mean_m / gsd_m:.0f} px)")
    else:
        print("  - Chưa có bounding box nào (cần gán nhãn trước khi train).")

    if total_boxes < 300:
        print(f"Cảnh báo Spec Mục 7: Hiện có {total_boxes} instance (< 300) — chưa đủ ngưỡng tối thiểu để train.")
        return False

    print(f"\nTỔNG KẾT: {total_boxes} NHÃN TÁN CỌ DẦU HỢP LỆ!")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kiểm tra toàn vẹn dataset YOLO tán cọ dầu")
    parser.add_argument("--dataset", default="data/yolo_palm")
    parser.add_argument("--gsd", type=float, default=0.0413)
    args = parser.parse_args()
    sys.exit(0 if test_yolo_dataset(args.dataset, args.gsd) else 1)
