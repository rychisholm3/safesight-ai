"""
Fine-tune YOLO26 on a PPE dataset for construction site safety monitoring.

The training config (config/train.yaml) applies aggressive geometric and
photometric augmentation so the trained model generalises across:
  - Any camera mount angle (overhead, side, elevated, tilted)
  - Any worker distance from camera (SAHI handles the rest at inference)
  - Any lighting condition (sun, dust, rain, IR night vision)
  - Any camera hardware quality

Usage:
    # GPU (recommended — takes 2–4 hours on RTX 3080+)
    python scripts/train.py --data data/ppe_dataset/data.yaml

    # CPU only (slow — use for testing the pipeline works)
    python scripts/train.py --data data/ppe_dataset/data.yaml --device cpu --epochs 2

    # Resume from last checkpoint
    python scripts/train.py --data data/ppe_dataset/data.yaml --resume

    # Use a larger base model for better accuracy
    python scripts/train.py --data data/ppe_dataset/data.yaml --model yolo26m.pt

The best weights are saved to models/safesight-ppe/weights/best.pt
Copy that to models/safesight-ppe.pt and point --model at it when running the pipeline.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO26 for PPE detection",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--data",    required=True, type=Path,
                        help="Path to dataset data.yaml (from download_dataset.py)")
    parser.add_argument("--config",  type=Path, default=Path("config/train.yaml"),
                        help="Training config YAML")
    parser.add_argument("--model",   default=None,
                        help="Override base model (default: from config/train.yaml)")
    parser.add_argument("--epochs",  type=int, default=None,
                        help="Override epoch count (default: from config/train.yaml)")
    parser.add_argument("--device",  default=None,
                        help="Override device: 0 for GPU, cpu for CPU")
    parser.add_argument("--resume",  action="store_true",
                        help="Resume from last checkpoint")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
        import yaml
    except ImportError:
        print("ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    if not args.data.exists():
        print(f"Dataset not found: {args.data}")
        print("Run scripts/download_dataset.py first.")
        sys.exit(1)

    # Load config and apply any CLI overrides
    cfg = yaml.safe_load(args.config.read_text())
    if args.model:
        cfg["model"] = args.model
    if args.epochs:
        cfg["epochs"] = args.epochs
    if args.device is not None:
        cfg["device"] = args.device

    base_model = cfg.pop("model")

    print("\nSafeSight — PPE Model Training")
    print(f"  Base model : {base_model}")
    print(f"  Dataset    : {args.data}")
    print(f"  Epochs     : {cfg.get('epochs')}")
    print(f"  Image size : {cfg.get('imgsz')}")
    print(f"  Device     : {cfg.get('device', 'auto')}")
    print(f"  Output     : models/{cfg.get('name', 'safesight-ppe')}/weights/best.pt")
    print()

    model = YOLO(base_model)

    if args.resume:
        last_ckpt = Path(f"models/{cfg.get('name', 'safesight-ppe')}/weights/last.pt")
        if not last_ckpt.exists():
            print(f"No checkpoint found at {last_ckpt} — starting from scratch")
        else:
            print(f"Resuming from {last_ckpt}")
            model = YOLO(str(last_ckpt))

    results = model.train(data=str(args.data), **cfg)

    # Copy best weights to a clean path for easy use
    best = Path(f"models/{cfg.get('name', 'safesight-ppe')}/weights/best.pt")
    dest = Path("models/safesight-ppe.pt")
    if best.exists():
        shutil.copy(best, dest)
        print(f"\nTraining complete.")
        print(f"Best weights: {best}")
        print(f"Copied to   : {dest}")
        print(f"\nTo use your trained model, run:")
        print(f"  python -m src.pipeline --source YOUR_SOURCE --model {dest}")
    else:
        print(f"\nTraining complete. Best weights at: {results.save_dir}/weights/best.pt")


if __name__ == "__main__":
    main()
