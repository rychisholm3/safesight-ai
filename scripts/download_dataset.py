"""
Download a labeled construction PPE dataset from Roboflow Universe.

The dataset includes images from multiple camera angles, heights, and lighting
conditions — exactly what's needed for CCTV variation robustness.

Classes: person, hardhat, no-hardhat, safety-vest, no-vest, gloves, boots, mask

Usage:
    python scripts/download_dataset.py --api-key YOUR_ROBOFLOW_KEY

Get a free API key at https://roboflow.com (no credit card needed).
The dataset downloads to data/ppe_dataset/ in YOLO format, ready to train.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def download(api_key: str, workspace: str, project: str, version: int, dest: Path) -> None:
    try:
        from roboflow import Roboflow
    except ImportError:
        print("roboflow package not installed. Run: pip install roboflow")
        sys.exit(1)

    print(f"\nConnecting to Roboflow...")
    rf = Roboflow(api_key=api_key)
    proj = rf.workspace(workspace).project(project)
    dataset = proj.version(version).download("yolov8", location=str(dest))
    print(f"\nDataset downloaded to: {dest}")
    print(f"Classes: {dataset.classes}")
    print(f"\nNext step: python scripts/train.py --data {dest}/data.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download PPE dataset from Roboflow")
    parser.add_argument("--api-key",   required=True, help="Roboflow API key")
    parser.add_argument("--workspace", default="roboflow-universe-projects",
                        help="Roboflow workspace slug")
    parser.add_argument("--project",   default="construction-site-safety",
                        help="Roboflow project slug")
    parser.add_argument("--version",   type=int, default=1,
                        help="Dataset version number")
    parser.add_argument("--dest",      type=Path, default=Path("data/ppe_dataset"),
                        help="Download destination")
    args = parser.parse_args()

    print("SafeSight — PPE Dataset Download")
    print(f"  Workspace : {args.workspace}")
    print(f"  Project   : {args.project}")
    print(f"  Version   : {args.version}")
    print(f"  Dest      : {args.dest}")
    download(args.api_key, args.workspace, args.project, args.version, args.dest)


if __name__ == "__main__":
    main()
