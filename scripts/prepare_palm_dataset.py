#!/usr/bin/env python3
"""
Trích xuất và chuẩn bị bộ dữ liệu cắt tile phục vụ gán nhãn YOLO Tán Cọ Dầu (Palm)
Tác giả: Dương Hữu Hinh
Tuân thủ: Docs/note_hinh_tan_cay.md (tile 640x640, overlap 15%, >=95% pixel hợp lệ, chia 80/20 theo tile)
"""

import argparse
import json
import os
import random
import shutil
import sys
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import MaskFlags

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from extract_rgb import extract_and_stretch_rgb, resolve_input_raster


def read_tile_source(ortho_rgb_path: str, source_raster: str = "auto"):
    """Đảm bảo tệp RGB tồn tại và đọc dữ liệu RGB kèm mask hợp lệ."""
    resolved_src = os.path.abspath(resolve_input_raster(source_raster))
    need_extract = not os.path.exists(ortho_rgb_path)
    if not need_extract:
        try:
            with rasterio.open(ortho_rgb_path) as existing:
                if existing.tags().get("SOURCE_RASTER") != resolved_src:
                    need_extract = True
        except Exception:
            need_extract = True

    if need_extract:
        extract_and_stretch_rgb(input_path=resolved_src, output_tif=ortho_rgb_path)

    with rasterio.open(ortho_rgb_path) as src:
        r, g, b = src.read(1), src.read(2), src.read(3)
        rgb_img = np.stack([r, g, b], axis=-1)
        h, w = r.shape
        mask_flags = src.mask_flag_enums[0] if src.mask_flag_enums else []
        internal_mask = src.read_masks(1)
        if MaskFlags.per_dataset in mask_flags or internal_mask.min() == 0:
            valid_mask = internal_mask > 0
        else:
            valid_mask = (r > 0) | (g > 0) | (b > 0)

    return rgb_img, valid_mask, w, h


def prepare_dataset(
    ortho_rgb_path: str = "data/outputs/ortho_rgb_3band.tif",
    source_raster: str = "auto",
    output_dir: str = "data/yolo_palm",
    tile_size: int = 640,
    overlap: float = 0.15,
    min_valid_ratio: float = 0.95,
    target_count: int = 18,
    train_ratio: float = 0.8,
    seed: int = 42,
    clean: bool = False,
):
    """Cắt tile 640x640, lọc >= 95% pixel hợp lệ và chia train/val 80/20 theo tile."""
    random.seed(seed)
    np.random.seed(seed)

    if clean and os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    print("=== GIAI ĐOẠN 2: CHUẨN BỊ TẬP DỮ LIỆU TILE HUẤN LUYỆN TÁN CỌ DẦU ===")
    rgb_img, valid_mask, w, h = read_tile_source(ortho_rgb_path, source_raster)
    stride = int(tile_size * (1.0 - overlap))

    print(f"  Kích thước ảnh: {w} x {h} px | Tile: {tile_size}x{tile_size} | Stride: {stride} px")

    candidate_tiles = []
    for r_idx, y in enumerate(range(0, h, stride)):
        for c_idx, x in enumerate(range(0, w, stride)):
            if y + tile_size > h or x + tile_size > w:
                continue
            ratio = float(np.mean(valid_mask[y:y + tile_size, x:x + tile_size]))
            if ratio >= min_valid_ratio:
                candidate_tiles.append({
                    "tile_id": f"r{r_idx:03d}_c{c_idx:03d}",
                    "valid_ratio": ratio,
                    "x": x,
                    "y": y,
                    "width": tile_size,
                    "height": tile_size,
                })

    print(f"  Tổng số tile đạt chuẩn (>= {int(min_valid_ratio * 100)}% pixel hợp lệ): {len(candidate_tiles)} ô")

    # Ưu tiên các tile vùng trung tâm rõ nét (r002..r006, c002..c006) + các vùng trống r002_c001, r003_c001
    preferred_ids = ["r003_c001", "r002_c001"]
    for r_target in (5, 4, 3, 2, 6):
        for c_target in (5, 4, 3, 2, 6):
            preferred_ids.append(f"r{r_target:03d}_c{c_target:03d}")

    cand_by_id = {c["tile_id"]: c for c in candidate_tiles}
    selected_tiles = []
    for tid in preferred_ids:
        if tid in cand_by_id and not any(t["tile_id"] == tid for t in selected_tiles):
            selected_tiles.append(cand_by_id[tid])
        if len(selected_tiles) >= target_count:
            break

    if len(selected_tiles) < target_count:
        for cand in candidate_tiles:
            if not any(t["tile_id"] == cand["tile_id"] for t in selected_tiles):
                selected_tiles.append(cand)
            if len(selected_tiles) >= target_count:
                break

    random.shuffle(selected_tiles)
    n_train = int(len(selected_tiles) * train_ratio)
    train_tiles = selected_tiles[:n_train]
    val_tiles = selected_tiles[n_train:]

    for t in train_tiles:
        t["split"] = "train"
    for t in val_tiles:
        t["split"] = "val"

    for split in ("train", "val"):
        os.makedirs(os.path.join(output_dir, "images", split), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "labels", split), exist_ok=True)

    all_exported = train_tiles + val_tiles
    for item in all_exported:
        tid = item["tile_id"]
        split = item["split"]
        x, y = item["x"], item["y"]
        tile_rgb = rgb_img[y:y + tile_size, x:x + tile_size]

        img_path = os.path.join(output_dir, "images", split, f"{tid}.jpg")
        lbl_path = os.path.join(output_dir, "labels", split, f"{tid}.txt")
        Image.fromarray(tile_rgb).save(img_path, quality=95)
        if not os.path.exists(lbl_path):
            open(lbl_path, "w", encoding="utf-8").close()

    yaml_path = os.path.join(output_dir, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as yf:
        yf.write(
            f"# Cấu hình dataset YOLO Tán Cọ Dầu (Palm)\n"
            f"path: {os.path.abspath(output_dir)}\n"
            f"train: images/train\n"
            f"val: images/val\n\n"
            f"names:\n  0: palm\n"
        )

    classes_path = os.path.join(output_dir, "classes.txt")
    with open(classes_path, "w", encoding="utf-8") as cf:
        cf.write("palm\n")

    summary_path = os.path.join(output_dir, "tiles_summary.json")
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(all_exported, sf, ensure_ascii=False, indent=2)

    print(f"  Train ({len(train_tiles)} tiles): {[t['tile_id'] for t in train_tiles]}")
    print(f"  Val   ({len(val_tiles)} tiles): {[t['tile_id'] for t in val_tiles]}")
    print(f"  Đã lưu cấu hình: {yaml_path}, {classes_path} và metadata: {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cắt tile và chia bộ dữ liệu YOLO 80/20")
    parser.add_argument("--rgb", default="data/outputs/ortho_rgb_3band.tif")
    parser.add_argument("--multispectral", default="auto")
    parser.add_argument("--output-dir", default="data/yolo_palm")
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--clean", action="store_true", help="Xóa thư mục output cũ trước khi cắt mới")
    args = parser.parse_args()
    prepare_dataset(
        ortho_rgb_path=args.rgb,
        source_raster=args.multispectral,
        output_dir=args.output_dir,
        target_count=args.count,
        clean=args.clean,
    )
