#!/usr/bin/env python3
"""
Giai đoạn 4: Huấn luyện Fine-tune mô hình YOLO nhận diện Tán Cọ Dầu (Palm)
Tác giả: Dương Hữu Hinh
Tuân thủ: docs/note_hinh_tan_cay.md (Mục 8) & docs/cac_buoc_xu_ly_tan_cay.md
"""

import argparse
import glob
import os
import shutil
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    """Đọc tham số dòng lệnh cho quá trình huấn luyện."""
    parser = argparse.ArgumentParser(description="Fine-tune YOLO nhận diện tán cọ dầu")
    parser.add_argument("--model", default="yolo11n.pt", help="Base weights (yolo11n.pt hoặc yolo11s.pt)")
    parser.add_argument("--data", default="data/yolo_palm/data.yaml", help="Đường dẫn file data.yaml")
    parser.add_argument("--epochs", type=int, default=150, help="Số epoch tối đa (dataset nhỏ cần >= 120)")
    parser.add_argument("--patience", type=int, default=35, help="Early stopping patience (epochs)")
    parser.add_argument("--imgsz", type=int, default=640, help="Kích thước ảnh đầu vào")
    parser.add_argument("--batch", type=int, default=4, help="Batch size (4 cho ~12-16 ảnh để có nhiều bước/epoch)")
    parser.add_argument("--device", default="cpu", help="Thiết bị tính toán (cpu, 0, mps)")
    parser.add_argument("--close-mosaic", type=int, default=15, help="Tắt mosaic ở N epoch cuối")
    parser.add_argument("--workers", type=int, default=0, help="Số luồng DataLoader (0 an toàn cho macOS/CPU)")
    parser.add_argument("--project", default="runs/palm_detect", help="Thư mục lưu runs")
    parser.add_argument("--name", default="yolo11n_palm", help="Tên thí nghiệm")
    parser.add_argument("--seed", type=int, default=42, help="Seed cố định tái lập kết quả")
    parser.add_argument("--docs-dir", default="docs", help="Thư mục lưu artifacts báo cáo")
    return parser.parse_args()


def validate_training_labels(data_yaml_path: str) -> tuple[int, int]:
    """Đảm bảo dữ liệu train/val tồn tại và đã được gán nhãn trước khi train."""
    dataset_dir = Path(data_yaml_path).resolve().parent
    train_lbls = glob.glob(str(dataset_dir / "labels" / "train" / "*.txt"))
    val_lbls = glob.glob(str(dataset_dir / "labels" / "val" / "*.txt"))

    def _count_boxes(paths: list[str]) -> int:
        count = 0
        for p in paths:
            with open(p, "r", encoding="utf-8") as f:
                count += sum(1 for line in f if line.strip())
        return count

    n_train = _count_boxes(train_lbls)
    n_val = _count_boxes(val_lbls)
    if n_train == 0 or n_val == 0:
        raise ValueError(
            f"Tập nhãn chưa sẵn sàng (train={n_train} box, val={n_val} box). "
            "Hãy gán nhãn chuẩn tại data/yolo_palm/labels/ (ví dụ bằng LabelImg/Roboflow/CVAT) trước khi huấn luyện."
        )
    return n_train, n_val


def export_training_artifacts(save_dir: Path, docs_dir: Path) -> None:
    """Sao chép best.pt, results.csv, confusion_matrix.png vào thư mục docs/."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "best.pt": save_dir / "weights" / "best.pt",
        "results.csv": save_dir / "results.csv",
        "confusion_matrix.png": save_dir / "confusion_matrix.png",
    }

    print(f"\n--- XUẤT ARTIFACTS SANG {docs_dir}/ ---")
    for target_name, src_path in artifacts.items():
        dst_path = docs_dir / target_name
        if src_path.exists():
            shutil.copy2(src_path, dst_path)
            print(f"  Đã lưu: {dst_path}")
        else:
            print(f"  Cảnh báo: Không tìm thấy {src_path}")


def evaluate_checkpoint_m2(metrics) -> float:
    """In bảng chỉ số Validation và kiểm tra ngưỡng nghiệm thu M2 (mAP50 >= 0.50)."""
    if metrics is None or not hasattr(metrics, "box"):
        print("Cảnh báo: Không trích xuất được chỉ số validation.")
        return 0.0

    mp, mr, map50, map50_95 = metrics.box.mean_results()
    print("\n--- KẾT QUẢ ĐÁNH GIÁ TRÊN TẬP VALIDATION (M2 CHECKPOINT) ---")
    print(f"  Precision (P): {mp:.4f}")
    print(f"  Recall (R):    {mr:.4f}")
    print(f"  mAP50:         {map50:.4f}")
    print(f"  mAP50-95:      {map50_95:.4f}")

    if map50 >= 0.50:
        print("  => Đạt tiêu chuẩn nghiệm thu M2 (mAP50 >= 0.50) ✅")
    else:
        print("  => CHƯA ĐẠT M2 (mAP50 < 0.50) — Cần báo Minh để chốt phương án dự phòng ⚠️")
    return float(map50)


def train_palm_model(args: argparse.Namespace) -> None:
    """Thực thi fine-tune YOLO trên tập dữ liệu tán cọ dầu."""
    if not os.path.exists(args.data):
        raise FileNotFoundError(f"Không tìm thấy tệp cấu hình dữ liệu: {args.data}")
    if not os.path.exists(args.model):
        raise FileNotFoundError(f"Không tìm thấy base weights: {args.model}")

    n_train_boxes, n_val_boxes = validate_training_labels(args.data)
    project_abs = os.path.abspath(args.project)

    print("=== GIAI ĐOẠN 4: HUẤN LUYỆN FINE-TUNE MÔ HÌNH YOLO TÁN CỌ DẦU ===")
    print(f"  Base model:   {args.model}")
    print(f"  Dataset:      {args.data} (train={n_train_boxes} boxes, val={n_val_boxes} boxes)")
    print(f"  Epochs:       {args.epochs} (patience={args.patience}, close_mosaic={args.close_mosaic})")
    print(f"  Batch/Imgsz:  batch={args.batch}, imgsz={args.imgsz}")
    print(f"  Thiết bị:     {args.device}")

    model = YOLO(args.model)
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        mosaic=1.0,
        close_mosaic=args.close_mosaic,
        workers=args.workers,
        cache=True,
        amp=args.device != "cpu",
        project=project_abs,
        name=args.name,
        exist_ok=True,
        seed=args.seed,
        plots=True,
        verbose=True,
    )

    save_dir = Path(getattr(results, "save_dir", None) or model.trainer.save_dir)
    evaluate_checkpoint_m2(results)
    export_training_artifacts(save_dir, Path(args.docs_dir))
    print("\n=== GIAI ĐOẠN 4 HOÀN TẤT ===")


if __name__ == "__main__":
    train_palm_model(parse_args())
